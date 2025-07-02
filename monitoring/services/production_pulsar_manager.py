"""
Production-Grade Pulsar Manager for Trading Systems
"""

import os
import logging
import time
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from prometheus_client import Counter, Histogram, Gauge
import pulsar
from pulsar.admin import PulsarAdmin

logger = logging.getLogger(__name__)

# Metrics
PULSAR_OPERATIONS_TOTAL = Counter(
    'pulsar_operations_total',
    'Total Pulsar operations',
    ['operation', 'topic', 'status']
)

PULSAR_OPERATION_DURATION = Histogram(
    'pulsar_operation_duration_seconds',
    'Pulsar operation duration',
    ['operation', 'topic']
)

PULSAR_CONNECTIONS_ACTIVE = Gauge(
    'pulsar_connections_active',
    'Active Pulsar connections'
)


class CircuitBreakerError(Exception):
    """Circuit breaker is open"""
    pass


class SimpleCircuitBreaker:
    """Simple circuit breaker implementation"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
    
    def __call__(self, func):
        def wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                else:
                    raise CircuitBreakerError("Circuit breaker is OPEN")
            
            try:
                result = func(*args, **kwargs)
                if self.state == "HALF_OPEN":
                    self.reset()
                return result
            except Exception as e:
                self.record_failure()
                raise
        
        return wrapper
    
    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
    
    def reset(self):
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
    
    @property
    def current_state(self):
        return self.state


@dataclass
class ProductionPulsarConfig:
    """Production configuration for Pulsar"""
    service_url: str = field(default_factory=lambda: os.getenv("PULSAR_SERVICE_URL", "pulsar://localhost:6650"))
    admin_url: str = field(default_factory=lambda: os.getenv("PULSAR_ADMIN_URL", "http://localhost:8080"))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    tenant: str = field(default_factory=lambda: os.getenv("PULSAR_TENANT", "public"))
    namespace: str = field(default_factory=lambda: os.getenv("PULSAR_NAMESPACE", "trading-signals"))
    use_tls: bool = field(default_factory=lambda: os.getenv("PULSAR_USE_TLS", "false").lower() == "true")
    auth_token: str = field(default_factory=lambda: os.getenv("PULSAR_AUTH_TOKEN", ""))
    connection_timeout_ms: int = 30000
    operation_timeout_ms: int = 30000
    max_connections_per_broker: int = 5
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60


class ProductionPulsarManager:
    """Production-grade Pulsar manager with enterprise features"""
    
    def __init__(self, config: Optional[ProductionPulsarConfig] = None):
        self.config = config or ProductionPulsarConfig()
        self._admin_client = None
        self._client = None
        self._producers = {}
        self._consumers = {}
        self._circuit_breaker = SimpleCircuitBreaker(
            failure_threshold=self.config.circuit_breaker_failure_threshold,
            recovery_timeout=self.config.circuit_breaker_recovery_timeout
        )
        self._health_status = {"status": "initializing", "last_check": time.time()}
        
    async def initialize(self) -> bool:
        """Initialize Pulsar connections"""
        try:
            await self._create_admin_client()
            await self._create_client()
            await self._validate_connections()
            
            self._health_status = {"status": "healthy", "last_check": time.time()}
            PULSAR_CONNECTIONS_ACTIVE.set(1)
            logger.info("Production Pulsar manager initialized successfully")
            return True
            
        except Exception as e:
            self._health_status = {"status": "unhealthy", "last_check": time.time(), "error": str(e)}
            logger.error(f"Failed to initialize Pulsar manager: {e}")
            raise
    
    async def _create_admin_client(self):
        """Create Pulsar admin client"""
        admin_config = {"service_url": self.config.admin_url}
        
        if self.config.auth_token:
            admin_config["authentication"] = pulsar.AuthenticationToken(self.config.auth_token)
        
        self._admin_client = PulsarAdmin(**admin_config)
    
    async def _create_client(self):
        """Create Pulsar client"""
        client_config = {
            "service_url": self.config.service_url,
            "connection_timeout_millis": self.config.connection_timeout_ms,
            "operation_timeout_seconds": self.config.operation_timeout_ms // 1000,
            "max_connections_per_broker": self.config.max_connections_per_broker
        }
        
        if self.config.auth_token:
            client_config["authentication"] = pulsar.AuthenticationToken(self.config.auth_token)
        
        self._client = pulsar.Client(**client_config)
    
    async def _validate_connections(self):
        """Validate connections"""
        try:
            tenants = self._admin_client.tenants().get_tenants()
            logger.info(f"Admin connection validated. Available tenants: {tenants}")
            
            test_topic = f"persistent://{self.config.tenant}/{self.config.namespace}/health-check"
            test_producer = self._client.create_producer(test_topic)
            test_producer.close()
            logger.info("Client connection validated")
            
        except Exception as e:
            raise ConnectionError(f"Connection validation failed: {e}")
    
    @asynccontextmanager
    async def get_producer(self, topic: str, **kwargs):
        """Get a producer with connection pooling"""
        producer_key = f"{topic}:{hash(str(kwargs))}"
        
        if producer_key not in self._producers:
            try:
                start_time = time.time()
                
                producer_config = {
                    "topic": topic,
                    "send_timeout_millis": 30000,
                    "batching_enabled": True,
                    "batching_max_messages": 1000,
                    "compression_type": pulsar.CompressionType.LZ4,
                    **kwargs
                }
                
                producer = self._client.create_producer(**producer_config)
                self._producers[producer_key] = producer
                
                duration = time.time() - start_time
                PULSAR_OPERATION_DURATION.labels(operation="create_producer", topic=topic).observe(duration)
                PULSAR_OPERATIONS_TOTAL.labels(operation="create_producer", topic=topic, status="success").inc()
                
            except Exception as e:
                PULSAR_OPERATIONS_TOTAL.labels(operation="create_producer", topic=topic, status="error").inc()
                raise
        
        try:
            yield self._producers[producer_key]
        finally:
            pass
    
    async def send_message(self, topic: str, message: Dict[str, Any], **kwargs) -> str:
        """Send message with monitoring"""
        start_time = time.time()
        
        try:
            async with self.get_producer(topic, **kwargs) as producer:
                message_data = json.dumps(message).encode('utf-8')
                
                @self._circuit_breaker
                def _send():
                    return producer.send(message_data)
                
                message_id = _send()
                
                duration = time.time() - start_time
                PULSAR_OPERATION_DURATION.labels(operation="send_message", topic=topic).observe(duration)
                PULSAR_OPERATIONS_TOTAL.labels(operation="send_message", topic=topic, status="success").inc()
                
                return str(message_id)
                
        except CircuitBreakerError as e:
            PULSAR_OPERATIONS_TOTAL.labels(operation="send_message", topic=topic, status="circuit_breaker").inc()
            raise
        except Exception as e:
            PULSAR_OPERATIONS_TOTAL.labels(operation="send_message", topic=topic, status="error").inc()
            raise
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get health status"""
        health_data = {
            "status": self._health_status["status"],
            "last_check": self._health_status["last_check"],
            "connections": {
                "admin": self._admin_client is not None,
                "client": self._client is not None,
                "producers": len(self._producers),
                "consumers": len(self._consumers)
            },
            "circuit_breaker": {
                "state": self._circuit_breaker.current_state,
                "failure_count": self._circuit_breaker.failure_count,
                "last_failure_time": self._circuit_breaker.last_failure_time
            }
        }
        
        if "error" in self._health_status:
            health_data["error"] = self._health_status["error"]
        
        return health_data
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get metrics"""
        try:
            topic_stats = {}
            namespace_name = f"{self.config.tenant}/{self.config.namespace}"
            
            try:
                topics = self._admin_client.topics().get_list(namespace_name)
                for topic in topics:
                    try:
                        stats = self._admin_client.topics().get_stats(topic)
                        topic_stats[topic] = {
                            "msg_rate_in": getattr(stats, 'msgRateIn', 0),
                            "msg_rate_out": getattr(stats, 'msgRateOut', 0),
                            "storage_size": getattr(stats, 'storageSize', 0)
                        }
                    except Exception as e:
                        topic_stats[topic] = {"error": str(e)}
            except Exception as e:
                pass
            
            return {
                "timestamp": time.time(),
                "health": await self.get_health_status(),
                "topics": topic_stats,
                "connection_pools": {
                    "producers": len(self._producers),
                    "consumers": len(self._consumers)
                }
            }
            
        except Exception as e:
            return {"error": str(e), "timestamp": time.time()}
    
    async def close(self):
        """Close all connections"""
        try:
            for producer in self._producers.values():
                try:
                    producer.close()
                except Exception:
                    pass
            
            for consumer in self._consumers.values():
                try:
                    consumer.close()
                except Exception:
                    pass
            
            if self._client:
                self._client.close()
            if self._admin_client:
                self._admin_client.close()
            
            PULSAR_CONNECTIONS_ACTIVE.set(0)
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


# Global instance
production_pulsar_manager = ProductionPulsarManager()


async def initialize_production_pulsar() -> bool:
    """Initialize production Pulsar manager"""
    return await production_pulsar_manager.initialize()


async def get_production_pulsar_health() -> Dict[str, Any]:
    """Get production Pulsar health status"""
    return await production_pulsar_manager.get_health_status()


async def get_production_pulsar_metrics() -> Dict[str, Any]:
    """Get production Pulsar metrics"""
    return await production_pulsar_manager.get_metrics() 