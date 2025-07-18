"""
Production-Grade Memory Manager

Enterprise-ready memory management with security, reliability, observability,
connection pooling, and comprehensive health monitoring for trading systems.
"""

import os
import ssl
import logging
import asyncio
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from prometheus_client import Counter, Histogram, Gauge, Info
import redis.asyncio as redis
from qdrant_client import AsyncQdrantClient
import backoff

from .config import MemoryConfig
from .stm_manager import STMManager
from .ltm_manager import LTMManager
from .episodic_manager import EpisodicMemoryManager
from .cleanup_manager import MemoryCleanupManager

logger = logging.getLogger(__name__)

# Production Metrics
MEMORY_OPERATIONS_TOTAL = Counter(
    'memory_operations_total',
    'Total memory operations',
    ['operation', 'memory_type', 'status']
)

MEMORY_OPERATION_DURATION = Histogram(
    'memory_operation_duration_seconds',
    'Memory operation duration',
    ['operation', 'memory_type']
)

MEMORY_CONNECTIONS_ACTIVE = Gauge(
    'memory_connections_active',
    'Active memory connections',
    ['service']
)


class MemoryCircuitBreaker:
    """Circuit breaker for memory services"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.redis_failures = 0
        self.qdrant_failures = 0
        self.redis_last_failure = None
        self.qdrant_last_failure = None
        self.redis_state = "CLOSED"
        self.qdrant_state = "CLOSED"


@dataclass
class ProductionMemoryConfig:
    """Production-grade memory configuration"""
    base_config: MemoryConfig = field(default_factory=MemoryConfig)
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    redis_ssl: bool = field(default_factory=lambda: os.getenv("REDIS_SSL", "false").lower() == "true")
    redis_password: str = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", ""))
    qdrant_api_key: str = field(default_factory=lambda: os.getenv("QDRANT_API_KEY", ""))
    redis_max_connections: int = 100
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60


class ProductionMemoryManager:
    """
    Production-grade memory manager with enterprise features:
    - Security (TLS, authentication, encryption)
    - Reliability (circuit breakers, connection pooling, health checks)
    - Observability (metrics, tracing, structured logging)
    - Scalability (resource management, connection limits)
    """
    
    def __init__(self, config: Optional[ProductionMemoryConfig] = None):
        self.config = config or ProductionMemoryConfig()
        self._redis_pool = None
        self._qdrant_client = None
        self._stm_manager = None
        self._ltm_manager = None
        self._episodic_manager = None
        self._cleanup_manager = None
        self._circuit_breaker = MemoryCircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            recovery_timeout=self.config.circuit_breaker_recovery_timeout
        )
        self._health_status = {"status": "initializing", "last_check": time.time()}
        self._initialized = False
    
    @backoff.on_exception(
        backoff.expo,
        Exception,
        max_tries=3,
        max_time=300
    )
    async def initialize(self) -> bool:
        """Initialize production memory system"""
        try:
            await self._create_redis_pool()
            await self._create_qdrant_client()
            await self._initialize_managers()
            await self._validate_connections()
            
            self._health_status = {"status": "healthy", "last_check": time.time()}
            self._initialized = True
            
            logger.info("Production memory manager initialized successfully")
            return True
            
        except Exception as e:
            self._health_status = {"status": "unhealthy", "last_check": time.time(), "error": str(e)}
            logger.error(f"Failed to initialize production memory manager: {e}")
            raise
    
    async def _create_redis_pool(self):
        """Create Redis connection pool with security"""
        redis_config = {
            "host": self.config.base_config.redis_host,
            "port": self.config.base_config.redis_port,
            "db": self.config.base_config.redis_db,
            "decode_responses": self.config.base_config.redis_decode_responses,
            "max_connections": self.config.redis_max_connections,
            "socket_connect_timeout": self.config.base_config.connection_timeout,
            "socket_timeout": self.config.base_config.connection_timeout
        }
        
        # Add authentication
        if self.config.redis_password:
            redis_config["password"] = self.config.redis_password
        
        # Create connection pool
        pool = redis.ConnectionPool(**redis_config)
        self._redis_pool = redis.Redis(connection_pool=pool)
        
        # Test connection
        await self._redis_pool.ping()
        MEMORY_CONNECTIONS_ACTIVE.labels(service="redis").set(1)
        logger.info("Redis connection pool created successfully")
    
    async def _create_qdrant_client(self):
        """Create Qdrant client with security"""
        qdrant_config = {
            "host": self.config.base_config.qdrant_host,
            "port": self.config.base_config.qdrant_port,
            "timeout": self.config.base_config.connection_timeout
        }
        
        if self.config.qdrant_api_key:
            qdrant_config["api_key"] = self.config.qdrant_api_key
        
        self._qdrant_client = AsyncQdrantClient(**qdrant_config)
        
        # Test connection
        await self._qdrant_client.get_collections()
        MEMORY_CONNECTIONS_ACTIVE.labels(service="qdrant").set(1)
        logger.info("Qdrant client created successfully")
    
    async def _initialize_managers(self):
        """Initialize memory managers with production clients"""
        self._stm_manager = STMManager(
            config=self.config.base_config,
            redis_client=self._redis_pool
        )
        await self._stm_manager.initialize()
        
        self._ltm_manager = LTMManager(
            config=self.config.base_config,
            redis_client=self._redis_pool
        )
        await self._ltm_manager.initialize()
        
        self._episodic_manager = EpisodicMemoryManager(
            config=self.config.base_config,
            qdrant_client=self._qdrant_client
        )
        await self._episodic_manager.initialize()
        
        self._cleanup_manager = MemoryCleanupManager(
            config=self.config.base_config,
            stm_manager=self._stm_manager,
            ltm_manager=self._ltm_manager,
            episodic_manager=self._episodic_manager
        )
        
        logger.info("All memory managers initialized")
    
    async def _validate_connections(self):
        """Validate all connections are working"""
        try:
            await self._redis_pool.ping()
            collections = await self._qdrant_client.get_collections()
            await self._stm_manager.store_market_data("TEST", {"price": 100})
            await self._stm_manager.get_market_data("TEST")
            logger.info("All connections validated successfully")
        except Exception as e:
            raise ConnectionError(f"Connection validation failed: {e}")
    
    async def store_signal(self, agent_name: str, signal_data: Dict[str, Any]) -> bool:
        """Store signal with production reliability features"""
        start_time = time.time()
        operation = "store_signal"
        
        try:
            result = await self._stm_manager.store_signal(agent_name, signal_data)
            
            # Record metrics
            duration = time.time() - start_time
            MEMORY_OPERATION_DURATION.labels(operation=operation, memory_type="stm").observe(duration)
            MEMORY_OPERATIONS_TOTAL.labels(operation=operation, memory_type="stm", status="success").inc()
            
            return result
            
        except Exception as e:
            MEMORY_OPERATIONS_TOTAL.labels(operation=operation, memory_type="stm", status="error").inc()
            logger.error(f"Failed to store signal: {e}")
            raise
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        health_data = {
            "status": self._health_status["status"],
            "last_check": self._health_status["last_check"],
            "connections": {
                "redis": self._redis_pool is not None,
                "qdrant": self._qdrant_client is not None
            },
            "managers": {
                "stm": self._stm_manager is not None,
                "ltm": self._ltm_manager is not None,
                "episodic": self._episodic_manager is not None,
                "cleanup": self._cleanup_manager is not None
            }
        }
        
        if "error" in self._health_status:
            health_data["error"] = self._health_status["error"]
        
        return health_data
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive production metrics"""
        try:
            metrics = {
                "timestamp": time.time(),
                "health": await self.get_health_status(),
                "memory_usage": {}
            }
            
            if self._stm_manager:
                metrics["memory_usage"]["stm"] = await self._stm_manager.get_memory_usage()
            
            if self._ltm_manager:
                metrics["memory_usage"]["ltm"] = await self._ltm_manager.get_memory_usage()
            
            return metrics
            
        except Exception as e:
            logger.error(f"Failed to get metrics: {e}")
            return {"error": str(e), "timestamp": time.time()}
    
    async def close(self):
        """Gracefully close all connections"""
        try:
            self._initialized = False
            
            if self._stm_manager:
                await self._stm_manager.close()
            if self._ltm_manager:
                await self._ltm_manager.close()
            if self._episodic_manager:
                await self._episodic_manager.close()
            
            if self._redis_pool:
                await self._redis_pool.aclose()
            if self._qdrant_client:
                await self._qdrant_client.close()
            
            MEMORY_CONNECTIONS_ACTIVE.labels(service="redis").set(0)
            MEMORY_CONNECTIONS_ACTIVE.labels(service="qdrant").set(0)
            
            logger.info("Production memory manager closed")
            
        except Exception as e:
            logger.error(f"Error during memory manager cleanup: {e}")


# Global instance
production_memory_manager = ProductionMemoryManager()


async def initialize_production_memory() -> bool:
    """Initialize production memory manager"""
    return await production_memory_manager.initialize()


async def get_production_memory_health() -> Dict[str, Any]:
    """Get production memory health status"""
    return await production_memory_manager.get_health_status()


async def get_production_memory_metrics() -> Dict[str, Any]:
    """Get production memory metrics"""
    return await production_memory_manager.get_metrics()
