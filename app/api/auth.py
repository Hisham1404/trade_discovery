"""
Authentication API endpoints for user registration, login, and verification.
Includes rate limiting, security validation, and comprehensive error handling.
"""

import random
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.models.user import (
    User, UserCreate, UserResponse, UserLogin, UserVerification, 
    ResendVerification, TwoFactorSetupResponse, TwoFactorVerifySetup,
    TwoFactorAuthenticate, RefreshTokenRequest, LoginResponse,
    TwoFactorLoginResponse
)
from app.services.notification import NotificationService
from app.services.totp import (
    generate_totp_secret, get_totp_uri, validate_totp_code, 
    generate_backup_codes
)
from app.services.jwt_manager import (
    create_access_token, create_refresh_token, create_temp_token,
    get_token_payload, refresh_access_token, extract_bearer_token,
    get_token_expiry_info
)
from app.services.session_manager import (
    create_user_session, invalidate_session, get_session
)

# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()

# Security
security = HTTPBearer()

# Notification service
notification_service = NotificationService()

# In-memory storage (replace with database in production)
users_db: Dict[str, User] = {}
users_by_phone: Dict[str, User] = {}
user_id_counter = 1





@router.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register_user(user_data: UserCreate, request: Request):
    """
    Register a new user account.
    Sends verification code via email/SMS.
    """
    global user_id_counter
    
    # Check if user already exists
    if user_data.email in users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    if user_data.phone in users_by_phone:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Phone already registered"
        )
    
    # Create new user
    user = User(
        user_id=user_id_counter,
        email=user_data.email,
        phone=user_data.phone,
        full_name=user_data.full_name,
        hashed_password=""  # Will be set by set_password
    )
    user.set_password(user_data.password)
    
    # Generate verification code
    verification_code = user.generate_verification_code()
    
    # Store user
    users_db[user_data.email] = user
    users_by_phone[user_data.phone] = user
    user_id_counter += 1
    
    # Send verification code
    try:
        if '@' in user_data.email:
            await notification_service.send_email_verification(
                user_data.email, verification_code
            )
        
        # Also send SMS verification
        await notification_service.send_sms_verification(
            user_data.phone, verification_code
        )
    except Exception as e:
        # Log error but don't fail registration
        print(f"Failed to send verification: {e}")
    
    return {
        "id": user.user_id,
        "email": user.email,
        "phone": user.phone,
        "full_name": user.full_name,
        "is_active": True,
        "is_verified": False,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "is_2fa_enabled": user.is_2fa_enabled,
        "backup_codes_count": len(user.backup_codes) if user.backup_codes else 0,
        "verification_required": True
    }


@router.post("/verify", response_model=dict)
@limiter.limit("10/minute")
async def verify_user(verification_data: dict, request: Request):
    """
    Verify user account with verification code.
    """
    # Accept both old schema {identifier, verification_code, verification_type}
    # and new schema {verification_code}
    verification_code = verification_data.get("verification_code")
    identifier = verification_data.get("identifier")

    user: User | None = None
    if identifier:
        user = get_user_by_identifier(identifier)

    if not user:
        # fallback search by code
        for u in users_db.values():
            if u.verification_code == verification_code:
                user = u
                break
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code"
        )
    
    if not user.verify_code(verification_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification code"
        )
    
    # Mark user as verified
    user.mark_as_verified()
    
    return {"message": "User verified successfully"}


