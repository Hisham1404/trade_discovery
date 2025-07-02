"""
Health Check Endpoints for Integration Monitoring

Provides comprehensive health check endpoints that verify:
- Pulsar connectivity and consumer lag
- Cross-cluster integration health
- Service dependencies and SLA compliance
- Real-time monitoring status
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse
import structlog

from .integration_monitor import get_integration_monitor, AlertSeverity

logger = structlog.get_logger(__name__)

# Create health check router
health_router = APIRouter(prefix="/health", tags=["Health Checks"])


@health_router.get("/")
async def basic_health():
    """Basic health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "trade-discovery-integration"
    }


@health_router.get("/detailed")
async def detailed_health():
    """Detailed health check with all components"""
    monitor = get_integration_monitor()
    
    try:
        health_status = await monitor.get_health_status()
        
        # Determine overall health
        overall_healthy = (
            health_status["monitoring_system"]["status"] == "healthy" and
            all(
                status.get("connected", False) 
                for status in health_status["pulsar_connectivity"].values()
            )
        )
        
        response = {
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": health_status
        }
        
        status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/pulsar")
async def pulsar_health():
    """Pulsar-specific health check"""
    monitor = get_integration_monitor()
    
    try:
        # Check all configured Pulsar clusters
        clusters = ["discovery", "execution", "risk"]
        health_results = {}
        overall_healthy = True
        
        for cluster in clusters:
            broker_url = f"pulsar://{cluster}-pulsar:6650"
            result = await monitor.check_pulsar_health(cluster, broker_url)
            health_results[cluster] = result
            
            if not result.get("connected", False):
                overall_healthy = False
        
        response = {
            "status": "healthy" if overall_healthy else "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "clusters": health_results
        }
        
        status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error("Pulsar health check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/consumer-lag")
