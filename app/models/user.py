"""
User authentication models and database models.
Includes Pydantic models for API validation and SQLAlchemy ORM models for data persistence.
"""

import re
import secrets
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import uuid4
from sqlalchemy import String, Boolean, DateTime, Text, func
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict
from passlib.context import CryptContext

from app.core.database import Base
from app.core.security import hash_password

# Password hashing configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# SQLAlchemy ORM Model
class User(Base):
    """SQLAlchemy ORM model for User entity with TimescaleDB support."""
    
    __tablename__ = "users"
    
    # Primary key using UUID
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), 
        primary_key=True, 
        default=lambda: str(uuid4()),
        comment="Unique user identifier"
    )
    
    # Authentication fields
    email: Mapped[str] = mapped_column(
        String(255), 
        unique=True, 
        nullable=False,
        index=True,
        comment="User email address"
    )
    phone: Mapped[str] = mapped_column(
        String(20), 
        unique=True, 
        nullable=False,
        index=True,
        comment="Indian phone number with country code"
    )
    password_hash: Mapped[str] = mapped_column(
        String(255), 
        nullable=False,
        comment="Bcrypt hashed password"
    )
    
    # Profile information
    full_name: Mapped[str] = mapped_column(
        String(100), 
        nullable=False,
        comment="User full name"
    )
    
    # Account status
    is_active: Mapped[bool] = mapped_column(
        Boolean, 
        default=True, 
        nullable=False,
        comment="Whether user account is active"
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="Whether user has verified email/phone"
    )
    
    # Verification fields
    verification_code: Mapped[Optional[str]] = mapped_column(
        String(6), 
        nullable=True,
        comment="6-digit verification code"
    )
    verification_code_expires: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="Verification code expiration time"
    )
    
    # 2FA fields
    totp_secret: Mapped[Optional[str]] = mapped_column(
        String(32), 
        nullable=True,
        comment="TOTP secret for 2FA"
    )
    is_2fa_enabled: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="Whether 2FA is enabled"
    )
    backup_codes: Mapped[Optional[List[str]]] = mapped_column(
        ARRAY(String), 
        nullable=True, 
        default=list,
        comment="2FA backup codes"
    )
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        comment="Account creation timestamp"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        onupdate=func.now(), 
        nullable=True,
        comment="Last update timestamp"
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="Last login timestamp"
    )
    
    def set_password(self, password: str) -> None:
        """Hash and set user password."""
        self.password_hash = pwd_context.hash(password)

    def verify_password(self, password: str) -> bool:
        """Verify a password against the hashed password."""
        return pwd_context.verify(password, self.password_hash)

    def generate_verification_code(self) -> str:
        """Generate a 6-digit verification code."""
        code = str(secrets.randbelow(1000000)).zfill(6)
        self.verification_code = code
        self.verification_code_expires = datetime.now() + timedelta(minutes=15)
        return code

    def verify_code(self, code: str) -> bool:
        """Verify the provided code against stored code."""
        if not self.verification_code or not code:
            return False
        
        # Check if code has expired
        if self.verification_code_expires and datetime.now() > self.verification_code_expires:
            return False
        
        return self.verification_code == code

    def mark_as_verified(self) -> None:
        """Mark user as verified and clear verification code."""
        self.is_verified = True
        self.verification_code = None
        self.verification_code_expires = None
        self.updated_at = datetime.now()

    def update_last_login(self) -> None:
        """Update last login timestamp."""
        self.last_login = datetime.now()
        self.updated_at = datetime.now()

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
        if self.backup_codes and code.upper() in self.backup_codes:
            self.backup_codes.remove(code.upper())
            return True
        return False

    def regenerate_backup_codes(self, new_codes: List[str]) -> None:
        """Replace all backup codes with new ones."""
        self.backup_codes = new_codes.copy()

    @property
    def backup_codes_count(self) -> int:
        """Get the number of remaining backup codes."""
        return len(self.backup_codes) if self.backup_codes else 0

    @property
    def verification_expires_at(self) -> Optional[datetime]:
        """Alias for verification_code_expires to maintain backward compatibility."""
        return self.verification_code_expires

    @verification_expires_at.setter
    def verification_expires_at(self, value: Optional[datetime]) -> None:
        """Setter for verification_expires_at alias."""
        self.verification_code_expires = value

    def to_dict(self) -> dict:
        """Convert User instance to dictionary for API responses."""
        return {
            "id": self.id or str(uuid4()),  # Generate UUID if None
            "email": self.email,
            "phone": self.phone,
            "full_name": self.full_name,
            "is_active": self.is_active if self.is_active is not None else True,
            "is_verified": self.is_verified if self.is_verified is not None else False,
            "created_at": self.created_at or datetime.now(),
            "updated_at": self.updated_at,
            "last_login": self.last_login,
            "is_2fa_enabled": self.is_2fa_enabled if self.is_2fa_enabled is not None else False,
            "backup_codes_count": self.backup_codes_count
        }

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', phone='{self.phone}')>"


