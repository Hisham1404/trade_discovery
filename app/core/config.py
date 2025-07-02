"""
Configuration management using Pydantic Settings.
Handles environment variables and application configuration.
"""

import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8", 
        case_sensitive=True,
        extra="ignore"  # Ignore extra environment variables
    )
    
    # Application Settings
    APP_NAME: str = Field(default="Discovery Cluster API", description="Application name")
    APP_VERSION: str = Field(default="1.0.0", description="Application version")
    DEBUG: bool = Field(default=True, description="Debug mode")
    
    # Security Settings
    JWT_SECRET_KEY: str = Field(
        default="your-secret-key-here-at-least-32-characters-long-for-development",
        description="Secret key for JWT token signing",
        min_length=32
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="JWT token expiration in minutes")
    
    @property
    def secret_key(self) -> str:
        """Alias for JWT_SECRET_KEY for backward compatibility."""
        return self.JWT_SECRET_KEY
    
    # Database Settings
    POSTGRES_DB: str = Field(default="discovery_cluster", description="PostgreSQL database name")
    POSTGRES_USER: str = Field(default="discovery_user", description="PostgreSQL username")
    POSTGRES_PASSWORD: str = Field(default="discovery_password", description="PostgreSQL password")
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    
    # Redis Settings
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_PASSWORD: Optional[str] = Field(default=None, description="Redis password")
    REDIS_DB: int = Field(default=0, description="Redis database number")
    
    # MinIO Settings (for immutable audit logging)
    MINIO_ENDPOINT: str = Field(default="localhost:9000", description="MinIO server endpoint")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="MinIO access key")
    MINIO_SECRET_KEY: str = Field(default="minioadmin123", description="MinIO secret key")
    MINIO_USE_SSL: bool = Field(default=False, description="Use SSL for MinIO connection")
    AUDIT_HMAC_SECRET: str = Field(
        default="audit-hmac-secret-key-at-least-32-characters-long",
        description="Secret key for audit log HMAC verification",
        min_length=32
    )
    
    # Testing
    TEST_DATABASE_URL: Optional[str] = Field(default=None, description="Override database URL specifically for tests")
    
    # CORS Settings
    ALLOWED_HOSTS: list = Field(default=["*"], description="Allowed CORS origins")
    
    # Environment
    ENVIRONMENT: str = Field(default="development", description="Environment name")
        
    @property
    def database_url(self) -> str:
        """Construct PostgreSQL database URL."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL."""
        password_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{password_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# Global settings instance
settings = Settings()

# Function to get settings for dependency injection
def get_settings() -> Settings:
    """Get application settings."""
    return settings 