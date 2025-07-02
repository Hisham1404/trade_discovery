"""
OpenTelemetry Instrumentation and Tracing Configuration

This module sets up comprehensive distributed tracing for the trade discovery platform
using OpenTelemetry with support for:
- FastAPI automatic instrumentation
- SQLAlchemy database operation tracing
- Redis cache operation tracing
- Custom spans for agent execution and signal generation
- OTLP and Jaeger exporters
- Trace sampling strategies
- Contextual attributes for enhanced observability
"""

import os
import logging
from typing import Optional, Dict, Any, Callable
from contextlib import contextmanager
from functools import wraps
import time
import asyncio

from opentelemetry import trace, baggage
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.propagate import set_global_textmap
from opentelemetry.trace import Status, StatusCode, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.sdk.trace.sampling import (
    TraceIdRatioBased,
    ParentBasedTraceIdRatio,
    ALWAYS_ON,
    ALWAYS_OFF,
)

logger = logging.getLogger(__name__)

# Global tracer instance
tracer: Optional[trace.Tracer] = None

# Configuration constants
SERVICE_NAME_VALUE = "trade-discovery-platform"
SERVICE_VERSION_VALUE = "1.0.0"
JAEGER_ENDPOINT = os.getenv("JAEGER_ENDPOINT", "http://localhost:14268/api/traces")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")
TRACE_SAMPLE_RATE = float(os.getenv("TRACE_SAMPLE_RATE", "0.1"))  # 10% sampling by default
ENABLE_CONSOLE_EXPORT = os.getenv("ENABLE_CONSOLE_EXPORT", "false").lower() == "true"

class TraceConfig:
    """Configuration class for OpenTelemetry tracing"""
    
    def __init__(
        self,
        service_name: str = SERVICE_NAME_VALUE,
        service_version: str = SERVICE_VERSION_VALUE,
        jaeger_endpoint: str = JAEGER_ENDPOINT,
        otlp_endpoint: str = OTLP_ENDPOINT,
        sample_rate: float = TRACE_SAMPLE_RATE,
        enable_console: bool = ENABLE_CONSOLE_EXPORT,
    ):
        self.service_name = service_name
        self.service_version = service_version
        self.jaeger_endpoint = jaeger_endpoint
        self.otlp_endpoint = otlp_endpoint
        self.sample_rate = sample_rate
        self.enable_console = enable_console


def setup_tracing(config: Optional[TraceConfig] = None) -> None:
    """
    Initialize OpenTelemetry tracing with comprehensive instrumentation
    
    Args:
        config: Optional TraceConfig instance. Uses defaults if None.
    """
    global tracer
    
    if config is None:
        config = TraceConfig()
    
    logger.info(f"Setting up OpenTelemetry tracing for service: {config.service_name}")
    
    # Create resource with service information
    resource = Resource.create({
        SERVICE_NAME: config.service_name,
        SERVICE_VERSION: config.service_version,
        "deployment.environment": os.getenv("ENVIRONMENT", "development"),
        "service.instance.id": os.getenv("POD_NAME", f"{config.service_name}-instance"),
        "telemetry.sdk.language": "python",
        "telemetry.sdk.name": "opentelemetry",
    })
    
    # Configure sampling strategy
    if config.sample_rate == 1.0:
        sampler = ALWAYS_ON
    elif config.sample_rate == 0.0:
        sampler = ALWAYS_OFF
    else:
        sampler = ParentBasedTraceIdRatio(config.sample_rate)
    
    # Create tracer provider
    trace_provider = TracerProvider(
        resource=resource,
        sampler=sampler
    )
    
    # Set up exporters
    exporters = []
    
    # OTLP Exporter (for OpenTelemetry Collector/Jaeger via OTLP)
    try:
        otlp_exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint)
        exporters.append(otlp_exporter)
        logger.info(f"OTLP exporter configured for endpoint: {config.otlp_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to configure OTLP exporter: {e}")
    
    # Jaeger Exporter (direct to Jaeger)
    try:
        jaeger_exporter = JaegerExporter(
            agent_host_name="localhost",
            agent_port=6831,
            collector_endpoint=config.jaeger_endpoint,
        )
        exporters.append(jaeger_exporter)
        logger.info(f"Jaeger exporter configured for endpoint: {config.jaeger_endpoint}")
    except Exception as e:
        logger.warning(f"Failed to configure Jaeger exporter: {e}")
    
    # Console Exporter (for debugging)
    if config.enable_console:
        console_exporter = ConsoleSpanExporter()
        exporters.append(console_exporter)
        logger.info("Console exporter enabled for debugging")
    
    # Add span processors for each exporter
    for exporter in exporters:
        span_processor = BatchSpanProcessor(
            exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            export_timeout_millis=30000,
            schedule_delay_millis=5000,
        )
        trace_provider.add_span_processor(span_processor)
    
    # Set the global tracer provider
    trace.set_tracer_provider(trace_provider)
    
    # Set up propagators for distributed tracing
    set_global_textmap(B3MultiFormat())
    
    # Initialize the global tracer
    tracer = trace.get_tracer(__name__)
    
    logger.info("OpenTelemetry tracing setup completed successfully")


