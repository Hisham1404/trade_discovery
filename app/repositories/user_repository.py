"""
User repository for authentication and user management operations.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.core.database import get_db_session
from .base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository for User entity with authentication-specific operations.
    """
    
    def __init__(self):
        super().__init__(User)
    
    async def get_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email address.
        
        Args:
            email: User email address
            
        Returns:
            User instance if found, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(User.email == email)
            )
            return result.scalar_one_or_none()
    
    async def get_by_phone(self, phone: str) -> Optional[User]:
        """
        Get user by phone number.
        
        Args:
            phone: User phone number
            
        Returns:
            User instance if found, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(User.phone == phone)
            )
            return result.scalar_one_or_none()
    
    async def get_by_email_or_phone(self, identifier: str) -> Optional[User]:
        """
        Get user by email or phone number.
        
        Args:
            identifier: Email address or phone number
            
        Returns:
            User instance if found, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(
                    or_(User.email == identifier, User.phone == identifier)
                )
            )
            return result.scalar_one_or_none()
    
    async def get_by_identifier(self, identifier: str) -> Optional[User]:
        """
        Get user by identifier (email or phone number).
        Alias for get_by_email_or_phone for consistent API.
        
        Args:
            identifier: Email address or phone number
            
        Returns:
            User instance if found, None otherwise
        """
        return await self.get_by_email_or_phone(identifier)
    
    async def email_exists(self, email: str) -> bool:
        """
        Check if email address is already registered.
        
        Args:
            email: Email address to check
            
        Returns:
            True if email exists, False otherwise
        """
        user = await self.get_by_email(email)
        return user is not None
    
    async def phone_exists(self, phone: str) -> bool:
        """
        Check if phone number is already registered.
        
        Args:
            phone: Phone number to check
            
        Returns:
            True if phone exists, False otherwise
        """
        user = await self.get_by_phone(phone)
        return user is not None
    
    async def create_user(self, email: str, phone: str, password: str, full_name: str) -> User:
        """
        Create a new user with encrypted password.
        
        Args:
            email: User email address
            phone: User phone number
            password: Plain text password (will be hashed)
            full_name: User full name
            
        Returns:
            Created user instance
        """
        async with get_db_session() as session:
            user = User(
                email=email,
                phone=phone,
                full_name=full_name
            )
            user.set_password(password)
            
            session.add(user)
            await session.commit()
            await session.refresh(user)
            return user
    
    async def verify_password(self, identifier: str, password: str) -> Optional[User]:
        """
        Verify user credentials and return user if valid.
        
        Args:
            identifier: Email address or phone number
            password: Plain text password
            
        Returns:
            User instance if credentials are valid, None otherwise
        """
        user = await self.get_by_email_or_phone(identifier)
        
        if user and user.verify_password(password):
            return user
        
        return None
    
    async def update_last_login(self, user_id: str) -> bool:
        """
        Update user's last login timestamp.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if updated successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id, 
            last_login=datetime.now(),
            updated_at=datetime.now()
        )
        return updated_user is not None
    
    async def set_verification_code(self, user_id: str, code: str, expires_at: datetime) -> bool:
        """
        Set verification code for user.
        
        Args:
            user_id: User identifier
            code: 6-digit verification code
            expires_at: Code expiration time
            
        Returns:
            True if updated successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id,
            verification_code=code,
            verification_code_expires=expires_at,
            updated_at=datetime.now()
        )
        return updated_user is not None
    
    async def verify_user(self, user_id: str) -> bool:
        """
        Mark user as verified and clear verification code.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if verified successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id,
            is_verified=True,
            verification_code=None,
            verification_code_expires=None,
            updated_at=datetime.now()
        )
        return updated_user is not None
    
    async def enable_2fa(self, user_id: str, totp_secret: str, backup_codes: List[str]) -> bool:
        """
        Enable 2FA for user.
        
        Args:
            user_id: User identifier
            totp_secret: TOTP secret key
            backup_codes: List of backup codes
            
        Returns:
            True if enabled successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id,
            totp_secret=totp_secret,
            backup_codes=backup_codes,
            is_2fa_enabled=True,
            updated_at=datetime.now()
        )
        return updated_user is not None
    
    async def disable_2fa(self, user_id: str) -> bool:
        """
        Disable 2FA for user.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if disabled successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id,
            totp_secret=None,
            backup_codes=[],
            is_2fa_enabled=False,
            updated_at=datetime.now()
        )
        return updated_user is not None
    
    async def use_backup_code(self, user_id: str, code: str) -> bool:
        """
        Use a backup code and remove it from the user's list.
        
        Args:
            user_id: User identifier
            code: Backup code to use
            
        Returns:
            True if code was valid and used, False otherwise
        """
        async with get_db_session() as session:
            user = await self.get_with_session(session, user_id)
            
            if not user or not user.backup_codes:
                return False
            
            if code.upper() in user.backup_codes:
                user.backup_codes.remove(code.upper())
                user.updated_at = datetime.now()
                await session.commit()
                return True
            
            return False
    
    async def get_active_users(self, limit: int = 100, offset: int = 0) -> List[User]:
        """
        Get active and verified users.
        
        Args:
            limit: Maximum number of users to return
            offset: Number of users to skip
            
        Returns:
            List of active users
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(User)
                .where(and_(User.is_active == True, User.is_verified == True))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_users_by_registration_date(
        self, 
        start_date: datetime, 
        end_date: datetime,
        limit: int = 100,
        offset: int = 0
    ) -> List[User]:
        """
        Get users registered within a date range.
        
        Args:
            start_date: Start of date range
            end_date: End of date range
            limit: Maximum number of users to return
            offset: Number of users to skip
            
        Returns:
            List of users registered in the date range
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(User)
                .where(and_(
                    User.created_at >= start_date,
                    User.created_at <= end_date
                ))
                .order_by(User.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def deactivate_user(self, user_id: str) -> bool:
        """
        Deactivate a user account.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if deactivated successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id,
            is_active=False,
            updated_at=datetime.now()
        )
        return updated_user is not None
    
    async def reactivate_user(self, user_id: str) -> bool:
        """
        Reactivate a user account.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if reactivated successfully, False otherwise
        """
        updated_user = await self.update_by_id(
            user_id,
            is_active=True,
            updated_at=datetime.now()
        )
        return updated_user is not None 