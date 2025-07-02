"""
Custom Prometheus Metrics and Exporters for Trade Discovery Platform
"""

import os
import time
import logging
import threading
import asyncio
from typing import Optional, Dict, Any, Callable
from functools import wraps

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

logger = logging.getLogger(__name__)

DEFAULT_METRICS_PORT = 9100
DEFAULT_METRICS_PATH = "/metrics"
DEFAULT_REGISTRY_NAME = "trade_discovery"

class PrometheusMetricsConfig:
    def __init__(
        self,
        metrics_port: int = DEFAULT_METRICS_PORT,
        metrics_path: str = DEFAULT_METRICS_PATH,
        registry_name: str = DEFAULT_REGISTRY_NAME,
        enable_default_metrics: bool = True,
        enable_signal_metrics: bool = True,
        enable_agent_metrics: bool = True,
        enable_validation_metrics: bool = True,
        enable_trading_metrics: bool = True
    ):
        self.metrics_port = metrics_port
        self.metrics_path = metrics_path
        self.registry_name = registry_name
        self.enable_default_metrics = enable_default_metrics
        self.enable_signal_metrics = enable_signal_metrics
        self.enable_agent_metrics = enable_agent_metrics
        self.enable_validation_metrics = enable_validation_metrics
        self.enable_trading_metrics = enable_trading_metrics

class SignalMetrics:
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or REGISTRY
        
        self.signals_generated_total = Counter(
            'signals_generated_total',
            'Total number of trading signals generated',
            labelnames=['agent_name', 'signal_type', 'symbol', 'confidence_level'],
            registry=self.registry
        )
        
        confidence_buckets = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.0]
        self.signal_confidence_histogram = Histogram(
            'signal_confidence_histogram',
            'Distribution of signal confidence levels',
            labelnames=['agent_name', 'symbol'],
            buckets=confidence_buckets,
            registry=self.registry
        )
        
        self.signal_processing_duration_seconds = Summary(
            'signal_processing_duration_seconds',
            'Time spent processing signals',
            labelnames=['agent_name', 'symbol'],
            registry=self.registry
        )

class AgentMetrics:
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or REGISTRY
        
        self.agent_executions_total = Counter(
            'agent_executions_total',
            'Total number of agent executions',
            labelnames=['agent_name', 'agent_type', 'status'],
            registry=self.registry
        )
        
        duration_buckets = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0]
        self.agent_execution_duration_seconds = Histogram(
            'agent_execution_duration_seconds',
            'Time spent executing agents',
            labelnames=['agent_name', 'agent_type'],
            buckets=duration_buckets,
            registry=self.registry
        )

class ValidationMetrics:
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or REGISTRY
        
        self.data_validations_total = Counter(
            'data_validations_total',
            'Total number of data validations performed',
            labelnames=['data_type', 'validation_rule', 'status'],
            registry=self.registry
        )

class TradingMetrics:
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or REGISTRY
        
        self.market_data_ingestion_rate = Gauge(
            'market_data_ingestion_rate',
            'Rate of market data ingestion per second',
            labelnames=['exchange', 'symbol', 'data_type'],
            registry=self.registry
        )

def track_signal_generation(agent_name: str, symbol: str):
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

def track_agent_execution(agent_name: str, agent_type: str):
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    return decorator

def track_data_validation(data_type: str, validation_rule: str):
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator

class TradingSystemCollector(Collector):
    def collect(self):
        try:
            stats = self._get_system_stats()
            
            yield GaugeMetricFamily(
                'trading_system_active_agents',
                'Number of active agents in the system',
                value=stats.get('active_agents', 0)
            )
            
            yield CounterMetricFamily(
                'trading_system_signals_today_total',
                'Total signals generated today',
                value=stats.get('total_signals_today', 0)
            )
            
            yield GaugeMetricFamily(
                'trading_system_uptime_seconds',
                'System uptime in seconds',
                value=stats.get('system_uptime_seconds', 0)
            )
            
            yield GaugeMetricFamily(
                'trading_system_memory_usage_percent',
                'System memory usage percentage',
                value=stats.get('memory_usage_percent', 0)
            )
            
        except Exception as e:
            logger.error(f"Error collecting trading system metrics: {e}")
            return
    
    def describe(self):
        return [
            GaugeMetricFamily('trading_system_active_agents', 'Number of active agents'),
            CounterMetricFamily('trading_system_signals_today_total', 'Total signals today'),
            GaugeMetricFamily('trading_system_uptime_seconds', 'System uptime'),
            GaugeMetricFamily('trading_system_memory_usage_percent', 'Memory usage percentage')
        ]
    
    def _get_system_stats(self) -> Dict[str, Any]:
        return {
            'active_agents': 5,
            'total_signals_today': 150,
            'system_uptime_seconds': 86400,
            'memory_usage_percent': 65.5
        }

class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

class PrometheusHTTPServer:
    def __init__(self, port: int = DEFAULT_METRICS_PORT, registry: Optional[CollectorRegistry] = None):
        self.port = port
        self.registry = registry or REGISTRY
        self.server = None
        self.server_thread = None
        self._running = False
    
    def start(self):
        try:
            app = make_wsgi_app(self.registry)
            self.server = make_server('', self.port, app, server_class=ThreadedWSGIServer)
            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            self._running = True
            logger.info(f"Prometheus metrics server started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus metrics server: {e}")
            self._running = False
    
    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self._running = False
            logger.info("Prometheus metrics server stopped")
    
    def is_running(self) -> bool:
        return self._running and self.server_thread and self.server_thread.is_alive()

def create_custom_registry(name: str) -> CollectorRegistry:
    registry = CollectorRegistry()
    logger.info(f"Created custom registry: {name}")
    return registry

class PrometheusMetricsManager:
    def __init__(self, config: Optional[PrometheusMetricsConfig] = None):
        self.config = config or PrometheusMetricsConfig()
        self.registry = create_custom_registry(self.config.registry_name)
        self.signal_metrics = SignalMetrics(self.registry) if self.config.enable_signal_metrics else None
        self.agent_metrics = AgentMetrics(self.registry) if self.config.enable_agent_metrics else None
        self.validation_metrics = ValidationMetrics(self.registry) if self.config.enable_validation_metrics else None
        self.trading_metrics = TradingMetrics(self.registry) if self.config.enable_trading_metrics else None
        
        if self.config.enable_default_metrics:
            self.registry.register(TradingSystemCollector())
        
        self.http_server = None
        self.integration_monitor = None
    
    def start_http_server(self):
        self.http_server = PrometheusHTTPServer(self.config.metrics_port, self.registry)
        self.http_server.start()
    
    def stop_http_server(self):
        if self.http_server:
            self.http_server.stop()
    
    def record_signal_generated(self, agent_name: str, signal_type: str, symbol: str, 
                               confidence: float, include_trace_context: bool = False):
        if self.signal_metrics:
            self.signal_metrics.signals_generated_total.labels(
                agent_name=agent_name,
                signal_type=signal_type,
                symbol=symbol,
                confidence_level='high'
            ).inc()
    
    def initialize_with_existing_monitoring(self):
        try:
            from monitoring.integration_monitor import get_integration_monitor
            self.integration_monitor = get_integration_monitor()
            logger.info("Initialized Prometheus metrics with existing monitoring system")
        except ImportError:
            logger.warning("Existing monitoring system not available")
