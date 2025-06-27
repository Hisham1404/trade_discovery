"""
User authentication models and database models.
Includes Pydantic models for API validation and database models for data persistence.
"""

import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, validator
from passlib.context import CryptContext

from app.core.security import hash_password

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserCreate(BaseModel):
    """Pydantic model for user registration data validation."""
    email: EmailStr = Field(..., description="User email address")
    phone: str = Field(..., description="Indian phone number with country code")
    password: str = Field(..., min_length=8, description="User password")
    full_name: str = Field(..., min_length=2, max_length=100, description="User full name")

    @validator('phone')
    def validate_indian_phone(cls, v):
        """Validate Indian phone number format"""
        if not v:
            raise ValueError('Phone number is required')
        
        # Indian phone number pattern: +91 followed by 10 digits
        pattern = r'^\+91[6-9]\d{9}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid Indian phone number format. Use +91XXXXXXXXXX')
        
        return v

    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password strength requirements"""
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long')
        
        # Check for at least one uppercase letter
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        
        # Check for at least one lowercase letter  
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        
        # Check for at least one digit
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        
        # Check for at least one special character
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        
        return v

    @validator('full_name')
    def validate_full_name(cls, v):
        """Validate full name format"""
        if not v or not v.strip():
            raise ValueError('Full name is required')
        
        # Remove extra spaces and validate
        v = re.sub(r'\s+', ' ', v.strip())
        
        # Check for valid characters (letters, numbers, spaces, some special chars)
        if not re.match(r'^[a-zA-Z0-9\s\.\-\']+$', v):
            raise ValueError('Full name can only contain letters, numbers, spaces, periods, hyphens, and apostrophes')
        
        return v


class UserResponse(BaseModel):
    """Pydantic model for user data in API responses."""
    id: int
    email: str
    phone: str
    full_name: str
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    is_2fa_enabled: bool
    backup_codes_count: int

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Pydantic model for user login data."""
    identifier: str = Field(..., description="Email address or phone number")
    password: str = Field(..., description="User password")

    @validator('identifier')
    def validate_identifier(cls, v):
        """Validate that identifier is either email or phone"""
        if not v:
            raise ValueError('Email or phone number is required')
        
        # Check if it's an email
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if re.match(email_pattern, v):
            return v
        
        # Check if it's an Indian phone number
        phone_pattern = r'^\+91[6-9]\d{9}$'
        if re.match(phone_pattern, v):
            return v
        
        raise ValueError('Identifier must be a valid email address or Indian phone number (+91XXXXXXXXXX)')


class UserVerification(BaseModel):
    """Pydantic model for user verification data."""
    identifier: str = Field(..., description="Email address or phone number")
    verification_code: str = Field(..., min_length=6, max_length=6, description="6-digit verification code")
    verification_type: str = Field(..., description="Type of verification: email or sms")

    @validator('verification_code')
    def validate_verification_code(cls, v):
        """Validate verification code format"""
        if not v.isdigit():
            raise ValueError('Verification code must be 6 digits')
        return v

    @validator('verification_type')
    def validate_verification_type(cls, v):
        """Validate verification type"""
        if v not in ['email', 'sms']:
            raise ValueError('Verification type must be either "email" or "sms"')
        return v


class ResendVerification(BaseModel):
    """Pydantic model for resending verification codes."""
    identifier: str = Field(..., description="Email address or phone number")
    verification_type: str = Field(..., description="Type of verification: email or sms")

    @validator('verification_type')
    def validate_verification_type(cls, v):
        """Validate verification type"""
        if v not in ['email', 'sms']:
            raise ValueError('Verification type must be either "email" or "sms"')
        return v


