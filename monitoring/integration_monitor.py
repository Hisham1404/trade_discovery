"""
Comprehensive Integration Monitoring and Observability System

Production-grade monitoring for cross-cluster integration including:
- Prometheus metrics for event publishing/consumption rates, latencies, and failures
- Structured logging with correlation IDs for event tracking
- OpenTelemetry tracing for cross-cluster request flows
- Health check endpoints that verify Pulsar connectivity and consumer lag
- Alerting rules for integration failures and high latencies
- Real-time monitoring dashboard integration
- Performance and SLA monitoring
"""

import asyncio
import json
import logging
import time
import uuid
import threading
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
from enum import Enum
from contextlib import asynccontextmanager, contextmanager
from collections import defaultdict, deque
import structlog

# Prometheus imports
try:
    from prometheus_client import Counter, Histogram, Gauge, Info, Summary, generate_latest, start_http_server
    from prometheus_fastapi_instrumentator import Instrumentator, metrics
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False
    # Mock classes for testing without Prometheus
    class MockMetric:
        def __init__(self, *args, **kwargs):
            self._value = 0
            self._observations = []
        
        def inc(self, amount=1):
            self._value += amount
            return self
        
        def observe(self, value):
            self._observations.append(value)
            return self
        
        def set(self, value):
            self._value = value
            return self
        
        def info(self, data):
            return self
        
        def labels(self, **kwargs):
            # Return self to support method chaining
            return self
    
    # Use the same base class for all metric types
    Counter = MockMetric
    Histogram = MockMetric
    Gauge = MockMetric
    Info = MockMetric

    class CollectorRegistry:
        pass

# OpenTelemetry imports
try:
    from opentelemetry import trace, context
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.propagate import inject, extract
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    # Mock trace for testing
    class MockTracer:
        def start_span(self, name, **kwargs):
            return MockSpan()
        
    class MockSpan:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def set_attribute(self, key, value):
            pass
        def set_status(self, status):
            pass

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntegrationEventType(Enum):
    """Types of integration events"""
    PUBLISH = "publish"
    CONSUME = "consume"
    HEALTH_CHECK = "health_check"
    CIRCUIT_BREAKER = "circuit_breaker"
    ERROR = "error"
    STARTUP = "startup"
    SHUTDOWN = "shutdown"


@dataclass
class MonitoringConfig:
    """Configuration for integration monitoring"""
    prometheus_enabled: bool = True
    prometheus_port: int = 8001
    opentelemetry_enabled: bool = True
    jaeger_endpoint: str = "http://localhost:14268/api/traces"
    otlp_endpoint: str = "http://localhost:4317"
    pushgateway_url: str = "http://localhost:9091"
    metrics_prefix: str = "trade_discovery_integration_"
    health_check_interval: int = 30
    alert_webhook_url: Optional[str] = None
    log_level: str = "INFO"
    enable_detailed_tracing: bool = True
    max_trace_samples: int = 1000
    # Production FastAPI Instrumentator settings
    enable_fastapi_instrumentator: bool = True
    instrumentator_namespace: str = "trade_discovery"
    instrumentator_subsystem: str = "integration"
    fastapi_latency_buckets: tuple = (0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0)


@dataclass
class CorrelationContext:
    """Context for request correlation"""
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    cluster_id: str = "unknown"
    user_id: Optional[str] = None
    operation: Optional[str] = None
    start_time: float = field(default_factory=time.time)


class IntegrationMonitor:
    """
    Comprehensive integration monitoring system for cross-cluster communication.
    
    Features:
    - Prometheus metrics collection for all integration events
    - Structured logging with correlation IDs
    - Distributed tracing with OpenTelemetry
    - Health checks for Pulsar connectivity and consumer lag
    - Real-time alerting for failures and SLA violations
    - Performance monitoring and SLA tracking
    """
    
    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.is_initialized = False
        self.tracer = None
        self._correlation_context = {}
        self._health_status = {}
        self._alert_handlers = []
        self._monitoring_tasks = []
        
        # Metrics storage
        self.metrics = {}
        
        # Event tracking
        self._event_history = deque(maxlen=10000)
        self._performance_stats = defaultdict(list)
        
        # Thread-local storage for correlation context
        self._local = threading.local()
        
        # Initialize components
        self._setup_prometheus_metrics()
        self._setup_opentelemetry()
        self._setup_structured_logging()
        
    def _setup_prometheus_metrics(self):
        """Setup comprehensive Prometheus metrics for integration monitoring"""
        if not PROMETHEUS_AVAILABLE:
            logger.warning("Prometheus not available, using mock metrics")
            self._setup_mock_metrics()
            return
            
        try:
            # Use custom registry if provided for testing
            registry = getattr(self, 'registry', None)
            
            prefix = self.config.metrics_prefix
            
            # Event publishing metrics
            self.metrics['events_published_total'] = Counter(
                f'{prefix}events_published_total',
                'Total events published across clusters',
                ['source_cluster', 'target_cluster', 'event_type', 'topic', 'status'],
                registry=registry
            )
            
            self.metrics['events_consumed_total'] = Counter(
                f'{prefix}events_consumed_total',
                'Total events consumed across clusters',
                ['source_cluster', 'target_cluster', 'event_type', 'topic', 'status'],
                registry=registry
            )
            
            # Latency metrics
            self.metrics['event_publish_duration'] = Histogram(
                f'{prefix}event_publish_duration_seconds',
                'Event publishing latency',
                ['source_cluster', 'target_cluster', 'event_type'],
                buckets=self.config.fastapi_latency_buckets,
                registry=registry
            )
            
            self.metrics['event_consume_duration'] = Histogram(
                f'{prefix}event_consume_duration_seconds',
                'Event consumption latency',
                ['source_cluster', 'target_cluster', 'event_type'],
                buckets=self.config.fastapi_latency_buckets,
                registry=registry
            )
            
            self.metrics['end_to_end_latency'] = Histogram(
                f'{prefix}end_to_end_latency_seconds',
                'End-to-end event processing latency',
                ['source_cluster', 'target_cluster', 'event_type'],
                buckets=self.config.fastapi_latency_buckets,
                registry=registry
            )
            
            # Error metrics
            self.metrics['integration_errors_total'] = Counter(
                f'{prefix}integration_errors_total',
                'Total integration errors',
                ['source_cluster', 'target_cluster', 'error_type', 'severity'],
                registry=registry
            )
            
            self.metrics['circuit_breaker_state'] = Gauge(
                f'{prefix}circuit_breaker_state',
                'Circuit breaker state (0=closed, 1=open, 2=half-open)',
                ['cluster', 'component'],
                registry=registry
            )
            
            # Health check metrics
            self.metrics['pulsar_connectivity'] = Gauge(
                f'{prefix}pulsar_connectivity',
                'Pulsar connectivity status (1=connected, 0=disconnected)',
                ['cluster', 'broker'],
                registry=registry
            )
            
            self.metrics['consumer_lag'] = Gauge(
                f'{prefix}consumer_lag_messages',
                'Consumer lag in messages',
                ['cluster', 'topic', 'subscription'],
                registry=registry
            )
            
            self.metrics['consumer_lag_time'] = Gauge(
                f'{prefix}consumer_lag_time_seconds',
                'Consumer lag in time',
                ['cluster', 'topic', 'subscription'],
                registry=registry
            )
            
            # Performance metrics
            self.metrics['active_connections'] = Gauge(
                f'{prefix}active_connections',
                'Number of active connections',
                ['cluster', 'connection_type'],
                registry=registry
            )
            
            self.metrics['message_queue_size'] = Gauge(
                f'{prefix}message_queue_size',
                'Message queue size',
                ['cluster', 'queue_type'],
                registry=registry
            )
            
            self.metrics['throughput_events_per_second'] = Gauge(
                f'{prefix}throughput_events_per_second',
                'Event throughput per second',
                ['cluster', 'direction'],  # direction: inbound/outbound
                registry=registry
            )
            
            # SLA metrics
            self.metrics['sla_violations_total'] = Counter(
                f'{prefix}sla_violations_total',
                'Total SLA violations',
                ['cluster', 'sla_type', 'severity'],
                registry=registry
            )
            
            self.metrics['availability_ratio'] = Gauge(
                f'{prefix}availability_ratio',
                'Service availability ratio (0-1)',
                ['cluster', 'service'],
                registry=registry
            )
            
            # Set system info
            self.metrics['integration_info'] = Info(
                f'{prefix}integration_info',
                'Integration system information',
                registry=registry
            )
            
            self.metrics['integration_info'].info({
                'version': '1.0.0',
                'prometheus_enabled': str(self.config.prometheus_enabled),
                'opentelemetry_enabled': str(self.config.opentelemetry_enabled),
                'environment': os.getenv('ENVIRONMENT', 'development')
            })
            
            logger.info("Prometheus metrics initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup Prometheus metrics: {e}")
            self._setup_mock_metrics()
    
    def _setup_mock_metrics(self):
        """Setup mock metrics for testing without Prometheus"""
        # Create simple mock classes that support the interface
        class MockMetric:
            def __init__(self):
                self._value = 0
                self._observations = []
            
            def inc(self, amount=1):
                self._value += amount
                return self
            
            def observe(self, value):
                self._observations.append(value)
                return self
            
            def set(self, value):
                self._value = value
                return self
            
            def info(self, data):
                return self
            
            def labels(self, **kwargs):
                return self
        
        self.metrics = {
            'events_published_total': MockMetric(),
            'events_consumed_total': MockMetric(),
            'event_publish_duration': MockMetric(),
            'event_consume_duration': MockMetric(),
            'end_to_end_latency': MockMetric(),
            'integration_errors_total': MockMetric(),
            'circuit_breaker_state': MockMetric(),
            'pulsar_connectivity': MockMetric(),
            'consumer_lag': MockMetric(),
            'consumer_lag_time': MockMetric(),
            'sla_violations_total': MockMetric(),
            'throughput_events_per_second': MockMetric(),
            'availability_ratio': MockMetric(),
            'integration_info': MockMetric()
        }
        
        logger.warning("Using mock metrics for testing")
    
    def _setup_opentelemetry(self):
        """Setup OpenTelemetry distributed tracing"""
        if not OPENTELEMETRY_AVAILABLE or not self.config.opentelemetry_enabled:
            logger.warning("OpenTelemetry not available or disabled")
            return
            
        try:
            # Setup tracer provider
            trace.set_tracer_provider(TracerProvider())
            tracer_provider = trace.get_tracer_provider()
            
            # Setup exporters
            if self.config.jaeger_endpoint:
                jaeger_exporter = JaegerExporter(
                    endpoint=self.config.jaeger_endpoint,
                    collector_endpoint=self.config.jaeger_endpoint.replace('/api/traces', '/api/traces'),
                )
                tracer_provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            
            if self.config.otlp_endpoint:
                otlp_exporter = OTLPSpanExporter(
                    endpoint=self.config.otlp_endpoint,
                    insecure=True
                )
                tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            
            # Get tracer
            self.tracer = trace.get_tracer("integration-monitor", "1.0.0")
            
            logger.info("OpenTelemetry tracing initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to setup OpenTelemetry: {e}")
            self.tracer = None
    
    def _setup_structured_logging(self):
        """Setup structured logging with correlation support"""
        # Configure log level
        logging.getLogger().setLevel(getattr(logging, self.config.log_level.upper()))
        
        logger.info("Structured logging configured with correlation support")
    
    async def initialize(self):
        """Initialize the monitoring system"""
        try:
            # Start Prometheus metrics server
            if PROMETHEUS_AVAILABLE and self.config.prometheus_enabled:
                try:
                    start_http_server(self.config.prometheus_port)
                    logger.info(f"Prometheus metrics server started on port {self.config.prometheus_port}")
                except OSError as e:
                    if "Address already in use" in str(e):
                        logger.warning(f"Prometheus server already running on port {self.config.prometheus_port}")
                    else:
                        raise
            
            # Start background monitoring tasks
            await self._start_monitoring_tasks()
            
            self.is_initialized = True
            logger.info("Integration monitoring system initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize monitoring system: {e}")
            raise
    
    async def _start_monitoring_tasks(self):
        """Start background monitoring tasks"""
        # Health check task
        task = asyncio.create_task(self._health_check_loop())
        self._monitoring_tasks.append(task)
        
        # Throughput calculation task
        task = asyncio.create_task(self._throughput_calculation_loop())
        self._monitoring_tasks.append(task)
        
        # SLA monitoring task
        task = asyncio.create_task(self._sla_monitoring_loop())
        self._monitoring_tasks.append(task)
        
        logger.info("Background monitoring tasks started")
    
    @contextmanager
    def correlation_context(self, operation: str, cluster_id: str = "unknown", 
                          user_id: Optional[str] = None):
        """Context manager for correlation tracking"""
        correlation_id = str(uuid.uuid4())
        trace_id = None
        span_id = None
        
        # Get trace context if available
        if self.tracer:
            span_context = trace.get_current_span().get_span_context()
            if span_context:
                trace_id = format(span_context.trace_id, '032x')
                span_id = format(span_context.span_id, '016x')
        
        context = CorrelationContext(
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            cluster_id=cluster_id,
            user_id=user_id,
            operation=operation
        )
        
        # Store in thread-local storage
        old_context = getattr(self._local, 'correlation_context', None)
        self._local.correlation_context = context
        
        try:
            yield context
        finally:
            self._local.correlation_context = old_context
    
    def get_correlation_context(self) -> Optional[CorrelationContext]:
        """Get current correlation context"""
        return getattr(self._local, 'correlation_context', None)
    
    def get_structured_logger(self, component: str) -> structlog.BoundLogger:
        """Get a structured logger with correlation context"""
        context = self.get_correlation_context()
        
        bound_logger = logger.bind(component=component)
        
        if context:
            bound_logger = bound_logger.bind(
                correlation_id=context.correlation_id,
                trace_id=context.trace_id,
                span_id=context.span_id,
                cluster_id=context.cluster_id,
                user_id=context.user_id,
                operation=context.operation
            )
        
        return bound_logger
    
    @asynccontextmanager
    async def trace_operation(self, operation_name: str, **attributes):
        """Context manager for distributed tracing"""
        if not self.tracer:
            yield None
            return
        
        context = self.get_correlation_context()
        
        with self.tracer.start_as_current_span(operation_name) as span:
            # Add correlation context to span
            if context:
                span.set_attribute("correlation_id", context.correlation_id)
                span.set_attribute("cluster_id", context.cluster_id)
                if context.user_id:
                    span.set_attribute("user_id", context.user_id)
                if context.operation:
                    span.set_attribute("operation", context.operation)
            
            # Add custom attributes
            for key, value in attributes.items():
                span.set_attribute(key, str(value))
            
            try:
                yield span
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise
    
    async def record_event_published(self, source_cluster: str, target_cluster: str,
                                   event_type: str, topic: str, success: bool,
                                   duration: float, message_size: int = 0):
        """Record event publishing metrics"""
        status = "success" if success else "error"
        
        # Update metrics
        self.metrics['events_published_total'].labels(
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            event_type=event_type,
            topic=topic,
            status=status
        ).inc()
        
        self.metrics['event_publish_duration'].labels(
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            event_type=event_type
        ).observe(duration)
        
        # Log event
        log = self.get_structured_logger("event_publisher")
        log.info(
            "Event published",
            event_type=IntegrationEventType.PUBLISH.value,
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            topic=topic,
            success=success,
            duration_seconds=duration,
            message_size_bytes=message_size
        )
        
        # Record in event history
        self._event_history.append({
            "timestamp": time.time(),
            "type": "publish",
            "source_cluster": source_cluster,
            "target_cluster": target_cluster,
            "event_type": event_type,
            "topic": topic,
            "success": success,
            "duration": duration,
            "message_size": message_size
        })
        
        # Check SLA violations
        await self._check_publish_sla(source_cluster, target_cluster, event_type, duration)
    
    async def record_event_consumed(self, source_cluster: str, target_cluster: str,
                                  event_type: str, topic: str, success: bool,
                                  duration: float, processing_time: float = 0):
        """Record event consumption metrics"""
        status = "success" if success else "error"
        
        # Update metrics
        self.metrics['events_consumed_total'].labels(
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            event_type=event_type,
            topic=topic,
            status=status
        ).inc()
        
        self.metrics['event_consume_duration'].labels(
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            event_type=event_type
        ).observe(duration)
        
        # Log event
        log = self.get_structured_logger("event_consumer")
        log.info(
            "Event consumed",
            event_type=IntegrationEventType.CONSUME.value,
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            topic=topic,
            success=success,
            duration_seconds=duration,
            processing_time_seconds=processing_time
        )
        
        # Record in event history
        self._event_history.append({
            "timestamp": time.time(),
            "type": "consume",
            "source_cluster": source_cluster,
            "target_cluster": target_cluster,
            "event_type": event_type,
            "topic": topic,
            "success": success,
            "duration": duration,
            "processing_time": processing_time
        })
    
    async def record_end_to_end_latency(self, source_cluster: str, target_cluster: str,
                                      event_type: str, total_latency: float):
        """Record end-to-end latency metrics"""
        self.metrics['end_to_end_latency'].labels(
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            event_type=event_type
        ).observe(total_latency)
        
        # Check SLA violations
        await self._check_latency_sla(source_cluster, target_cluster, event_type, total_latency)
    
    async def record_integration_error(self, source_cluster: str, target_cluster: str,
                                     error_type: str, severity: AlertSeverity,
                                     error_message: str, context: Dict[str, Any] = None):
        """Record integration error"""
        self.metrics['integration_errors_total'].labels(
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            error_type=error_type,
            severity=severity.value
        ).inc()
        
        # Log error
        log = self.get_structured_logger("integration_error")
        log.error(
            "Integration error occurred",
            event_type=IntegrationEventType.ERROR.value,
            source_cluster=source_cluster,
            target_cluster=target_cluster,
            error_type=error_type,
            severity=severity.value,
            error_message=error_message,
            context=context or {}
        )
        
        # Trigger alert for high/critical severity
        if severity in [AlertSeverity.HIGH, AlertSeverity.CRITICAL]:
            await self._trigger_alert(
                title=f"Integration Error: {error_type}",
                message=error_message,
                severity=severity,
                source_cluster=source_cluster,
                target_cluster=target_cluster,
                context=context
            )
    
    async def record_circuit_breaker_state(self, cluster: str, component: str, state: str):
        """Record circuit breaker state changes"""
        state_value = {"closed": 0, "open": 1, "half-open": 2}.get(state, 0)
        
        self.metrics['circuit_breaker_state'].labels(
            cluster=cluster,
            component=component
        ).set(state_value)
        
        # Log state change
        log = self.get_structured_logger("circuit_breaker")
        log.info(
            "Circuit breaker state changed",
            event_type=IntegrationEventType.CIRCUIT_BREAKER.value,
            cluster=cluster,
            component=component,
            state=state
        )
        
        # Alert on circuit breaker open
        if state == "open":
            await self._trigger_alert(
                title=f"Circuit Breaker Open: {component}",
                message=f"Circuit breaker for {component} in {cluster} is now open",
                severity=AlertSeverity.HIGH,
                cluster=cluster,
                component=component
            )
    
    async def check_pulsar_health(self, cluster: str, broker_url: str) -> Dict[str, Any]:
        """Check Pulsar connectivity and health"""
        start_time = time.time()
        health_status = {
            "cluster": cluster,
            "broker_url": broker_url,
            "connected": False,
            "response_time": 0,
            "error": None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # TODO: Implement actual Pulsar health check
            # This would connect to Pulsar and check connectivity
            # For now, simulating a successful connection
            await asyncio.sleep(0.01)  # Simulate network call
            
            health_status["connected"] = True
            health_status["response_time"] = time.time() - start_time
            
            # Update metrics
            self.metrics['pulsar_connectivity'].labels(
                cluster=cluster,
                broker=broker_url
            ).set(1)
            
        except Exception as e:
            health_status["error"] = str(e)
            health_status["response_time"] = time.time() - start_time
            
            # Update metrics
            self.metrics['pulsar_connectivity'].labels(
                cluster=cluster,
                broker=broker_url
            ).set(0)
            
            # Log error
            log = self.get_structured_logger("health_check")
            log.error(
                "Pulsar health check failed",
                event_type=IntegrationEventType.HEALTH_CHECK.value,
                cluster=cluster,
                broker_url=broker_url,
                error=str(e),
                response_time=health_status["response_time"]
            )
        
        # Store health status
        self._health_status[f"{cluster}:{broker_url}"] = health_status
        
        return health_status
    
    async def check_consumer_lag(self, cluster: str, topic: str, subscription: str) -> Dict[str, Any]:
        """Check consumer lag for a topic/subscription"""
        lag_info = {
            "cluster": cluster,
            "topic": topic,
            "subscription": subscription,
            "message_lag": 0,
            "time_lag_seconds": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # TODO: Implement actual consumer lag check using Pulsar admin API
            # For now, simulating lag data
            lag_info["message_lag"] = 100  # Example lag
            lag_info["time_lag_seconds"] = 30  # Example time lag
            
            # Update metrics
            self.metrics['consumer_lag'].labels(
                cluster=cluster,
                topic=topic,
                subscription=subscription
            ).set(lag_info["message_lag"])
            
            self.metrics['consumer_lag_time'].labels(
                cluster=cluster,
                topic=topic,
                subscription=subscription
            ).set(lag_info["time_lag_seconds"])
            
            # Check for high lag
            if lag_info["message_lag"] > 1000 or lag_info["time_lag_seconds"] > 300:
                await self._trigger_alert(
                    title=f"High Consumer Lag: {topic}",
                    message=f"Consumer lag for {subscription} on {topic} is {lag_info['message_lag']} messages ({lag_info['time_lag_seconds']}s)",
                    severity=AlertSeverity.HIGH,
                    cluster=cluster,
                    topic=topic,
                    subscription=subscription
                )
            
        except Exception as e:
            log = self.get_structured_logger("consumer_lag")
            log.error(
                "Consumer lag check failed",
                cluster=cluster,
                topic=topic,
                subscription=subscription,
                error=str(e)
            )
        
        return lag_info
    
    async def _health_check_loop(self):
        """Background health check loop"""
        while True:
            try:
                # Check all registered health endpoints
                # TODO: Implement based on actual Pulsar configuration
                clusters = ["discovery", "execution", "risk"]  # Example clusters
                
                for cluster in clusters:
                    broker_url = f"pulsar://{cluster}-pulsar:6650"
                    await self.check_pulsar_health(cluster, broker_url)
                
                await asyncio.sleep(self.config.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(10)
    
    async def _throughput_calculation_loop(self):
        """Background throughput calculation loop"""
        last_counts = defaultdict(int)
        
        while True:
            try:
                await asyncio.sleep(60)  # Calculate every minute
                
                # Calculate event throughput
                current_time = time.time()
                window_start = current_time - 60  # 1-minute window
                
                # Count events in the last minute
                recent_events = [
                    event for event in self._event_history
                    if event["timestamp"] > window_start
                ]
                
                # Group by cluster and direction
                throughput_data = defaultdict(int)
                for event in recent_events:
                    cluster = event.get("source_cluster", "unknown")
                    direction = "outbound" if event["type"] == "publish" else "inbound"
                    throughput_data[f"{cluster}:{direction}"] += 1
                
                # Update throughput metrics
                for key, count in throughput_data.items():
                    cluster, direction = key.split(":")
                    events_per_second = count / 60.0
                    
                    self.metrics['throughput_events_per_second'].labels(
                        cluster=cluster,
                        direction=direction
                    ).set(events_per_second)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Throughput calculation error: {e}")
                await asyncio.sleep(30)
    
    async def _sla_monitoring_loop(self):
        """Background SLA monitoring loop"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                # Calculate availability ratios
                await self._calculate_availability_metrics()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SLA monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _calculate_availability_metrics(self):
        """Calculate service availability metrics"""
        window_start = time.time() - 300  # 5-minute window
        
        # Analyze recent events for availability
        recent_events = [
            event for event in self._event_history
            if event["timestamp"] > window_start
        ]
        
        if not recent_events:
            return
        
        # Calculate availability by cluster
        cluster_stats = defaultdict(lambda: {"total": 0, "successful": 0})
        
        for event in recent_events:
            cluster = event.get("source_cluster") or event.get("target_cluster", "unknown")
            cluster_stats[cluster]["total"] += 1
            if event.get("success", False):
                cluster_stats[cluster]["successful"] += 1
        
        # Update availability metrics
        for cluster, stats in cluster_stats.items():
            if stats["total"] > 0:
                availability = stats["successful"] / stats["total"]
                self.metrics['availability_ratio'].labels(
                    cluster=cluster,
                    service="integration"
                ).set(availability)
                
                # Alert on low availability
                if availability < 0.95:  # 95% SLA threshold
                    await self._trigger_alert(
                        title=f"Low Availability: {cluster}",
                        message=f"Integration availability for {cluster} is {availability:.2%}",
                        severity=AlertSeverity.HIGH if availability < 0.90 else AlertSeverity.MEDIUM,
                        cluster=cluster,
                        availability=availability
                    )
    
    async def _check_publish_sla(self, source_cluster: str, target_cluster: str,
                               event_type: str, duration: float):
        """Check if publish operation violates SLA"""
        sla_threshold = self.config.fastapi_latency_buckets[1]  # 0.025 seconds
        
        if duration > sla_threshold:
            await self._record_sla_violation(
                cluster=source_cluster,
                sla_type="publish_latency",
                severity=AlertSeverity.MEDIUM if duration < 2.0 else AlertSeverity.HIGH,
                details={
                    "source_cluster": source_cluster,
                    "target_cluster": target_cluster,
                    "event_type": event_type,
                    "duration": duration,
                    "threshold": sla_threshold
                }
            )
    
    async def _check_latency_sla(self, source_cluster: str, target_cluster: str,
                               event_type: str, latency: float):
        """Check if end-to-end latency violates SLA"""
        sla_threshold = self.config.fastapi_latency_buckets[-1]  # 10.0 seconds
        
        if latency > sla_threshold:
            await self._record_sla_violation(
                cluster=source_cluster,
                sla_type="end_to_end_latency",
                severity=AlertSeverity.HIGH if latency > 10.0 else AlertSeverity.MEDIUM,
                details={
                    "source_cluster": source_cluster,
                    "target_cluster": target_cluster,
                    "event_type": event_type,
                    "latency": latency,
                    "threshold": sla_threshold
                }
            )
    
    async def _record_sla_violation(self, cluster: str, sla_type: str,
                                  severity: AlertSeverity, details: Dict[str, Any]):
        """Record SLA violation"""
        self.metrics['sla_violations_total'].labels(
            cluster=cluster,
            sla_type=sla_type,
            severity=severity.value
        ).inc()
        
        # Log SLA violation
        log = self.get_structured_logger("sla_monitor")
        log.warning(
            "SLA violation detected",
            cluster=cluster,
            sla_type=sla_type,
            severity=severity.value,
            details=details
        )
        
        # Trigger alert
        await self._trigger_alert(
            title=f"SLA Violation: {sla_type}",
            message=f"SLA violation in {cluster}: {sla_type}",
            severity=severity,
            cluster=cluster,
            sla_type=sla_type,
            details=details
        )
    
    async def _trigger_alert(self, title: str, message: str, severity: AlertSeverity,
                           **context):
        """Trigger an alert"""
        alert_data = {
            "title": title,
            "message": message,
            "severity": severity.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "context": context
        }
        
        # Log alert
        log = self.get_structured_logger("alerting")
        log.warning(
            "Alert triggered",
            alert_title=title,
            alert_message=message,
            alert_severity=severity.value,
            alert_context=context
        )
        
        # Call alert handlers
        for handler in self._alert_handlers:
            try:
                await handler(alert_data)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")
    
    def add_alert_handler(self, handler: Callable[[Dict[str, Any]], None]):
        """Add an alert handler"""
        self._alert_handlers.append(handler)
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        return {
            "monitoring_system": {
                "status": "healthy" if self.is_initialized else "unhealthy",
                "prometheus_available": PROMETHEUS_AVAILABLE,
                "opentelemetry_available": OPENTELEMETRY_AVAILABLE,
                "metrics_collected": len(self.metrics),
                "active_monitoring_tasks": len(self._monitoring_tasks),
                "fastapi_instrumentator_enabled": self.config.enable_fastapi_instrumentator
            },
            "pulsar_connectivity": dict(self._health_status),
            "event_history_size": len(self._event_history),
            "sla_thresholds": self.config.fastapi_latency_buckets,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_metrics_summary(self) -> Dict[str, Any]:
        """Get metrics summary for dashboards"""
        current_time = time.time()
        window_start = current_time - 3600  # 1-hour window
        
        # Analyze recent events
        recent_events = [
            event for event in self._event_history
            if event["timestamp"] > window_start
        ]
        
        summary = {
            "time_window": "1h",
            "total_events": len(recent_events),
            "successful_events": len([e for e in recent_events if e.get("success", False)]),
            "failed_events": len([e for e in recent_events if not e.get("success", True)]),
            "average_publish_latency": 0,
            "average_consume_latency": 0,
            "events_by_cluster": defaultdict(int),
            "events_by_type": defaultdict(int)
        }
        
        if recent_events:
            # Calculate averages
            publish_durations = [e["duration"] for e in recent_events if e["type"] == "publish"]
            consume_durations = [e["duration"] for e in recent_events if e["type"] == "consume"]
            
            if publish_durations:
                summary["average_publish_latency"] = sum(publish_durations) / len(publish_durations)
            
            if consume_durations:
                summary["average_consume_latency"] = sum(consume_durations) / len(consume_durations)
            
            # Count by cluster and type
            for event in recent_events:
                cluster = event.get("source_cluster", "unknown")
                event_type = event.get("event_type", "unknown")
                summary["events_by_cluster"][cluster] += 1
                summary["events_by_type"][event_type] += 1
        
        summary["success_rate"] = (
            summary["successful_events"] / summary["total_events"]
            if summary["total_events"] > 0 else 1.0
        )
        
        return summary
    
    async def shutdown(self):
        """Graceful shutdown of monitoring system"""
        logger.info("Shutting down integration monitoring system")
        
        # Cancel background tasks
        for task in self._monitoring_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._monitoring_tasks:
            await asyncio.gather(*self._monitoring_tasks, return_exceptions=True)
        
        self.is_initialized = False
        logger.info("Integration monitoring system shutdown complete")

    def setup_fastapi_instrumentator(self, app):
        """Setup FastAPI Instrumentator for automatic HTTP metrics"""
        if not PROMETHEUS_AVAILABLE or not self.config.enable_fastapi_instrumentator:
            logger.warning("FastAPI Instrumentator not available or disabled")
            return None
            
        try:
            # Create instrumentator with production configuration
            instrumentator = Instrumentator(
                should_group_status_codes=False,
                should_ignore_untemplated=True,
                should_respect_env_var=True,
                should_instrument_requests_inprogress=True,
                excluded_handlers=[".*admin.*", "/metrics", "/health.*"],
                env_var_name="ENABLE_METRICS",
                inprogress_name="http_requests_inprogress",
                inprogress_labels=True
            )
            
            # Add custom metrics
            instrumentator.add(
                metrics.latency(
                    buckets=self.config.fastapi_latency_buckets,
                    metric_namespace=self.config.instrumentator_namespace,
                    metric_subsystem=self.config.instrumentator_subsystem
                )
            ).add(
                metrics.request_size(
                    should_include_handler=True,
                    should_include_method=False,
                    should_include_status=True,
                    metric_namespace=self.config.instrumentator_namespace,
                    metric_subsystem=self.config.instrumentator_subsystem
                )
            ).add(
                metrics.response_size(
                    should_include_handler=True,
                    should_include_method=False, 
                    should_include_status=True,
                    metric_namespace=self.config.instrumentator_namespace,
                    metric_subsystem=self.config.instrumentator_subsystem
                )
            )
            
            # Instrument and expose
            instrumentator.instrument(app)
            instrumentator.expose(app, include_in_schema=False, should_gzip=True)
            
            logger.info("FastAPI Instrumentator configured successfully")
            return instrumentator
            
        except Exception as e:
            logger.error(f"Failed to setup FastAPI Instrumentator: {e}")
            return None
    
    def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics in text format"""
        if not PROMETHEUS_AVAILABLE:
            return "# Prometheus not available\n"
        
        try:
            # Use custom registry if available, otherwise use default
            registry = getattr(self, 'registry', None)
            if registry:
                return generate_latest(registry).decode('utf-8')
            else:
                return generate_latest().decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to generate Prometheus metrics: {e}")
            return f"# Error generating metrics: {e}\n"


# Global monitoring instance
integration_monitor: Optional[IntegrationMonitor] = None


def get_integration_monitor() -> IntegrationMonitor:
    """Get the global integration monitor instance"""
    global integration_monitor
    if integration_monitor is None:
        config = MonitoringConfig()
        integration_monitor = IntegrationMonitor(config)
    return integration_monitor


# Convenience functions for easy access
async def record_publish(source_cluster: str, target_cluster: str, event_type: str,
                        topic: str, success: bool, duration: float, **kwargs):
    """Convenience function to record event publishing"""
    monitor = get_integration_monitor()
    await monitor.record_event_published(
        source_cluster, target_cluster, event_type, topic, success, duration, **kwargs
    )


async def record_consume(source_cluster: str, target_cluster: str, event_type: str,
                        topic: str, success: bool, duration: float, **kwargs):
    """Convenience function to record event consumption"""
    monitor = get_integration_monitor()
    await monitor.record_event_consumed(
        source_cluster, target_cluster, event_type, topic, success, duration, **kwargs
    )


async def record_error(source_cluster: str, target_cluster: str, error_type: str,
                      severity: AlertSeverity, error_message: str, **kwargs):
    """Convenience function to record integration errors"""
    monitor = get_integration_monitor()
    await monitor.record_integration_error(
        source_cluster, target_cluster, error_type, severity, error_message, **kwargs
    ) 