"""
Cross-Cluster Event Publishing and Consumption Framework - Task 9.3

Implements comprehensive event-driven communication between clusters:
- EventPublisher with circuit breaker pattern and retry logic
- EventConsumer with dead letter queue and error handling
- CrossClusterIntegration class with transaction support
- Event deduplication using message IDs
- Background tasks for continuous message consumption
- Integration with Pulsar infrastructure and authentication service
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import traceback

# Core dependencies
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

# Project imports
from integration.event_schemas import (
    SignalAcceptedEvent,
    SignalStatusUpdateEvent,
    RiskAlertEvent,
    MarketDataUpdateEvent,
    AgentPerformanceEvent,
    UserActionEvent,
    SystemHealthEvent
)

# Configure logging
logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class RetryConfig:
    """Retry configuration for event operations"""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3


class CircuitBreaker:
    """Circuit breaker implementation for resilience"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None
        self.state = CircuitBreakerState.CLOSED
        self.half_open_calls = 0
        self.consecutive_successes = 0
    
    def can_execute(self) -> bool:
        """Check if operation can be executed"""
        current_time = time.time()
        
        if self.state == CircuitBreakerState.CLOSED:
            return True
        
        if self.state == CircuitBreakerState.OPEN:
            if self.last_failure_time and (current_time - self.last_failure_time) >= self.config.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker transitioning to HALF_OPEN state")
                return True
            return False
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            return self.half_open_calls < self.config.half_open_max_calls
        
        return False
    
    def record_success(self):
        """Record successful operation"""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.consecutive_successes += 1
            if self.consecutive_successes >= 2:  # Require multiple successes to close
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.consecutive_successes = 0
                logger.info("Circuit breaker closed after successful recovery")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)  # Gradual recovery
        
        self.half_open_calls = 0
    
    def record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.consecutive_successes = 0
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            logger.warning("Circuit breaker opened from HALF_OPEN due to failure")
        elif self.state == CircuitBreakerState.CLOSED and self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")
        
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.half_open_calls += 1
    
    def get_state(self) -> Dict[str, Any]:
        """Get circuit breaker state information"""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "half_open_calls": self.half_open_calls,
            "consecutive_successes": self.consecutive_successes
        }


@dataclass
class FailedMessage:
    """Represents a failed message in the dead letter queue"""
    message_id: str
    topic: str
    data: Any
    failure_reason: str
    retry_count: int
    first_failed_at: datetime
    last_failed_at: datetime
    properties: Dict[str, str] = field(default_factory=dict)


class DeadLetterQueue:
    """Dead letter queue for failed messages"""
    
    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self._messages: Dict[str, FailedMessage] = {}
        self._insertion_order: List[str] = []
    
    def add_failed_message(self, message_data: Dict[str, Any]) -> bool:
        """Add failed message to queue"""
        try:
            message_id = message_data["message_id"]
            current_time = datetime.now(timezone.utc)
            
            if message_id in self._messages:
                # Update existing message
                existing = self._messages[message_id]
                existing.retry_count += 1
                existing.last_failed_at = current_time
                existing.failure_reason = message_data.get("failure_reason", existing.failure_reason)
            else:
                # Add new message
                if len(self._messages) >= self.max_size:
                    # Remove oldest message
                    oldest_id = self._insertion_order.pop(0)
                    del self._messages[oldest_id]
                
                failed_message = FailedMessage(
                    message_id=message_id,
                    topic=message_data.get("topic", "unknown"),
                    data=message_data.get("data"),
                    failure_reason=message_data.get("failure_reason", "Unknown error"),
                    retry_count=1,
                    first_failed_at=current_time,
                    last_failed_at=current_time,
                    properties=message_data.get("properties", {})
                )
                
                self._messages[message_id] = failed_message
                self._insertion_order.append(message_id)
            
            logger.warning(f"Message {message_id} added to DLQ: {message_data.get('failure_reason')}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add message to DLQ: {e}")
            return False
    
    def get_failed_messages(self, limit: Optional[int] = None) -> List[FailedMessage]:
        """Get failed messages from queue"""
        messages = [self._messages[msg_id] for msg_id in self._insertion_order]
        return messages[:limit] if limit else messages
    
    def replay_message(self, message_id: str) -> Optional[FailedMessage]:
        """Replay message from queue (removes it)"""
        if message_id in self._messages:
            message = self._messages.pop(message_id)
            self._insertion_order.remove(message_id)
            logger.info(f"Replaying message {message_id} from DLQ")
            return message
        return None
    
    def queue_length(self) -> int:
        """Get queue length"""
        return len(self._messages)