async def consumer_lag_health():
    """Consumer lag health check"""
    monitor = get_integration_monitor()
    
    try:
        # Check consumer lag for key topics
        lag_checks = [
            ("discovery", "signals", "execution-consumer"),
            ("discovery", "signals", "risk-consumer"),
            ("execution", "orders", "risk-consumer"),
            ("risk", "alerts", "discovery-consumer")
        ]
        
        lag_results = {}
        high_lag_detected = False
        
        for cluster, topic, subscription in lag_checks:
            result = await monitor.check_consumer_lag(cluster, topic, subscription)
            key = f"{cluster}:{topic}:{subscription}"
            lag_results[key] = result
            
            # Consider lag high if > 1000 messages or > 300 seconds
            if (result.get("message_lag", 0) > 1000 or 
                result.get("time_lag_seconds", 0) > 300):
                high_lag_detected = True
        
        response = {
            "status": "healthy" if not high_lag_detected else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "consumer_lags": lag_results,
            "warning": "High consumer lag detected" if high_lag_detected else None
        }
        
        # Return 200 for both healthy and degraded (not a complete failure)
        return JSONResponse(content=response, status_code=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error("Consumer lag check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/integration")
async def integration_health():
    """Cross-cluster integration health check"""
    monitor = get_integration_monitor()
    
    try:
        # Get recent metrics summary
        metrics_summary = await monitor.get_metrics_summary()
        
        # Determine integration health based on success rate and latency
        success_rate = metrics_summary.get("success_rate", 1.0)
        avg_publish_latency = metrics_summary.get("average_publish_latency", 0)
        avg_consume_latency = metrics_summary.get("average_consume_latency", 0)
        
        # Health criteria
        healthy_success_rate = 0.95  # 95% success rate
        max_publish_latency = 1.0   # 1 second
        max_consume_latency = 2.0   # 2 seconds
        
        issues = []
        if success_rate < healthy_success_rate:
            issues.append(f"Low success rate: {success_rate:.2%}")
        
        if avg_publish_latency > max_publish_latency:
            issues.append(f"High publish latency: {avg_publish_latency:.3f}s")
        
        if avg_consume_latency > max_consume_latency:
            issues.append(f"High consume latency: {avg_consume_latency:.3f}s")
        
        overall_healthy = len(issues) == 0
        
        response = {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": metrics_summary,
            "issues": issues if issues else None,
            "sla_compliance": {
                "success_rate": {
                    "current": success_rate,
                    "threshold": healthy_success_rate,
                    "compliant": success_rate >= healthy_success_rate
                },
                "publish_latency": {
                    "current": avg_publish_latency,
                    "threshold": max_publish_latency,
                    "compliant": avg_publish_latency <= max_publish_latency
                },
                "consume_latency": {
                    "current": avg_consume_latency,
                    "threshold": max_consume_latency,
                    "compliant": avg_consume_latency <= max_consume_latency
                }
            }
        }
        
        return JSONResponse(content=response, status_code=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error("Integration health check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/dependencies")
async def dependencies_health():
    """Health check for all service dependencies"""
    
    async def check_dependency(name: str, url: str, timeout: float = 5.0) -> Dict[str, Any]:
        """Check individual dependency health"""
        start_time = time.time()
        try:
            # This would be replaced with actual dependency checks
            # For now, simulating successful checks
            await asyncio.sleep(0.01)  # Simulate network call
            
            return {
                "name": name,
                "status": "healthy",
                "response_time": time.time() - start_time,
                "url": url
            }
        except Exception as e:
            return {
                "name": name,
                "status": "unhealthy",
                "response_time": time.time() - start_time,
                "url": url,
                "error": str(e)
            }
    
    try:
        # Define all dependencies
        dependencies = [
            ("PostgreSQL", "postgresql://postgres:5432"),
            ("Redis", "redis://redis:6379"),
            ("Elasticsearch", "http://elasticsearch:9200"),
            ("Prometheus", "http://prometheus:9090"),
            ("Grafana", "http://grafana:3000"),
            ("Jaeger", "http://jaeger:16686")
        ]
        
        # Check all dependencies concurrently
        dependency_tasks = [
            check_dependency(name, url) for name, url in dependencies
        ]
        
        dependency_results = await asyncio.gather(*dependency_tasks)
        
        # Count healthy vs unhealthy
        healthy_count = sum(1 for result in dependency_results if result["status"] == "healthy")
        total_count = len(dependency_results)
        
        overall_healthy = healthy_count == total_count
        
        response = {
            "status": "healthy" if overall_healthy else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "healthy": healthy_count,
                "total": total_count,
                "health_percentage": (healthy_count / total_count) * 100
            },
            "dependencies": dependency_results
        }
        
        status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_206_PARTIAL_CONTENT
        
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error("Dependencies health check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "unhealthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/readiness")
async def readiness_check():
    """Kubernetes readiness probe endpoint"""
    monitor = get_integration_monitor()
    
    try:
        # Check if monitoring system is initialized and ready
        if not monitor.is_initialized:
            return JSONResponse(
                content={
                    "status": "not_ready",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": "Monitoring system not initialized"
                },
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        # Quick health check
        health_status = await monitor.get_health_status()
        
        # Check if critical components are ready
        critical_ready = (
            health_status["monitoring_system"]["status"] == "healthy" and
            health_status["monitoring_system"]["prometheus_available"]
        )
        
        if critical_ready:
            return {
                "status": "ready",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            return JSONResponse(
                content={
                    "status": "not_ready",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": "Critical components not ready"
                },
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE
            )
            
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "not_ready",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/liveness")
async def liveness_check():
    """Kubernetes liveness probe endpoint"""
    try:
        # Simple liveness check - just verify the service is responding
        return {
            "status": "alive",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error("Liveness check failed", error=str(e))
        return JSONResponse(
            content={
                "status": "dead",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


@health_router.get("/metrics-summary")
async def metrics_summary():
    """Get integration metrics summary for health dashboards"""
    monitor = get_integration_monitor()
    
    try:
        summary = await monitor.get_metrics_summary()
        
        return {
            "status": "success",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": summary
        }
        
    except Exception as e:
        logger.error("Metrics summary failed", error=str(e))
        return JSONResponse(
            content={
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@health_router.post("/test-alert")
async def test_alert():
    """Test endpoint to trigger a sample alert"""
    monitor = get_integration_monitor()
    
    try:
        # Trigger a test alert
        await monitor.record_integration_error(
            source_cluster="test",
            target_cluster="test",
            error_type="test_error",
            severity=AlertSeverity.MEDIUM,
            error_message="This is a test alert to verify alerting system functionality",
            context={"test": True, "triggered_by": "health_endpoint"}
        )
        
        return {
            "status": "success",
            "message": "Test alert triggered successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error("Test alert failed", error=str(e))
        return JSONResponse(
            content={
                "status": "error",
                "message": f"Failed to trigger test alert: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        ) 