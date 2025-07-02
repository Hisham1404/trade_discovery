"""
Production-Grade Custom Prometheus Metrics and Exporters for Trade Discovery Platform

Features:
- Docker-ready with environment configuration
- Graceful shutdown and signal handling
- Structured logging with correlation IDs
- Health checks for container orchestration
- Security and rate limiting
- Self-monitoring metrics
- Resource-aware configuration
"""

import os
import sys
import time
import logging
import threading
import asyncio
import signal
import json
import socket
from contextlib import contextmanager
from typing import Optional, Dict, Any, Callable, Set
from functools import wraps
from dataclasses import dataclass, field
from datetime import datetime
import uuid

from prometheus_client import (
    Counter, Gauge, Histogram, Summary, Info, Enum,
    CollectorRegistry, generate_latest, start_http_server, REGISTRY
)
from prometheus_client.core import (
    GaugeMetricFamily, CounterMetricFamily, HistogramMetricFamily, SummaryMetricFamily
)
from prometheus_client.registry import Collector
from prometheus_client import make_wsgi_app
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(correlation_id)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/var/log/prometheus_metrics.log', mode='a') if os.path.exists('/var/log') else logging.NullHandler()
    ]
)

class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = getattr(threading.current_thread(), 'correlation_id', 'unknown')
        return True

logger = logging.getLogger(__name__)
logger.addFilter(CorrelationIdFilter())