def instrument_fastapi(app) -> bool:
    """
    Automatically instrument FastAPI application
    
    Args:
        app: FastAPI application instance
        
    Returns:
        True if instrumentation succeeded, False otherwise
    """
    try:
        FastAPIInstrumentor.instrument_app(
            app,
            tracer_provider=trace.get_tracer_provider(),
            excluded_urls="/health,/metrics,/docs,/redoc,/openapi.json",
            span_name_prefix="API",
        )
        logger.info("FastAPI auto-instrumentation enabled")
        return True
    except Exception as e:
        logger.error(f"Failed to instrument FastAPI: {e}")
        return False


def instrument_sqlalchemy(engine) -> bool:
    """
    Automatically instrument SQLAlchemy engine
    
    Args:
        engine: SQLAlchemy engine instance
        
    Returns:
        True if instrumentation succeeded, False otherwise
    """
    try:
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("SQLAlchemy auto-instrumentation enabled")
        return True
    except Exception as e:
        logger.error(f"Failed to instrument SQLAlchemy: {e}")
        return False


def instrument_redis() -> None:
    """Automatically instrument Redis connections"""
    try:
        RedisInstrumentor().instrument(
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("Redis auto-instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument Redis: {e}")


def instrument_httpx() -> None:
    """Automatically instrument HTTPX client"""
    try:
        HTTPXClientInstrumentor().instrument(
            tracer_provider=trace.get_tracer_provider(),
        )
        logger.info("HTTPX auto-instrumentation enabled")
    except Exception as e:
        logger.error(f"Failed to instrument HTTPX: {e}")


def setup_all_instrumentation(app, engine=None) -> None:
    """
    Set up all available instrumentations
    
    Args:
        app: FastAPI application instance
        engine: Optional SQLAlchemy engine instance
    """
    instrument_fastapi(app)
    if engine:
        instrument_sqlalchemy(engine)
    instrument_redis()
    instrument_httpx()


# Custom Span Creation Utilities

@contextmanager
def create_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Dict[str, Any]] = None,
    set_status_on_exception: bool = True,
):
    """
    Context manager for creating custom spans
    
    Args:
        name: Span name
        kind: Span kind (INTERNAL, SERVER, CLIENT, etc.)
        attributes: Optional attributes to add to the span
        set_status_on_exception: Whether to set error status on exceptions
    """
    if not tracer:
        yield None
        return
    
    with tracer.start_as_current_span(name, kind=kind) as span:
        try:
            if attributes:
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span
        except Exception as e:
            if set_status_on_exception:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
            raise


