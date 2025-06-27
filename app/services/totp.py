"""
TOTP (Time-based One-Time Password) service for two-factor authentication.
Provides secure TOTP secret generation, QR code URIs, and code validation.
"""

import secrets
import pyotp
from typing import Optional
from urllib.parse import quote


def generate_totp_secret() -> str:
    """
    Generate a secure random TOTP secret.
    
    Returns:
        str: Base32-encoded secret (32 characters)
    """
    # Generate 20 random bytes (160 bits) for strong security
    random_bytes = secrets.token_bytes(20)
    # Convert to base32 (TOTP standard)
    secret = pyotp.random_base32()
    return secret


def get_totp_uri(secret: str, email: str, issuer: str = "Discovery Cluster") -> str:
    """
    Generate TOTP URI for QR code generation.
    
    Args:
        secret: Base32-encoded TOTP secret
        email: User's email address
        issuer: Service name for the authenticator app
        
    Returns:
        str: TOTP URI for QR code generation
    """
    # URL encode the email and issuer for safety
    encoded_email = quote(email)
    encoded_issuer = quote(issuer)
    
    # Create TOTP instance
    totp = pyotp.TOTP(secret)
    
    # Generate provisioning URI
    uri = totp.provisioning_uri(
        name=email,
        issuer_name=issuer
    )
    
    return uri


def validate_totp_code(secret: str, code: str, window: int = 1) -> bool:
    """
    Validate a TOTP code against the secret.
    
    Args:
        secret: Base32-encoded TOTP secret
        code: 6-digit TOTP code to validate
        window: Number of time windows to accept (default: 1)
                window=1 means accept current + 1 previous + 1 next
                
    Returns:
        bool: True if code is valid, False otherwise
    """
    try:
        # Ensure code is 6 digits
        if not code or len(code) != 6 or not code.isdigit():
            return False
        
        # Create TOTP instance
        totp = pyotp.TOTP(secret)
        
        # Verify code with time window tolerance
        # This allows for small clock differences between server and client
        return totp.verify(code, valid_window=window)
        
    except Exception:
        # Any error in validation should return False
        return False


def generate_backup_codes(count: int = 8) -> list[str]:
    """
    Generate backup codes for account recovery.
    
    Args:
        count: Number of backup codes to generate
        
    Returns:
        list[str]: List of backup codes (8 characters each)
    """
    backup_codes = []
    for _ in range(count):
        # Generate 8-character alphanumeric backup code
        code = secrets.token_hex(4).upper()  # 4 bytes = 8 hex chars
        backup_codes.append(code)
    
    return backup_codes


def validate_backup_code(user_backup_codes: list[str], provided_code: str) -> bool:
    """
    Validate a backup code and remove it from the list if valid.
    
    Args:
        user_backup_codes: List of user's remaining backup codes
        provided_code: Code provided by user
        
    Returns:
        bool: True if code is valid and removed, False otherwise
    """
    try:
        # Normalize the provided code
        provided_code = provided_code.upper().strip()
        
        if provided_code in user_backup_codes:
            # Remove the used backup code
            user_backup_codes.remove(provided_code)
            return True
        
        return False
        
    except Exception:
        return False 