@router.post("/resend-verification", response_model=dict)
@limiter.limit("3/minute")
async def resend_verification(resend_data: ResendVerification, request: Request):
    """
    Resend verification code to user.
    """
    # Find user by email or phone
    user = None
    if '@' in resend_data.identifier:
        user = users_db.get(resend_data.identifier)
    else:
        # Normalize phone number
        phone = resend_data.identifier
        if not phone.startswith('+'):
            phone = f'+91{phone}'
        user = users_by_phone.get(phone)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already verified"
        )
    
    # Generate new verification code
    verification_code = user.generate_verification_code()
    
    # Send verification code
    try:
        if '@' in resend_data.identifier:
            await notification_service.send_email_verification(
                user.email, verification_code
            )
        else:
            await notification_service.send_sms_verification(
                user.phone, verification_code
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send verification code"
        )
    
    return {"message": "Verification code sent successfully"}


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login_user(login_data: UserLogin, request: Request):
    """
    Login user with email/phone and password.
    Returns tokens or 2FA challenge.
    """
    # Find user by email or phone
    user = None
    if '@' in login_data.identifier:
        user = users_db.get(login_data.identifier)
    else:
        # Normalize phone number
        phone = login_data.identifier
        if not phone.startswith('+'):
            phone = f'+91{phone}'
        user = users_by_phone.get(phone)
    
    if not user or not user.verify_password(login_data.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your account first"
        )
    
    # Check if 2FA is enabled
    if user.is_2fa_enabled:
        # Create temporary token for 2FA verification
        temp_token_data = {
            "user_id": user.user_id,
            "email": user.email,
            "stage": "2fa_required"
        }
        temp_token = create_temp_token(temp_token_data)
        
        return LoginResponse(
            access_token="",
            token_type="bearer",
            expires_in=0,
            requires_2fa=True,
            temp_token=temp_token
        )
    
    # No 2FA required, complete login
    user_data = {
        "user_id": user.user_id,
        "email": user.email,
        "is_verified": user.is_verified,
        "is_2fa_enabled": user.is_2fa_enabled
    }
    
    access_token = create_access_token(user_data)
    refresh_token = create_refresh_token(user_data)
    
    # Create session
    session_data = {
        "user_id": user.user_id,
        "email": user.email,
        "login_time": datetime.utcnow().isoformat(),
        "ip_address": get_remote_address(request),
        "user_agent": request.headers.get("user-agent", "Unknown")
    }
    session_id = create_user_session(user.user_id, session_data)
    
    # Update last login
    user.last_login = datetime.utcnow()
    
    token_info = get_token_expiry_info(access_token)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        session_id=session_id,
        token_type="bearer",
        expires_in=token_info["expires_in_seconds"] if token_info else 1800,
        requires_2fa=False,
        user=UserResponse(**user.to_dict())
    )


# 2FA Endpoints

@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Setup 2FA for authenticated user.
    Returns TOTP secret and QR code URI.
    """
    token = credentials.credentials
    payload = get_token_payload(token, expected_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Find user
    user = None
    for u in users_db.values():
        if u.user_id == payload["user_id"]:
            user = u
            break
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Generate TOTP secret and backup codes
    totp_secret = generate_totp_secret()
    qr_uri = get_totp_uri(totp_secret, user.email)
    backup_codes = generate_backup_codes()
    
    # Store temporarily (will be confirmed in verify-setup)
    user.totp_secret = totp_secret
    user.backup_codes = backup_codes
    
    return TwoFactorSetupResponse(
        secret=totp_secret,
        qr_code_uri=qr_uri,
        backup_codes=backup_codes
    )


@router.post("/2fa/verify-setup", response_model=dict)
async def verify_2fa_setup(
    setup_data: TwoFactorVerifySetup,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Verify and enable 2FA setup.
    """
    token = credentials.credentials
    payload = get_token_payload(token, expected_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Find user
    user = None
    for u in users_db.values():
        if u.user_id == payload["user_id"]:
            user = u
            break
    
    if not user or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA setup not initiated"
        )
    
    # Verify TOTP code
    if not validate_totp_code(user.totp_secret, setup_data.totp_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP code"
        )
    
    # Enable 2FA
    user.is_2fa_enabled = True
    
    return {"message": "2FA enabled successfully"}