def trace_agent_execution(agent_name: str, signal_type: str = None):
    """
    Decorator for tracing agent execution
    
    Args:
        agent_name: Name of the agent being executed
        signal_type: Optional signal type being processed
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attributes = {
                "agent.name": agent_name,
                "agent.function": func.__name__,
                "agent.execution.start_time": time.time(),
            }
            if signal_type:
                attributes["signal.type"] = signal_type
            
            with create_span(
                f"agent.execution.{agent_name}",
                SpanKind.INTERNAL,
                attributes
            ) as span:
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    if span:
                        span.set_attribute("agent.execution.duration_ms", execution_time * 1000)
                        span.set_attribute("agent.execution.success", True)
                    return result
                except Exception as e:
                    execution_time = time.time() - start_time
                    if span:
                        span.set_attribute("agent.execution.duration_ms", execution_time * 1000)
                        span.set_attribute("agent.execution.success", False)
                        span.set_attribute("agent.error.type", type(e).__name__)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            attributes = {
                "agent.name": agent_name,
                "agent.function": func.__name__,
                "agent.execution.start_time": time.time(),
            }
            if signal_type:
                attributes["signal.type"] = signal_type
            
            with create_span(
                f"agent.execution.{agent_name}",
                SpanKind.INTERNAL,
                attributes
            ) as span:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    execution_time = time.time() - start_time
                    if span:
                        span.set_attribute("agent.execution.duration_ms", execution_time * 1000)
                        span.set_attribute("agent.execution.success", True)
                    return result
                except Exception as e:
                    execution_time = time.time() - start_time
                    if span:
                        span.set_attribute("agent.execution.duration_ms", execution_time * 1000)
                        span.set_attribute("agent.execution.success", False)
                        span.set_attribute("agent.error.type", type(e).__name__)
                    raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def trace_signal_generation(symbol: str, confidence: float = None):
    """
    Decorator for tracing signal generation workflows
    
    Args:
        symbol: Trading symbol being analyzed
        confidence: Optional confidence level of the signal
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attributes = {
                "signal.symbol": symbol,
                "signal.generation.function": func.__name__,
                "signal.generation.start_time": time.time(),
            }
            if confidence is not None:
                attributes["signal.confidence"] = confidence
            
            with create_span(
                f"signal.generation.{symbol}",
                SpanKind.INTERNAL,
                attributes
            ) as span:
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    generation_time = time.time() - start_time
                    if span:
                        span.set_attribute("signal.generation.duration_ms", generation_time * 1000)
                        span.set_attribute("signal.generation.success", True)
                        # Extract signal attributes from result if available
                        if hasattr(result, 'confidence'):
                            span.set_attribute("signal.result.confidence", result.confidence)
                        if hasattr(result, 'signal_type'):
                            span.set_attribute("signal.result.type", result.signal_type)
                    return result
                except Exception as e:
                    generation_time = time.time() - start_time
                    if span:
                        span.set_attribute("signal.generation.duration_ms", generation_time * 1000)
                        span.set_attribute("signal.generation.success", False)
                        span.set_attribute("signal.error.type", type(e).__name__)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            attributes = {
                "signal.symbol": symbol,
                "signal.generation.function": func.__name__,
                "signal.generation.start_time": time.time(),
            }
            if confidence is not None:
                attributes["signal.confidence"] = confidence
            
            with create_span(
                f"signal.generation.{symbol}",
                SpanKind.INTERNAL,
                attributes
            ) as span:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    generation_time = time.time() - start_time
                    if span:
                        span.set_attribute("signal.generation.duration_ms", generation_time * 1000)
                        span.set_attribute("signal.generation.success", True)
                        # Extract signal attributes from result if available
                        if hasattr(result, 'confidence'):
                            span.set_attribute("signal.result.confidence", result.confidence)
                        if hasattr(result, 'signal_type'):
                            span.set_attribute("signal.result.type", result.signal_type)
                    return result
                except Exception as e:
                    generation_time = time.time() - start_time
                    if span:
                        span.set_attribute("signal.generation.duration_ms", generation_time * 1000)
                        span.set_attribute("signal.generation.success", False)
                        span.set_attribute("signal.error.type", type(e).__name__)
                    raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def trace_data_validation(data_type: str, validation_rules: str = None):
    """
    Decorator for tracing data validation workflows
    
    Args:
        data_type: Type of data being validated
        validation_rules: Optional description of validation rules
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attributes = {
                "validation.data_type": data_type,
                "validation.function": func.__name__,
                "validation.start_time": time.time(),
            }
            if validation_rules:
                attributes["validation.rules"] = validation_rules
            
            with create_span(
                f"data.validation.{data_type}",
                SpanKind.INTERNAL,
                attributes
            ) as span:
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    validation_time = time.time() - start_time
                    if span:
                        span.set_attribute("validation.duration_ms", validation_time * 1000)
                        span.set_attribute("validation.success", True)
                        if isinstance(result, dict) and "errors" in result:
                            span.set_attribute("validation.error_count", len(result["errors"]))
                    return result
                except Exception as e:
                    validation_time = time.time() - start_time
                    if span:
                        span.set_attribute("validation.duration_ms", validation_time * 1000)
                        span.set_attribute("validation.success", False)
                        span.set_attribute("validation.error.type", type(e).__name__)
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            attributes = {
                "validation.data_type": data_type,
                "validation.function": func.__name__,
                "validation.start_time": time.time(),
            }
            if validation_rules:
                attributes["validation.rules"] = validation_rules
            
            with create_span(
                f"data.validation.{data_type}",
                SpanKind.INTERNAL,
                attributes
            ) as span:
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    validation_time = time.time() - start_time
                    if span:
                        span.set_attribute("validation.duration_ms", validation_time * 1000)
                        span.set_attribute("validation.success", True)
                        if isinstance(result, dict) and "errors" in result:
                            span.set_attribute("validation.error_count", len(result["errors"]))
                    return result
                except Exception as e:
                    validation_time = time.time() - start_time
                    if span:
                        span.set_attribute("validation.duration_ms", validation_time * 1000)
                        span.set_attribute("validation.success", False)
                        span.set_attribute("validation.error.type", type(e).__name__)
                    raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def add_baggage(key: str, value: str) -> None:
    """
    Add baggage item to the current context
    
    Args:
        key: Baggage key
        value: Baggage value
    """
    baggage.set_baggage(key, value)


def get_baggage(key: str) -> Optional[str]:
    """
    Get baggage item from the current context
    
    Args:
        key: Baggage key
    
    Returns:
        Baggage value or None if not found
    """
    return baggage.get_baggage(key)


def get_current_trace_id() -> Optional[str]:
    """
    Get the current trace ID
    
    Returns:
        Current trace ID as hex string, or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return None


