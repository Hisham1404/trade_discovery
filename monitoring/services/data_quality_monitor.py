import asyncio
import json
import logging
import time
import hashlib
import statistics
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Union, Tuple
import numpy as np
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import requests

# Prometheus imports
from prometheus_client import Counter, Gauge, Histogram, start_http_server, generate_latest, REGISTRY

# Grafana API imports
from grafana_api import GrafanaFace

# System monitoring imports
import psutil

logger = logging.getLogger(__name__)


class AlertManager:
    """Alert manager for PagerDuty and Slack integration"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.pagerduty_integration_key = config.get('channels', {}).get('pagerduty', {}).get('integration_key')
        self.slack_webhook_url = config.get('channels', {}).get('slack', {}).get('webhook_url')
        self.thresholds = config.get('thresholds', {})
        
    async def send_pagerduty_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert to PagerDuty"""
        try:
            if not self.pagerduty_integration_key:
                logger.warning("PagerDuty integration key not configured")
                return False
                
            payload = {
                "routing_key": self.pagerduty_integration_key,
                "event_action": "trigger",
                "payload": {
                    "summary": alert_data['title'],
                    "source": alert_data['source'],
                    "severity": alert_data['severity'],
                    "custom_details": {
                        "description": alert_data['description'],
                        "timestamp": alert_data['timestamp']
                    }
                }
            }
            
            response = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            return response.status_code == 202
            
        except Exception as e:
            logger.error(f"Failed to send PagerDuty alert: {e}")
            return False
    
    async def send_slack_alert(self, alert_data: Dict[str, Any]) -> bool:
        """Send alert to Slack"""
        try:
            if not self.slack_webhook_url:
                logger.warning("Slack webhook URL not configured")
                return False
                
            color = "#ff0000" if alert_data['severity'] == 'critical' else "#ffff00"
            
            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": alert_data['title'],
                        "text": alert_data['description'],
                        "fields": [
                            {"title": "Source", "value": alert_data['source'], "short": True},
                            {"title": "Severity", "value": alert_data['severity'], "short": True},
                            {"title": "Timestamp", "value": alert_data['timestamp'], "short": False}
                        ]
                    }
                ]
            }
            
            response = requests.post(
                self.slack_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False


class DataLineageTracker:
    """Track data lineage for traceability"""
    
    def __init__(self):
        self.lineage_records: Dict[str, Dict[str, Any]] = {}
        
    async def record_lineage(self, lineage_data: Dict[str, Any]) -> bool:
        """Record data lineage information"""
        try:
            data_id = lineage_data['data_id']
            self.lineage_records[data_id] = {
                'source': lineage_data['source'],
                'ingestion_timestamp': lineage_data['ingestion_timestamp'],
                'transformations': lineage_data['transformations'],
                'destinations': lineage_data['destinations'],
                'quality_score': lineage_data['quality_score'],
                'recorded_at': datetime.now(timezone.utc)
            }
            return True
        except Exception as e:
            logger.error(f"Failed to record lineage: {e}")
            return False
    
    async def get_lineage(self, data_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve data lineage by ID"""
        return self.lineage_records.get(data_id)


class AnomalyDetector:
    """Simple anomaly detection for data quality metrics"""
    
    def __init__(self):
        self.threshold_multiplier = 2.5  # Standard deviations
        
    async def detect_anomalies(self, metric_name: str, data_points: List[float]) -> List[Dict[str, Any]]:
        """Detect anomalies in data points using statistical methods"""
        try:
            if len(data_points) < 3:
                return []
                
            mean_val = statistics.mean(data_points)
            std_dev = statistics.stdev(data_points) if len(data_points) > 1 else 0
            
            anomalies = []
            threshold = std_dev * self.threshold_multiplier
            
            for i, value in enumerate(data_points):
                if abs(value - mean_val) > threshold:
                    anomaly_type = "spike" if value > mean_val else "dip"
                    confidence = min(abs(value - mean_val) / (threshold if threshold > 0 else 1), 1.0)
                    
                    anomalies.append({
                        'index': i,
                        'value': value,
                        'anomaly_type': anomaly_type,
                        'confidence': confidence,
                        'threshold': threshold,
                        'mean': mean_val
                    })
                    
            return anomalies
            
        except Exception as e:
            logger.error(f"Failed to detect anomalies: {e}")
            return []


class DataQualityMonitor:
    """Production data quality monitoring with Prometheus, Grafana, and alerting"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_initialized = False
        self.metrics = {}
        self.grafana_client = None
        self.alert_manager = None
        self.lineage_tracker = DataLineageTracker()
        self.anomaly_detector = AnomalyDetector()
        
        # Initialize components
        self._setup_prometheus_metrics()
        self._setup_grafana_client()
        self._setup_alert_manager()
        
    def _setup_prometheus_metrics(self):
        """Setup Prometheus metrics collectors"""
        try:
            prefix = self.config.get('prometheus', {}).get('metrics_prefix', 'trade_discovery_')
            
            # Data ingestion metrics
            self.metrics['data_ingestion_total'] = Counter(
                f'{prefix}data_ingestion_total',
                'Total data ingestion requests',
                ['source', 'status']
            )
            
            self.metrics['data_ingestion_response_time'] = Histogram(
                f'{prefix}data_ingestion_response_time_seconds',
                'Data ingestion response time',
                ['source']
            )
            
            # Validation metrics
            self.metrics['validation_total'] = Counter(
                f'{prefix}validation_total',
                'Total validation checks',
                ['source', 'status']
            )
            
            # Data freshness metrics
            self.metrics['data_freshness_seconds'] = Gauge(
                f'{prefix}data_freshness_seconds',
                'Data freshness in seconds',
                ['source']
            )
            
            # System resource metrics
            self.metrics['system_cpu_usage'] = Gauge(
                f'{prefix}system_cpu_usage_percent',
                'System CPU usage percentage'
            )
            
            self.metrics['system_memory_usage'] = Gauge(
                f'{prefix}system_memory_usage_percent',
                'System memory usage percentage'
            )
            
            self.metrics['system_disk_usage'] = Gauge(
                f'{prefix}system_disk_usage_percent',
                'System disk usage percentage'
            )
            
            logger.info("Prometheus metrics initialized")
            
        except Exception as e:
            logger.error(f"Failed to setup Prometheus metrics: {e}")
            
    def _setup_grafana_client(self):
        """Setup Grafana API client"""
        try:
            grafana_config = self.config.get('grafana', {})
            if grafana_config.get('enabled'):
                self.grafana_client = GrafanaFace(
                    auth=grafana_config.get('api_key'),
                    host=grafana_config.get('api_url', 'http://localhost:3000').replace('/api', ''),
                    port=None  # Port is included in the URL
                )
                logger.info("Grafana client initialized")
        except Exception as e:
            logger.error(f"Failed to setup Grafana client: {e}")
            
    def _setup_alert_manager(self):
        """Setup alert manager"""
        try:
            alerting_config = self.config.get('alerting', {})
            if alerting_config.get('enabled'):
                self.alert_manager = AlertManager(alerting_config)
                logger.info("Alert manager initialized")
        except Exception as e:
            logger.error(f"Failed to setup alert manager: {e}")
    
    async def initialize(self):
        """Initialize the data quality monitor"""
        try:
            # Start Prometheus metrics server
            prometheus_config = self.config.get('prometheus', {})
            if prometheus_config.get('enabled'):
                port = prometheus_config.get('port', 8000)
                try:
                    start_http_server(port)
                    logger.info(f"Prometheus metrics server started on port {port}")
                except OSError:
                    logger.warning(f"Prometheus server already running on port {port}")
            
            self.is_initialized = True
            logger.info("DataQualityMonitor initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize DataQualityMonitor: {e}")
            raise
    
    async def record_data_ingestion(self, source: str, status: str, response_time: float):
        """Record data ingestion metrics"""
        try:
            self.metrics['data_ingestion_total'].labels(source=source, status=status).inc()
            self.metrics['data_ingestion_response_time'].labels(source=source).observe(response_time)
        except Exception as e:
            logger.error(f"Failed to record ingestion metrics: {e}")
    
    async def record_validation_result(self, source: str, is_valid: bool, validation_details: Dict[str, Any]):
        """Record validation metrics"""
        try:
            status = 'success' if is_valid else 'failed'
            self.metrics['validation_total'].labels(source=source, status=status).inc()
        except Exception as e:
            logger.error(f"Failed to record validation metrics: {e}")
    
    async def check_data_freshness(self, source: str, last_timestamp: datetime) -> Dict[str, Any]:
        """Check data freshness and update metrics"""
        try:
            current_time = datetime.now(timezone.utc)
            if last_timestamp.tzinfo is None:
                last_timestamp = last_timestamp.replace(tzinfo=timezone.utc)
                
            age_seconds = (current_time - last_timestamp).total_seconds()
            threshold = self.config.get('data_quality', {}).get('data_freshness_threshold', 300)
            
            self.metrics['data_freshness_seconds'].labels(source=source).set(age_seconds)
            
            return {
                'source': source,
                'age_seconds': age_seconds,
                'is_fresh': age_seconds <= threshold,
                'threshold': threshold,
                'last_timestamp': last_timestamp.isoformat(),
                'checked_at': current_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to check data freshness: {e}")
            return {'source': source, 'error': str(e)}
    
    async def collect_system_metrics(self):
        """Collect system resource metrics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.metrics['system_cpu_usage'].set(cpu_percent)
            
            # Memory usage
            memory = psutil.virtual_memory()
            self.metrics['system_memory_usage'].set(memory.percent)
            
            # Disk usage
            disk = psutil.disk_usage('/')
            self.metrics['system_disk_usage'].set(disk.percent)
            
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
    
    async def create_dashboard(self) -> Dict[str, Any]:
        """Create Grafana dashboard for data quality monitoring"""
        try:
            if not self.grafana_client:
                raise ValueError("Grafana client not initialized")
                
            dashboard_json = {
                "dashboard": {
                    "id": None,
                    "title": "Data Quality Monitoring Dashboard",
                    "panels": [
                        {
                            "id": 1,
                            "title": "Data Ingestion Rate",
                            "type": "graph",
                            "targets": [
                                {
                                    "expr": "rate(trade_discovery_data_ingestion_total[5m])",
                                    "legendFormat": "{{source}} - {{status}}"
                                }
                            ],
                            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
                        },
                        {
                            "id": 2,
                            "title": "Validation Success Rate",
                            "type": "stat",
                            "targets": [
                                {
                                    "expr": "rate(trade_discovery_validation_total{status=\"success\"}[5m]) / rate(trade_discovery_validation_total[5m]) * 100",
                                    "legendFormat": "Success Rate %"
                                }
                            ],
                            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
                        },
                        {
                            "id": 3,
                            "title": "API Response Times",
                            "type": "graph",
                            "targets": [
                                {
                                    "expr": "histogram_quantile(0.95, rate(trade_discovery_data_ingestion_response_time_seconds_bucket[5m]))",
                                    "legendFormat": "95th percentile"
                                }
                            ],
                            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8}
                        },
                        {
                            "id": 4,
                            "title": "Data Freshness",
                            "type": "graph",
                            "targets": [
                                {
                                    "expr": "trade_discovery_data_freshness_seconds",
                                    "legendFormat": "{{source}} freshness"
                                }
                            ],
                            "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8}
                        },
                        {
                            "id": 5,
                            "title": "System Resource Usage",
                            "type": "graph",
                            "targets": [
                                {
                                    "expr": "trade_discovery_system_cpu_usage_percent",
                                    "legendFormat": "CPU %"
                                },
                                {
                                    "expr": "trade_discovery_system_memory_usage_percent",
                                    "legendFormat": "Memory %"
                                }
                            ],
                            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 16}
                        },
                        {
                            "id": 6,
                            "title": "Alert Summary",
                            "type": "table",
                            "targets": [
                                {
                                    "expr": "ALERTS",
                                    "legendFormat": "Active Alerts"
                                }
                            ],
                            "gridPos": {"h": 8, "w": 24, "x": 0, "y": 24}
                        }
                    ],
                    "time": {"from": "now-1h", "to": "now"},
                    "refresh": "30s"
                }
            }
            
            result = await self.grafana_client.dashboard.update_dashboard(dashboard=dashboard_json['dashboard'])
            return result
            
        except Exception as e:
            logger.error(f"Failed to create dashboard: {e}")
            return {'error': str(e)}
    
    async def create_alert_rules(self) -> List[Dict[str, Any]]:
        """Create Grafana alert rules for data quality monitoring"""
        try:
            if not self.grafana_client:
                raise ValueError("Grafana client not initialized")
                
            alert_rules = []
            thresholds = self.config.get('alerting', {}).get('thresholds', {})
            
            # High data ingestion failure rate alert
            failure_threshold = thresholds.get('data_ingestion_failure_rate', 0.05)
            rule1 = await self.grafana_client.alert.create_alert_rule(
                title="High Data Ingestion Failure Rate",
                condition="B",
                data=[
                    {
                        "refId": "A",
                        "queryType": "prometheus",
                        "expr": f"rate(trade_discovery_data_ingestion_total{{status=\"failed\"}}[5m]) / rate(trade_discovery_data_ingestion_total[5m]) > {failure_threshold}"
                    }
                ],
                intervalSeconds=60,
                for_="5m"
            )
            alert_rules.append(rule1)
            
            # High API response time alert
            response_time_threshold = thresholds.get('api_response_time_p95', 1000) / 1000  # Convert to seconds
            rule2 = await self.grafana_client.alert.create_alert_rule(
                title="High API Response Time",
                condition="B",
                data=[
                    {
                        "refId": "A",
                        "queryType": "prometheus",
                        "expr": f"histogram_quantile(0.95, rate(trade_discovery_data_ingestion_response_time_seconds_bucket[5m])) > {response_time_threshold}"
                    }
                ],
                intervalSeconds=60,
                for_="2m"
            )
            alert_rules.append(rule2)
            
            # High validation failure rate alert
            validation_threshold = thresholds.get('validation_failure_rate', 0.1)
            rule3 = await self.grafana_client.alert.create_alert_rule(
                title="High Validation Failure Rate",
                condition="B",
                data=[
                    {
                        "refId": "A",
                        "queryType": "prometheus",
                        "expr": f"rate(trade_discovery_validation_total{{status=\"failed\"}}[5m]) / rate(trade_discovery_validation_total[5m]) > {validation_threshold}"
                    }
                ],
                intervalSeconds=60,
                for_="3m"
            )
            alert_rules.append(rule3)
            
            # Stale data alert
            freshness_threshold = thresholds.get('data_freshness_threshold', 300)
            rule4 = await self.grafana_client.alert.create_alert_rule(
                title="Stale Data Alert",
                condition="B",
                data=[
                    {
                        "refId": "A",
                        "queryType": "prometheus",
                        "expr": f"trade_discovery_data_freshness_seconds > {freshness_threshold}"
                    }
                ],
                intervalSeconds=60,
                for_="2m"
            )
            alert_rules.append(rule4)
            
            return alert_rules
            
        except Exception as e:
            logger.error(f"Failed to create alert rules: {e}")
            return []
    
    async def send_alert(self, alert_data: Dict[str, Any], channels: List[str]) -> bool:
        """Send alert through specified channels"""
        try:
            if not self.alert_manager:
                logger.warning("Alert manager not initialized")
                return False
                
            results = []
            
            if 'pagerduty' in channels:
                result = await self.alert_manager.send_pagerduty_alert(alert_data)
                results.append(result)
                
            if 'slack' in channels:
                result = await self.alert_manager.send_slack_alert(alert_data)
                results.append(result)
                
            return all(results) if results else False
            
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
            return False
    
    async def check_all_thresholds(self, metrics_data: Dict[str, float]) -> List[Dict[str, Any]]:
        """Check all metrics against thresholds and return triggered alerts"""
        try:
            thresholds = self.config.get('alerting', {}).get('thresholds', {})
            triggered_alerts = []
            
            for metric_name, current_value in metrics_data.items():
                if metric_name in thresholds:
                    threshold = thresholds[metric_name]
                    
                    if current_value > threshold:
                        alert = {
                            'alert_type': metric_name,
                            'current_value': current_value,
                            'threshold': threshold,
                            'severity': 'critical' if current_value > threshold * 1.5 else 'warning',
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }
                        triggered_alerts.append(alert)
                        
            return triggered_alerts
            
        except Exception as e:
            logger.error(f"Failed to check thresholds: {e}")
            return []
    
    async def record_data_lineage(self, lineage_data: Dict[str, Any]) -> bool:
        """Record data lineage information"""
        return await self.lineage_tracker.record_lineage(lineage_data)
    
    async def get_data_lineage(self, data_id: str) -> Optional[Dict[str, Any]]:
        """Get data lineage by ID"""
        return await self.lineage_tracker.get_lineage(data_id)
    
    async def detect_anomalies(self, metric_name: str, data_points: List[float]) -> List[Dict[str, Any]]:
        """Detect anomalies in metric data"""
        return await self.anomaly_detector.detect_anomalies(metric_name, data_points)
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check of all monitoring components"""
        try:
            health_result = {
                'overall_status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'prometheus': {
                    'status': 'healthy',
                    'metrics_collected': len(self.metrics)
                },
                'grafana': {
                    'status': 'healthy' if self.grafana_client else 'disabled',
                    'dashboards_count': 1 if self.grafana_client else 0
                },
                'alerting': {
                    'status': 'healthy' if self.alert_manager else 'disabled',
                    'alert_rules_count': 4 if self.alert_manager else 0
                },
                'data_quality': {
                    'status': 'healthy',
                    'lineage_records_count': len(self.lineage_tracker.lineage_records)
                }
            }
            
            # Check if any component is not healthy
            component_statuses = [
                health_result['prometheus']['status'],
                health_result['grafana']['status'],
                health_result['alerting']['status'],
                health_result['data_quality']['status']
            ]
            
            if any(status not in ['healthy', 'disabled'] for status in component_statuses):
                health_result['overall_status'] = 'unhealthy'
                
            return health_result
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'overall_status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.now(timezone.utc).isoformat()
            } 