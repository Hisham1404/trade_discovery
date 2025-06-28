"""
Database connections and session management.
Handles PostgreSQL/TimescaleDB and Redis connections for the trading platform.
"""

import logging
from typing import Optional, AsyncGenerator, Any
from contextlib import asynccontextmanager
import redis.asyncio as redis
import redis as redis_sync
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from sqlalchemy.engine import Engine

from .config import settings

logger = logging.getLogger(__name__)

# Global Redis client instances
_redis_client_async: Optional[redis.Redis] = None
_redis_client_sync: Optional[redis_sync.Redis] = None

# Global PostgreSQL engine and session factory
_pg_engine: Optional[AsyncSession] = None
_async_session_factory: Optional[async_sessionmaker] = None


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


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


async def init_db_engine():
    """
    Initialize PostgreSQL database engine with TimescaleDB support.
    """
    global _pg_engine, _async_session_factory
    
    if _pg_engine is None:
        try:
            # Determine which database dialect we are working with.
            database_url_raw: str = getattr(settings, "TEST_DATABASE_URL", None) or settings.database_url

            # If the URL is postgres, switch to asyncpg driver automatically for async support
            if database_url_raw.startswith("postgresql://"):
                database_url = database_url_raw.replace("postgresql://", "postgresql+asyncpg://")
            else:
                # Leave other driver URLs untouched (e.g. sqlite+aiosqlite:///:memory:)
                database_url = database_url_raw

            # Extra engine options for PostgreSQL only
            engine_kwargs: dict[str, Any] = {
                "echo": settings.DEBUG,
            }

            if database_url.startswith("postgresql+asyncpg"):
                engine_kwargs.update({
                    "pool_size": 20,
                    "max_overflow": 30,
                    "pool_pre_ping": True,
                    "pool_recycle": 3600,
                    "connect_args": {
                        "server_settings": {
                            "jit": "off",
                            "application_name": "discovery_cluster_api"
                        }
                    }
                })

            _pg_engine = create_async_engine(database_url, **engine_kwargs)

            # Create async session factory
            _async_session_factory = async_sessionmaker(
                bind=_pg_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )

            # Perform driver-specific initialization (Timescale extension etc.)
            if database_url.startswith("postgresql+asyncpg"):
                async with _pg_engine.begin() as conn:
                    # Enable TimescaleDB extension (safe-guarded)
                    try:
                        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb;"))
                    except Exception as ts_err:
                        logger.warning(f"Could not ensure TimescaleDB extension: {ts_err}")

                    # Log Postgres version
                    result = await conn.execute(text("SELECT version();"))
                    version = result.scalar()
                    logger.info(f"Connected to PostgreSQL: {version}")

                    # Log TimescaleDB version if available
                    result = await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb';"))
                    ts_version = result.scalar()
                    if ts_version:
                        logger.info(f"TimescaleDB extension enabled: version {ts_version}")
            else:
                # For non-Postgres dialects (e.g., SQLite for testing) just validate connection
                async with _pg_engine.begin() as conn:
                    await conn.execute(text("SELECT 1"))
                    logger.info(f"Connected to DB for testing: {database_url}")

        except Exception as e:
            logger.error(f"Failed to initialize database engine: {e}")
            raise


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get async database session with proper cleanup.
    
    Yields:
        AsyncSession for database operations
    """
    if _async_session_factory is None:
        await init_db_engine()
    
    async with _async_session_factory() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()


async def get_db() -> AsyncSession:
    """
    Dependency for FastAPI to get database session.
    
    Returns:
        AsyncSession for database operations
    """
    async with get_db_session() as session:
        return session


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


async def close_db_engine():
    """
    Close PostgreSQL database engine gracefully.
    """
    global _pg_engine, _async_session_factory
    
    if _pg_engine:
        try:
            await _pg_engine.dispose()
            logger.info("PostgreSQL engine disposed")
        except Exception as e:
            logger.error(f"Error disposing PostgreSQL engine: {e}")
        finally:
            _pg_engine = None
            _async_session_factory = None


async def close_all_connections():
    """
    Close all database connections gracefully.
    """
    await close_redis_connection()
    await close_db_engine()


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


async def postgres_health_check() -> bool:
    """
    Check PostgreSQL/TimescaleDB connection health.
    
    Returns:
        True if PostgreSQL is healthy, False otherwise
    """
    try:
        async with get_db_session() as session:
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return False


async def full_health_check() -> dict:
    """
    Comprehensive health check for all database systems.
    
    Returns:
        Dictionary with health status for each system
    """
    health_status = {
        "redis": await redis_health_check(),
        "postgresql": await postgres_health_check(),
        "overall": False
    }
    
    health_status["overall"] = all(health_status.values())
    return health_status


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


# TimescaleDB specific utilities
async def create_hypertable(table_name: str, time_column: str, chunk_time_interval: str = "7 days") -> bool:
    """
    Convert a regular table to a TimescaleDB hypertable.
    
    Args:
        table_name: Name of the table to convert
        time_column: Name of the time column for partitioning
        chunk_time_interval: Time interval for chunk partitioning
        
    Returns:
        True if hypertable created successfully
    """
    try:
        async with get_db_session() as session:
            # Check if already a hypertable
            check_query = text("""
                SELECT 1 FROM timescaledb_information.hypertables 
                WHERE hypertable_name = :table_name
            """)
            result = await session.execute(check_query, {"table_name": table_name})
            
            if result.scalar():
                logger.info(f"Table {table_name} is already a hypertable")
                return True
            
            # Create hypertable
            create_query = text(f"""
                SELECT create_hypertable('{table_name}', '{time_column}', 
                                        chunk_time_interval => INTERVAL '{chunk_time_interval}')
            """)
            await session.execute(create_query)
            await session.commit()
            
            logger.info(f"Successfully created hypertable: {table_name}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to create hypertable {table_name}: {e}")
        return False


async def add_retention_policy(table_name: str, retention_period: str = "7 years") -> bool:
    """
    Add data retention policy to a hypertable.
    
    Args:
        table_name: Name of the hypertable
        retention_period: How long to retain data
        
    Returns:
        True if retention policy added successfully
    """
    try:
        async with get_db_session() as session:
            query = text(f"""
                SELECT add_retention_policy('{table_name}', INTERVAL '{retention_period}')
            """)
            await session.execute(query)
            await session.commit()
            
            logger.info(f"Added retention policy to {table_name}: {retention_period}")
            return True
            
    except Exception as e:
        logger.error(f"Failed to add retention policy to {table_name}: {e}")
        return False 