def get_current_span_id() -> Optional[str]:
    """
    Get the current span ID
    
    Returns:
        Current span ID as hex string, or None if no active span
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, '016x')
    return None


def add_span_attribute(key: str, value: Any) -> None:
    """
    Add an attribute to the current span
    
    Args:
        key: Attribute key
        value: Attribute value
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span.set_attribute(key, value)


def add_span_event(name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
    """
    Add an event to the current span
    
    Args:
        name: Event name
        attributes: Optional event attributes
    """
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        span.add_event(name, attributes or {})


def shutdown_tracing() -> None:
    """Gracefully shutdown the tracing system"""
    try:
        trace_provider = trace.get_tracer_provider()
        if hasattr(trace_provider, 'shutdown'):
            trace_provider.shutdown()
        logger.info("OpenTelemetry tracing shutdown completed")
    except Exception as e:
        logger.error(f"Error during tracing shutdown: {e}")


# Example usage functions for testing and demonstration

async def example_agent_execution():
    """Example of agent execution tracing"""
    
    @trace_agent_execution("technical_agent", "momentum")
    async def analyze_momentum(symbol: str):
        # Simulate agent work
        await asyncio.sleep(0.1)
        add_span_attribute("analysis.indicators", "RSI,MACD,SMA")
        add_span_event("calculation.completed", {"indicators_count": 3})
        return {"signal": "BUY", "confidence": 0.85}
    
    result = await analyze_momentum("RELIANCE")
    return result


async def example_signal_generation():
    """Example of signal generation tracing"""
    
    @trace_signal_generation("RELIANCE", 0.75)
    async def generate_trading_signal(symbol: str):
        # Simulate signal generation
        await asyncio.sleep(0.05)
        add_span_attribute("market.condition", "bullish")
        add_span_event("signal.created", {"type": "momentum", "strength": "strong"})
        return {"symbol": symbol, "signal": "BUY", "confidence": 0.85}
    
    result = await generate_trading_signal("RELIANCE")
    return result


async def example_data_validation():
    """Example of data validation tracing"""
    
    @trace_data_validation("market_data", "price_range,volume_positive,timestamp_recent")
    async def validate_market_data(data: dict):
        # Simulate validation
        await asyncio.sleep(0.02)
        errors = []
        if data.get("price", 0) <= 0:
            errors.append("Invalid price")
        add_span_attribute("validation.field_count", len(data))
        add_span_event("validation.completed", {"error_count": len(errors)})
        return {"valid": len(errors) == 0, "errors": errors}
    
    test_data = {"price": 100.50, "volume": 1000, "timestamp": time.time()}
    result = await validate_market_data(test_data)
    return result


# Initialize tracing on module import if environment variable is set
if os.getenv("AUTO_INIT_TRACING", "false").lower() == "true":
    setup_tracing()
    logger.info("OpenTelemetry tracing auto-initialized") 