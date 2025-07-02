"""
Production-Grade FastAPI Application for Trade Discovery Platform

Integrated with:
- Prometheus FastAPI Instrumentator for automatic HTTP metrics
- Integration monitoring system for cross-cluster observability
- Comprehensive health checks and SLA monitoring
- Structured logging with correlation IDs
- OpenTelemetry tracing for distributed requests
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from contextlib import asynccontextmanager
import structlog
import time
from datetime import datetime, timezone

from app.core.config import settings
from app.core.database import init_db_engine
from app.api import auth, signals, alerts, websockets, audit
from monitoring.integration_monitor import get_integration_monitor, MonitoringConfig
from monitoring.health_endpoints import health_router
from monitoring.tracing import (
    setup_tracing, 
    setup_all_instrumentation, 
    TraceConfig,
    shutdown_tracing,
    get_current_trace_id,
    add_span_attribute
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management with monitoring initialization"""
    # Initialize OpenTelemetry tracing first
    logger.info("Initializing OpenTelemetry tracing")
    trace_config = TraceConfig(
        service_name="trade-discovery-platform",
        service_version="1.0.0",
        sample_rate=0.1 if not settings.DEBUG else 1.0,  # Higher sampling in debug mode
        enable_console=settings.DEBUG
    )
    setup_tracing(trace_config)
    
    # Initialize database engine for instrumentation
    engine = init_db_engine()
    
    # Setup all OpenTelemetry instrumentations
    setup_all_instrumentation(app, engine)
    
    # Initialize monitoring system
    logger.info("Initializing production monitoring system")
    monitor = get_integration_monitor()
    
    # Configure monitoring for production
    monitor.config.prometheus_enabled = True
    monitor.config.opentelemetry_enabled = True
    monitor.config.enable_fastapi_instrumentator = True
    monitor.config.log_level = "INFO"
    
    # Initialize monitoring
    await monitor.initialize()
    
    # Setup FastAPI Instrumentator for automatic HTTP metrics
    instrumentator = monitor.setup_fastapi_instrumentator(app)
    
    logger.info("Application startup complete", 
                monitoring_enabled=monitor.is_initialized,
                prometheus_available=monitor.config.prometheus_enabled,
                instrumentator_configured=instrumentator is not None,
                tracing_enabled=True)
    
    yield
    
    # Shutdown
    logger.info("Shutting down application")
    await monitor.shutdown()
    
    # Shutdown OpenTelemetry tracing
    shutdown_tracing()
    
    logger.info("Application shutdown complete")


# Create FastAPI application with production configuration
app = FastAPI(
    title="Trade Discovery Platform",
    description="Production-grade trading signal discovery and execution platform with comprehensive monitoring",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
    servers=[
        {"url": "https://api.tradediscovery.com", "description": "Production environment"},
        {"url": "https://staging-api.tradediscovery.com", "description": "Staging environment"},
        {"url": "http://localhost:8000", "description": "Development environment"}
    ]
)

# Production security middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"] if settings.DEBUG else ["api.tradediscovery.com", "staging-api.tradediscovery.com"]
)

