"""
UI Dependencies - Common dependencies used across UI routes
"""
import logging
from typing import Optional

from fastapi import Request, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.auth_service import crud_user as auth_crud
from app.auth_service import schemas as auth_schemas

logger = logging.getLogger("ui.dependencies")


async def get_current_ui_user(
    request: Request, 
    db: Session = Depends(get_db)
) -> Optional[auth_schemas.UserPublic]:
    """
    Get current authenticated user from UI session.
    
    Returns:
        UserPublic if authenticated, None otherwise
    """
    user_id = request.session.get("user_id")
    if user_id:
        try:
            user_db = auth_crud.get_user_by_id(db, user_id=int(user_id))
            if user_db:
                return auth_schemas.UserPublic.model_validate(user_db)
        except ValueError:
            logger.warning(f"Invalid user_id format in session: {user_id}")
            request.session.pop("user_id", None)
            request.session.pop("user_email", None)
        except Exception as e:
            logger.exception(f"Error fetching user by ID from session: {e}")
    return None


async def require_ui_user(
    request: Request,
    db: Session = Depends(get_db)
) -> auth_schemas.UserPublic:
    """
    Require authenticated user for UI routes.
    
    Raises HTTPException if not authenticated.
    """
    from fastapi import HTTPException, status
    
    user = await get_current_ui_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user 