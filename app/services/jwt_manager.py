"""
JWT (JSON Web Token) manager for secure token creation and validation.
Handles access tokens, refresh tokens, and session management.
"""

from jose import jwt
from jose.exceptions import JWTError, ExpiredSignatureError
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from app.core.config import settings


# JWT Configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        data: Payload data to encode in the token
        expires_delta: Custom expiration time (default: 30 minutes)
        
    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT refresh token.
    
    Args:
        data: Payload data to encode in the token
        expires_delta: Custom expiration time (default: 7 days)
        
    Returns:
        str: Encoded JWT refresh token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def create_temp_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a temporary token for 2FA verification.
    
    Args:
        data: Payload data to encode in the token
        expires_delta: Custom expiration time (default: 5 minutes)
        
    Returns:
        str: Encoded JWT temporary token
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=5)  # Short-lived for 2FA
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "temp_2fa"
    })
    
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Dict[str, Any]:
    """
    Decode a JWT token.
    
    Args:
        token: JWT token to decode
        
    Returns:
        Dict[str, Any]: Decoded token payload
        
    Raises:
        jwt.InvalidTokenError: If token is invalid or expired
    """
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        return payload
    except ExpiredSignatureError:
        raise JWTError("Token has expired")
    except JWTError:
        raise JWTError("Invalid token")


def validate_token(token: str, expected_type: Optional[str] = None) -> bool:
    """
    Validate a JWT token.
    
    Args:
        token: JWT token to validate
        expected_type: Expected token type ("access", "refresh", "temp_2fa")
        
    Returns:
        bool: True if token is valid, False otherwise
    """
    try:
        payload = decode_token(token)
        
        # Check token type if specified
        if expected_type and payload.get("type") != expected_type:
            return False
        
        # Check expiration (decode_token already handles this)
        return True
        
    except JWTError:
        return False


def get_token_payload(token: str, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get token payload if valid.
    
    Args:
        token: JWT token to validate and decode
        expected_type: Expected token type
        
    Returns:
        Optional[Dict[str, Any]]: Token payload if valid, None otherwise
    """
    try:
        if validate_token(token, expected_type):
            return decode_token(token)
        return None
    except Exception:
        return None


def refresh_access_token(refresh_token: str) -> Optional[str]:
    """
    Generate new access token from valid refresh token.
    
    Args:
        refresh_token: Valid refresh token
        
    Returns:
        Optional[str]: New access token if refresh token is valid, None otherwise
    """
    try:
        # Validate refresh token
        payload = get_token_payload(refresh_token, expected_type="refresh")
        if not payload:
            return None
        
        # Create new access token with same user data
        user_data = {
            "user_id": payload.get("user_id"),
            "email": payload.get("email"),
            "is_verified": payload.get("is_verified"),
            "is_2fa_enabled": payload.get("is_2fa_enabled")
        }
        
        return create_access_token(user_data)
        
    except Exception:
        return None


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """
    Extract token from Authorization header.
    
    Args:
        authorization_header: Authorization header value
        
    Returns:
        Optional[str]: Extracted token or None
    """
    if not authorization_header:
        return None
    
    try:
        scheme, token = authorization_header.split()
        if scheme.lower() != "bearer":
            return None
        return token
    except ValueError:
        return None


def get_token_expiry_info(token: str) -> Optional[Dict[str, Any]]:
    """
    Get token expiration information.
    
    Args:
        token: JWT token
        
    Returns:
        Optional[Dict[str, Any]]: Expiry info with remaining time
    """
    try:
        payload = decode_token(token)
        exp = payload.get("exp")
        iat = payload.get("iat")
        
        if not exp:
            return None
        
        exp_datetime = datetime.fromtimestamp(exp)
        iat_datetime = datetime.fromtimestamp(iat) if iat else None
        now = datetime.utcnow()
        
        return {
            "expires_at": exp_datetime.isoformat(),
            "issued_at": iat_datetime.isoformat() if iat_datetime else None,
            "expires_in_seconds": max(0, int((exp_datetime - now).total_seconds())),
            "is_expired": exp_datetime < now
        }
        
    except Exception:
        return None 