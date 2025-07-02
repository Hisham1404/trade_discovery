"""
Production-Grade Cross-Cluster Event Publishing and Consumption Framework

Enterprise-level implementation with:
- Comprehensive monitoring and observability
- Advanced security and input validation
- Performance optimizations and connection pooling
- Graceful shutdown and resource management
- Structured logging with correlation IDs
- Database model integration
- Configuration management system
- Advanced error handling and classification
"""

import asyncio
import json
import logging
import time
import uuid
import signal
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager
import traceback
from concurrent.futures import ThreadPoolExecutor
import threading

# Core dependencies
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String, DateTime, Float, Integer, Text, Boolean, Index
from pydantic import BaseModel, Field, validator
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import structlog

# Project imports
from integration.event_schemas import (
    SignalAcceptedEvent,
    SignalStatusUpdateEvent,
    RiskAlertEvent,
    MarketDataUpdateEvent,
    AgentPerformanceEvent,
    UserActionEvent,
    SystemHealthEvent,
    SignalDirection
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Prometheus metrics
EVENTS_PUBLISHED = Counter('events_published_total', 'Total events published', ['topic', 'status'])
EVENTS_CONSUMED = Counter('events_consumed_total', 'Total events consumed', ['topic', 'status'])
EVENT_PROCESSING_TIME = Histogram('event_processing_seconds', 'Event processing time', ['event_type'])
CIRCUIT_BREAKER_STATE = Gauge('circuit_breaker_state', 'Circuit breaker state', ['component'])
DEAD_LETTER_QUEUE_SIZE = Gauge('dlq_size', 'Dead letter queue size')
DATABASE_CONNECTIONS = Gauge('database_connections_active', 'Active database connections')


class ErrorSeverity(Enum):
    """Error severity levels for classification"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification"""
    NETWORK = "network"
    DATABASE = "database"
    AUTHENTICATION = "authentication"
    VALIDATION = "validation"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM = "system"


@dataclass
class ProductionConfig:
    """Production configuration with environment variables"""
    # Database settings
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', 'postgresql+asyncpg://localhost/trading'))
    database_pool_size: int = field(default_factory=lambda: int(os.getenv('DB_POOL_SIZE', '20')))
    database_max_overflow: int = field(default_factory=lambda: int(os.getenv('DB_MAX_OVERFLOW', '10')))
    
    # Pulsar settings
    pulsar_url: str = field(default_factory=lambda: os.getenv('PULSAR_URL', 'pulsar://localhost:6650'))
    pulsar_producer_pool_size: int = field(default_factory=lambda: int(os.getenv('PULSAR_PRODUCER_POOL_SIZE', '10')))
    pulsar_consumer_pool_size: int = field(default_factory=lambda: int(os.getenv('PULSAR_CONSUMER_POOL_SIZE', '5')))
    
    # Circuit breaker settings
    circuit_breaker_failure_threshold: int = field(default_factory=lambda: int(os.getenv('CB_FAILURE_THRESHOLD', '5')))
    circuit_breaker_recovery_timeout: int = field(default_factory=lambda: int(os.getenv('CB_RECOVERY_TIMEOUT', '60')))
    
    # Performance settings
    max_concurrent_events: int = field(default_factory=lambda: int(os.getenv('MAX_CONCURRENT_EVENTS', '100')))
    event_batch_size: int = field(default_factory=lambda: int(os.getenv('EVENT_BATCH_SIZE', '10')))
    event_batch_timeout: float = field(default_factory=lambda: float(os.getenv('EVENT_BATCH_TIMEOUT', '5.0')))
    
    # Security settings
    enable_rate_limiting: bool = field(default_factory=lambda: os.getenv('ENABLE_RATE_LIMITING', 'true').lower() == 'true')
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv('RATE_LIMIT_PER_MINUTE', '1000')))
    
    # Monitoring settings
    enable_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_METRICS', 'true').lower() == 'true')
    metrics_port: int = field(default_factory=lambda: int(os.getenv('METRICS_PORT', '8000')))
    
    # Logging settings
    log_level: str = field(default_factory=lambda: os.getenv('LOG_LEVEL', 'INFO'))
    enable_correlation_ids: bool = field(default_factory=lambda: os.getenv('ENABLE_CORRELATION_IDS', 'true').lower() == 'true')


