"""
UI Project Routes - Handles project management pages
"""
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path
import httpx

from fastapi import APIRouter, Request, Depends, Form, Query, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.config import settings
from app.core.security import decrypt_data
from app.auth_service import schemas as auth_schemas
from app.project_service import crud_project as project_crud
from app.project_service import schemas as project_schemas
from app.project_service.api import get_github_repos_for_user_logic
from app.project_service import crud_full_scan
from app.models import User, FullProjectAnalysisRequest, AnalysisFinding, PyAnalysisSeverity
from app.models.project_model import LLMProviderEnum, OutputLanguageEnum
from app.models.full_project_analysis_request_model import FullProjectAnalysisStatus
from app.common.message_queue.kafka_producer import send_pr_analysis_task
from app.ui.dependencies import get_current_ui_user, require_ui_user

logger = logging.getLogger("ui.projects")

# Templates setup
APP_DIR = Path(__file__).resolve().parent.parent
templates_directory = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_directory))

router = APIRouter(prefix="/ui/projects", tags=["Web UI - Projects"])


@router.get("/add", response_class=HTMLResponse, name="ui_add_project_get")
async def add_project_page_ui_get(
    request: Request,
    gh_repo_id: Optional[str] = Query(None),
    gh_repo_name: Optional[str] = Query(None),
    gh_main_branch: Optional[str] = Query(None),
    gh_language: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Serve the add project page"""
    logger.debug(
        f"HANDLER add_project_page_ui_get - Received query: "
        f"gh_repo_id='{gh_repo_id}', gh_repo_name='{gh_repo_name}', gh_main_branch='{gh_main_branch}'"
    )
    
    if not current_user:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "warning", "message": "Please login to add a project."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_login_get"), status_code=status.HTTP_302_FOUND)

    error_message_github: Optional[str] = None
    github_connected = False
    db_user_full = db.query(User).filter(User.id == current_user.id).first()
    
    if db_user_full and db_user_full.github_access_token_encrypted:
        github_connected = True
    else:
        error_message_github = "GitHub account not connected. Webhooks might not be created automatically. Please connect your GitHub account via the Dashboard."
    
    prefill_data = {
        "repo_id": gh_repo_id,
        "repo_name": gh_repo_name,
        "main_branch": gh_main_branch if gh_main_branch else "main",
        "language": gh_language
    }
    
    default_settings_for_template = {
        "DEFAULT_LLM_PROVIDER": settings.DEFAULT_LLM_PROVIDER,
        "OLLAMA_DEFAULT_MODEL": settings.OLLAMA_DEFAULT_MODEL,
        "OPENAI_DEFAULT_MODEL": settings.OPENAI_DEFAULT_MODEL,
        "GEMINI_DEFAULT_MODEL": settings.GEMINI_DEFAULT_MODEL,
        "LLM_DEFAULT_TEMPERATURE": getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.1),
        "DEFAULT_OUTPUT_LANGUAGE": getattr(settings, 'DEFAULT_OUTPUT_LANGUAGE', 'en')
    }
    
    return templates.TemplateResponse("pages/projects/add_project.html", {
        "request": request,
        "page_title": "Add New Project",
        "current_user": current_user,
        "github_connected": github_connected,
        "error_github": error_message_github,
        "prefill_data": prefill_data,
        "default_settings": default_settings_for_template,
        "current_year": datetime.now().year
    })


@router.post("/add", response_class=RedirectResponse, name="ui_add_project_post")
async def add_project_page_ui_post(
    request: Request,
    # Project Identification
    github_repo_id: str = Form(...),
    repo_name: str = Form(...),
    main_branch: str = Form(...),
    language: Optional[str] = Form(None),
    custom_project_notes: Optional[str] = Form(None),
    # LLM & Analysis Language Configuration
    llm_provider: Optional[LLMProviderEnum] = Form(LLMProviderEnum.OLLAMA),
    llm_model_name: Optional[str] = Form(None),
    llm_temperature: Optional[float] = Form(0.1),
    llm_api_key_override: Optional[str] = Form(None),
    output_language: Optional[OutputLanguageEnum] = Form(OutputLanguageEnum.ENGLISH),
    # Dependencies
    db: Session = Depends(get_db),
    current_user: auth_schemas.UserPublic = Depends(require_ui_user)
):
    """Handle project creation form submission"""
    logger.info(f"UI: User {current_user.email} submitting new project: Repo '{repo_name}', Provider '{llm_provider.value if llm_provider else 'default'}'")
    flash_messages = request.session.get("_flash_messages", [])

    project_create_schema = project_schemas.ProjectCreate(
        github_repo_id=github_repo_id,
        repo_name=repo_name,
        main_branch=main_branch,
        language=language,
        custom_project_notes=custom_project_notes,
        llm_provider=llm_provider,
        llm_model_name=llm_model_name,
        llm_temperature=llm_temperature,
        llm_api_key_override=llm_api_key_override,
        output_language=output_language
    )
    
    db_project = project_crud.create_project(
        db=db, 
        project_in=project_create_schema, 
        user_id=current_user.id
    )

    if not db_project:
        flash_messages.append({
            "category": "error", 
            "message": "Failed to add project. It might already exist or there was a database issue."
        })
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_add_project_get"), status_code=status.HTTP_302_FOUND)
    
    logger.info(f"UI: Project '{db_project.repo_name}' (ID: {db_project.id}) created in DB for user {current_user.email}.")

    # Setup webhook
    webhook_created_successfully = await _setup_github_webhook(db, db_project, current_user, flash_messages)
    
    if webhook_created_successfully:
        flash_messages.append({
            "category": "success", 
            "message": f"Project '{db_project.repo_name}' added and webhook integration is set up!"
        })
    elif not any(fm["category"] in ["error", "warning"] for fm in flash_messages):
        flash_messages.append({
            "category": "success", 
            "message": f"Project '{db_project.repo_name}' added."
        })
    
    request.session["_flash_messages"] = flash_messages
    return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)


@router.post("/{project_id_path}/trigger-full-scan", name="ui_trigger_full_scan_post")
async def ui_trigger_full_scan_for_project_post(
    request: Request,
    project_id_path: int,
    db: Session = Depends(get_db),
    current_user: auth_schemas.UserPublic = Depends(require_ui_user)
):
    """Trigger a full project scan"""
    logger.info(f"UI: User {current_user.email} triggering full project scan for project ID: {project_id_path}")
    
    db_project = project_crud.get_project_by_id(db, project_id=project_id_path, user_id=current_user.id)
    if not db_project:
        logger.warning(f"UI Trigger Full Scan: Project ID {project_id_path} not found or not owned by user {current_user.email}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found or not owned by user")

    # Check for existing scans
    existing_scans = db.query(FullProjectAnalysisRequest).filter(
        FullProjectAnalysisRequest.project_id == project_id_path,
        FullProjectAnalysisRequest.status.in_([
            FullProjectAnalysisStatus.PENDING,
            FullProjectAnalysisStatus.PROCESSING,
            FullProjectAnalysisStatus.SOURCE_FETCHED,
            FullProjectAnalysisStatus.CKG_BUILDING,
            FullProjectAnalysisStatus.ANALYZING
        ])
    ).first()
    
    if existing_scans:
        logger.warning(f"UI Trigger Full Scan: Scan already in progress for project ID {project_id_path} (Request ID: {existing_scans.id})")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A full project scan is already in progress or pending (ID: {existing_scans.id}, Status: {existing_scans.status.value})."
        )

    try:
        scan_request = crud_full_scan.create_full_scan_request(
            db=db, project_id=db_project.id, branch_name=db_project.main_branch
        )
        logger.info(f"UI Trigger Full Scan: Created FullProjectAnalysisRequest ID: {scan_request.id} for project {db_project.repo_name}")

        kafka_task_data = {
            "task_type": "full_project_scan",
            "full_project_analysis_request_id": scan_request.id,
            "project_id": db_project.id,
            "user_id": current_user.id,
            "github_repo_id": db_project.github_repo_id,
            "repo_full_name": db_project.repo_name,
            "branch_to_scan": db_project.main_branch,
        }
        
        success_kafka = await send_pr_analysis_task(kafka_task_data)
        
        if success_kafka:
            logger.info(f"UI Trigger Full Scan: Task for FullProjectAnalysisRequest ID {scan_request.id} sent to Kafka.")
            return {
                "message": f"Full scan request (ID: {scan_request.id}) for branch '{db_project.main_branch}' has been successfully queued.",
                "id": scan_request.id,
                "status": scan_request.status.value
            }
        else:
            logger.error(f"UI Trigger Full Scan: Failed to send task for FullProjectAnalysisRequest ID {scan_request.id} to Kafka.")
            crud_full_scan.update_full_scan_request_status(db, scan_request.id, FullProjectAnalysisStatus.FAILED, "Kafka send error")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to queue analysis task due to Kafka issue.")

    except Exception as e:
        logger.exception(f"UI Trigger Full Scan: Error triggering full scan for project ID {project_id_path}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An unexpected error occurred: {str(e)}")


@router.get(
    "/list-gh-repos-for-ui",
    response_model=List[project_schemas.GitHubRepoSchema],
    name="ui_list_gh_repos_for_form",
    summary="Fetch user's GitHub repos for UI forms (uses session auth)"
)
async def ui_list_github_repos_for_add_project_form(
    request: Request,
    db: Session = Depends(get_db),
    current_ui_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """List GitHub repositories for UI forms"""
    if not current_ui_user:
        logger.warning("UI list GH repos: Attempt to list GH repos for UI without active session.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not authenticated. Please login again."
        )

    db_user_full = db.query(User).filter(User.id == current_ui_user.id).first()
    if not db_user_full:
        logger.error(f"UI list GH repos: User ID {current_ui_user.id} from session not found in DB.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User account not found in database."
        )

    try:
        repos = await get_github_repos_for_user_logic(db_user_full, db)
        return repos if repos else []
    except Exception as e:
        logger.error(f"UI list GH repos: Error fetching repos for user {current_ui_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch GitHub repositories."
        )


@router.get("/{project_id_path}", response_class=HTMLResponse, name="ui_project_detail_get")
async def project_detail_page_ui_get(
    request: Request,
    project_id_path: int,
    db: Session = Depends(get_db),
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Display project detail page with analysis history"""
    if not current_user:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "warning", "message": "Please login to view project details."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_login_get"), status_code=status.HTTP_302_FOUND)

    logger.info(f"Serving project detail page for project ID: {project_id_path}, user: {current_user.email}")
    
    project_db_model = project_crud.get_project_by_id(db, project_id=project_id_path, user_id=current_user.id)
    
    if not project_db_model:
        logger.warning(f"Project ID {project_id_path} not found or not owned by user {current_user.email}.")
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "error", "message": "Project not found or you do not have access."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)

    # Convert Project model to Pydantic schema
    project_public_data = project_schemas.ProjectPublic.model_validate(project_db_model)
    
    if project_db_model.llm_api_key_override_encrypted:
        project_public_data.llm_api_key_override_is_set = True
    else:
        project_public_data.llm_api_key_override_is_set = False

    default_settings_for_template = {
        "DEFAULT_LLM_PROVIDER": settings.DEFAULT_LLM_PROVIDER,
        "OLLAMA_DEFAULT_MODEL": settings.OLLAMA_DEFAULT_MODEL,
        "OPENAI_DEFAULT_MODEL": settings.OPENAI_DEFAULT_MODEL,
        "GEMINI_DEFAULT_MODEL": settings.GEMINI_DEFAULT_MODEL,
        "LLM_DEFAULT_TEMPERATURE": getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.1),
        "DEFAULT_OUTPUT_LANGUAGE": getattr(settings, 'DEFAULT_OUTPUT_LANGUAGE', 'en')
    }

    # Get analysis history
    from app.webhook_service import crud_pr_analysis as pr_crud
    from app.project_service.schemas import AnalysisHistoryItem
    from app.models.pr_analysis_request_model import PRAnalysisStatus
    
    pr_scans_db = pr_crud.get_pr_analysis_requests_by_project_id(db, project_id=project_id_path, limit=10)
    full_scans_db = crud_full_scan.get_full_scan_requests_for_project(db, project_id=project_id_path, limit=10)
    
    analysis_history = []

    # Process PR Scans
    for pr_req_db in pr_scans_db:
        errors, warnings, others = 0, 0, 0
        if pr_req_db.status == PRAnalysisStatus.COMPLETED:
            findings_severities = db.query(AnalysisFinding.severity)\
                                    .filter(AnalysisFinding.pr_analysis_request_id == pr_req_db.id)\
                                    .all()
            for severity_tuple in findings_severities:
                severity_enum_member = severity_tuple[0]
                if severity_enum_member == PyAnalysisSeverity.ERROR: errors += 1
                elif severity_enum_member == PyAnalysisSeverity.WARNING: warnings += 1
                else: others += 1
        
        report_url_str = None
        try:
            report_url_str = str(request.url_for('ui_pr_report_get', request_id_param=pr_req_db.id))
        except Exception as e:
            logger.warning(f"Could not generate report URL for PR scan ID {pr_req_db.id}: {e}")

        analysis_history.append(
            AnalysisHistoryItem(
                id=pr_req_db.id, 
                scan_type="pr",
                identifier=f"PR #{pr_req_db.pr_number}", 
                title=pr_req_db.pr_title,
                status=pr_req_db.status.value,
                requested_at=pr_req_db.requested_at, 
                report_url=report_url_str,
                total_errors=errors, 
                total_warnings=warnings, 
                total_other_findings=others
            )
        )
        
    # Process Full Project Scans
    for full_req_db in full_scans_db:
        errors_full, warnings_full, others_full = 0, 0, 0
        if full_req_db.status == FullProjectAnalysisStatus.COMPLETED:
            findings_severities_full = db.query(AnalysisFinding.severity)\
                                        .filter(AnalysisFinding.full_project_analysis_request_id == full_req_db.id)\
                                        .all()
            for severity_tuple in findings_severities_full:
                severity_enum_member = severity_tuple[0]
                if severity_enum_member == PyAnalysisSeverity.ERROR: errors_full += 1
                elif severity_enum_member == PyAnalysisSeverity.WARNING: warnings_full += 1
                else: others_full += 1
        
        report_url_full_scan_str = None
        try:
            report_url_full_scan_str = str(request.url_for('ui_full_scan_report_get', request_id_param=full_req_db.id))
        except Exception as e:
            logger.warning(f"Could not generate report URL for full scan ID {full_req_db.id}: {e}")

        analysis_history.append(
            AnalysisHistoryItem(
                id=full_req_db.id, 
                scan_type="full",
                identifier=f"Branch: {full_req_db.branch_name}", 
                title=f"Full Scan - {full_req_db.branch_name}",
                status=full_req_db.status.value,
                requested_at=full_req_db.requested_at, 
                report_url=report_url_full_scan_str,
                total_errors=errors_full, 
                total_warnings=warnings_full, 
                total_other_findings=others_full
            )
        )

    # Sort analysis history by request time (descending)
    analysis_history.sort(key=lambda item: item.requested_at, reverse=True)
    analysis_history = analysis_history[:20]  # Limit to 20 most recent

    return templates.TemplateResponse("pages/projects/project_detail.html", {
        "request": request,
        "page_title": f"Project: {project_public_data.repo_name}",
        "current_user": current_user,
        "project": project_public_data,
        "default_settings": default_settings_for_template,
        "analysis_history_items": analysis_history,
        "current_year": datetime.now().year
    })


