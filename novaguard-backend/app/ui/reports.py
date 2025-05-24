"""
UI Report Routes - Handles analysis report pages
"""
import logging
from datetime import datetime
from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from neo4j import AsyncGraphDatabase

from app.core.db import get_db
from app.auth_service import schemas as auth_schemas
from app.project_service import crud_project as project_crud
from app.project_service import crud_full_scan
from app.webhook_service import crud_pr_analysis as pr_crud
from app.analysis_module import crud_finding as finding_crud
from app.models import AnalysisFinding, PyAnalysisSeverity, PyFindingLevel
from app.models.pr_analysis_request_model import PRAnalysisStatus
from app.models.full_project_analysis_request_model import FullProjectAnalysisStatus
from app.ckg_builder.query_api import CKGQueryAPI
from app.ui.dependencies import get_current_ui_user

logger = logging.getLogger("ui.reports")

# Templates setup
APP_DIR = Path(__file__).resolve().parent.parent
templates_directory = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_directory))

router = APIRouter(prefix="/ui/reports", tags=["Web UI - Reports"])


async def get_latest_project_graph_id(project_id: int) -> str:
    """
    Query Neo4j for the latest project_graph_id for the given project_id (novaguard_id).
    Returns the most recently created Project node's graph_id, or falls back to novaguard_project_{project_id}.
    """
    uri = "bolt://novaguard_neo4j:7687"  # Use Docker service name for Neo4j
    user = "neo4j"
    password = "yourStrongPassword"  # Updated to match docker-compose.yml
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (p:Project)
            WHERE p.novaguard_id = $project_id
            RETURN p.graph_id AS graph_id
            ORDER BY p.created_at DESC
            LIMIT 1
            """,
            {"project_id": str(project_id)}
        )
        record = await result.single()
        await driver.close()
        
        if record and record["graph_id"]:
            return record["graph_id"]
        return f"novaguard_project_{project_id}"  # fallback


@router.get("/full-scan/{request_id_param}/report", response_class=HTMLResponse, name="ui_full_scan_report_get")
async def ui_full_scan_report_page(
    request: Request,
    request_id_param: int,
    db: Session = Depends(get_db),
    current_user: Optional[auth_schemas.UserPublic] = Depends(get_current_ui_user)
):
    """Display full project scan report"""
    if not current_user:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "warning", "message": "Please login to view reports."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_login_get"), status_code=status.HTTP_302_FOUND)

    logger.info(f"User {current_user.email} requesting Full Scan Report for Request ID: {request_id_param}")

    # Get FullProjectAnalysisRequest from DB
    full_scan_request_db = crud_full_scan.get_full_scan_request_by_id(db, request_id=request_id_param)
    
    if not full_scan_request_db:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "error", "message": "Full Project Scan Request not found."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)

    # Check project ownership
    project_of_scan = project_crud.get_project_by_id(db, project_id=full_scan_request_db.project_id, user_id=current_user.id)
    if not project_of_scan:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "error", "message": "You do not have permission to view this scan report."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)

    # Get findings for this Full Scan Request
    all_findings_for_full_scan = db.query(AnalysisFinding)\
        .filter(AnalysisFinding.full_project_analysis_request_id == request_id_param)\
        .order_by(AnalysisFinding.severity, AnalysisFinding.file_path, AnalysisFinding.line_start)\
        .all()
    
    project_level_findings = [f for f in all_findings_for_full_scan if f.finding_level == PyFindingLevel.PROJECT or f.finding_level == PyFindingLevel.MODULE]
    granular_findings = [f for f in all_findings_for_full_scan if f.finding_level == PyFindingLevel.FILE]

    # Get project summary from error_message of full_scan_request_db
    project_summary_from_db = full_scan_request_db.error_message if full_scan_request_db.status == FullProjectAnalysisStatus.COMPLETED else None
    if full_scan_request_db.status == FullProjectAnalysisStatus.FAILED and full_scan_request_db.error_message:
        project_summary_from_db = f"Analysis failed: {full_scan_request_db.error_message}"

    # Project Graph Visualization
    project_graph_id = full_scan_request_db.project_graph_id
    if not project_graph_id:
        # Fallback to old logic if no project_graph_id is stored
        project_graph_id = await get_latest_project_graph_id(project_of_scan.id)
    
    ckg_api = CKGQueryAPI()
    project_graph = await ckg_api.get_project_graph_for_visualization(project_graph_id)
    
    # Highlight nodes with architectural issues (project_level_findings)
    highlight_node_ids = set()
    for finding in project_level_findings:
        if hasattr(finding, 'meta_data') and finding.meta_data and 'ckg_node_id' in finding.meta_data:
            highlight_node_ids.add(finding.meta_data['ckg_node_id'])

    return templates.TemplateResponse(
        "pages/reports/full_scan_report.html",
        {
            "request": request,
            "page_title": f"Full Scan Report: {project_of_scan.repo_name} ({full_scan_request_db.branch_name})",
            "current_user": current_user,
            "project": project_of_scan,
            "scan_request_details": full_scan_request_db,
            "project_summary": project_summary_from_db,
            "project_level_findings": project_level_findings,
            "granular_findings": granular_findings,
            "current_year": datetime.now().year,
            "project_graph": project_graph,
            "highlight_node_ids": list(highlight_node_ids),
            "project_graph_id": project_graph_id,
        }
    )


@router.get("/pr-analysis/{request_id_param}/report", response_class=HTMLResponse, name="ui_pr_report_get")
async def ui_pr_analysis_report_page(
    request: Request,
    request_id_param: int,
    db: Session = Depends(get_db),
    current_user: auth_schemas.UserPublic = Depends(get_current_ui_user)
):
    """Display PR analysis report"""
    logger.info(f"User {current_user.email} requesting PR Analysis Report for Request ID: {request_id_param}")

    # Get PR analysis request from DB
    pr_analysis_request_db = pr_crud.get_pr_analysis_request_by_id(db, request_id=request_id_param)
    
    if not pr_analysis_request_db:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "error", "message": "PR Analysis Request not found."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)

    # Check project ownership
    project_of_pr = project_crud.get_project_by_id(db, project_id=pr_analysis_request_db.project_id, user_id=current_user.id)
    if not project_of_pr:
        flash_messages = request.session.get("_flash_messages", [])
        flash_messages.append({"category": "error", "message": "You do not have permission to view this PR analysis report."})
        request.session["_flash_messages"] = flash_messages
        return RedirectResponse(url=request.url_for("ui_dashboard_get"), status_code=status.HTTP_302_FOUND)

    # Get findings for this PR analysis
    findings_for_pr = finding_crud.get_findings_by_request_id(db, pr_analysis_request_id=request_id_param)

    # Group findings by severity
    findings_by_severity = {
        "ERROR": [f for f in findings_for_pr if f.severity == PyAnalysisSeverity.ERROR],
        "WARNING": [f for f in findings_for_pr if f.severity == PyAnalysisSeverity.WARNING],
        "INFO": [f for f in findings_for_pr if f.severity == PyAnalysisSeverity.INFO],
        "NOTE": [f for f in findings_for_pr if f.severity == PyAnalysisSeverity.NOTE]
    }

    return templates.TemplateResponse(
        "pages/reports/pr_analysis_report.html",
        {
            "request": request,
            "page_title": f"PR Analysis Report: {project_of_pr.repo_name} - PR #{pr_analysis_request_db.pr_number}",
            "current_user": current_user,
            "project": project_of_pr,
            "pr_request_details": pr_analysis_request_db,
            "findings_by_severity": findings_by_severity,
            "all_findings": findings_for_pr,
            "current_year": datetime.now().year
        }
    ) 