class User:
    """Database model for User entity."""
    
    _id_counter = 1  # class level counter for tests without explicit id

    def __init__(
        self,
        email: str,
        phone: str,
        full_name: str,
        password: str | None = None,
        user_id: Optional[int] = None,
        hashed_password: Optional[str] = None,
        verification_code: Optional[str] = None,
        verification_code_expires: Optional[datetime] = None,
        is_verified: bool = False,
        created_at: Optional[datetime] = None,
        totp_secret: Optional[str] = None,
        is_2fa_enabled: bool = False,
        backup_codes: Optional[List[str]] = None
    ):
        # Auto assign id if not provided (used heavily in tests)
        if user_id is None:
            user_id = User._id_counter
            User._id_counter += 1
        self.user_id = user_id

        self.email = email
        self.phone = phone
        self.full_name = full_name
        self.hashed_password = hashed_password or ""
        self.verification_code = verification_code
        self.verification_code_expires = verification_code_expires
        self.is_verified = is_verified
        self.created_at = created_at or datetime.now()
        self.updated_at: Optional[datetime] = None
        self.last_login: Optional[datetime] = None
        self.totp_secret = totp_secret
        self.is_2fa_enabled = is_2fa_enabled
        self.backup_codes = backup_codes or []

        # If a plain password is provided, hash it automatically (for legacy tests)
        if password is not None:
            self.set_password(password)

    def set_password(self, password: str) -> None:
        """Hash and set user password"""
        self.hashed_password = pwd_context.hash(password)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the hashed password."""
        return pwd_context.verify(password, self.hashed_password)

    def generate_verification_code(self) -> str:
        """Generate a 6-digit verification code"""
        code = str(secrets.randbelow(1000000)).zfill(6)
        self.verification_code = code
        self.verification_code_expires = datetime.now() + timedelta(minutes=15)
        return code

    def verify_code(self, code: str) -> bool:
        """Verify the provided code against stored code"""
        if not self.verification_code or not code:
            return False
        
        # Check if code has expired
        if self.verification_code_expires and datetime.now() > self.verification_code_expires:
            return False
        
        return self.verification_code == code

    def mark_as_verified(self) -> None:
        """Mark user as verified and clear verification code"""
        self.is_verified = True
        self.verification_code = None
        self.verification_code_expires = None
        self.updated_at = datetime.now()

    def update_last_login(self) -> None:
        """Update last login timestamp"""
        self.last_login = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> dict:
        """Convert user object to dictionary for API responses"""
        return {
            "id": self.user_id,
            "email": self.email,
            "phone": self.phone,
            "full_name": self.full_name,
            "is_active": True,
            "is_verified": self.is_verified,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_login": self.last_login,
            "is_2fa_enabled": self.is_2fa_enabled,
            "backup_codes_count": len(self.backup_codes) if self.backup_codes else 0
        }

    def __repr__(self) -> str:
        return f"<User(user_id={self.user_id}, email='{self.email}', phone='{self.phone}')>"

    def enable_2fa(self, totp_secret: str, backup_codes: List[str]) -> None:
        """Enable 2FA with TOTP secret and backup codes."""
        self.totp_secret = totp_secret
        self.backup_codes = backup_codes.copy()
        self.is_2fa_enabled = True

    def disable_2fa(self) -> None:
        """Disable 2FA and clear related data."""
        self.totp_secret = None
        self.backup_codes = []
        self.is_2fa_enabled = False

    def use_backup_code(self, code: str) -> bool:
        """Use a backup code (removes it from the list if valid)."""
        if code.upper() in self.backup_codes:
            self.backup_codes.remove(code.upper())
            return True
        return False

    def regenerate_backup_codes(self, new_codes: List[str]) -> None:
        """Replace all backup codes with new ones."""
        self.backup_codes = new_codes.copy()

    # ------- Backward-compat aliases expected by old tests ---------

    @property
    def id(self):  # noqa: D401
        return self.user_id

    @property
    def password_hash(self):
        return self.hashed_password
    
    @password_hash.setter 
    def password_hash(self, value: str):
        """Allow setting password_hash directly for backward compatibility"""
        # Store the value directly without re-hashing if it's already hashed
        if value and (value.startswith('$2b$') or len(value) == 60):
            # Already hashed password
            self.hashed_password = value
        else:
            # Plain password - hash it
            self.hashed_password = pwd_context.hash(value) if value else ""

    @property
    def verification_expires_at(self):
        return self.verification_code_expires
    
    @verification_expires_at.setter
    def verification_expires_at(self, value):
        """Allow setting verification_expires_at for backward compatibility"""
        self.verification_code_expires = value

    @property
    def is_active(self):  # legacy attribute always True
        return True


# 2FA Related Schemas

class TwoFactorSetupResponse(BaseModel):
    """Schema for 2FA setup response."""
    secret: str
    qr_code_uri: str
    backup_codes: List[str]


class TwoFactorVerifySetup(BaseModel):
    """Schema for verifying 2FA setup."""
    totp_code: str
    
    @validator('totp_code')
    def validate_totp_code(cls, v):
        """Validate TOTP code format."""
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError('TOTP code must be 6 digits')
        return v


class TwoFactorAuthenticate(BaseModel):
    """Schema for 2FA authentication."""
    temp_token: str
    totp_code: str
    
    @validator('totp_code')
    def validate_totp_code(cls, v):
        """Validate TOTP code format."""
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError('TOTP code must be 6 digits')
        return v


class RefreshTokenRequest(BaseModel):
    """Schema for refresh token request."""
    refresh_token: str


class LoginResponse(BaseModel):
    """Schema for login response."""
    access_token: str
    refresh_token: Optional[str] = None
    session_id: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    requires_2fa: bool = False
    temp_token: Optional[str] = None
    user: Optional[UserResponse] = None


class TwoFactorLoginResponse(BaseModel):
    """Schema for completed 2FA login response."""
    access_token: str
    refresh_token: str
    session_id: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse 