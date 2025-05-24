"""
NovaGuard-AI Main Application
Refactored for better maintainability and separation of concerns
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
import json

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.graph_db import close_async_neo4j_driver, get_async_neo4j_driver

# Import API routers
from app.auth_service.api import router as auth_api_router
from app.project_service.api import router as project_api_router  
from app.webhook_service.api import router as webhook_api_router

# Import UI router
from app.ui.router import ui_router

# Import CKG Query API
from app.ckg_builder.query_api import CKGQueryAPI

# Configure logging
logger = logging.getLogger("main_app")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s [%(name)s:%(lineno)s] - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

# Directory setup
APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent

# Create FastAPI app
app = FastAPI(
    title="NovaGuard-AI",
    version="2.0.0", 
    description="Intelligent and In-depth Code Analysis Platform",
    debug=settings.DEBUG
)

# Setup session middleware
SESSION_SECRET_KEY = settings.SESSION_SECRET_KEY
if not SESSION_SECRET_KEY or SESSION_SECRET_KEY == "default_session_secret_for_dev_only":
    logger.warning("SESSION_SECRET_KEY is not securely set in .env.")
    if not SESSION_SECRET_KEY:
        SESSION_SECRET_KEY = "a_very_default_and_insecure_session_key_for_dev_only_please_change"

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="novaguard_session",
    max_age=14 * 24 * 60 * 60,
    https_only=False
)

# Setup static files
static_directory = APP_DIR / "static"
if not static_directory.is_dir():
    logger.error(f"Static files directory NOT FOUND at: {static_directory}")
else:
    logger.info(f"Static files directory configured at: {static_directory}")
    app.mount("/static", StaticFiles(directory=str(static_directory)), name="static")

# Include routers
app.include_router(auth_api_router, prefix="/api/auth", tags=["API - Authentication"])
app.include_router(project_api_router, prefix="/api/projects", tags=["API - Projects"])
app.include_router(webhook_api_router, prefix="/api/webhooks", tags=["API - Webhooks"])
app.include_router(ui_router)


@app.on_event("startup")
async def on_startup_event():
    """Application startup event handler"""
    logger.info("Application is starting up...")
    
    # Verify Neo4j connectivity
    try:
        driver = await get_async_neo4j_driver()
        if driver:
            await driver.verify_connectivity()
            logger.info("Successfully connected to Neo4j and verified connectivity.")
        else:
            logger.error("Neo4j driver could not be initialized on startup.")
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j on startup: {e}", exc_info=True)


@app.on_event("shutdown")
async def on_shutdown_event():
    """Application shutdown event handler"""
    logger.info("Application is shutting down...")
    await close_async_neo4j_driver()
    logger.info("Application shutdown complete.")


@app.get("/api/ckg/graph", response_class=JSONResponse, tags=["API - CKG Visualization"])
async def get_ckg_graph_data(
    project_graph_id: str,
    mode: str = "architectural_overview", 
    detail_level: int = 1,
    changed_node_ids: Optional[str] = None,  # comma-separated string
    central_node_id: Optional[str] = None,
    context_node_ids: Optional[str] = None,  # comma-separated string
    depth: Optional[int] = None,
    filters: Optional[str] = None  # JSON string
):
    """Get CKG graph data for visualization"""
    try:
        ckg_api = CKGQueryAPI()
        
        # Parse parameters
        changed_nodes = changed_node_ids.split(',') if changed_node_ids else None
        context_nodes = context_node_ids.split(',') if context_node_ids else None
        
        # Parse filters if provided
        filter_dict = {}
        if filters:
            try:
                filter_dict = json.loads(filters)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON in filters parameter: {filters}")
        
        # Get graph data based on mode
        if mode == "architectural_overview":
            graph_data = await ckg_api.get_project_graph_for_visualization(
                project_graph_id=project_graph_id,
                detail_level=detail_level
            )
        elif mode == "change_impact" and changed_nodes:
            graph_data = await ckg_api.get_change_impact_graph(
                project_graph_id=project_graph_id,
                changed_node_ids=changed_nodes,
                detail_level=detail_level
            )
        elif mode == "focused_view" and central_node_id:
            graph_data = await ckg_api.get_focused_subgraph(
                project_graph_id=project_graph_id,
                central_node_id=central_node_id,
                context_node_ids=context_nodes,
                depth=depth or 2
            )
        else:
            # Default to architectural overview
            graph_data = await ckg_api.get_project_graph_for_visualization(
                project_graph_id=project_graph_id,
                detail_level=detail_level
            )
        
        return JSONResponse(content=graph_data)
        
    except Exception as e:
        logger.error(f"Error fetching CKG graph data: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to fetch graph data",
                "message": str(e)
            }
        )


@app.get("/health", tags=["Health Check"])
async def health_check():
    """Application health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    } 