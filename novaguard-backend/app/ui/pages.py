"""
UI Page Routes - Handles main pages like home, about, dashboard
"""
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.auth_service import schemas as auth_schemas
from app.project_service import crud_project as project_crud
from app.project_service import schemas as project_schemas
from app.project_service.api import get_github_repos_for_user_logic
from app.models import User
from app.ui.dependencies import get_current_ui_user
from app.core.config import settings
from pathlib import Path

logger = logging.getLogger("ui.pages")

# Templates setup
APP_DIR = Path(__file__).resolve().parent.parent
templates_directory = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_directory))

router = APIRouter(tags=["Web UI - Pages"])


@router.get("/", response_class=HTMLResponse, name="ui_home")
async def serve_home_page(
    request: Request, 
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Serve the home page"""
    logger.debug(f"HOME - Path: {request.url.path}, Query Params: {request.query_params}")
    logger.debug(f"HOME - Session: {request.session}")
    logger.info(f"Serving home page UI. User: {current_user.email if current_user else 'Guest'}")
    
    return templates.TemplateResponse("pages/home.html", {
        "request": request,
        "page_title": "Welcome to NovaGuard-AI",
        "current_user": current_user,
        "current_year": datetime.now().year
    })


@router.get("/about", response_class=HTMLResponse, name="ui_about_get")
async def serve_about_page(
    request: Request, 
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Serve the about page"""
    logger.info(f"Serving About page UI. User: {current_user.email if current_user else 'Guest'}")
    
    return templates.TemplateResponse("pages/about.html", {
        "request": request,
        "page_title": "About NovaGuard AI",
        "current_user": current_user,
        "current_year": datetime.now().year
    })


@router.get("/dashboard", response_class=HTMLResponse, name="ui_dashboard_get")
async def serve_dashboard_page_ui(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Serve the user dashboard"""
    logger.debug(f"DASHBOARD - Path: {request.url.path}, Query Params: {request.query_params}")
    logger.debug(f"DASHBOARD - Session: {request.session}")

    if not current_user:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "warning", "message": "Please login to access the dashboard."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_login_get"), status_code=status.HTTP_302_FOUND)

    logger.info(f"Serving dashboard page for user: {current_user.email}")
    user_projects = project_crud.get_projects_by_user(db, user_id=current_user.id, limit=1000)

    github_connected = False
    available_github_repos: List[project_schemas.GitHubRepoSchema] = []
    
    db_user_full = db.query(User).filter(User.id == current_user.id).first()

    if db_user_full and db_user_full.github_access_token_encrypted:
        github_connected = True
        logger.info(f"User {current_user.email} is connected to GitHub. Fetching their repositories.")
        
        try:
            github_repos_list_from_api = await get_github_repos_for_user_logic(db_user_full, db)
            
            added_repo_gh_ids = {str(p.github_repo_id) for p in user_projects}
            
            if github_repos_list_from_api:
                for repo_from_gh in github_repos_list_from_api:
                    if str(repo_from_gh.id) not in added_repo_gh_ids:
                        available_github_repos.append(repo_from_gh)
                        
                logger.info(f"Found {len(available_github_repos)} available GitHub repos for user {current_user.email}")
            else:
                logger.warning(f"GitHub API returned empty repo list for user {current_user.email}")
                
        except Exception as e:
            logger.error(f"Failed to fetch GitHub repos for user {current_user.email}: {e}", exc_info=True)

    # Get flash messages
    flash_messages = request.session.pop("_flash_messages", [])

    return templates.TemplateResponse("pages/dashboard/dashboard.html", {
        "request": request,
        "page_title": "Dashboard",
        "current_user": current_user,
        "current_year": datetime.now().year,
        "projects": user_projects,  # Change 'user_projects' to 'projects' to match template
        "github_connected": github_connected,
        "available_github_repos": available_github_repos,
        "flash_messages": flash_messages
    }) 