"""
Notification service for sending verification codes via email and SMS.
Handles email and SMS delivery for user verification process.
"""

import logging
import asyncio

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for handling email and SMS notifications."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def send_email_verification(self, email: str, verification_code: str) -> bool:
        """Send verification code via email."""
        try:
            self.logger.info(f"Sending verification email to {email} with code {verification_code}")
            await asyncio.sleep(0.1)  # Simulate email sending delay
            return True
        except Exception as e:
            self.logger.error(f"Failed to send verification email to {email}: {e}")
            return False
    
    async def send_sms_verification(self, phone: str, verification_code: str) -> bool:
        """Send verification code via SMS."""
        try:
            self.logger.info(f"Sending verification SMS to {phone} with code {verification_code}")
            await asyncio.sleep(0.1)  # Simulate SMS sending delay
            return True
        except Exception as e:
            self.logger.error(f"Failed to send verification SMS to {phone}: {e}")
            return False
    
    def send_email_verification_sync(self, email: str, verification_code: str) -> bool:
        """Synchronous version for testing"""
        try:
            self.logger.info(f"Sending verification email to {email} with code {verification_code}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send verification email to {email}: {e}")
            return False
    
    def send_sms_verification_sync(self, phone: str, verification_code: str) -> bool:
        """Synchronous version for testing"""
        try:
            self.logger.info(f"Sending verification SMS to {phone} with code {verification_code}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send verification SMS to {phone}: {e}")
            return False


# Backward compatibility functions
async def send_verification_email(email: str, verification_code: str) -> bool:
    """Send verification code via email."""
    service = NotificationService()
    return await service.send_email_verification(email, verification_code)


async def send_verification_sms(phone: str, verification_code: str) -> bool:
    """Send verification code via SMS."""
    service = NotificationService()
    return await service.send_sms_verification(phone, verification_code)


def send_verification_email_sync(email: str, verification_code: str) -> bool:
    """Synchronous version for testing"""
    service = NotificationService()
    return service.send_email_verification_sync(email, verification_code)


def send_verification_sms_sync(phone: str, verification_code: str) -> bool:
    """Synchronous version for testing"""
    service = NotificationService()
    return service.send_sms_verification_sync(phone, verification_code) 