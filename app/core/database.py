"""
Database connections and session management.
Handles Redis connections for session management and caching.
"""

import logging
from typing import Optional
import redis.asyncio as redis
import redis as redis_sync

from .config import settings

logger = logging.getLogger(__name__)

# Global Redis client instances
_redis_client_async: Optional[redis.Redis] = None
_redis_client_sync: Optional[redis_sync.Redis] = None


async def get_redis_client_async() -> redis.Redis:
    """
    Get async Redis client instance with connection pooling.
    
    Returns:
        Async Redis client instance
    """
    global _redis_client_async
    
    if _redis_client_async is None:
        try:
            _redis_client_async = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # Test connection
            await _redis_client_async.ping()
            logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    return _redis_client_async


def get_redis_client() -> redis_sync.Redis:
    """
    Synchronous Redis client getter for compatibility.
    
    Returns:
        Synchronous Redis client instance
    """
    global _redis_client_sync
    
    if _redis_client_sync is None:
        try:
            _redis_client_sync = redis_sync.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            logger.info(f"Redis client configured for {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            
        except Exception as e:
            logger.error(f"Failed to configure Redis client: {e}")
            raise
    
    return _redis_client_sync


async def close_redis_connection():
    """
    Close Redis connections gracefully.
    """
    global _redis_client_async, _redis_client_sync
    
    if _redis_client_async:
        try:
            await _redis_client_async.close()
            logger.info("Async Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing async Redis connection: {e}")
        finally:
            _redis_client_async = None
    
    if _redis_client_sync:
        try:
            _redis_client_sync.close()
            logger.info("Sync Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing sync Redis connection: {e}")
        finally:
            _redis_client_sync = None


async def redis_health_check() -> bool:
    """
    Check Redis connection health.
    
    Returns:
        True if Redis is healthy, False otherwise
    """
    try:
        client = await get_redis_client_async()
        await client.ping()
        return True
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return False


class RedisSessionManager:
    """
    Manages user sessions in Redis.
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.session_prefix = "session:"
        self.default_ttl = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # Convert to seconds
    
    async def create_session(self, user_id: str, token: str, ttl: Optional[int] = None) -> bool:
        """
        Create a new user session.
        
        Args:
            user_id: User identifier
            token: JWT token
            ttl: Time to live in seconds (defaults to token expiration)
            
        Returns:
            True if session created successfully
        """
        try:
            key = f"{self.session_prefix}{user_id}"
            ttl = ttl or self.default_ttl
            
            await self.redis.setex(key, ttl, token)
            logger.debug(f"Session created for user {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create session for user {user_id}: {e}")
            return False
    
    async def get_session(self, user_id: str) -> Optional[str]:
        """
        Get user session token.
        
        Args:
            user_id: User identifier
            
        Returns:
            JWT token if session exists, None otherwise
        """
        try:
            key = f"{self.session_prefix}{user_id}"
            token = await self.redis.get(key)
            return token
            
        except Exception as e:
            logger.error(f"Failed to get session for user {user_id}: {e}")
            return None
    
    async def delete_session(self, user_id: str) -> bool:
        """
        Delete user session.
        
        Args:
            user_id: User identifier
            
        Returns:
            True if session deleted successfully
        """
        try:
            key = f"{self.session_prefix}{user_id}"
            result = await self.redis.delete(key)
            logger.debug(f"Session deleted for user {user_id}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to delete session for user {user_id}: {e}")
            return False
    
    async def refresh_session(self, user_id: str, ttl: Optional[int] = None) -> bool:
        """
        Refresh session TTL.
        
        Args:
            user_id: User identifier
            ttl: Time to live in seconds (defaults to token expiration)
            
        Returns:
            True if session refreshed successfully
        """
        try:
            key = f"{self.session_prefix}{user_id}"
            ttl = ttl or self.default_ttl
            
            result = await self.redis.expire(key, ttl)
            if result:
                logger.debug(f"Session refreshed for user {user_id}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Failed to refresh session for user {user_id}: {e}")
            return False 