# CORS middleware with production settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else [
        "https://tradediscovery.com",
        "https://app.tradediscovery.com",
        "https://staging.tradediscovery.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def monitoring_middleware(request: Request, call_next):
    """Add monitoring and correlation context to all requests"""
    start_time = time.time()
    
    # Get monitoring instance
    monitor = get_integration_monitor()
    
    # Get OpenTelemetry trace context
    trace_id = get_current_trace_id()
    
    # Create correlation context
    user_id = getattr(request.state, 'user_id', None)
    operation = f"{request.method} {request.url.path}"
    
    with monitor.correlation_context(
        operation=operation,
        cluster_id="trade-discovery-api",
        user_id=user_id
    ) as ctx:
        
        # Add correlation ID and trace context to request state
        request.state.correlation_id = ctx.correlation_id
        request.state.trace_id = trace_id
        
        # Add OpenTelemetry span attributes
        add_span_attribute("http.method", request.method)
        add_span_attribute("http.url", str(request.url))
        add_span_attribute("http.path", request.url.path)
        add_span_attribute("correlation.id", ctx.correlation_id)
        if user_id:
            add_span_attribute("user.id", user_id)
        
        try:
            # Process request with tracing
            async with monitor.trace_operation(
                operation_name=operation,
                http_method=request.method,
                http_url=str(request.url),
                user_id=user_id
            ):
                response = await call_next(request)
                
                # Record successful request
                duration = time.time() - start_time
                
                # Add response attributes to span
                add_span_attribute("http.status_code", response.status_code)
                add_span_attribute("http.response_duration_ms", duration * 1000)
                
                # Add trace context to response headers
                if trace_id:
                    response.headers["X-Trace-ID"] = trace_id
                response.headers["X-Correlation-ID"] = ctx.correlation_id
                
                # Log request completion
                log = monitor.get_structured_logger("http_request")
                log.info(
                    "HTTP request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration=duration,
                    user_id=user_id,
                    trace_id=trace_id,
                    correlation_id=ctx.correlation_id
                )
                
                return response
                
        except Exception as e:
            # Record failed request
            duration = time.time() - start_time
            
            # Add error attributes to span
            add_span_attribute("http.status_code", 500)
            add_span_attribute("http.response_duration_ms", duration * 1000)
            add_span_attribute("error.type", type(e).__name__)
            add_span_attribute("error.message", str(e))
            
            # Log error
            log = monitor.get_structured_logger("http_error")
            log.error(
                "HTTP request failed",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration=duration,
                user_id=user_id,
                trace_id=trace_id,
                correlation_id=ctx.correlation_id
            )
            
            # Return error response
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": "Internal server error",
                    "correlation_id": ctx.correlation_id,
                    "trace_id": trace_id,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                headers={
                    "X-Trace-ID": trace_id or "unknown",
                    "X-Correlation-ID": ctx.correlation_id
                }
            )


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus metrics endpoint"""
    monitor = get_integration_monitor()
    metrics_data = monitor.get_prometheus_metrics()
    return PlainTextResponse(content=metrics_data, media_type="text/plain")


@app.get("/")
async def root(request: Request):
    """Root endpoint with system information"""
    monitor = get_integration_monitor()
    health_status = await monitor.get_health_status()
    
    # Add trace context
    trace_id = get_current_trace_id()
    correlation_id = getattr(request.state, 'correlation_id', None)
    
    return {
        "service": "Trade Discovery Platform",
        "version": "1.0.0",
        "status": "operational",
        "monitoring": {
            "enabled": monitor.is_initialized,
            "prometheus_available": health_status["monitoring_system"]["prometheus_available"],
            "opentelemetry_available": health_status["monitoring_system"]["opentelemetry_available"],
            "tracing_enabled": trace_id is not None
        },
        "request_context": {
            "trace_id": trace_id,
            "correlation_id": correlation_id
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documentation": "/docs" if settings.DEBUG else "Contact API team for documentation"
    }


@app.get("/api/status")
async def api_status(request: Request):
    """API status endpoint with detailed metrics"""
    monitor = get_integration_monitor()
    metrics_summary = await monitor.get_metrics_summary()
    health_status = await monitor.get_health_status()
    
    # Add trace context
    trace_id = get_current_trace_id()
    correlation_id = getattr(request.state, 'correlation_id', None)
    
    return {
        "status": "healthy" if monitor.is_initialized else "degraded",
        "metrics": metrics_summary,
        "health": health_status,
        "tracing": {
            "enabled": trace_id is not None,
            "current_trace_id": trace_id,
            "correlation_id": correlation_id
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/test-monitoring")
async def test_monitoring():
    """Test endpoint to verify monitoring functionality"""
    monitor = get_integration_monitor()
    
    # Record test events
    await monitor.record_event_published(
        source_cluster="trade-discovery-api",
        target_cluster="test",
        event_type="test_signal",
        topic="test_topic",
        success=True,
        duration=0.05
    )
    
    await monitor.record_event_consumed(
        source_cluster="test",
        target_cluster="trade-discovery-api",
        event_type="test_signal",
        topic="test_topic",
        success=True,
        duration=0.03
    )
    
    return {
        "message": "Monitoring test completed successfully",
        "events_recorded": 2,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.post("/api/test-tracing")
async def test_tracing(request: Request):
    """Test endpoint to verify OpenTelemetry tracing functionality"""
    from monitoring.tracing import (
        example_agent_execution,
        example_signal_generation,
        example_data_validation,
        create_span,
        add_span_event
    )
    
    trace_id = get_current_trace_id()
    correlation_id = getattr(request.state, 'correlation_id', None)
    
    # Add test attributes to current span
    add_span_attribute("test.type", "tracing_verification")
    add_span_attribute("test.endpoint", "/api/test-tracing")
    
    results = {}
    
    # Test 1: Agent execution tracing
    with create_span("test.agent_execution", attributes={"test.step": "1"}) as span:
        add_span_event("Starting agent execution test")
        agent_result = await example_agent_execution()
        results["agent_execution"] = {
            "success": True,
            "result": agent_result,
            "span_created": span is not None
        }
        add_span_event("Agent execution test completed", {"result": str(agent_result)})
    
    # Test 2: Signal generation tracing
    with create_span("test.signal_generation", attributes={"test.step": "2"}) as span:
        add_span_event("Starting signal generation test")
        signal_result = await example_signal_generation()
        results["signal_generation"] = {
            "success": True,
            "result": signal_result,
            "span_created": span is not None
        }
        add_span_event("Signal generation test completed", {"result": str(signal_result)})
    
    # Test 3: Data validation tracing
    with create_span("test.data_validation", attributes={"test.step": "3"}) as span:
        add_span_event("Starting data validation test")
        validation_result = await example_data_validation()
        results["data_validation"] = {
            "success": True,
            "result": validation_result,
            "span_created": span is not None
        }
        add_span_event("Data validation test completed", {"result": str(validation_result)})
    
    # Final test summary
    add_span_event("All tracing tests completed successfully")
    
    return {
        "message": "OpenTelemetry tracing test completed successfully",
        "trace_id": trace_id,
        "correlation_id": correlation_id,
        "tests_executed": 3,
        "results": results,
        "tracing_context": {
            "trace_id": trace_id,
            "spans_created": sum(1 for r in results.values() if r.get("span_created", False))
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Include API routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(signals.router, prefix="/api/v1/signals", tags=["Trading Signals"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["Alerts"])
app.include_router(websockets.router, prefix="/api/v1/ws", tags=["WebSocket"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["Audit & Compliance"])

# Include health check endpoints
app.include_router(health_router, tags=["Health Checks"])


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler with monitoring"""
    monitor = get_integration_monitor()
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    
    log = monitor.get_structured_logger("http_error")
    log.warning(
        "Resource not found",
        path=request.url.path,
        method=request.method,
        correlation_id=correlation_id
    )
    
    return JSONResponse(
        status_code=404,
        content={
            "error": "Resource not found",
            "path": request.url.path,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """Custom 500 handler with monitoring"""
    monitor = get_integration_monitor()
    correlation_id = getattr(request.state, 'correlation_id', 'unknown')
    
    log = monitor.get_structured_logger("http_error")
    log.error(
        "Internal server error",
        error=str(exc),
        path=request.url.path,
        method=request.method,
        correlation_id=correlation_id
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    
    # Production server configuration
    uvicorn_config = {
        "host": "0.0.0.0",
        "port": 8000,
        "log_level": "info",
        "access_log": True,
        "use_colors": False,
        "server_header": False,
        "date_header": False
    }
    
    if settings.DEBUG:
        uvicorn_config.update({
            "reload": True,
            "reload_dirs": ["app", "monitoring"],
            "log_level": "debug"
        })
    else:
        uvicorn_config.update({
            "workers": 4,
            "loop": "uvloop",
            "http": "httptools"
        })
    
    logger.info("Starting Trade Discovery Platform", config=uvicorn_config)
    uvicorn.run("app.main:app", **uvicorn_config) 