@router.post("/2fa/authenticate", response_model=TwoFactorLoginResponse)
@limiter.limit("10/minute")
async def authenticate_2fa(auth_data: TwoFactorAuthenticate, request: Request):
    """
    Complete 2FA authentication with TOTP code.
    """
    # Verify temp token
    payload = get_token_payload(auth_data.temp_token, expected_type="temp_2fa")
    
    if not payload or payload.get("stage") != "2fa_required":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired temp token"
        )
    
    # Find user
    user = None
    for u in users_db.values():
        if u.user_id == payload["user_id"]:
            user = u
            break
    
    if not user or not user.is_2fa_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA not enabled for this user"
        )
    
    # Verify TOTP code or backup code
    code_valid = False
    if validate_totp_code(user.totp_secret, auth_data.totp_code):
        code_valid = True
    elif user.use_backup_code(auth_data.totp_code):
        code_valid = True
    
    if not code_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid TOTP or backup code"
        )
    
    # Create final tokens
    user_data = {
        "user_id": user.user_id,
        "email": user.email,
        "is_verified": user.is_verified,
        "is_2fa_enabled": user.is_2fa_enabled
    }
    
    access_token = create_access_token(user_data)
    refresh_token = create_refresh_token(user_data)
    
    # Create session
    session_data = {
        "user_id": user.user_id,
        "email": user.email,
        "login_time": datetime.utcnow().isoformat(),
        "ip_address": get_remote_address(request),
        "user_agent": request.headers.get("user-agent", "Unknown"),
        "2fa_verified": True
    }
    session_id = create_user_session(user.user_id, session_data)
    
    # Update last login
    user.last_login = datetime.utcnow()
    
    token_info = get_token_expiry_info(access_token)
    
    return TwoFactorLoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        session_id=session_id,
        token_type="bearer",
        expires_in=token_info["expires_in_seconds"] if token_info else 1800,
        user=UserResponse(**user.to_dict())
    )


@router.post("/refresh", response_model=dict)
async def refresh_token(refresh_data: RefreshTokenRequest):
    """
    Refresh access token using refresh token.
    """
    new_access_token = refresh_access_token(refresh_data.refresh_token)
    
    if not new_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token"
        )
    
    token_info = get_token_expiry_info(new_access_token)
    
    return {
        "access_token": new_access_token,
        "token_type": "bearer",
        "expires_in": token_info["expires_in_seconds"] if token_info else 1800
    }


@router.post("/logout", response_model=dict)
async def logout_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Logout user and invalidate session.
    """
    token = credentials.credentials
    payload = get_token_payload(token, expected_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Find and invalidate all user sessions
    user_id = payload["user_id"]
    from app.services.session_manager import invalidate_all_user_sessions
    invalidated_count = invalidate_all_user_sessions(user_id)
    
    return {
        "message": "Logged out successfully",
        "sessions_invalidated": invalidated_count
    }


@router.get("/me", response_model=UserResponse)
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get current authenticated user information.
    """
    token = credentials.credentials
    payload = get_token_payload(token, expected_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Find user
    user = None
    for u in users_db.values():
        if u.user_id == payload["user_id"]:
            user = u
            break
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(**user.to_dict())


@router.post("/2fa/disable", response_model=dict)
async def disable_2fa(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Disable 2FA for authenticated user.
    """
    token = credentials.credentials
    payload = get_token_payload(token, expected_type="access")
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
    
    # Find user
    user = None
    for u in users_db.values():
        if u.user_id == payload["user_id"]:
            user = u
            break
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Disable 2FA
    user.disable_2fa()
    
    return {"message": "2FA disabled successfully"}


### Helper functions for tests ###

# Re-export notification functions for backward-compat tests
from app.services.notification import (
    send_verification_email as send_verification_email,
    send_verification_sms as send_verification_sms,
)


def get_user_by_email(email: str) -> User | None:  # noqa: E501
    """Return user by email if exists (test helper)."""
    return users_db.get(email)


def get_user_by_phone(phone: str) -> User | None:  # noqa: E501
    """Return user by phone if exists (test helper)."""
    return users_by_phone.get(phone)


def get_user_by_identifier(identifier: str) -> User | None:  # noqa: E501
    """Return user by email or phone (test helper)."""
    if "@" in identifier:
        return get_user_by_email(identifier)
    # normalise phone
    phone = identifier if identifier.startswith("+") else f"+91{identifier}".rstrip()
    return get_user_by_phone(phone) 