# Pydantic Models for API Validation

class UserCreate(BaseModel):
    """Pydantic model for user registration data validation."""
    email: EmailStr = Field(..., description="User email address")
    phone: str = Field(..., description="Indian phone number with country code")
    password: str = Field(..., min_length=8, description="User password")
    full_name: str = Field(..., min_length=2, max_length=100, description="User full name")

    @field_validator('phone')
    @classmethod
    def validate_indian_phone(cls, v):
        """Validate Indian phone number format"""
        if not v:
            raise ValueError('Phone number is required')
        
        # Indian phone number pattern: +91 followed by 10 digits
        pattern = r'^\+91[6-9]\d{9}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid Indian phone number format. Use +91XXXXXXXXXX')
        
        return v

    @field_validator('password')
    @classmethod
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

    @field_validator('full_name')
    @classmethod
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
    model_config = ConfigDict(from_attributes=True)
    
    id: str
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


class UserLogin(BaseModel):
    """Pydantic model for user login data."""
    identifier: str = Field(..., description="Email address or phone number")
    password: str = Field(..., description="User password")

    @field_validator('identifier')
    @classmethod
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

    @field_validator('verification_code')
    @classmethod
    def validate_verification_code(cls, v):
        """Validate verification code format"""
        if not v.isdigit():
            raise ValueError('Verification code must be 6 digits')
        return v

    @field_validator('verification_type')
    @classmethod
    def validate_verification_type(cls, v):
        """Validate verification type"""
        if v not in ['email', 'sms']:
            raise ValueError('Verification type must be either "email" or "sms"')
        return v


class ResendVerification(BaseModel):
    """Pydantic model for resending verification codes."""
    identifier: str = Field(..., description="Email address or phone number")
    verification_type: str = Field(..., description="Type of verification: email or sms")

    @field_validator('verification_type')
    @classmethod
    def validate_verification_type(cls, v):
        """Validate verification type"""
        if v not in ['email', 'sms']:
            raise ValueError('Verification type must be either "email" or "sms"')
        return v


# 2FA Related Schemas

class TwoFactorSetupResponse(BaseModel):
    """Schema for 2FA setup response."""
    secret: str
    qr_code_uri: str
    backup_codes: List[str]


class TwoFactorVerifySetup(BaseModel):
    """Schema for verifying 2FA setup."""
    totp_code: str
    
    @field_validator('totp_code')
    @classmethod
    def validate_totp_code(cls, v):
        """Validate TOTP code format."""
        if not v or len(v) != 6 or not v.isdigit():
            raise ValueError('TOTP code must be 6 digits')
        return v


class TwoFactorAuthenticate(BaseModel):
    """Schema for 2FA authentication."""
    temp_token: str
    totp_code: str
    
    @field_validator('totp_code')
    @classmethod
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