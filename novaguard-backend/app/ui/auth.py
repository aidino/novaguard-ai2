"""
UI Authentication Routes - Handles login, register, logout pages
"""
import logging
from typing import Optional
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.auth_service import crud_user as auth_crud
from app.auth_service import schemas as auth_schemas
from app.core.security import verify_password

logger = logging.getLogger("ui.auth")

# Templates setup
APP_DIR = Path(__file__).resolve().parent.parent
templates_directory = APP_DIR / "templates"
templates = Jinja2Templates(directory=str(templates_directory))

router = APIRouter(prefix="/ui/auth", tags=["Web UI - Authentication"])


@router.get("/login", response_class=HTMLResponse, name="ui_login_get")
async def login_page_get(
    request: Request, 
    error: Optional[str] = None, 
    success: Optional[str] = None
):
    """Serve the login page"""
    return templates.TemplateResponse("pages/auth/login.html", {
        "request": request, 
        "error": error, 
        "success": success
    })


@router.post("/login", response_class=RedirectResponse, name="ui_login_post")
async def login_page_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    """Handle login form submission"""
    user = auth_crud.get_user_by_email(db, email=email)
    
    if not user or not verify_password(password, user.password_hash):
        return RedirectResponse(
            url=request.url_for("ui_login_get") + "?error=Invalid%20email%20or%20password", 
            status_code=status.HTTP_302_FOUND
        )
    
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    
    return RedirectResponse(
        url=request.url_for("ui_dashboard_get"), 
        status_code=status.HTTP_302_FOUND
    )


@router.get("/register", response_class=HTMLResponse, name="ui_register_get")
async def register_page_get(
    request: Request, 
    error: Optional[str] = None
):
    """Serve the registration page"""
    return templates.TemplateResponse("pages/auth/register.html", {
        "request": request, 
        "error": error
    })


@router.post("/register", response_class=RedirectResponse, name="ui_register_post")
async def register_page_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    confirm_password: str = Form(...), 
    db: Session = Depends(get_db)
):
    """Handle registration form submission"""
    if password != confirm_password:
        return RedirectResponse(
            url=request.url_for("ui_register_get") + "?error=Passwords%20do%20not%20match", 
            status_code=status.HTTP_302_FOUND
        )
    
    # Check if user already exists
    if auth_crud.get_user_by_email(db, email=email):
        return RedirectResponse(
            url=request.url_for("ui_register_get") + "?error=Email%20already%20registered", 
            status_code=status.HTTP_302_FOUND
        )
    
    try:
        user_create = auth_schemas.UserCreate(email=email, password=password)
        user = auth_crud.create_user(db, user=user_create)
        
        # Auto-login after registration
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email
        
        return RedirectResponse(
            url=request.url_for("ui_dashboard_get"), 
            status_code=status.HTTP_302_FOUND
        )
        
    except Exception as e:
        logger.error(f"Registration failed: {e}")
        return RedirectResponse(
            url=request.url_for("ui_register_get") + "?error=Registration%20failed", 
            status_code=status.HTTP_302_FOUND
        )


@router.get("/logout", response_class=RedirectResponse, name="ui_logout_get")
async def logout_page_get(request: Request):
    """Handle user logout"""
    request.session.clear()
    
    return RedirectResponse(
        url=request.url_for("ui_home"), 
        status_code=status.HTTP_302_FOUND
    ) 