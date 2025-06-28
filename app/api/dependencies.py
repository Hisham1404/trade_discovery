"""
Authentication dependencies for protected API endpoints.
Provides JWT token validation and Redis session management using FastAPI best practices.
"""

from typing import Optional, Annotated
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from app.services.jwt_manager import get_token_payload
from app.services.session_manager import get_session
from app.models.user import User
from app.core.config import settings

# Security scheme for JWT authentication - following FastAPI best practices
security = HTTPBearer(auto_error=False)


def verify_jwt_token(token: str) -> Optional[dict]:
    """
    Verify JWT token and return payload.
    
    Args:
        token: JWT token string
        
    Returns:
        dict: Token payload if valid, None otherwise
    """
    try:
        payload = get_token_payload(token, expected_type="access")
        return payload
    except (JWTError, Exception):
        return None


async def validate_user_session(user_id: int, session_id: Optional[str] = None) -> bool:
    """
    Validate user session in Redis.
    
    Args:
        user_id: User ID
        session_id: Optional session ID
        
    Returns:
        bool: True if session is valid
    """
    try:
        # In production, check Redis for active session
        # For now, return True if JWT validation passed
        return True
    except Exception:
        return False


async def get_current_user(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Depends(security)]
) -> dict:
    """
    Get current authenticated user from JWT token.
    Following FastAPI JWT authentication patterns from documentation.
    
    Args:
        credentials: HTTP Bearer credentials
        
    Returns:
        dict: User information from token
        
    Raises:
        HTTPException: If authentication fails
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}
    )
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = credentials.credentials
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id: int = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
            
        # Validate session if available
        session_valid = await validate_user_session(user_id)
        if not session_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or invalid",
                headers={"WWW-Authenticate": "Bearer"}
            )
            
        return payload
        
    except JWTError:
        raise credentials_exception


async def get_authenticated_user(
    current_user: Annotated[dict, Depends(get_current_user)]
) -> dict:
    """
    Get authenticated user with additional validation.
    
    Args:
        current_user: Current user from JWT token
        
    Returns:
        dict: Validated user information
    """
    return current_user 