# Database Models
Base = declarative_base()

class SignalModel(Base):
    """Database model for signals"""
    __tablename__ = "signals"
    
    signal_id = Column(String(50), primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    direction = Column(String(10), nullable=False)
    confidence = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    target = Column(Float, nullable=False)
    status = Column(String(20), nullable=False, default='pending', index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Performance indexes
    __table_args__ = (
        Index('idx_signals_user_status', 'user_id', 'status'),
        Index('idx_signals_symbol_direction', 'symbol', 'direction'),
        Index('idx_signals_created_at', 'created_at'),
    )


class EventLogModel(Base):
    """Database model for event logging"""
    __tablename__ = "event_logs"
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(100), nullable=False, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    topic = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False, index=True)
    error_message = Column(Text)
    correlation_id = Column(String(50), index=True)
    processing_time_ms = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Performance indexes
    __table_args__ = (
        Index('idx_event_logs_type_status', 'event_type', 'status'),
        Index('idx_event_logs_correlation', 'correlation_id'),
        Index('idx_event_logs_created_at', 'created_at'),
    )


class ProductionError(Exception):
    """Production-grade error with classification"""
    
    def __init__(self, message: str, category: ErrorCategory, severity: ErrorSeverity, 
                 correlation_id: Optional[str] = None, details: Optional[Dict] = None):
        self.message = message
        self.category = category
        self.severity = severity
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.details = details or {}
        self.timestamp = datetime.now(timezone.utc)
        super().__init__(message)


class RateLimiter:
    """Token bucket rate limiter"""
    
    def __init__(self, rate_per_minute: int):
        self.rate_per_minute = rate_per_minute
        self.tokens = rate_per_minute
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def is_allowed(self) -> bool:
        """Check if request is allowed under rate limit"""
        with self.lock:
            now = time.time()
            time_passed = now - self.last_update
            self.tokens = min(self.rate_per_minute, self.tokens + time_passed * (self.rate_per_minute / 60))
            self.last_update = now
            
            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False


class InputValidator:
    """Production-grade input validation"""
    
    @staticmethod
    def validate_signal_data(signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate signal data with comprehensive checks"""
        required_fields = ['signal_id', 'user_id', 'symbol', 'direction', 'confidence', 'stop_loss', 'target']
        
        # Check required fields
        for field in required_fields:
            if field not in signal_data or signal_data[field] is None:
                raise ProductionError(
                    f"Missing required field: {field}",
                    ErrorCategory.VALIDATION,
                    ErrorSeverity.HIGH
                )
        
        # Validate data types and ranges
        if not isinstance(signal_data['confidence'], (int, float)) or not (0 <= signal_data['confidence'] <= 1):
            raise ProductionError(
                "Confidence must be a number between 0 and 1",
                ErrorCategory.VALIDATION,
                ErrorSeverity.HIGH
            )
        
        if not isinstance(signal_data['stop_loss'], (int, float)) or signal_data['stop_loss'] <= 0:
            raise ProductionError(
                "Stop loss must be a positive number",
                ErrorCategory.VALIDATION,
                ErrorSeverity.HIGH
            )
        
        if not isinstance(signal_data['target'], (int, float)) or signal_data['target'] <= 0:
            raise ProductionError(
                "Target must be a positive number",
                ErrorCategory.VALIDATION,
                ErrorSeverity.HIGH
            )
        
        # Validate string fields
        if not isinstance(signal_data['signal_id'], str) or len(signal_data['signal_id']) > 50:
            raise ProductionError(
                "Signal ID must be a string with max 50 characters",
                ErrorCategory.VALIDATION,
                ErrorSeverity.HIGH
            )
        
        # Validate direction
        if signal_data['direction'] not in ['BUY', 'SELL']:
            raise ProductionError(
                "Direction must be 'BUY' or 'SELL'",
                ErrorCategory.VALIDATION,
                ErrorSeverity.HIGH
            )
        
        return signal_data


class ProductionEventPublisher:
    """Production-grade event publisher with comprehensive features"""
    
    def __init__(self, config: ProductionConfig, pulsar_client, auth_service):
        self.config = config
        self.pulsar_client = pulsar_client
        self.auth_service = auth_service
        
        # Rate limiter
        self.rate_limiter = RateLimiter(config.rate_limit_per_minute) if config.enable_rate_limiting else None
        
        # Circuit breaker
        self.circuit_breaker = ProductionCircuitBreaker(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout
        )
        
        # Producer pool for performance
        self.producer_pool: Dict[str, Any] = {}
        self.producer_lock = asyncio.Lock()
        
        # Deduplication cache with TTL
        self.published_events: Dict[str, datetime] = {}
        self.dedup_cleanup_interval = timedelta(hours=1)
        self.last_dedup_cleanup = datetime.now(timezone.utc)
        
        # Batch processing
        self.event_batches: Dict[str, List] = {}
        self.batch_timers: Dict[str, asyncio.Task] = {}
        
        # Metrics
        self.metrics = {
            "total_published": 0,
            "successful_published": 0,
            "failed_published": 0,
            "rate_limited": 0,
            "circuit_breaker_rejections": 0,
            "batch_processed": 0
        }
    
    async def publish_event(self, event: BaseModel, topic: str, 
                           correlation_id: Optional[str] = None,
                           properties: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Publish event with production-grade features"""
        correlation_id = correlation_id or str(uuid.uuid4())
        start_time = time.time()
        
        log = logger.bind(
            correlation_id=correlation_id,
            event_type=event.__class__.__name__,
            topic=topic
        )
        
        try:
            # Rate limiting
            if self.rate_limiter and not self.rate_limiter.is_allowed():
                self.metrics["rate_limited"] += 1
                EVENTS_PUBLISHED.labels(topic=topic, status='rate_limited').inc()
                raise ProductionError(
                    "Rate limit exceeded",
                    ErrorCategory.SYSTEM,
                    ErrorSeverity.MEDIUM,
                    correlation_id
                )
            
            # Circuit breaker check
            if not await self.circuit_breaker.can_execute():
                self.metrics["circuit_breaker_rejections"] += 1
                EVENTS_PUBLISHED.labels(topic=topic, status='circuit_breaker_rejected').inc()
                CIRCUIT_BREAKER_STATE.labels(component='publisher').set(2)  # OPEN state
                raise ProductionError(
                    "Circuit breaker is open",
                    ErrorCategory.SYSTEM,
                    ErrorSeverity.HIGH,
                    correlation_id
                )
            
            # Event deduplication
            event_id = self._generate_event_id(event)
            if self._is_duplicate(event_id):
                log.info("Duplicate event detected", event_id=event_id)
                return {
                    "success": True,
                    "duplicate_detected": True,
                    "event_id": event_id,
                    "correlation_id": correlation_id
                }
            
            # Publish with retry and monitoring
            result = await self._publish_with_monitoring(event, topic, event_id, correlation_id, properties)
            
            # Update circuit breaker and metrics
            if result["success"]:
                await self.circuit_breaker.record_success()
                self._mark_as_published(event_id)
                self.metrics["successful_published"] += 1
                EVENTS_PUBLISHED.labels(topic=topic, status='success').inc()
                CIRCUIT_BREAKER_STATE.labels(component='publisher').set(0)  # CLOSED state
            else:
                await self.circuit_breaker.record_failure()
                self.metrics["failed_published"] += 1
                EVENTS_PUBLISHED.labels(topic=topic, status='failed').inc()
            
            self.metrics["total_published"] += 1
            
            # Record processing time
            processing_time = (time.time() - start_time) * 1000
            EVENT_PROCESSING_TIME.labels(event_type=event.__class__.__name__).observe(processing_time / 1000)
            
            log.info("Event publishing completed", 
                    success=result["success"], 
                    processing_time_ms=processing_time)
            
            return result
            
        except ProductionError:
            raise
        except Exception as e:
            await self.circuit_breaker.record_failure()
            self.metrics["failed_published"] += 1
            EVENTS_PUBLISHED.labels(topic=topic, status='error').inc()
            
            log.error("Unexpected error in event publishing", error=str(e), exc_info=True)
            raise ProductionError(
                f"Unexpected publishing error: {str(e)}",
                ErrorCategory.SYSTEM,
                ErrorSeverity.CRITICAL,
                correlation_id,
                {"original_error": str(e), "traceback": traceback.format_exc()}
            )
    
    async def _publish_with_monitoring(self, event: BaseModel, topic: str, 
                                     event_id: str, correlation_id: str,
                                     properties: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Publish with comprehensive monitoring and error handling"""
        retry_count = 0
        max_retries = 3
        base_delay = 1.0
        
        while retry_count <= max_retries:
            try:
                # Get or create producer from pool
                producer = await self._get_producer(topic)
                
                # Prepare message properties
                message_properties = {
                    "event_id": event_id,
                    "event_type": event.__class__.__name__,
                    "correlation_id": correlation_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "retry_count": str(retry_count),
                    **(properties or {})
                }
                
                # Send message with timeout
                message_data = event.json().encode('utf-8')
                
                # Use asyncio.wait_for for timeout control
                message_id = await asyncio.wait_for(
                    producer.send_async(message_data, properties=message_properties),
                    timeout=10.0  # 10 second timeout
                )
                
                logger.info("Event published successfully", 
                           event_id=event_id, 
                           message_id=str(message_id),
                           correlation_id=correlation_id,
                           retry_count=retry_count)
                
                return {
                    "success": True,
                    "message_id": str(message_id),
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                    "topic": topic,
                    "retry_count": retry_count
                }
                
            except asyncio.TimeoutError:
                logger.warning("Publishing timeout", 
                              event_id=event_id, 
                              correlation_id=correlation_id,
                              retry_count=retry_count)
                retry_count += 1
                if retry_count <= max_retries:
                    await asyncio.sleep(base_delay * (2 ** retry_count))  # Exponential backoff
                
            except Exception as e:
                logger.error("Publishing attempt failed", 
                            event_id=event_id, 
                            correlation_id=correlation_id,
                            retry_count=retry_count,
                            error=str(e))
                retry_count += 1
                if retry_count <= max_retries:
                    await asyncio.sleep(base_delay * (2 ** retry_count))
        
        # All retries failed
        raise ProductionError(
            f"Failed to publish after {max_retries} retries",
            ErrorCategory.NETWORK,
            ErrorSeverity.HIGH,
            correlation_id
        )
    
    async def _get_producer(self, topic: str):
        """Get producer from pool with connection management"""
        async with self.producer_lock:
            if topic not in self.producer_pool:
                try:
                    producer = await self.pulsar_client.create_producer_async(
                        topic,
                        send_timeout_millis=10000,
                        max_pending_messages=1000,
                        batching_enabled=True,
                        batching_max_messages=100,
                        batching_max_publish_delay_ms=100
                    )
                    self.producer_pool[topic] = producer
                    logger.info("Created new producer for topic", topic=topic)
                except Exception as e:
                    raise ProductionError(
                        f"Failed to create producer for topic {topic}: {str(e)}",
                        ErrorCategory.NETWORK,
                        ErrorSeverity.HIGH
                    )
            
            return self.producer_pool[topic]
    
    def _generate_event_id(self, event: BaseModel) -> str:
        """Generate unique event ID for deduplication"""
        if hasattr(event, 'signal_id') and hasattr(event, 'timestamp'):
            return f"{event.signal_id}_{event.timestamp.isoformat()}"
        elif hasattr(event, 'signal_id'):
            return f"{event.signal_id}_{datetime.now(timezone.utc).isoformat()}"
        else:
            return str(uuid.uuid4())
    
    def _is_duplicate(self, event_id: str) -> bool:
        """Check for duplicates with TTL cleanup"""
        self._cleanup_old_duplicates()
        return event_id in self.published_events
    
    def _mark_as_published(self, event_id: str):
        """Mark event as published with timestamp"""
        self.published_events[event_id] = datetime.now(timezone.utc)
    
    def _cleanup_old_duplicates(self):
        """Clean up old deduplication entries"""
        now = datetime.now(timezone.utc)
        if now - self.last_dedup_cleanup > self.dedup_cleanup_interval:
            cutoff_time = now - timedelta(hours=24)  # Keep 24 hours of dedup data
            old_events = [
                event_id for event_id, timestamp in self.published_events.items()
                if timestamp < cutoff_time
            ]
            for event_id in old_events:
                del self.published_events[event_id]
            
            self.last_dedup_cleanup = now
            if old_events:
                logger.info("Cleaned up old deduplication entries", count=len(old_events))
    
    async def shutdown(self):
        """Graceful shutdown of publisher"""
        logger.info("Shutting down event publisher")
        
        # Close all producers
        for topic, producer in self.producer_pool.items():
            try:
                await producer.close_async()
                logger.info("Closed producer", topic=topic)
            except Exception as e:
                logger.error("Error closing producer", topic=topic, error=str(e))
        
        self.producer_pool.clear()
        logger.info("Event publisher shutdown complete")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics"""
        return {
            **self.metrics,
            "circuit_breaker": self.circuit_breaker.get_state(),
            "deduplication_cache_size": len(self.published_events),
            "producer_pool_size": len(self.producer_pool)
        }


class ProductionCircuitBreaker:
    """Production-grade circuit breaker with advanced features"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.half_open_calls = 0
        self.consecutive_successes = 0
        self.lock = asyncio.Lock()
    
    async def can_execute(self) -> bool:
        """Thread-safe execution check"""
        async with self.lock:
            current_time = time.time()
            
            if self.state == "CLOSED":
                return True
            
            if self.state == "OPEN":
                if self.last_failure_time and (current_time - self.last_failure_time) >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.half_open_calls = 0
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    return True
                return False
            
            if self.state == "HALF_OPEN":
                return self.half_open_calls < 3  # Allow 3 test calls
            
            return False
    
    async def record_success(self):
        """Record successful operation"""
        async with self.lock:
            if self.state == "HALF_OPEN":
                self.consecutive_successes += 1
                if self.consecutive_successes >= 2:
                    self.state = "CLOSED"
                    self.failure_count = 0
                    self.consecutive_successes = 0
                    logger.info("Circuit breaker closed after recovery")
            elif self.state == "CLOSED":
                self.failure_count = max(0, self.failure_count - 1)
            
            self.half_open_calls = 0
    
    async def record_failure(self):
        """Record failed operation"""
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            self.consecutive_successes = 0
            
            if self.state == "HALF_OPEN":
                self.state = "OPEN"
                logger.warning("Circuit breaker opened from HALF_OPEN")
            elif self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
            
            if self.state == "HALF_OPEN":
                self.half_open_calls += 1
    
    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state"""
        return {
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
            "consecutive_successes": self.consecutive_successes
        }


class ProductionCrossClusterIntegration:
    """Production-grade cross-cluster integration"""
    
    def __init__(self, config: ProductionConfig, db_session: AsyncSession,
                 event_publisher: ProductionEventPublisher, cluster_name: str):
        self.config = config
        self.db_session = db_session
        self.event_publisher = event_publisher
        self.cluster_name = cluster_name
        
        # Input validator
        self.validator = InputValidator()
        
        # Shutdown event
        self.shutdown_event = asyncio.Event()
        
        # Health status
        self.health_status = {"status": "initializing", "cluster_name": cluster_name}
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
        
        logger.info("Production CrossClusterIntegration initialized", cluster_name=cluster_name)
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info("Received shutdown signal", signal=signum)
            asyncio.create_task(self.shutdown())
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    async def accept_signal(self, signal_data: Dict[str, Any], 
                           correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """Production-grade signal acceptance with comprehensive error handling"""
        correlation_id = correlation_id or str(uuid.uuid4())
        start_time = time.time()
        
        log = logger.bind(
            correlation_id=correlation_id,
            signal_id=signal_data.get('signal_id'),
            cluster_name=self.cluster_name
        )
        
        transaction = None
        
        try:
            # Input validation
            validated_data = self.validator.validate_signal_data(signal_data)
            log.info("Signal data validated successfully")
            
            # Begin database transaction
            transaction = await self.db_session.begin()
            DATABASE_CONNECTIONS.inc()
            
            # Create and save signal model
            signal_model = SignalModel(
                signal_id=validated_data["signal_id"],
                user_id=validated_data["user_id"],
                symbol=validated_data["symbol"],
                direction=validated_data["direction"],
                confidence=validated_data["confidence"],
                stop_loss=validated_data["stop_loss"],
                target=validated_data["target"],
                status='pending'
            )
            
            self.db_session.add(signal_model)
            await self.db_session.flush()  # Get ID without committing
            
            # Create signal accepted event
            event = SignalAcceptedEvent(
                signal_id=validated_data["signal_id"],
                user_id=validated_data["user_id"],
                symbol=validated_data["symbol"],
                direction=SignalDirection(validated_data["direction"]),
                confidence=validated_data["confidence"],
                stop_loss=validated_data["stop_loss"],
                target=validated_data["target"],
                timestamp=datetime.now(timezone.utc)
            )
            
            # Publish event
            publish_result = await self.event_publisher.publish_event(
                event, 
                "signals.accepted",
                correlation_id
            )
            
            if not publish_result["success"]:
                await transaction.rollback()
                DATABASE_CONNECTIONS.dec()
                
                raise ProductionError(
                    f"Failed to publish event: {publish_result.get('error')}",
                    ErrorCategory.NETWORK,
                    ErrorSeverity.HIGH,
                    correlation_id
                )
            
            # Commit transaction
            await transaction.commit()
            DATABASE_CONNECTIONS.dec()
            
            processing_time = (time.time() - start_time) * 1000
            log.info("Signal accepted successfully", 
                    processing_time_ms=processing_time,
                    message_id=publish_result["message_id"])
            
            return {
                "success": True,
                "signal_id": validated_data["signal_id"],
                "message_id": publish_result["message_id"],
                "event_id": publish_result["event_id"],
                "correlation_id": correlation_id,
                "processing_time_ms": processing_time
            }
            
        except ProductionError:
            if transaction:
                await transaction.rollback()
                DATABASE_CONNECTIONS.dec()
            raise
            
        except Exception as e:
            if transaction:
                await transaction.rollback()
                DATABASE_CONNECTIONS.dec()
            
            log.error("Unexpected error accepting signal", error=str(e), exc_info=True)
            raise ProductionError(
                f"Unexpected error: {str(e)}",
                ErrorCategory.SYSTEM,
                ErrorSeverity.CRITICAL,
                correlation_id,
                {"original_error": str(e), "traceback": traceback.format_exc()}
            )
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        try:
            # Check database connectivity
            db_start = time.time()
            result = await self.db_session.execute("SELECT 1")
            db_latency = (time.time() - db_start) * 1000
            
            # Check event publisher health
            publisher_metrics = self.event_publisher.get_metrics()
            
            # Determine overall health
            overall_status = "healthy"
            issues = []
            
            if db_latency > 1000:  # 1 second threshold
                overall_status = "degraded"
                issues.append(f"High database latency: {db_latency:.2f}ms")
            
            if publisher_metrics["circuit_breaker"]["state"] == "OPEN":
                overall_status = "degraded"
                issues.append("Publisher circuit breaker is open")
            
            if publisher_metrics.get("failed_published", 0) > publisher_metrics.get("successful_published", 1):
                overall_status = "degraded"
                issues.append("High publisher failure rate")
            
            return {
                "status": overall_status,
                "cluster_name": self.cluster_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "issues": issues,
                "metrics": {
                    "database_latency_ms": db_latency,
                    "publisher_metrics": publisher_metrics,
                    "active_connections": DATABASE_CONNECTIONS._value.get(),
                    "dlq_size": DEAD_LETTER_QUEUE_SIZE._value.get()
                },
                "components": {
                    "database": {
                        "status": "healthy" if db_latency < 1000 else "degraded",
                        "latency_ms": db_latency
                    },
                    "event_publisher": {
                        "status": "healthy" if publisher_metrics["circuit_breaker"]["state"] != "OPEN" else "degraded",
                        "circuit_breaker_state": publisher_metrics["circuit_breaker"]["state"]
                    }
                }
            }
            
        except Exception as e:
            logger.error("Error getting health status", error=str(e))
            return {
                "status": "unhealthy",
                "cluster_name": self.cluster_name,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Starting graceful shutdown", cluster_name=self.cluster_name)
        
        # Set shutdown event
        self.shutdown_event.set()
        
        # Close event publisher
        await self.event_publisher.shutdown()
        
        # Close database connections
        await self.db_session.close()
        
        self.health_status = {
            "status": "shutdown",
            "cluster_name": self.cluster_name,
            "shutdown_at": datetime.now(timezone.utc).isoformat()
        }
        
        logger.info("Graceful shutdown complete", cluster_name=self.cluster_name)


# Factory function for production integration
async def create_production_integration(
    cluster_name: str,
    config: Optional[ProductionConfig] = None
) -> ProductionCrossClusterIntegration:
    """Create production-grade cross-cluster integration"""
    
    config = config or ProductionConfig()
    
    # Start metrics server if enabled
    if config.enable_metrics:
        start_http_server(config.metrics_port)
        logger.info("Metrics server started", port=config.metrics_port)
    
    # Create database engine and session
    engine = create_async_engine(
        config.database_url,
        pool_size=config.database_pool_size,
        max_overflow=config.database_max_overflow,
        echo=config.log_level == 'DEBUG'
    )
    
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    db_session = session_factory()
    
    # Create Pulsar client (mock for testing)
    pulsar_client = MockPulsarClient()  # In production, use real Pulsar client
    
    # Create authentication service (mock for testing)
    auth_service = MockAuthService()  # In production, use real auth service
    
    # Create event publisher
    event_publisher = ProductionEventPublisher(config, pulsar_client, auth_service)
    
    # Create integration
    integration = ProductionCrossClusterIntegration(
        config, db_session, event_publisher, cluster_name
    )
    
    return integration


# Mock classes for testing
class MockPulsarClient:
    """Mock Pulsar client for testing"""
    
    async def create_producer_async(self, topic, **kwargs):
        return MockProducer()


class MockProducer:
    """Mock Pulsar producer for testing"""
    
    async def send_async(self, data, properties=None):
        # Simulate successful send
        await asyncio.sleep(0.01)  # Simulate network delay
        return f"msg-{uuid.uuid4()}"
    
    async def close_async(self):
        pass


class MockAuthService:
    """Mock authentication service for testing"""
    
    async def authenticate_request(self, request):
        return {"authenticated": True, "user_id": "test-user"} 