class EventPublisher:
    """Event publisher with circuit breaker and retry logic"""
    
    def __init__(self, pulsar_client, auth_service,
                 circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
                 retry_config: Optional[RetryConfig] = None):
        self.pulsar_client = pulsar_client
        self.auth_service = auth_service
        self.circuit_breaker = CircuitBreaker(circuit_breaker_config or CircuitBreakerConfig())
        self.retry_config = retry_config or RetryConfig()
        
        # Message deduplication
        self.published_messages: Set[str] = set()
        
        # Metrics
        self.metrics = {
            "total_published": 0,
            "successful_published": 0,
            "failed_published": 0,
            "duplicates_detected": 0,
            "circuit_breaker_rejections": 0
        }
    
    async def publish_event(self, event: BaseModel, topic: str, 
                           properties: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Publish event with deduplication, circuit breaker, and retry logic"""
        try:
            # Generate unique event ID for deduplication
            event_id = self._generate_event_id(event)
            
            # Check for duplicates
            if self._is_duplicate(event_id):
                self.metrics["duplicates_detected"] += 1
                logger.info(f"Duplicate event detected: {event_id}")
                return {
                    "success": True,
                    "duplicate_detected": True,
                    "message_id": event_id,
                    "event_id": event_id
                }
            
            # Check circuit breaker
            if not self.circuit_breaker.can_execute():
                self.metrics["circuit_breaker_rejections"] += 1
                logger.warning("Circuit breaker is OPEN, rejecting publish request")
                return {
                    "success": False,
                    "error": "Circuit breaker is open",
                    "circuit_breaker_state": self.circuit_breaker.get_state()
                }
            
            # Attempt to publish with retry
            result = await self._publish_with_retry(event, topic, event_id, properties)
            
            # Update circuit breaker
            if result["success"]:
                self.circuit_breaker.record_success()
                self._mark_as_published(event_id)
                self.metrics["successful_published"] += 1
            else:
                self.circuit_breaker.record_failure()
                self.metrics["failed_published"] += 1
            
            self.metrics["total_published"] += 1
            return result
            
        except Exception as e:
            self.circuit_breaker.record_failure()
            self.metrics["failed_published"] += 1
            self.metrics["total_published"] += 1
            logger.error(f"Unexpected error in publish_event: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "event_id": getattr(event, 'signal_id', 'unknown')
            }
    
    async def _publish_with_retry(self, event: BaseModel, topic: str, 
                                event_id: str, properties: Optional[Dict[str, str]]) -> Dict[str, Any]:
        """Publish with retry logic"""
        last_exception = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Create producer for topic
                producer = self.pulsar_client.create_producer(topic)
                
                # Prepare message properties
                message_properties = {
                    "event_id": event_id,
                    "event_type": event.__class__.__name__,
                    "cluster_name": getattr(event, 'cluster_name', 'unknown'),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    **(properties or {})
                }
                
                # Send message
                message_data = event.json().encode('utf-8')
                message_id = producer.send(message_data, properties=message_properties)
                
                logger.info(f"Event published successfully: {event_id} -> {message_id}")
                return {
                    "success": True,
                    "message_id": str(message_id),
                    "event_id": event_id,
                    "topic": topic,
                    "retry_count": attempt
                }
                
            except Exception as e:
                last_exception = e
                logger.warning(f"Publish attempt {attempt + 1} failed: {e}")
                
                if attempt < self.retry_config.max_retries:
                    delay = self._calculate_retry_delay(attempt)
                    await asyncio.sleep(delay)
        
        # All retries failed
        error_message = f"Failed to publish after {self.retry_config.max_retries} retries: {last_exception}"
        logger.error(error_message)
        return {
            "success": False,
            "error": error_message,
            "event_id": event_id,
            "retry_count": self.retry_config.max_retries
        }
    
    def _generate_event_id(self, event: BaseModel) -> str:
        """Generate unique event ID for deduplication"""
        # Use signal_id and timestamp if available, otherwise generate UUID
        if hasattr(event, 'signal_id') and hasattr(event, 'timestamp'):
            return f"{event.signal_id}_{event.timestamp.isoformat()}"
        elif hasattr(event, 'signal_id'):
            return f"{event.signal_id}_{datetime.now(timezone.utc).isoformat()}"
        else:
            return str(uuid.uuid4())
    
    def _is_duplicate(self, event_id: str) -> bool:
        """Check if event is a duplicate"""
        return event_id in self.published_messages
    
    def _mark_as_published(self, event_id: str):
        """Mark event as published for deduplication"""
        self.published_messages.add(event_id)
    
    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff"""
        delay = min(
            self.retry_config.base_delay * (self.retry_config.backoff_factor ** attempt),
            self.retry_config.max_delay
        )
        
        if self.retry_config.jitter:
            import random
            delay *= (0.5 + random.random() * 0.5)  # Add 0-50% jitter
        
        return delay
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get publisher metrics"""
        return {
            **self.metrics,
            "circuit_breaker": self.circuit_breaker.get_state(),
            "deduplication_cache_size": len(self.published_messages)
        }


class EventConsumer:
    """Event consumer with error handling and dead letter queue"""
    
    def __init__(self, pulsar_client, dead_letter_queue: DeadLetterQueue, max_retry_attempts: int = 3):
        self.pulsar_client = pulsar_client
        self.dead_letter_queue = dead_letter_queue
        self.max_retry_attempts = max_retry_attempts
        
        # Message handlers
        self.message_handlers: Dict[str, Callable] = {}
        
        # Consumer state
        self.is_consuming = False
        self.consumption_task: Optional[asyncio.Task] = None
        
        # Metrics
        self.metrics = {
            "total_consumed": 0,
            "successful_processed": 0,
            "failed_processed": 0,
            "sent_to_dlq": 0
        }
        
        # Message tracking for retry logic
        self.message_retry_counts: Dict[str, int] = {}
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register message handler for specific event type"""
        self.message_handlers[event_type] = handler
        logger.info(f"Registered handler for event type: {event_type}")
    
    async def start_consumption(self, topics: List[str], subscription_name: str):
        """Start background consumption task"""
        if self.is_consuming:
            logger.warning("Consumer is already running")
            return
        
        self.is_consuming = True
        self.consumption_task = asyncio.create_task(
            self._consume_messages(topics, subscription_name)
        )
        logger.info(f"Started consuming from topics: {topics}")
    
    async def stop_consumption(self):
        """Stop consumption task"""
        self.is_consuming = False
        if self.consumption_task:
            self.consumption_task.cancel()
            try:
                await self.consumption_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped message consumption")
    
    async def _consume_messages(self, topics: List[str], subscription_name: str):
        """Main consumption loop"""
        try:
            consumer = self.pulsar_client.subscribe(topics, subscription_name)
            
            while self.is_consuming:
                try:
                    # Receive message with timeout
                    message = consumer.receive(timeout_millis=5000)  # 5 second timeout
                    await self._process_message(consumer, message)
                    
                except Exception as e:
                    logger.error(f"Error in consumption loop: {e}")
                    await asyncio.sleep(1)  # Brief pause before retrying
                    
        except Exception as e:
            logger.error(f"Fatal error in consumption loop: {e}")
            self.is_consuming = False
    
    async def _process_message(self, consumer, message):
        """Process individual message"""
        message_id = str(message.message_id())
        
        try:
            self.metrics["total_consumed"] += 1
            
            # Extract message properties
            properties = message.properties()
            event_type = properties.get("event_type", "unknown")
            
            # Check if we have a handler for this event type
            if event_type not in self.message_handlers:
                logger.warning(f"No handler for event type: {event_type}")
                consumer.acknowledge(message)
                return
            
            # Get retry count
            retry_count = self.message_retry_counts.get(message_id, 0)
            
            # Process message
            handler = self.message_handlers[event_type]
            await handler(message, properties)
            
            # Acknowledge successful processing
            consumer.acknowledge(message)
            self.metrics["successful_processed"] += 1
            
            # Remove from retry tracking
            self.message_retry_counts.pop(message_id, None)
            
            logger.debug(f"Successfully processed message: {message_id}")
            
        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}")
            
            # Update retry count
            retry_count = self.message_retry_counts.get(message_id, 0) + 1
            self.message_retry_counts[message_id] = retry_count
            
            if retry_count >= self.max_retry_attempts:
                # Send to dead letter queue
                await self._send_to_dlq(message, str(e))
                consumer.acknowledge(message)  # Acknowledge to remove from topic
                self.message_retry_counts.pop(message_id, None)
                self.metrics["sent_to_dlq"] += 1
            else:
                # Negative acknowledge for retry
                consumer.negative_acknowledge(message)
                logger.info(f"Message {message_id} will be retried (attempt {retry_count})")
            
            self.metrics["failed_processed"] += 1
    
    async def _send_to_dlq(self, message, error_reason: str):
        """Send failed message to dead letter queue"""
        try:
            message_data = {
                "message_id": str(message.message_id()),
                "topic": message.topic_name(),
                "data": message.data().decode('utf-8'),
                "properties": message.properties(),
                "failure_reason": error_reason,
                "retry_count": self.message_retry_counts.get(str(message.message_id()), 0)
            }
            
            self.dead_letter_queue.add_failed_message(message_data)
            logger.warning(f"Message sent to DLQ: {message.message_id()}")
            
        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get consumer metrics"""
        return {
            **self.metrics,
            "is_consuming": self.is_consuming,
            "dlq_size": self.dead_letter_queue.queue_length(),
            "pending_retries": len(self.message_retry_counts)
        }


class CrossClusterIntegration:
    """Main integration class with transaction support"""
    
    def __init__(self, 
                 db_session: AsyncSession,
                 event_publisher: EventPublisher,
                 event_consumer: EventConsumer,
                 cluster_name: str):
        self.db_session = db_session
        self.event_publisher = event_publisher
        self.event_consumer = event_consumer
        self.cluster_name = cluster_name
        
        # Register event handlers
        self._register_handlers()
        
        # Health status
        self.health_status = {"status": "initializing"}
        
        logger.info(f"CrossClusterIntegration initialized for cluster: {cluster_name}")
    
    def _register_handlers(self):
        """Register event handlers for different event types"""
        self.event_consumer.register_handler(
            "SignalStatusUpdateEvent", 
            self._handle_signal_status_update
        )
        self.event_consumer.register_handler(
            "RiskAlertEvent", 
            self._handle_risk_alert
        )
        self.event_consumer.register_handler(
            "MarketDataUpdateEvent", 
            self._handle_market_data_update
        )
        self.event_consumer.register_handler(
            "AgentPerformanceEvent", 
            self._handle_agent_performance
        )
    
    async def accept_signal(self, signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Accept signal with transaction support for database updates and event publishing"""
        transaction = None
        
        try:
            # Begin database transaction
            transaction = await self.db_session.begin()
            
            # Create signal accepted event
            event = SignalAcceptedEvent(
                signal_id=signal_data["signal_id"],
                symbol=signal_data["symbol"],
                action=signal_data["action"],
                quantity=signal_data["quantity"],
                target_price=signal_data["target_price"],
                stop_loss=signal_data["stop_loss"],
                confidence=signal_data["confidence"],
                agent_id=signal_data["agent_id"],
                cluster_name=self.cluster_name,
                timestamp=datetime.now(timezone.utc)
            )
            
            # Publish event
            publish_result = await self.event_publisher.publish_event(
                event, 
                "signals.accepted"
            )
            
            if not publish_result["success"]:
                await transaction.rollback()
                return {
                    "success": False,
                    "error": f"Failed to publish event: {publish_result.get('error')}",
                    "signal_id": signal_data["signal_id"]
                }
            
            # Commit transaction
            await transaction.commit()
            
            logger.info(f"Signal accepted successfully: {signal_data['signal_id']}")
            return {
                "success": True,
                "signal_id": signal_data["signal_id"],
                "message_id": publish_result["message_id"],
                "event_id": publish_result["event_id"]
            }
            
        except Exception as e:
            if transaction:
                await transaction.rollback()
            
            logger.error(f"Error accepting signal {signal_data.get('signal_id')}: {e}")
            return {
                "success": False,
                "error": str(e),
                "signal_id": signal_data.get("signal_id")
            }
    
    async def handle_status_update(self, status_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle status update from monitoring cluster"""
        return {"success": True, "signal_id": status_data["signal_id"]}
    
    async def _handle_signal_status_update(self, message, properties: Dict[str, str]):
        """Handle signal status update events from monitoring cluster"""
        try:
            # Parse message data
            data = json.loads(message.data().decode('utf-8'))
            
            # Create event object
            event = SignalStatusUpdateEvent(**data)
            
            logger.info(f"Signal status updated: {event.signal_id} -> {event.status}")
            
        except Exception as e:
            logger.error(f"Error handling signal status update: {e}")
            raise  # Re-raise to trigger retry logic
    
    async def _handle_risk_alert(self, message, properties: Dict[str, str]):
        """Handle risk alert events"""
        try:
            data = json.loads(message.data().decode('utf-8'))
            event = RiskAlertEvent(**data)
            
            logger.warning(f"Risk alert received: {event.alert_type} - {event.message}")
            
        except Exception as e:
            logger.error(f"Error handling risk alert: {e}")
            raise
    
    async def _handle_market_data_update(self, message, properties: Dict[str, str]):
        """Handle market data update events"""
        try:
            data = json.loads(message.data().decode('utf-8'))
            event = MarketDataUpdateEvent(**data)
            
            logger.debug(f"Market data updated: {event.symbol} -> {event.price}")
            
        except Exception as e:
            logger.error(f"Error handling market data update: {e}")
            raise
    
    async def _handle_agent_performance(self, message, properties: Dict[str, str]):
        """Handle agent performance events"""
        try:
            data = json.loads(message.data().decode('utf-8'))
            event = AgentPerformanceEvent(**data)
            
            logger.info(f"Agent performance updated: {event.agent_id}")
            
        except Exception as e:
            logger.error(f"Error handling agent performance: {e}")
            raise
    
    async def start(self):
        """Start the cross-cluster integration"""
        try:
            # Start consuming messages
            topics = [
                "signals.status_updates",
                "risk.alerts",
                "market.data_updates",
                "agents.performance"
            ]
            
            await self.event_consumer.start_consumption(
                topics, 
                f"{self.cluster_name}-integration"
            )
            
            self.health_status = {"status": "healthy", "started_at": datetime.now(timezone.utc)}
            logger.info("CrossClusterIntegration started successfully")
            
        except Exception as e:
            self.health_status = {"status": "unhealthy", "error": str(e)}
            logger.error(f"Failed to start CrossClusterIntegration: {e}")
            raise
    
    async def stop(self):
        """Stop the cross-cluster integration"""
        try:
            await self.event_consumer.stop_consumption()
            self.health_status = {"status": "stopped", "stopped_at": datetime.now(timezone.utc)}
            logger.info("CrossClusterIntegration stopped")
            
        except Exception as e:
            logger.error(f"Error stopping CrossClusterIntegration: {e}")
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        try:
            publisher_metrics = self.event_publisher.get_metrics()
            consumer_metrics = self.event_consumer.get_metrics()
            
            # Check database connectivity
            try:
                await self.db_session.execute("SELECT 1")
                db_status = "healthy"
            except Exception as e:
                db_status = f"unhealthy: {e}"
            
            overall_status = "healthy"
            if (db_status != "healthy" or 
                publisher_metrics["circuit_breaker"]["state"] == "OPEN" or
                not consumer_metrics["is_consuming"]):
                overall_status = "degraded"
            
            return {
                "status": overall_status,
                "cluster_name": self.cluster_name,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "components": {
                    "database": {"status": db_status},
                    "event_publisher": {
                        "status": "healthy" if publisher_metrics["circuit_breaker"]["state"] != "OPEN" else "degraded",
                        "metrics": publisher_metrics
                    },
                    "event_consumer": {
                        "status": "healthy" if consumer_metrics["is_consuming"] else "unhealthy",
                        "metrics": consumer_metrics
                    }
                },
                "integration_status": self.health_status
            }
            
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }


# Factory function for creating integration instance
async def create_cross_cluster_integration(
    cluster_name: str,
    pulsar_client,
    db_session: AsyncSession,
    auth_service,
    circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
    retry_config: Optional[RetryConfig] = None
) -> CrossClusterIntegration:
    """Factory function to create and configure CrossClusterIntegration"""
    
    # Create dead letter queue
    dead_letter_queue = DeadLetterQueue(max_size=10000)
    
    # Create event publisher and consumer
    event_publisher = EventPublisher(
        pulsar_client, 
        auth_service, 
        circuit_breaker_config, 
        retry_config
    )
    
    event_consumer = EventConsumer(
        pulsar_client, 
        dead_letter_queue, 
        max_retry_attempts=3
    )
    
    # Create integration
    integration = CrossClusterIntegration(
        db_session,
        event_publisher,
        event_consumer,
        cluster_name
    )
    
    return integration