@router.get("/{project_id}/settings", response_class=HTMLResponse, name="ui_project_settings_get")
async def project_settings_page_ui_get(
    request: Request,
    project_id: int,
    db: Session = Depends(get_db),
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Display project settings page"""
    if not current_user:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "warning", "message": "Please login to access project settings."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_login_get"), status_code=status.HTTP_302_FOUND)

    logger.info(f"Serving project settings page for project ID: {project_id}, user: {current_user.email}")

    project_from_db = project_crud.get_project_by_id(db, project_id=project_id, user_id=current_user.id)
    
    if not project_from_db:
        logger.warning(f"Project settings: Project ID {project_id} not found or not owned by user {current_user.email}.")
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "error", "message": "Project not found or you do not have access."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)

    # Convert to Pydantic for template
    project_public = project_schemas.ProjectPublic.model_validate(project_from_db)
    
    # Check if API key override is set
    if project_from_db.llm_api_key_override_encrypted:
        project_public.llm_api_key_override_is_set = True
    else:
        project_public.llm_api_key_override_is_set = False

    default_settings_for_template = {
        "DEFAULT_LLM_PROVIDER": settings.DEFAULT_LLM_PROVIDER,
        "OLLAMA_DEFAULT_MODEL": settings.OLLAMA_DEFAULT_MODEL,
        "OPENAI_DEFAULT_MODEL": settings.OPENAI_DEFAULT_MODEL,
        "GEMINI_DEFAULT_MODEL": settings.GEMINI_DEFAULT_MODEL,
        "LLM_DEFAULT_TEMPERATURE": getattr(settings, 'LLM_DEFAULT_TEMPERATURE', 0.1),
        "DEFAULT_OUTPUT_LANGUAGE": getattr(settings, 'DEFAULT_OUTPUT_LANGUAGE', 'en')
    }

    # Get flash messages
    flash_messages = request.session.pop("_flash_messages", [])

    return templates.TemplateResponse("pages/projects/project_settings.html", {
        "request": request,
        "page_title": f"Settings: {project_public.repo_name}",
        "current_user": current_user,
        "project": project_public,
        "default_settings": default_settings_for_template,
        "flash_messages": flash_messages,
        "current_year": datetime.now().year
    })


@router.post("/{project_id}/settings", response_class=RedirectResponse, name="ui_project_settings_post")
async def project_settings_page_ui_post(
    request: Request,
    project_id: int,
    # Form data
    main_branch: str = Form(...),
    language: Optional[str] = Form(None),
    custom_project_notes: Optional[str] = Form(None),
    llm_provider: Optional[LLMProviderEnum] = Form(None),
    llm_model_name: Optional[str] = Form(None),
    llm_temperature: Optional[float] = Form(None),
    llm_api_key_override: Optional[str] = Form(None),
    output_language: Optional[OutputLanguageEnum] = Form(None),
    # Dependencies
    db: Session = Depends(get_db),
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Handle project settings update"""
    if not current_user:
        return RedirectResponse(url=request.url_for("ui_login_get"), status_code=status.HTTP_302_FOUND)

    flash_messages = request.session.get("_flash_messages", [])

    try:
        # Prepare update data
        project_update_data = project_schemas.ProjectUpdate(
            main_branch=main_branch,
            language=language,
            custom_project_notes=custom_project_notes,
            llm_provider=llm_provider,
            llm_model_name=llm_model_name,
            llm_temperature=llm_temperature,
            llm_api_key_override=llm_api_key_override,
            output_language=output_language
        )

        # Update project
        updated_project = project_crud.update_project(
            db=db,
            project_id=project_id,
            project_update=project_update_data,
            user_id=current_user.id
        )

        if updated_project:
            flash_messages.append({
                "category": "success", 
                "message": f"Project '{updated_project.repo_name}' settings updated successfully."
            })
        else:
            flash_messages.append({
                "category": "error", 
                "message": "Failed to update project settings."
            })

    except Exception as e:
        logger.error(f"Error updating project settings: {e}")
        flash_messages.append({
            "category": "error", 
            "message": "An error occurred while updating project settings."
        })

    request.session["_flash_messages"] = flash_messages
    return RedirectResponse(
        url=request.url_for("ui_project_settings_get", project_id=project_id), 
        status_code=status.HTTP_302_FOUND
    )


@router.post("/{project_id_path}/delete", name="ui_delete_project_post")
async def delete_project_ui_post(
    request: Request,
    project_id_path: int,
    db: Session = Depends(get_db),
    current_user: auth_schemas.UserPublic = Depends(require_ui_user)
):
    """Handle project deletion"""
    flash_messages = request.session.get("_flash_messages", [])

    try:
        # Delete project (this should handle webhook cleanup too)
        success = project_crud.delete_project(
            db=db, 
            project_id=project_id_path, 
            user_id=current_user.id
        )

        if success:
            flash_messages.append({
                "category": "success", 
                "message": "Project deleted successfully."
            })
        else:
            flash_messages.append({
                "category": "error", 
                "message": "Failed to delete project or project not found."
            })

    except Exception as e:
        logger.error(f"Error deleting project: {e}")
        flash_messages.append({
            "category": "error", 
            "message": "An error occurred while deleting the project."
        })

    request.session["_flash_messages"] = flash_messages
    return RedirectResponse(
        url=request.url_for("ui_dashboard_get"), 
        status_code=status.HTTP_302_FOUND
    )


# Helper function for webhook setup
async def _setup_github_webhook(
    db: Session, 
    db_project, 
    current_user: auth_schemas.UserPublic, 
    flash_messages: List
) -> bool:
    """Setup GitHub webhook for the project"""
    db_user_full = db.query(User).filter(User.id == current_user.id).first()
    webhook_created_successfully = False

    if db_user_full and db_user_full.github_access_token_encrypted:
        github_token = decrypt_data(db_user_full.github_access_token_encrypted)
        
        if github_token and settings.NOVAGUARD_PUBLIC_URL and '/' in db_project.repo_name:
            webhook_payload_url = f"{settings.NOVAGUARD_PUBLIC_URL.rstrip('/')}/api/webhooks/github"
            github_hook_data = {
                "name": "web",
                "active": True,
                "events": ["pull_request"],
                "config": {
                    "url": webhook_payload_url,
                    "content_type": "json",
                    "secret": settings.GITHUB_WEBHOOK_SECRET
                }
            }
            create_hook_url = f"https://api.github.com/repos/{db_project.repo_name}/hooks"
            headers_gh = {
                "Authorization": f"token {github_token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
            
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    hook_response = await client.post(create_hook_url, json=github_hook_data, headers=headers_gh)
                    
                    if hook_response.status_code == 201:
                        webhook_id_on_github = str(hook_response.json().get("id"))
                        db_project.github_webhook_id = webhook_id_on_github
                        db.commit()
                        db.refresh(db_project)
                        webhook_created_successfully = True
                        logger.info(f"Successfully created webhook (ID: {webhook_id_on_github}) for project '{db_project.repo_name}' and saved to DB.")
                    elif hook_response.status_code == 422 and "Hook already exists" in hook_response.text:
                        logger.warning(f"Webhook already exists for '{db_project.repo_name}'. Assuming it's correctly configured.")
                        webhook_created_successfully = True
                    else:
                        logger.error(f"Failed to create webhook (Status {hook_response.status_code}): {hook_response.text} for {db_project.repo_name}")
                        
            except httpx.HTTPStatusError as e_http_hook:
                error_detail = e_http_hook.response.json().get('message', str(e_http_hook)) if e_http_hook.response.content else str(e_http_hook)
                logger.error(f"HTTP error creating GitHub webhook for '{db_project.repo_name}': {e_http_hook.response.status_code} - {error_detail}")
                flash_messages.append({
                    "category": "warning", 
                    "message": f"Project '{db_project.repo_name}' added, but webhook creation failed: {error_detail}"
                })
            except Exception as e_hook:
                logger.exception(f"Unexpected error creating GitHub webhook for '{db_project.repo_name}'.")
                flash_messages.append({
                    "category": "warning", 
                    "message": f"Project '{db_project.repo_name}' added, but webhook creation failed with an unexpected error."
                })
                
        elif not github_token:
            flash_messages.append({
                "category": "error", 
                "message": f"Project '{db_project.repo_name}' added, but GitHub token decryption failed. Webhook not created."
            })
        elif not settings.NOVAGUARD_PUBLIC_URL:
            flash_messages.append({
                "category": "warning", 
                "message": f"Project '{db_project.repo_name}' added, but server's public URL for webhooks is not configured. Webhook setup skipped."
            })
        elif '/' not in db_project.repo_name:
            flash_messages.append({
                "category": "error", 
                "message": f"Project '{db_project.repo_name}' added, but repository name format is invalid ('owner/repo'). Webhook not created."
            })
    else:
        flash_messages.append({
            "category": "warning", 
            "message": f"Project '{db_project.repo_name}' added, but GitHub account is not connected or token is missing. Webhook setup skipped. Please connect/reconnect GitHub via Dashboard."
        })

    return webhook_created_successfully 