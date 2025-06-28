"""
Main FastAPI application for the Discovery Cluster.
Trading Signal Generation Platform
"""

import logging
import structlog
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import close_redis_connection, redis_health_check
from app.api.auth import router as auth_router

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("🚀 Discovery Cluster API starting up...")
    
    # Test Redis connection
    try:
        await redis_health_check()
        logger.info("✅ Redis connection established")
    except Exception as e:
        logger.warning(f"⚠️ Redis connection failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Discovery Cluster API shutting down...")
    await close_redis_connection()
    logger.info("✅ Cleanup completed")


# Create FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="High-performance API for trading signal discovery and real-time market analysis",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001", 
        "https://tradediscovery.app",
        "http://localhost",
        "http://localhost:8080"
    ] + settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time", "X-Request-ID"],
    max_age=600
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Log all HTTP requests"""
    start_time = datetime.now()
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration = (datetime.now() - start_time).total_seconds()
    
    # Log response
    logger.info(f"{request.method} {request.url} - {response.status_code} - {duration:.3f}s")
    
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc} - Path: {request.url.path}")
    
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include routers
app.include_router(auth_router, prefix="/auth", tags=["authentication"])

# Import and include signals router
from app.api.signals import router as signals_router
app.include_router(signals_router, prefix="/api", tags=["signals"])

# Import and include alerts router
from app.api.alerts import router as alerts_router
app.include_router(alerts_router, prefix="/api", tags=["alerts"])

# Import and include WebSocket router
from app.api.websockets import router as websocket_router
app.include_router(websocket_router, prefix="/ws", tags=["websockets"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Discovery Cluster API",
        "version": settings.APP_VERSION,
        "status": "operational",
        "docs": "/docs" if settings.DEBUG else "Documentation disabled in production"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.APP_VERSION,
        "services": {}
    }
    
    # Check Redis connection
    try:
        await redis_health_check()
        health_status["services"]["redis"] = "healthy"
    except Exception:
        health_status["services"]["redis"] = "unhealthy"
        health_status["status"] = "degraded"
    
    return health_status


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    ) 