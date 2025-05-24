"""
UI Router Aggregation - Combines all UI routers
"""
from fastapi import APIRouter

from app.ui import pages, auth, projects, reports

# Create main UI router
ui_router = APIRouter()

# Include all UI routers
ui_router.include_router(pages.router)
ui_router.include_router(auth.router)
ui_router.include_router(projects.router)
ui_router.include_router(reports.router)

# Export for easy import
__all__ = ["ui_router"] 