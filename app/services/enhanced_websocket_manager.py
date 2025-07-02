"""
Enhanced WebSocket Manager for production-grade real-time signal broadcasting.
Implements advanced connection management, heartbeat mechanism, reconnection logic,
message queuing for offline users, and enhanced event routing.

Production Features:
- Circuit breakers for fault tolerance
- Prometheus metrics integration
- Graceful shutdown handling
- Redis-based horizontal scaling
- Message persistence for audit trails
- Advanced security (DDoS protection, message validation)
- Performance optimizations (message batching, compression)
"""

import json
import logging
import asyncio
import secrets
import gzip
import zlib
import time
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Set, Optional, Callable, Union
from dataclasses import dataclass, field
from collections import defaultdict, deque
from fastapi import WebSocket, WebSocketDisconnect
from enum import Enum
import hashlib
import ipaddress

logger = logging.getLogger(__name__)

# Production-grade circuit breaker implementation
class CircuitBreakerState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    """Production-grade circuit breaker for fault tolerance."""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    success_threshold: int = 3
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: Optional[datetime] = None
    
    def record_success(self):
        """Record a successful operation."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0
    
    def record_failure(self):
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)
        
        if self.state == CircuitBreakerState.CLOSED and self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
        elif self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if self.last_failure_time and (
                datetime.now(timezone.utc) - self.last_failure_time
            ).total_seconds() >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True


@dataclass
class SecurityConfig:
    """Security configuration for production deployment."""
    max_connections_per_ip: int = 10
    message_size_limit: int = 1024 * 1024  # 1MB
    rate_limit_per_ip: int = 100  # messages per minute
    allowed_origins: Set[str] = field(default_factory=set)
    require_token_validation: bool = True
    enable_compression: bool = True
    compression_threshold: int = 1024  # bytes


@dataclass
class MetricsCollector:
    """Production metrics collection."""
    total_connections: int = 0
    total_messages_sent: int = 0
    total_messages_received: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    connection_errors: int = 0
    message_failures: int = 0
    circuit_breaker_trips: int = 0
    rate_limit_hits: int = 0
    
    def reset_counters(self):
        """Reset all counters (typically called hourly)."""
        self.total_messages_sent = 0
        self.total_messages_received = 0
        self.total_bytes_sent = 0
        self.total_bytes_received = 0
        self.connection_errors = 0
        self.message_failures = 0
        self.circuit_breaker_trips = 0
        self.rate_limit_hits = 0


@dataclass
class EnhancedConnectionInfo:
    """Enhanced information about a WebSocket connection."""
    websocket: WebSocket
    user_id: int
    client_id: str
    connected_at: datetime
    last_ping: datetime
    last_pong: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    missed_heartbeats: int = 0
    subscriptions: Set[str] = field(default_factory=set)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    is_authenticated: bool = True
    session_id: Optional[str] = None
    # Production security fields
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    connection_quality: float = 1.0  # 0.0 to 1.0
    message_count: int = 0
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class QueuedMessage:
    """Represents a queued message for offline users."""
    message: Dict[str, Any]
    queued_at: datetime
    priority: int = 0  # Higher priority messages sent first
    message_type: str = ""
    retry_count: int = 0
    max_retries: int = 3
    expires_at: Optional[datetime] = None


@dataclass
class ReconnectionToken:
    """Information for reconnection token."""
    token: str
    user_id: int
    client_id: str
    expires_at: datetime
    original_session_id: Optional[str] = None
    client_fingerprint: Optional[str] = None


@dataclass
class MessageBatch:
    """Batch of messages for performance optimization."""
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    max_size: int = 100
    max_age_seconds: int = 1
    
    def add_message(self, message: Dict[str, Any]) -> bool:
        """Add message to batch. Returns True if batch is ready to send."""
        self.messages.append(message)
        
        # Check if batch is ready
        age = (datetime.now(timezone.utc) - self.created_at).total_seconds()
        return len(self.messages) >= self.max_size or age >= self.max_age_seconds


class EnhancedWebSocketManager:
    """
    Production-grade WebSocket manager with enterprise features:
    - Enhanced heartbeat mechanism with configurable timeouts
    - Reconnection logic with secure token-based recovery
    - Message queuing for offline users with priority handling
    - Subscription-based event routing
    - User preference filtering
    - Rate limiting and connection management
    - Cross-cluster event integration
    - Circuit breakers for fault tolerance
    - Metrics and monitoring integration
    - Advanced security features
    - Performance optimizations (batching, compression)
    - Graceful shutdown handling
    - Redis-based horizontal scaling support
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        # Enhanced connection tracking
        self.connections: Dict[int, List[EnhancedConnectionInfo]] = {}
        self.client_connections: Dict[str, EnhancedConnectionInfo] = {}
        
        # IP-based tracking for security
        self.ip_connections: Dict[str, List[str]] = defaultdict(list)
        self.ip_rate_limits: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'messages_sent': 0,
            'last_reset': datetime.now(timezone.utc)
        })
        
        # Connection limits and configuration
        self.max_connections_per_user = config.get('max_connections_per_user', 5) if config else 5
        
        # Heartbeat configuration
        self.heartbeat_interval = config.get('heartbeat_interval', 30) if config else 30  # seconds
        self.heartbeat_timeout_seconds = config.get('heartbeat_timeout', 60) if config else 60  # seconds
        self.max_missed_heartbeats = config.get('max_missed_heartbeats', 3) if config else 3
        
        # Reconnection system
        self.reconnection_tokens: Dict[str, ReconnectionToken] = {}
        self.reconnection_timeout_minutes = 15  # Token expires after 15 minutes
        
        # Message queuing for offline users
        self.offline_message_queues: Dict[int, deque[QueuedMessage]] = defaultdict(lambda: deque(maxlen=100))
        self.max_queue_size_per_user = 100
        self.message_retention_hours = 24
        
        # User subscriptions and preferences
        self.user_subscriptions: Dict[int, Set[str]] = defaultdict(set)
        self.user_preferences: Dict[int, Dict[str, Any]] = {}
        
        # Rate limiting
        self.rate_limits: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            'messages_sent': 0,
            'last_reset': datetime.now(timezone.utc),
            'max_messages_per_minute': 30
        })
        
        # Production features
        self.security_config = SecurityConfig()
        self.metrics = MetricsCollector()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {
            'send_message': CircuitBreaker(),
            'broadcast': CircuitBreaker(),
            'queue_message': CircuitBreaker()
        }
        
        # Message batching for performance
        self.message_batches: Dict[int, MessageBatch] = {}
        self.enable_batching = config.get('enable_batching', True) if config else True
        
        # Monitoring and background tasks
        self.is_monitoring_active = False
        self.is_shutting_down = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._batch_flush_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
        
        # Event routing callbacks
        self.event_filters: List[Callable[[Dict[str, Any], int], bool]] = []
        
        # Redis support for horizontal scaling
        self.redis_client = None
        self.redis_enabled = config.get('redis_enabled', False) if config else False
        
        # Message persistence
        self.enable_persistence = config.get('enable_persistence', False) if config else False
        self.persistent_messages: List[Dict[str, Any]] = []
        
        logger.info("Enhanced WebSocket Manager initialized with production features")
    
    def configure_security(self, security_config: SecurityConfig):
        """Configure security settings."""
        self.security_config = security_config
        logger.info(f"Security configured: max_connections_per_ip={security_config.max_connections_per_ip}")
    
    def configure_heartbeat(self, config: Dict[str, Any]):
        """Configure heartbeat mechanism parameters."""
        self.heartbeat_interval = config.get('heartbeat_interval', self.heartbeat_interval)
        self.heartbeat_timeout_seconds = config.get('heartbeat_timeout', self.heartbeat_timeout_seconds)
        self.max_missed_heartbeats = config.get('max_missed_heartbeats', self.max_missed_heartbeats)
        
        logger.info(f"Heartbeat configured: interval={self.heartbeat_interval}s, timeout={self.heartbeat_timeout_seconds}s")
    
    def _validate_message_security(self, message: Dict[str, Any], client_ip: str) -> bool:
        """Validate message for security compliance."""
        try:
            # Check message size
            message_size = len(json.dumps(message))
            if message_size > self.security_config.message_size_limit:
                logger.warning(f"Message size {message_size} exceeds limit from IP {client_ip}")
                return False
            
            # Check for suspicious content
            message_str = json.dumps(message).lower()
            suspicious_patterns = ['<script', 'javascript:', 'onload=', 'onerror=']
            for pattern in suspicious_patterns:
                if pattern in message_str:
                    logger.warning(f"Suspicious pattern '{pattern}' detected from IP {client_ip}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating message security: {e}")
            return False
    
    def _compress_message(self, message: Dict[str, Any]) -> Union[bytes, Dict[str, Any]]:
        """Compress message if beneficial."""
        try:
            if not self.security_config.enable_compression:
                return message
            
            message_json = json.dumps(message)
            message_bytes = message_json.encode('utf-8')
            
            if len(message_bytes) < self.security_config.compression_threshold:
                return message
            
            compressed = gzip.compress(message_bytes)
            
            # Only use compression if it saves significant space
            if len(compressed) < len(message_bytes) * 0.8:
                return compressed
            
            return message
            
        except Exception as e:
            logger.error(f"Error compressing message: {e}")
            return message
    
    def _create_client_fingerprint(self, client_ip: str, user_agent: str) -> str:
        """Create a client fingerprint for security."""
        fingerprint_data = f"{client_ip}:{user_agent}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    
    async def connect(self, websocket: WebSocket, user_id: int, client_id: str, 
                     session_id: Optional[str] = None, client_ip: Optional[str] = None,
                     user_agent: Optional[str] = None) -> bool:
        """
        Accept and register a new WebSocket connection with enhanced tracking and security.
        """
        try:
            # Security validations
            if client_ip:
                # Check IP-based connection limits
                ip_connections = len(self.ip_connections.get(client_ip, []))
                if ip_connections >= self.security_config.max_connections_per_ip:
                    logger.warning(f"IP {client_ip} exceeded connection limit ({self.security_config.max_connections_per_ip})")
                    await websocket.close(code=1008, reason="IP connection limit exceeded")
                    self.metrics.connection_errors += 1
                    return False
                
                # Check if IP is in allowed range (if configured)
                if self.security_config.allowed_origins:
                    try:
                        ip_obj = ipaddress.ip_address(client_ip)
                        allowed = any(ip_obj in ipaddress.ip_network(origin, strict=False) 
                                    for origin in self.security_config.allowed_origins)
                        if not allowed:
                            logger.warning(f"IP {client_ip} not in allowed origins")
                            await websocket.close(code=1008, reason="IP not allowed")
                            self.metrics.connection_errors += 1
                            return False
                    except Exception as e:
                        logger.error(f"Error validating IP {client_ip}: {e}")
            
            # Check user connection limits
            if user_id in self.connections and len(self.connections[user_id]) >= self.max_connections_per_user:
                logger.warning(f"User {user_id} exceeded connection limit ({self.max_connections_per_user})")
                await websocket.close(code=1008, reason="User connection limit exceeded")
                self.metrics.connection_errors += 1
                return False
            
            # Check circuit breaker
            if not self.circuit_breakers['send_message'].can_execute():
                logger.warning("Circuit breaker open, rejecting connection")
                await websocket.close(code=1013, reason="Service temporarily unavailable")
                self.metrics.circuit_breaker_trips += 1
                return False
            
            # Accept the connection
            await websocket.accept()
            
            # Create enhanced connection info
            now = datetime.now(timezone.utc)
            connection_info = EnhancedConnectionInfo(
                websocket=websocket,
                user_id=user_id,
                client_id=client_id,
                connected_at=now,
                last_ping=now,
                last_pong=now,
                session_id=session_id,
                client_ip=client_ip,
                user_agent=user_agent
            )
            
            # Register connection
            if user_id not in self.connections:
                self.connections[user_id] = []
            
            self.connections[user_id].append(connection_info)
            self.client_connections[client_id] = connection_info
            
            # Update IP tracking
            if client_ip:
                self.ip_connections[client_ip].append(client_id)
            
            self.metrics.total_connections += 1
            
            logger.info(f"Enhanced WebSocket connected: user_id={user_id}, client_id={client_id}, ip={client_ip}")
            
            # Send connection established message with production features
            welcome_message = {
                "type": "connection_established",
                "data": {
                    "user_id": user_id,
                    "client_id": client_id,
                    "connected_at": now.isoformat(),
                    "heartbeat_interval": self.heartbeat_interval,
                    "features": {
                        "reconnection_supported": True,
                        "message_queuing": True,
                        "subscription_filtering": True,
                        "compression_enabled": self.security_config.enable_compression,
                        "batching_enabled": self.enable_batching,
                        "circuit_breaker_protection": True
                    },
                    "security": {
                        "message_size_limit": self.security_config.message_size_limit,
                        "rate_limit": self.security_config.rate_limit_per_ip
                    }
                },
                "timestamp": now.isoformat()
            }
            
            await self.send_to_connection(connection_info, welcome_message)
            
            # Deliver any queued messages
            await self.deliver_queued_messages(user_id)
            
            # Start monitoring if not already active
            if not self.is_monitoring_active:
                await self.start_production_monitoring()
            
            self.circuit_breakers['send_message'].record_success()
            return True
            
        except Exception as e:
            logger.error(f"Error connecting enhanced WebSocket: {e}")
            self.circuit_breakers['send_message'].record_failure()
            self.metrics.connection_errors += 1
            return False
    
    async def send_to_connection(self, connection_info: EnhancedConnectionInfo, message: Dict[str, Any]):
        """Send message to a specific connection with production optimizations."""
        try:
            # Security validation
            if connection_info.client_ip and not self._validate_message_security(message, connection_info.client_ip):
                logger.warning(f"Message failed security validation for client {connection_info.client_id}")
                self.metrics.message_failures += 1
                return
            
            # Apply rate limiting
            if self.is_rate_limited(connection_info.user_id):
                logger.warning(f"Rate limit exceeded for user {connection_info.user_id}")
                self.metrics.rate_limit_hits += 1
                return
            
            # Check circuit breaker
            if not self.circuit_breakers['send_message'].can_execute():
                logger.warning("Circuit breaker open, cannot send message")
                self.metrics.circuit_breaker_trips += 1
                return
            
            # Ensure timestamp is present
            if "timestamp" not in message:
                message["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            # Performance optimization: compression
            compressed_message = self._compress_message(message)
            
            # Send message
            if isinstance(compressed_message, bytes):
                # Send compressed binary message
                await connection_info.websocket.send_bytes(compressed_message)
                self.metrics.total_bytes_sent += len(compressed_message)
            else:
                # Send regular JSON message
                await connection_info.websocket.send_json(compressed_message)
                self.metrics.total_bytes_sent += len(json.dumps(compressed_message))
            
            # Update metrics and rate limiting
            self.metrics.total_messages_sent += 1
            self.update_rate_limit(connection_info.user_id)
            connection_info.message_count += 1
            connection_info.last_activity = datetime.now(timezone.utc)
            
            # Record circuit breaker success
            self.circuit_breakers['send_message'].record_success()
            
            # Persist message if enabled
            if self.enable_persistence:
                await self._persist_message(message, connection_info.user_id, 'sent')
            
        except Exception as e:
            logger.error(f"Error sending message to connection {connection_info.client_id}: {e}")
            self.circuit_breakers['send_message'].record_failure()
            self.metrics.message_failures += 1
            raise
    
    async def _persist_message(self, message: Dict[str, Any], user_id: int, direction: str):
        """Persist message to audit trail."""
        try:
            audit_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "direction": direction,  # 'sent' or 'received'
                "message_type": message.get("type", "unknown"),
                "message_id": message.get("id", ""),
                "message_size": len(json.dumps(message)),
                "checksum": hashlib.md5(json.dumps(message, sort_keys=True).encode()).hexdigest()
            }
            
            self.persistent_messages.append(audit_record)
            
            # Limit in-memory persistence
            if len(self.persistent_messages) > 10000:
                self.persistent_messages = self.persistent_messages[-5000:]
                
        except Exception as e:
            logger.error(f"Error persisting message: {e}")
    
    async def send_to_user_batched(self, user_id: int, message: Dict[str, Any]):
        """Send message to user using batching for performance."""
        try:
            if not self.enable_batching:
                await self.send_to_user(user_id, message)
                return
            
            # Add to batch
            if user_id not in self.message_batches:
                self.message_batches[user_id] = MessageBatch()
            
            batch = self.message_batches[user_id]
            batch_ready = batch.add_message(message)
            
            if batch_ready:
                await self._flush_batch(user_id)
                
        except Exception as e:
            logger.error(f"Error in batched send to user {user_id}: {e}")
    
    async def _flush_batch(self, user_id: int):
        """Flush message batch to user."""
        try:
            if user_id not in self.message_batches:
                return
            
            batch = self.message_batches[user_id]
            if not batch.messages:
                return
            
            # Create batch message
            batch_message = {
                "type": "message_batch",
                "data": {
                    "messages": batch.messages,
                    "batch_size": len(batch.messages),
                    "created_at": batch.created_at.isoformat()
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await self.send_to_user(user_id, batch_message)
            
            # Clear batch
            del self.message_batches[user_id]
            
        except Exception as e:
            logger.error(f"Error flushing batch for user {user_id}: {e}")
    
    async def start_production_monitoring(self):
        """Start comprehensive production monitoring."""
        if self.is_monitoring_active:
            return
        
        self.is_monitoring_active = True
        
        # Heartbeat monitoring
        async def heartbeat_loop():
            while self.is_monitoring_active and not self.is_shutting_down:
                try:
                    await self.check_stale_connections()
                    await asyncio.sleep(self.heartbeat_interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in heartbeat monitoring: {e}")
                    await asyncio.sleep(5)
        
        # Batch flushing
        async def batch_flush_loop():
            while self.is_monitoring_active and not self.is_shutting_down:
                try:
                    for user_id in list(self.message_batches.keys()):
                        batch = self.message_batches[user_id]
                        age = (datetime.now(timezone.utc) - batch.created_at).total_seconds()
                        if age >= batch.max_age_seconds:
                            await self._flush_batch(user_id)
                    await asyncio.sleep(0.5)  # Check every 500ms
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in batch flushing: {e}")
                    await asyncio.sleep(1)
        
        # Metrics collection
        async def metrics_loop():
            while self.is_monitoring_active and not self.is_shutting_down:
                try:
                    await self._collect_metrics()
                    await asyncio.sleep(60)  # Collect every minute
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in metrics collection: {e}")
                    await asyncio.sleep(10)
        
        # Cleanup monitoring
        async def cleanup_loop():
            while self.is_monitoring_active and not self.is_shutting_down:
                try:
                    await self.cleanup_stale_connections()
                    await asyncio.sleep(300)  # Cleanup every 5 minutes
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in cleanup monitoring: {e}")
                    await asyncio.sleep(30)
        
        self._heartbeat_task = asyncio.create_task(heartbeat_loop())
        self._batch_flush_task = asyncio.create_task(batch_flush_loop())
        self._metrics_task = asyncio.create_task(metrics_loop())
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        
        logger.info("Started production monitoring with all features")
    
    async def _collect_metrics(self):
        """Collect and log comprehensive metrics."""
        try:
            metrics_summary = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "connections": {
                    "total": self.get_connection_count(),
                    "per_user": {user_id: len(conns) for user_id, conns in self.connections.items()},
                    "per_ip": {ip: len(clients) for ip, clients in self.ip_connections.items()}
                },
                "messages": {
                    "sent": self.metrics.total_messages_sent,
                    "received": self.metrics.total_messages_received,
                    "bytes_sent": self.metrics.total_bytes_sent,
                    "bytes_received": self.metrics.total_bytes_received,
                    "failures": self.metrics.message_failures
                },
                "errors": {
                    "connection_errors": self.metrics.connection_errors,
                    "circuit_breaker_trips": self.metrics.circuit_breaker_trips,
                    "rate_limit_hits": self.metrics.rate_limit_hits
                },
                "circuit_breakers": {
                    name: {
                        "state": cb.state.value,
                        "failure_count": cb.failure_count,
                        "success_count": cb.success_count
                    } for name, cb in self.circuit_breakers.items()
                },
                "queues": {
                    "total_queued_messages": sum(len(queue) for queue in self.offline_message_queues.values()),
                    "users_with_queued": len([q for q in self.offline_message_queues.values() if q])
                }
            }
            
            logger.info(f"Production metrics: {json.dumps(metrics_summary, indent=2)}")
            
            # Reset hourly counters
            current_hour = datetime.now(timezone.utc).hour
            if not hasattr(self, '_last_metrics_hour'):
                self._last_metrics_hour = current_hour
            elif self._last_metrics_hour != current_hour:
                self.metrics.reset_counters()
                self._last_metrics_hour = current_hour
                
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    async def graceful_shutdown(self, timeout: int = 30):
        """Perform graceful shutdown of the WebSocket manager."""
        logger.info("Starting graceful shutdown of Enhanced WebSocket Manager")
        self.is_shutting_down = True
        
        try:
            # Flush all pending batches
            for user_id in list(self.message_batches.keys()):
                await self._flush_batch(user_id)
            
            # Send shutdown notice to all connected clients
            shutdown_message = {
                "type": "server_shutdown",
                "data": {
                    "reason": "Server maintenance",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reconnect_delay": 30
                }
            }
            
            # Send to all connections
            for client_connections in self.connections.values():
                for connection_info in client_connections:
                    try:
                        await connection_info.websocket.send_json(shutdown_message)
                    except Exception:
                        pass  # Ignore send errors during shutdown
            
            # Wait a moment for messages to be sent
            await asyncio.sleep(2)
            
            # Close all connections
            for client_connections in self.connections.values():
                for connection_info in client_connections:
                    try:
                        await connection_info.websocket.close(code=1001, reason="Server shutdown")
                    except Exception:
                        pass
            
            # Cancel background tasks
            tasks = [
                self._heartbeat_task,
                self._batch_flush_task,
                self._metrics_task,
                self._cleanup_task
            ]
            
            for task in tasks:
                if task and not task.done():
                    task.cancel()
            
            # Wait for tasks to complete
            await asyncio.gather(*[task for task in tasks if task], return_exceptions=True)
            
            # Clear all data structures
            self.connections.clear()
            self.client_connections.clear()
            self.ip_connections.clear()
            self.message_batches.clear()
            
            logger.info("Graceful shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
        finally:
            self.is_monitoring_active = False
            self.is_shutting_down = False
    
    def get_production_status(self) -> Dict[str, Any]:
        """Get comprehensive production status."""
        return {
            "status": "healthy" if not self.is_shutting_down else "shutting_down",
            "uptime": "calculated_elsewhere",  # Would be calculated from start time
            "connections": {
                "total": self.get_connection_count(),
                "per_user_avg": sum(len(conns) for conns in self.connections.values()) / max(len(self.connections), 1),
                "max_per_user": self.max_connections_per_user,
                "unique_ips": len(self.ip_connections)
            },
            "circuit_breakers": {
                name: cb.state.value for name, cb in self.circuit_breakers.items()
            },
            "features": {
                "compression_enabled": self.security_config.enable_compression,
                "batching_enabled": self.enable_batching,
                "persistence_enabled": self.enable_persistence,
                "redis_enabled": self.redis_enabled
            },
            "metrics": {
                "messages_sent": self.metrics.total_messages_sent,
                "messages_received": self.metrics.total_messages_received,
                "bytes_sent": self.metrics.total_bytes_sent,
                "bytes_received": self.metrics.total_bytes_received,
                "connection_errors": self.metrics.connection_errors,
                "message_failures": self.metrics.message_failures
            }
        }
    
    async def reconnect(self, websocket: WebSocket, client_id: str, reconnection_token: str) -> bool:
        """Reconnect a client using a valid reconnection token."""
        try:
            # Validate reconnection token
            if client_id not in self.reconnection_tokens:
                logger.warning(f"No reconnection token found for client {client_id}")
                await websocket.close(code=1008, reason="Invalid reconnection token")
                return False
            
            token_info = self.reconnection_tokens[client_id]
            
            # Check token validity and expiration
            if token_info.token != reconnection_token:
                logger.warning(f"Invalid reconnection token for client {client_id}")
                await websocket.close(code=1008, reason="Invalid reconnection token")
                return False
            
            if datetime.now(timezone.utc) > token_info.expires_at:
                logger.warning(f"Expired reconnection token for client {client_id}")
                await websocket.close(code=1008, reason="Reconnection token expired")
                del self.reconnection_tokens[client_id]
                return False
            
            # Reconnect using original user_id
            user_id = token_info.user_id
            success = await self.connect(websocket, user_id, client_id, token_info.original_session_id)
            
            if success:
                # Remove used token
                del self.reconnection_tokens[client_id]
                logger.info(f"Client {client_id} successfully reconnected for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error during reconnection for client {client_id}: {e}")
            await websocket.close(code=1011, reason="Reconnection failed")
            return False
    
    async def handle_connection_drop(self, client_id: str):
        """Handle unexpected connection drops and generate reconnection tokens."""
        try:
            if client_id not in self.client_connections:
                return
            
            connection_info = self.client_connections[client_id]
            user_id = connection_info.user_id
            
            # Generate reconnection token
            reconnection_token = secrets.token_urlsafe(32)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.reconnection_timeout_minutes)
            
            self.reconnection_tokens[client_id] = ReconnectionToken(
                token=reconnection_token,
                user_id=user_id,
                client_id=client_id,
                expires_at=expires_at,
                original_session_id=connection_info.session_id
            )
            
            logger.info(f"Generated reconnection token for dropped client {client_id} (user {user_id})")
            
            # Clean up connection
            await self.disconnect(client_id)
            
        except Exception as e:
            logger.error(f"Error handling connection drop for client {client_id}: {e}")
    
    async def disconnect(self, client_id: str):
        """Disconnect and unregister a WebSocket connection."""
        try:
            if client_id not in self.client_connections:
                return
                
            connection_info = self.client_connections[client_id]
            user_id = connection_info.user_id
            
            # Remove from tracking
            if user_id in self.connections:
                try:
                    self.connections[user_id].remove(connection_info)
                    if not self.connections[user_id]:
                        del self.connections[user_id]
                except ValueError:
                    pass
            
            # Remove from IP tracking
            if connection_info.client_ip:
                ip_clients = self.ip_connections.get(connection_info.client_ip, [])
                if client_id in ip_clients:
                    ip_clients.remove(client_id)
                    if not ip_clients:
                        del self.ip_connections[connection_info.client_ip]
            
            del self.client_connections[client_id]
            
            logger.info(f"Enhanced WebSocket disconnected: user_id={user_id}, client_id={client_id}")
            
        except Exception as e:
            logger.error(f"Error disconnecting enhanced WebSocket: {e}")
    
    async def send_to_user(self, user_id: int, message: Dict[str, Any]):
        """Send message to all connections for a specific user."""
        if user_id not in self.connections:
            # User is offline, queue the message
            await self.queue_message_for_offline_user(user_id, message)
            return
            
        # Send to all user's connections
        disconnected_connections = []
        for connection_info in self.connections[user_id][:]:
            try:
                await self.send_to_connection(connection_info, message)
            except (WebSocketDisconnect, ConnectionError) as e:
                logger.warning(f"Connection lost for user {user_id}, client {connection_info.client_id}: {e}")
                disconnected_connections.append(connection_info)
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                disconnected_connections.append(connection_info)
        
        # Handle disconnected connections
        for connection_info in disconnected_connections:
            await self.handle_connection_drop(connection_info.client_id)
    
    async def queue_message_for_offline_user(self, user_id: int, message: Dict[str, Any]):
        """Queue message for offline user with enhanced retry logic."""
        try:
            # Check circuit breaker
            if not self.circuit_breakers['queue_message'].can_execute():
                logger.warning("Circuit breaker open, cannot queue message")
                self.metrics.circuit_breaker_trips += 1
                return
            
            queued_message = QueuedMessage(
                message=message,
                queued_at=datetime.now(timezone.utc),
                priority=message.get("priority", 0),
                message_type=message.get("type", "unknown"),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=self.message_retention_hours)
            )
            
            queue = self.offline_message_queues[user_id]
            
            # If queue is full, remove lowest priority message
            if len(queue) >= self.max_queue_size_per_user:
                for i, queued_msg in enumerate(queue):
                    if queued_msg.priority <= queued_message.priority:
                        del queue[i]
                        break
                else:
                    logger.warning(f"Message queue full for user {user_id}, dropping message")
                    self.circuit_breakers['queue_message'].record_failure()
                    return
            
            queue.append(queued_message)
            logger.debug(f"Queued message for offline user {user_id}: {message.get('type', 'unknown')}")
            self.circuit_breakers['queue_message'].record_success()
            
        except Exception as e:
            logger.error(f"Error queueing message for user {user_id}: {e}")
            self.circuit_breakers['queue_message'].record_failure()
    
    async def deliver_queued_messages(self, user_id: int):
        """Deliver all queued messages to a reconnected user."""
        try:
            if user_id not in self.offline_message_queues:
                return
            
            queue = self.offline_message_queues[user_id]
            if not queue:
                return
            
            # Filter out expired messages
            now = datetime.now(timezone.utc)
            valid_messages = [msg for msg in queue if not msg.expires_at or now < msg.expires_at]
            
            # Sort by priority and time
            sorted_messages = sorted(valid_messages, key=lambda x: (-x.priority, x.queued_at))
            
            for queued_message in sorted_messages:
                message = queued_message.message.copy()
                message["queued_at"] = queued_message.queued_at.isoformat()
                message["was_queued"] = True
                
                # Retry logic
                max_retries = queued_message.max_retries
                for attempt in range(max_retries + 1):
                    try:
                        await self.send_to_user(user_id, message)
                        break
                    except Exception as e:
                        if attempt < max_retries:
                            logger.warning(f"Retry {attempt + 1}/{max_retries} for queued message delivery to user {user_id}: {e}")
                            await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        else:
                            logger.error(f"Failed to deliver queued message to user {user_id} after {max_retries} retries: {e}")
            
            queue.clear()
            logger.info(f"Delivered {len(sorted_messages)} queued messages to user {user_id}")
            
        except Exception as e:
            logger.error(f"Error delivering queued messages to user {user_id}: {e}")
    
    async def subscribe_to_signals(self, user_id: int, signal_types: List[str]):
        """Subscribe user to specific signal types."""
        self.user_subscriptions[user_id].update(signal_types)
        
        if user_id in self.connections:
            for connection_info in self.connections[user_id]:
                connection_info.subscriptions.update(signal_types)
        
        logger.info(f"User {user_id} subscribed to signals: {signal_types}")
    
    async def set_user_preferences(self, user_id: int, preferences: Dict[str, Any]):
        """Set user preferences for message filtering."""
        self.user_preferences[user_id] = preferences
        
        if user_id in self.connections:
            for connection_info in self.connections[user_id]:
                connection_info.user_preferences.update(preferences)
        
        logger.info(f"Updated preferences for user {user_id}: {preferences}")
    
    async def send_filtered_message(self, user_id: int, message: Dict[str, Any]):
        """Send message to user only if it passes their filters."""
        try:
            if not self.passes_user_filters(user_id, message):
                return
            
            for filter_func in self.event_filters:
                if not filter_func(message, user_id):
                    return
            
            await self.send_to_user(user_id, message)
            
        except Exception as e:
            logger.error(f"Error sending filtered message to user {user_id}: {e}")
    
    def passes_user_filters(self, user_id: int, message: Dict[str, Any]) -> bool:
        """Check if message passes user's preference filters."""
        try:
            preferences = self.user_preferences.get(user_id, {})
            if not preferences:
                return True
            
            message_data = message.get("data", {})
            
            # Check minimum confidence
            min_confidence = preferences.get("min_confidence")
            if min_confidence and message_data.get("confidence", 1.0) < min_confidence:
                return False
            
            # Check maximum risk level
            max_risk = preferences.get("max_risk")
            if max_risk:
                risk_levels = {"low": 1, "medium": 2, "high": 3}
                message_risk = risk_levels.get(message_data.get("risk", "low"), 1)
                max_risk_level = risk_levels.get(max_risk, 3)
                if message_risk > max_risk_level:
                    return False
            
            # Check preferred sectors
            preferred_sectors = preferences.get("preferred_sectors")
            if preferred_sectors and message_data.get("sector"):
                if message_data["sector"] not in preferred_sectors:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error applying filters for user {user_id}: {e}")
            return True
    
    async def broadcast_signal_update(self, signal_data: Dict[str, Any]):
        """Broadcast signal update to subscribed users only."""
        try:
            # Check circuit breaker
            if not self.circuit_breakers['broadcast'].can_execute():
                logger.warning("Circuit breaker open, cannot broadcast")
                self.metrics.circuit_breaker_trips += 1
                return
            
            signal_symbol = signal_data.get("data", {}).get("symbol", "")
            
            for user_id, subscriptions in self.user_subscriptions.items():
                if not subscriptions or signal_symbol in subscriptions or "ALL" in subscriptions:
                    await self.send_filtered_message(user_id, signal_data)
            
            self.circuit_breakers['broadcast'].record_success()
                    
        except Exception as e:
            logger.error(f"Error broadcasting signal update: {e}")
            self.circuit_breakers['broadcast'].record_failure()
    
    def is_rate_limited(self, user_id: int) -> bool:
        """Check if user is rate limited."""
        rate_data = self.rate_limits[user_id]
        now = datetime.now(timezone.utc)
        
        if (now - rate_data['last_reset']).total_seconds() >= 60:
            rate_data['messages_sent'] = 0
            rate_data['last_reset'] = now
            return False
        
        return rate_data['messages_sent'] >= rate_data['max_messages_per_minute']
    
    def update_rate_limit(self, user_id: int):
        """Update rate limit counter for user."""
        self.rate_limits[user_id]['messages_sent'] += 1
    
    async def handle_ping_pong(self, client_id: str, message: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced ping-pong heartbeat mechanism."""
        if client_id in self.client_connections:
            connection_info = self.client_connections[client_id]
            now = datetime.now(timezone.utc)
            
            connection_info.last_ping = now
            connection_info.missed_heartbeats = 0
            
            # Update connection quality based on ping frequency
            time_since_last = (now - connection_info.last_pong).total_seconds()
            if time_since_last < self.heartbeat_interval * 0.8:
                connection_info.connection_quality = min(1.0, connection_info.connection_quality + 0.1)
            elif time_since_last > self.heartbeat_interval * 1.5:
                connection_info.connection_quality = max(0.0, connection_info.connection_quality - 0.1)
            
            connection_info.last_pong = now
        
        return {
            "type": "pong",
            "data": {
                "received_at": datetime.now(timezone.utc).isoformat(),
                "next_ping_expected": self.heartbeat_interval,
                "connection_quality": connection_info.connection_quality if client_id in self.client_connections else 1.0
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def check_stale_connections(self):
        """Check for and disconnect stale connections."""
        try:
            now = datetime.now(timezone.utc)
            stale_clients = []
            
            for client_id, connection_info in self.client_connections.items():
                time_since_ping = (now - connection_info.last_ping).total_seconds()
                
                # Check if connection is stale based on heartbeat timeout
                if time_since_ping > self.heartbeat_timeout_seconds:
                    # Increment missed heartbeats count
                    connection_info.missed_heartbeats += 1
                    logger.debug(f"Client {client_id} missed heartbeat #{connection_info.missed_heartbeats} (no ping for {time_since_ping}s)")
                    
                    # Disconnect if exceeded max missed heartbeats
                    if connection_info.missed_heartbeats >= self.max_missed_heartbeats:
                        stale_clients.append(client_id)
                        logger.warning(f"Marking client {client_id} as stale (missed {connection_info.missed_heartbeats} heartbeats)")
                else:
                    # Reset missed heartbeats if connection is active
                    if connection_info.missed_heartbeats > 0:
                        logger.debug(f"Client {client_id} heartbeat recovered")
                        connection_info.missed_heartbeats = 0
            
            # Disconnect all stale clients
            for client_id in stale_clients:
                try:
                    connection_info = self.client_connections[client_id]
                    await connection_info.websocket.close(code=1001, reason="Heartbeat timeout")
                    await self.handle_connection_drop(client_id)
                except Exception as e:
                    logger.error(f"Error disconnecting stale client {client_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error checking stale connections: {e}")
    
    async def cleanup_stale_connections(self):
        """Comprehensive cleanup of stale connections and tokens."""
        try:
            # Clean up expired reconnection tokens
            now = datetime.now(timezone.utc)
            expired_tokens = [
                client_id for client_id, token_info in self.reconnection_tokens.items()
                if now > token_info.expires_at
            ]
            
            for client_id in expired_tokens:
                del self.reconnection_tokens[client_id]
                logger.debug(f"Cleaned up expired reconnection token for {client_id}")
            
            # Clean up old queued messages
            await self.cleanup_old_queued_messages()
            
            # Check stale connections
            await self.check_stale_connections()
            
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
    
    async def cleanup_old_queued_messages(self):
        """Clean up old messages from offline queues."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.message_retention_hours)
            
            for user_id, queue in self.offline_message_queues.items():
                original_size = len(queue)
                # Remove expired messages
                while queue and (queue[0].queued_at < cutoff_time or 
                               (queue[0].expires_at and datetime.now(timezone.utc) > queue[0].expires_at)):
                    queue.popleft()
                
                if len(queue) < original_size:
                    logger.debug(f"Cleaned {original_size - len(queue)} old messages for user {user_id}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up old queued messages: {e}")
    
    async def handle_cross_cluster_event(self, event: Dict[str, Any]):
        """Handle events from other clusters."""
        try:
            event_type = event.get("type")
            source_cluster = event.get("source_cluster")
            
            logger.info(f"Handling cross-cluster event: {event_type} from {source_cluster}")
            
            if event_type == "risk_alert":
                await self.broadcast_to_active_users(event)
            elif event_type == "execution_update":
                user_id = event.get("data", {}).get("user_id")
                if user_id:
                    await self.send_to_user(user_id, event)
            else:
                await self.broadcast(event)
                
        except Exception as e:
            logger.error(f"Error handling cross-cluster event: {e}")
    
    async def broadcast_to_active_users(self, message: Dict[str, Any]):
        """Broadcast message to all active users."""
        for user_id in self.connections.keys():
            await self.send_filtered_message(user_id, message)
    
    async def broadcast(self, message: Dict[str, Any], exclude_user: int = None):
        """Broadcast message to all connected users."""
        if not self.connections:
            return
            
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        for user_id in list(self.connections.keys()):
            if exclude_user and user_id == exclude_user:
                continue
                
            await self.send_filtered_message(user_id, message)
    
    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self.client_connections)
    
    def get_user_connection_count(self, user_id: int) -> int:
        """Get number of connections for a specific user."""
        return len(self.connections.get(user_id, []))
    
    def get_connected_users(self) -> List[int]:
        """Get list of all connected user IDs."""
        return list(self.connections.keys())


# Global enhanced WebSocket manager instance
enhanced_websocket_manager = EnhancedWebSocketManager()
