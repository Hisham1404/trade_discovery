"""
Memory Layer Configuration

This module defines configuration classes and enums for the memory layer system.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class MemoryType(Enum):
    """Memory layer types for the three-layer memory system."""
    STM = "short_term"
    LTM = "long_term"
    EPISODIC = "episodic"


@dataclass
class MemoryConfig:
    """Configuration for the memory layer system."""
    
    # TTL settings (in seconds)
    stm_ttl_seconds: int = 3600  # 1 hour
    ltm_ttl_seconds: int = 604800  # 7 days
    
    # Size limits
    max_stm_size: int = 10000
    max_ltm_size: int = 50000
    max_episodic_size: int = 100000
    
    # Cleanup settings
    cleanup_interval_seconds: int = 3600  # 1 hour
    
    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    redis_decode_responses: bool = True
    
    # Qdrant configuration
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_https: bool = False
    qdrant_api_key: Optional[str] = None
    qdrant_collection_name: str = "episodic_memory"
    
    # Vector embedding settings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    
    # Performance settings
    max_concurrent_operations: int = 100
    connection_timeout: int = 30
    operation_timeout: int = 60
    
    def __post_init__(self):
        """Validate configuration parameters."""
        if self.stm_ttl_seconds <= 0:
            raise ValueError("STM TTL must be positive")
        if self.ltm_ttl_seconds <= 0:
            raise ValueError("LTM TTL must be positive")
        if self.max_stm_size <= 0:
            raise ValueError("STM size limit must be positive")
        if self.max_ltm_size <= 0:
            raise ValueError("LTM size limit must be positive")
        if self.max_episodic_size <= 0:
            raise ValueError("Episodic size limit must be positive")
        if self.cleanup_interval_seconds <= 0:
            raise ValueError("Cleanup interval must be positive")
        if self.embedding_dimension <= 0:
            raise ValueError("Embedding dimension must be positive")
    
    @property
    def redis_url(self) -> str:
        """Generate Redis connection URL."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    @property
    def qdrant_url(self) -> str:
        """Generate Qdrant connection URL."""
        protocol = "https" if self.qdrant_https else "http"
        return f"{protocol}://{self.qdrant_host}:{self.qdrant_port}" 