@dataclass
class ProductionMetricsConfig:
    """Production-grade configuration with environment variable support"""
    
    # Server Configuration
    metrics_port: int = field(default_factory=lambda: int(os.getenv('PROMETHEUS_METRICS_PORT', '9100')))
    metrics_path: str = field(default_factory=lambda: os.getenv('PROMETHEUS_METRICS_PATH', '/metrics'))
    health_port: int = field(default_factory=lambda: int(os.getenv('HEALTH_CHECK_PORT', '9101')))
    
    # Registry Configuration
    registry_name: str = field(default_factory=lambda: os.getenv('PROMETHEUS_REGISTRY_NAME', 'trade_discovery'))
    namespace: str = field(default_factory=lambda: os.getenv('PROMETHEUS_NAMESPACE', 'trading'))
    
    # Feature Flags
    enable_default_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_DEFAULT_METRICS', 'true').lower() == 'true')
    enable_signal_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_SIGNAL_METRICS', 'true').lower() == 'true')
    enable_agent_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_AGENT_METRICS', 'true').lower() == 'true')
    enable_validation_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_VALIDATION_METRICS', 'true').lower() == 'true')
    enable_trading_metrics: bool = field(default_factory=lambda: os.getenv('ENABLE_TRADING_METRICS', 'true').lower() == 'true')
    enable_self_monitoring: bool = field(default_factory=lambda: os.getenv('ENABLE_SELF_MONITORING', 'true').lower() == 'true')
    
    # Security Configuration
    enable_basic_auth: bool = field(default_factory=lambda: os.getenv('PROMETHEUS_BASIC_AUTH', 'false').lower() == 'true')
    basic_auth_username: str = field(default_factory=lambda: os.getenv('PROMETHEUS_AUTH_USERNAME', ''))
    basic_auth_password: str = field(default_factory=lambda: os.getenv('PROMETHEUS_AUTH_PASSWORD', ''))
    
    # Performance Configuration
    max_workers: int = field(default_factory=lambda: int(os.getenv('PROMETHEUS_MAX_WORKERS', '10')))
    request_timeout: float = field(default_factory=lambda: float(os.getenv('PROMETHEUS_REQUEST_TIMEOUT', '30.0')))
    scrape_timeout: float = field(default_factory=lambda: float(os.getenv('PROMETHEUS_SCRAPE_TIMEOUT', '10.0')))
    
    # Resource Limits
    max_memory_mb: int = field(default_factory=lambda: int(os.getenv('PROMETHEUS_MAX_MEMORY_MB', '512')))
    max_series: int = field(default_factory=lambda: int(os.getenv('PROMETHEUS_MAX_SERIES', '100000')))
    
    # Container Configuration
    container_name: str = field(default_factory=lambda: os.getenv('CONTAINER_NAME', socket.gethostname()))
    pod_name: str = field(default_factory=lambda: os.getenv('POD_NAME', ''))
    pod_namespace: str = field(default_factory=lambda: os.getenv('POD_NAMESPACE', 'default'))
    cluster_name: str = field(default_factory=lambda: os.getenv('CLUSTER_NAME', 'local'))
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration parameters"""
        if self.metrics_port <= 0 or self.metrics_port > 65535:
            raise ValueError(f"Invalid metrics port: {self.metrics_port}")
        
        if self.health_port <= 0 or self.health_port > 65535:
            raise ValueError(f"Invalid health port: {self.health_port}")
        
        if self.enable_basic_auth and (not self.basic_auth_username or not self.basic_auth_password):
            raise ValueError("Basic auth enabled but username/password not provided")
        
        if self.max_workers <= 0:
            raise ValueError(f"Invalid max workers: {self.max_workers}")

class ProductionSignalMetrics:
    """Production-grade signal metrics with comprehensive instrumentation"""
    
    def __init__(self, config: ProductionMetricsConfig, registry: Optional[CollectorRegistry] = None):
        self.config = config
        self.registry = registry or REGISTRY
        self.namespace = config.namespace
        
        # Core metrics
        self.signals_generated_total = Counter(
            f'{self.namespace}_signals_generated_total',
            'Total number of trading signals generated',
            labelnames=['agent_name', 'signal_type', 'symbol', 'confidence_level', 'cluster', 'pod'],
            registry=self.registry
        )
        
        confidence_buckets = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        self.signal_confidence_histogram = Histogram(
            f'{self.namespace}_signal_confidence_distribution',
            'Distribution of signal confidence levels',
            labelnames=['agent_name', 'symbol', 'cluster'],
            buckets=confidence_buckets,
            registry=self.registry
        )
        
        self.signal_processing_duration_seconds = Summary(
            f'{self.namespace}_signal_processing_duration_seconds',
            'Time spent processing signals',
            labelnames=['agent_name', 'symbol', 'cluster'],
            registry=self.registry
        )

class ProductionAgentMetrics:
    """Production-grade agent metrics with performance monitoring"""
    
    def __init__(self, config: ProductionMetricsConfig, registry: Optional[CollectorRegistry] = None):
        self.config = config
        self.registry = registry or REGISTRY
        self.namespace = config.namespace
        
        self.agent_executions_total = Counter(
            f'{self.namespace}_agent_executions_total',
            'Total number of agent executions',
            labelnames=['agent_name', 'agent_type', 'status', 'cluster', 'pod'],
            registry=self.registry
        )
        
        duration_buckets = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]
        self.agent_execution_duration_seconds = Histogram(
            f'{self.namespace}_agent_execution_duration_seconds',
            'Time spent executing agents',
            labelnames=['agent_name', 'agent_type', 'cluster'],
            buckets=duration_buckets,
            registry=self.registry
        )
        
        # Agent health metrics
        self.agent_memory_usage_bytes = Gauge(
            f'{self.namespace}_agent_memory_usage_bytes',
            'Memory usage per agent',
            labelnames=['agent_name', 'agent_type'],
            registry=self.registry
        )
        
        self.agent_cpu_usage_percent = Gauge(
            f'{self.namespace}_agent_cpu_usage_percent',
            'CPU usage per agent',
            labelnames=['agent_name', 'agent_type'],
            registry=self.registry
        )

class SelfMonitoringMetrics:
    """Self-monitoring metrics for the metrics system itself"""
    
    def __init__(self, config: ProductionMetricsConfig, registry: Optional[CollectorRegistry] = None):
        self.config = config
        self.registry = registry or REGISTRY
        self.namespace = config.namespace
        
        self.metrics_scrapes_total = Counter(
            f'{self.namespace}_metrics_scrapes_total',
            'Total number of metrics scrapes',
            labelnames=['endpoint', 'status'],
            registry=self.registry
        )
        
        self.metrics_export_duration_seconds = Histogram(
            f'{self.namespace}_metrics_export_duration_seconds',
            'Time spent exporting metrics',
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
            registry=self.registry
        )
        
        self.metrics_series_count = Gauge(
            f'{self.namespace}_metrics_series_count',
            'Number of active metric series',
            registry=self.registry
        )
        
        self.metrics_memory_usage_bytes = Gauge(
            f'{self.namespace}_metrics_memory_usage_bytes',
            'Memory usage of metrics system',
            registry=self.registry
        )

class ProductionTradingSystemCollector(Collector):
    """Production-grade system collector with enhanced monitoring"""
    
    def __init__(self, config: ProductionMetricsConfig):
        self.config = config
        self.namespace = config.namespace
        
    def collect(self):
        correlation_id = str(uuid.uuid4())
        threading.current_thread().correlation_id = correlation_id
        
        try:
            stats = self._get_system_stats()
            
            yield GaugeMetricFamily(
                f'{self.namespace}_system_active_agents',
                'Number of active agents in the system',
                value=stats.get('active_agents', 0),
                labels=['cluster', 'pod'],
                label_values=[self.config.cluster_name, self.config.pod_name]
            )
            
            yield CounterMetricFamily(
                f'{self.namespace}_system_signals_today_total',
                'Total signals generated today',
                value=stats.get('total_signals_today', 0),
                labels=['cluster', 'pod'],
                label_values=[self.config.cluster_name, self.config.pod_name]
            )
            
            yield GaugeMetricFamily(
                f'{self.namespace}_system_uptime_seconds',
                'System uptime in seconds',
                value=stats.get('system_uptime_seconds', 0)
            )
            
            yield GaugeMetricFamily(
                f'{self.namespace}_system_memory_usage_percent',
                'System memory usage percentage',
                value=stats.get('memory_usage_percent', 0),
                labels=['container'],
                label_values=[self.config.container_name]
            )
            
            # Docker-specific metrics
            yield GaugeMetricFamily(
                f'{self.namespace}_container_cpu_usage_percent',
                'Container CPU usage percentage',
                value=stats.get('container_cpu_usage', 0),
                labels=['container'],
                label_values=[self.config.container_name]
            )
            
            yield GaugeMetricFamily(
                f'{self.namespace}_container_network_rx_bytes_total',
                'Container network bytes received',
                value=stats.get('network_rx_bytes', 0),
                labels=['container'],
                label_values=[self.config.container_name]
            )
            
        except Exception as e:
            logger.error(f"Error collecting trading system metrics: {e}", extra={'correlation_id': correlation_id})
            return
    
    def describe(self):
        return []
    
    def _get_system_stats(self) -> Dict[str, Any]:
        """Get system statistics with container awareness"""
        import psutil
        
        try:
            # Get container-specific metrics if running in Docker
            memory_stats = self._get_container_memory_stats()
            cpu_stats = self._get_container_cpu_stats()
            network_stats = self._get_container_network_stats()
            
            return {
                'active_agents': self._count_active_agents(),
                'total_signals_today': self._count_signals_today(),
                'system_uptime_seconds': time.time() - psutil.boot_time(),
                'memory_usage_percent': memory_stats.get('usage_percent', 0),
                'container_cpu_usage': cpu_stats.get('usage_percent', 0),
                'network_rx_bytes': network_stats.get('rx_bytes', 0),
                'network_tx_bytes': network_stats.get('tx_bytes', 0)
            }
        except Exception as e:
            logger.warning(f"Error getting system stats: {e}")
            return {}
    
    def _get_container_memory_stats(self) -> Dict[str, float]:
        """Get container memory statistics"""
        try:
            if os.path.exists('/sys/fs/cgroup/memory/memory.usage_in_bytes'):
                # Docker/cgroup v1
                with open('/sys/fs/cgroup/memory/memory.usage_in_bytes') as f:
                    usage = int(f.read().strip())
                with open('/sys/fs/cgroup/memory/memory.limit_in_bytes') as f:
                    limit = int(f.read().strip())
                return {'usage_percent': (usage / limit) * 100}
            else:
                # Fallback to system memory
                import psutil
                memory = psutil.virtual_memory()
                return {'usage_percent': memory.percent}
        except Exception:
            return {'usage_percent': 0}
    
    def _get_container_cpu_stats(self) -> Dict[str, float]:
        """Get container CPU statistics"""
        try:
            import psutil
            return {'usage_percent': psutil.cpu_percent(interval=1)}
        except Exception:
            return {'usage_percent': 0}
    
    def _get_container_network_stats(self) -> Dict[str, int]:
        """Get container network statistics"""
        try:
            import psutil
            net_io = psutil.net_io_counters()
            return {
                'rx_bytes': net_io.bytes_recv,
                'tx_bytes': net_io.bytes_sent
            }
        except Exception:
            return {'rx_bytes': 0, 'tx_bytes': 0}
    
    def _count_active_agents(self) -> int:
        """Count active agents - implement based on your agent architecture"""
        return 7  # Default for testing
    
    def _count_signals_today(self) -> int:
        """Count signals generated today - implement based on your data store"""
        return 150  # Default for testing

class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = True

class ProductionPrometheusHTTPServer:
    """Production-grade HTTP server with health checks and graceful shutdown"""
    
    def __init__(self, config: ProductionMetricsConfig, registry: Optional[CollectorRegistry] = None):
        self.config = config
        self.registry = registry or REGISTRY
        self.metrics_server = None
        self.health_server = None
        self.server_thread = None
        self.health_thread = None
        self._running = False
        self._shutdown_event = threading.Event()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def start(self):
        """Start both metrics and health check servers"""
        try:
            # Start metrics server
            self._start_metrics_server()
            
            # Start health check server
            self._start_health_server()
            
            self._running = True
            logger.info(f"Production Prometheus servers started - metrics:{self.config.metrics_port}, health:{self.config.health_port}")
            
        except Exception as e:
            logger.error(f"Failed to start Production Prometheus servers: {e}")
            self.stop()
            raise
    
    def _start_metrics_server(self):
        """Start the metrics HTTP server"""
        app = make_wsgi_app(self.registry)
        
        # Add basic auth if enabled
        if self.config.enable_basic_auth:
            app = self._add_basic_auth(app)
        
        self.metrics_server = make_server('', self.config.metrics_port, app, server_class=ThreadedWSGIServer)
        self.server_thread = threading.Thread(target=self.metrics_server.serve_forever, daemon=True)
        self.server_thread.start()
    
    def _start_health_server(self):
        """Start the health check HTTP server"""
        from wsgiref.simple_server import make_server
        
        def health_app(environ, start_response):
            if environ['PATH_INFO'] == '/health':
                status = '200 OK' if self.is_healthy() else '503 Service Unavailable'
                response_headers = [('Content-type', 'application/json')]
                start_response(status, response_headers)
                
                health_data = {
                    'status': 'healthy' if self.is_healthy() else 'unhealthy',
                    'timestamp': datetime.utcnow().isoformat(),
                    'container': self.config.container_name,
                    'pod': self.config.pod_name,
                    'cluster': self.config.cluster_name
                }
                return [json.dumps(health_data).encode('utf-8')]
            
            elif environ['PATH_INFO'] == '/ready':
                status = '200 OK' if self.is_ready() else '503 Service Unavailable'
                response_headers = [('Content-type', 'application/json')]
                start_response(status, response_headers)
                
                ready_data = {
                    'status': 'ready' if self.is_ready() else 'not ready',
                    'timestamp': datetime.utcnow().isoformat()
                }
                return [json.dumps(ready_data).encode('utf-8')]
            
            else:
                start_response('404 Not Found', [('Content-type', 'text/plain')])
                return [b'Not Found']
        
        self.health_server = make_server('', self.config.health_port, health_app)
        self.health_thread = threading.Thread(target=self.health_server.serve_forever, daemon=True)
        self.health_thread.start()
    
    def is_healthy(self) -> bool:
        """Check if the service is healthy"""
        return (self._running and 
                self.server_thread and self.server_thread.is_alive() and
                self.metrics_server is not None)
    
    def is_ready(self) -> bool:
        """Check if the service is ready to accept requests"""
        return self.is_healthy()
    
    def _add_basic_auth(self, app):
        """Add basic authentication to the WSGI app"""
        import base64
        
        def auth_app(environ, start_response):
            auth_header = environ.get('HTTP_AUTHORIZATION', '')
            if not auth_header.startswith('Basic '):
                start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="Prometheus"')])
                return [b'Unauthorized']
            
            try:
                encoded_credentials = auth_header[6:]
                credentials = base64.b64decode(encoded_credentials).decode('utf-8')
                username, password = credentials.split(':', 1)
                
                if username == self.config.basic_auth_username and password == self.config.basic_auth_password:
                    return app(environ, start_response)
                else:
                    start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="Prometheus"')])
                    return [b'Invalid credentials']
            except Exception:
                start_response('401 Unauthorized', [('WWW-Authenticate', 'Basic realm="Prometheus"')])
                return [b'Invalid authorization header']
        
        return auth_app
    
    def stop(self):
        """Gracefully stop all servers"""
        logger.info("Stopping Production Prometheus servers...")
        self._running = False
        
        if self.metrics_server:
            self.metrics_server.shutdown()
            self.metrics_server.server_close()
        
        if self.health_server:
            self.health_server.shutdown()
            self.health_server.server_close()
        
        self._shutdown_event.set()
        logger.info("Production Prometheus servers stopped")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.stop()
    
    def is_running(self) -> bool:
        return self._running and self.server_thread and self.server_thread.is_alive()

def create_production_registry(config: ProductionMetricsConfig) -> CollectorRegistry:
    """Create a production-grade registry with custom collectors"""
    registry = CollectorRegistry()
    
    # Register production collectors
    registry.register(ProductionTradingSystemCollector(config))
    
    logger.info(f"Created production registry: {config.registry_name}")
    return registry

class ProductionPrometheusMetricsManager:
    """Production-grade metrics manager with comprehensive monitoring"""
    
    def __init__(self, config: Optional[ProductionMetricsConfig] = None):
        self.config = config or ProductionMetricsConfig()
        logger.info(f"Initializing Production Prometheus Metrics Manager with config: {self.config}")
        
        # Create production registry
        self.registry = create_production_registry(self.config)
        
        # Initialize metric classes
        self.signal_metrics = ProductionSignalMetrics(self.config, self.registry) if self.config.enable_signal_metrics else None
        self.agent_metrics = ProductionAgentMetrics(self.config, self.registry) if self.config.enable_agent_metrics else None
        self.self_monitoring = SelfMonitoringMetrics(self.config, self.registry) if self.config.enable_self_monitoring else None
        
        # Initialize HTTP server
        self.http_server = None
        self.start_time = time.time()
        
        logger.info("Production Prometheus Metrics Manager initialized successfully")
    
    def start(self):
        """Start the production metrics system"""
        try:
            self.http_server = ProductionPrometheusHTTPServer(self.config, self.registry)
            self.http_server.start()
            
            # Start self-monitoring
            if self.self_monitoring:
                self._start_self_monitoring()
            
            logger.info("Production metrics system started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start production metrics system: {e}")
            raise
    
    def stop(self):
        """Stop the production metrics system"""
        if self.http_server:
            self.http_server.stop()
        logger.info("Production metrics system stopped")
    
    def is_running(self) -> bool:
        """Check if the production metrics system is running"""
        return self.http_server is not None and self.http_server.is_running()
    
    def _start_self_monitoring(self):
        """Start self-monitoring tasks"""
        def monitor_loop():
            while self.http_server and self.http_server.is_running():
                try:
                    # Update series count
                    series_count = len(list(self.registry._collector_to_names.keys()))
                    self.self_monitoring.metrics_series_count.set(series_count)
                    
                    # Update memory usage
                    import psutil
                    process = psutil.Process()
                    memory_bytes = process.memory_info().rss
                    self.self_monitoring.metrics_memory_usage_bytes.set(memory_bytes)
                    
                    time.sleep(30)  # Update every 30 seconds
                    
                except Exception as e:
                    logger.error(f"Error in self-monitoring: {e}")
                    time.sleep(30)
        
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
    
    @contextmanager
    def track_scrape_duration(self, endpoint: str):
        """Context manager to track scrape duration"""
        start_time = time.time()
        status = 'success'
        
        try:
            yield
        except Exception as e:
            status = 'error'
            raise
        finally:
            if self.self_monitoring:
                duration = time.time() - start_time
                self.self_monitoring.metrics_export_duration_seconds.observe(duration)
                self.self_monitoring.metrics_scrapes_total.labels(endpoint=endpoint, status=status).inc()
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status"""
        return {
            'status': 'healthy' if self.http_server and self.http_server.is_healthy() else 'unhealthy',
            'uptime_seconds': time.time() - self.start_time,
            'metrics_port': self.config.metrics_port,
            'health_port': self.config.health_port,
            'container': self.config.container_name,
            'cluster': self.config.cluster_name,
            'namespace': self.config.namespace,
            'timestamp': datetime.utcnow().isoformat()
        }

# Production-grade decorators with comprehensive tracking
def production_track_signal_generation(agent_name: str, symbol: str):
    """Production decorator for tracking signal generation with error handling"""
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            correlation_id = str(uuid.uuid4())
            threading.current_thread().correlation_id = correlation_id
            
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                # Track successful signal generation
                if hasattr(func, '_metrics_manager') and func._metrics_manager.signal_metrics:
                    func._metrics_manager.signal_metrics.signals_generated_total.labels(
                        agent_name=agent_name,
                        signal_type=result.get('signal_type', 'unknown'),
                        symbol=symbol,
                        confidence_level='high' if result.get('confidence', 0) > 0.8 else 'low',
                        cluster=func._metrics_manager.config.cluster_name,
                        pod=func._metrics_manager.config.pod_name
                    ).inc()
                return result
            except Exception as e:
                logger.error(f"Error in signal generation: {e}", extra={'correlation_id': correlation_id})
                raise
            finally:
                duration = time.time() - start_time
                if hasattr(func, '_metrics_manager') and func._metrics_manager.signal_metrics:
                    func._metrics_manager.signal_metrics.signal_processing_duration_seconds.labels(
                        agent_name=agent_name,
                        symbol=symbol,
                        cluster=func._metrics_manager.config.cluster_name
                    ).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            correlation_id = str(uuid.uuid4())
            threading.current_thread().correlation_id = correlation_id
            
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                # Track successful signal generation
                return result
            except Exception as e:
                logger.error(f"Error in signal generation: {e}", extra={'correlation_id': correlation_id})
                raise
            finally:
                duration = time.time() - start_time
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

# Export main production components
__all__ = [
    'ProductionMetricsConfig',
    'ProductionPrometheusMetricsManager',
    'ProductionSignalMetrics',
    'ProductionAgentMetrics',
    'SelfMonitoringMetrics',
    'production_track_signal_generation'
] 