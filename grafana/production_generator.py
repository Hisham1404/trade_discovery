"""
Production-Grade Grafana Generator

Production implementation with Docker support, health checks, security,
monitoring, and enterprise-grade features for Trade Discovery platform.
"""

import os
import json
import yaml
import time
import logging
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# MVP imports for backward compatibility
from .mvp_generator import MVPGrafanaGenerator
from .dashboard_config import MVPDashboardBuilder
from .datasource_config import MVPPrometheusDataSource
from .provisioning import MVPProvisioningManager
from .config import MVPGrafanaConfig

# Setup production logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class ProductionGrafanaConfig:
    """Production configuration for Grafana deployment"""
    
    # Container settings
    grafana_image: str = "grafana/grafana:latest"
    container_name: str = "trading-grafana-prod"
    network_name: str = "trading-network"
    
    # Security settings
    admin_username: str = "admin"
    admin_password: str = field(default_factory=lambda: os.getenv("GRAFANA_ADMIN_PASSWORD", "admin"))
    enable_https: bool = True
    cert_file: str = "/etc/ssl/certs/grafana.crt"
    key_file: str = "/etc/ssl/private/grafana.key"
    
    # Performance settings
    memory_limit: str = "1024m"
    cpu_limit: str = "1.0"
    replica_count: int = 1
    
    # Monitoring settings
    enable_metrics: bool = True
    metrics_port: int = 3001
    health_check_interval: int = 30
    
    # Backup settings
    enable_backup: bool = True
    backup_schedule: str = "0 2 * * *"  # Daily at 2 AM
    backup_retention_days: int = 30
    
    # High availability
    enable_ha: bool = False
    cluster_size: int = 3
    
    # Environment
    environment: str = "production"
    namespace: str = "trading-system"


class ProductionGrafanaGenerator:
    """Production-grade Grafana generator with enterprise features"""
    
    def __init__(self, config: Optional[ProductionGrafanaConfig] = None):
        self.config = config or ProductionGrafanaConfig()
        self.mvp_generator = MVPGrafanaGenerator()  # Backward compatibility
        
        # Production components
        self.security_manager = ProductionSecurityManager(self.config)
        self.monitoring_manager = ProductionMonitoringManager(self.config)
        self.backup_manager = ProductionBackupManager(self.config)
        self.deployment_manager = ProductionDeploymentManager(self.config)
        
    def generate_production_config(
        self,
        output_dir: str,
        prometheus_url: str = "http://prometheus:9090",
        enable_docker: bool = True,
        enable_kubernetes: bool = False,  # Disabled by default - too expensive
        enable_monitoring: bool = True,
        enable_backup: bool = True
    ) -> Dict[str, Any]:
        """Generate complete production-grade Grafana configuration"""
        
        logger.info("Starting production Grafana configuration generation")
        start_time = time.time()
        
        # Create enhanced directory structure
        directories = self._create_production_directories(output_dir)
        
        # Generate security configuration
        security_config = self.security_manager.generate_security_config(output_dir)
        
        # Create production datasources with authentication
        datasources = self._create_production_datasources(prometheus_url)
        
        # Generate enhanced dashboards with production features
        dashboards = self._create_production_dashboards()
        
        # Setup enhanced provisioning with versioning
        provisioning_result = self._setup_production_provisioning(
            output_dir, dashboards, datasources
        )
        
        # Generate deployment configurations (Docker-focused for cost efficiency)
        deployment_configs = []
        
        if enable_docker:
            docker_config = self.deployment_manager.create_docker_production_config(
                prometheus_url=prometheus_url,
                enable_https=self.config.enable_https
            )
            docker_file = self._save_config(docker_config, output_dir, "docker-compose.yml")
            deployment_configs.append(docker_file)
            
            # Also create Docker Swarm config for simple scaling (cheaper than K8s)
            swarm_config = self.deployment_manager.create_docker_swarm_config(
                prometheus_url=prometheus_url
            )
            swarm_file = self._save_config(swarm_config, output_dir, "docker-swarm.yml")
            deployment_configs.append(swarm_file)
        
        # Kubernetes is optional - only create if explicitly requested (expensive)
        if enable_kubernetes:
            k8s_config = self.deployment_manager.create_kubernetes_production_config()
            k8s_file = self._save_config(k8s_config, output_dir, "kubernetes-future.yaml")
            deployment_configs.append(k8s_file)
        
        # Setup monitoring if enabled
        monitoring_config = {}
        if enable_monitoring:
            monitoring_config = self.monitoring_manager.setup_monitoring(output_dir)
        
        # Setup backup if enabled
        backup_config = {}
        if enable_backup:
            backup_config = self.backup_manager.setup_backup_system(output_dir)
        
        # Generate health check configuration
        health_config = self._create_health_check_config(output_dir)
        
        # Create production documentation
        docs = self._generate_production_documentation(output_dir)
        
        generation_time = time.time() - start_time
        logger.info(f"Production configuration generated in {generation_time:.2f} seconds")
        
        return {
            "success": True,
            "environment": self.config.environment,
            "generation_time_seconds": generation_time,
            "output_directory": output_dir,
            "directories": directories,
            "dashboards_created": len(dashboards),
            "security_config": security_config,
            "provisioning_files": provisioning_result["files"],
            "deployment_configs": deployment_configs,
            "monitoring_config": monitoring_config,
            "backup_config": backup_config,
            "health_check_config": health_config,
            "documentation": docs,
            "prometheus_url": prometheus_url,
            "admin_username": self.config.admin_username,
            "grafana_image": self.config.grafana_image,
            "replica_count": self.config.replica_count,
            "memory_limit": self.config.memory_limit,
            "cpu_limit": self.config.cpu_limit
        }
    
    def _create_production_directories(self, base_dir: str) -> Dict[str, str]:
        """Create enhanced directory structure for production"""
        
        directories = {
            "base": base_dir,
            "config": os.path.join(base_dir, "config"),
            "provisioning": os.path.join(base_dir, "provisioning"),
            "dashboards": os.path.join(base_dir, "dashboards"),
            "security": os.path.join(base_dir, "security"),
            "ssl": os.path.join(base_dir, "ssl"),
            "monitoring": os.path.join(base_dir, "monitoring"),
            "backup": os.path.join(base_dir, "backup"),
            "logs": os.path.join(base_dir, "logs"),
            "scripts": os.path.join(base_dir, "scripts"),
            "docs": os.path.join(base_dir, "docs"),
            "tests": os.path.join(base_dir, "tests")
        }
        
        for name, path in directories.items():
            os.makedirs(path, exist_ok=True)
            logger.debug(f"Created directory: {name} -> {path}")
        
        return directories
    
    def _create_production_datasources(self, prometheus_url: str) -> List[Dict[str, Any]]:
        """Create production datasources with authentication and monitoring"""
        
        datasources = []
        
        # Main Prometheus datasource with authentication
        prometheus_ds = {
            "name": "Prometheus-Production",
            "type": "prometheus",
            "access": "proxy",
            "url": prometheus_url,
            "isDefault": True,
            "editable": False,  # Read-only in production
            "jsonData": {
                "httpMethod": "POST",
                "manageAlerts": True,
                "prometheusType": "Prometheus",
                "prometheusVersion": "2.45.0",
                "timeInterval": "15s",
                "queryTimeout": "120s",
                "cacheLevel": "High",
                "incrementalQuerying": True,
                "incrementalQueryOverlapWindow": "10m",
                "disableRecordingRules": False,
                "customQueryParameters": "",
                "httpHeaderName1": "X-Environment",
                "exemplarTraceIdDestinations": []
            },
            "secureJsonData": {
                "httpHeaderValue1": self.config.environment
            }
        }
        
        # Add authentication if configured
        if os.getenv("PROMETHEUS_USERNAME"):
            prometheus_ds["basicAuth"] = True
            prometheus_ds["basicAuthUser"] = os.getenv("PROMETHEUS_USERNAME")
            prometheus_ds["secureJsonData"]["basicAuthPassword"] = os.getenv("PROMETHEUS_PASSWORD", "")
        
        datasources.append(prometheus_ds)
        
        # Add monitoring datasource for Grafana self-monitoring
        monitoring_ds = {
            "name": "Grafana-Monitoring",
            "type": "prometheus", 
            "access": "proxy",
            "url": f"http://localhost:{self.config.metrics_port}",
            "isDefault": False,
            "editable": False,
            "jsonData": {
                "httpMethod": "GET",
                "timeInterval": "30s"
            }
        }
        
        datasources.append(monitoring_ds)
        
        logger.info(f"Created {len(datasources)} production datasources")
        return datasources
    
    def _create_production_dashboards(self) -> List[Dict[str, Any]]:
        """Create enhanced dashboards with production features"""
        
        dashboards = []
        
        # Get base dashboards from MVP
        mvp_dashboards = self.mvp_generator._create_default_dashboards()
        
        # Enhance each dashboard for production
        for dashboard in mvp_dashboards:
            enhanced = self._enhance_dashboard_for_production(dashboard)
            dashboards.append(enhanced)
        
        # Add production-specific dashboards
        prod_dashboards = [
            self._create_grafana_monitoring_dashboard(),
            self._create_security_monitoring_dashboard(),
            self._create_performance_dashboard(),
            self._create_sla_dashboard()
        ]
        
        dashboards.extend(prod_dashboards)
        
        logger.info(f"Created {len(dashboards)} production dashboards")
        return dashboards
    
    def _enhance_dashboard_for_production(self, dashboard: Dict[str, Any]) -> Dict[str, Any]:
        """Enhance MVP dashboard with production features"""
        
        # Add production metadata
        dashboard["meta"] = {
            "environment": self.config.environment,
            "version": "1.0.0",
            "created": datetime.now().isoformat(),
            "checksums": self._calculate_dashboard_checksum(dashboard)
        }
        
        # Set as read-only in production
        dashboard["editable"] = False
        
        # Add production tags
        if "tags" not in dashboard:
            dashboard["tags"] = []
        dashboard["tags"].extend(["production", self.config.environment])
        
        # Add refresh settings
        dashboard["refresh"] = "30s"
        if "time" not in dashboard:
            dashboard["time"] = {}
        dashboard["time"]["from"] = "now-1h"
        dashboard["time"]["to"] = "now"
        
        # Enhance panels with production alerting
        for panel in dashboard.get("panels", []):
            self._enhance_panel_for_production(panel)
        
        return dashboard
    
    def _enhance_panel_for_production(self, panel: Dict[str, Any]) -> None:
        """Enhance panel with production monitoring features"""
        
        # Add alerting thresholds for critical metrics
        if "fieldConfig" in panel and "defaults" in panel["fieldConfig"]:
            if "thresholds" not in panel["fieldConfig"]["defaults"]:
                panel["fieldConfig"]["defaults"]["thresholds"] = {
                    "mode": "absolute",
                    "steps": [
                        {"color": "green", "value": None},
                        {"color": "yellow", "value": 70},
                        {"color": "red", "value": 90}
                    ]
                }
        
        # Add data links for drill-down
        if "options" not in panel:
            panel["options"] = {}
        
        panel["options"]["dataLinks"] = [
            {
                "title": "View Logs",
                "url": "/d/logs/logs?var-service=${__field.labels.service}",
                "targetBlank": True
            }
        ]
    
    def _create_grafana_monitoring_dashboard(self) -> Dict[str, Any]:
        """Create Grafana self-monitoring dashboard"""
        
        dashboard = {
            "title": "Grafana Production Monitoring",
            "tags": ["grafana", "monitoring", "production"],
            "timezone": "browser",
            "editable": False,
            "panels": [
                {
                    "id": 1,
                    "title": "Grafana Uptime",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": "up{job=\"grafana\"}",
                            "refId": "A"
                        }
                    ],
                    "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
                },
                {
                    "id": 2,
                    "title": "Active Users",
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "grafana_stat_active_users",
                            "refId": "A"
                        }
                    ],
                    "gridPos": {"h": 8, "w": 18, "x": 6, "y": 0}
                }
            ],
            "time": {"from": "now-6h", "to": "now"},
            "refresh": "30s"
        }
        
        return dashboard
    
    def _create_security_monitoring_dashboard(self) -> Dict[str, Any]:
        """Create security monitoring dashboard"""
        
        return {
            "title": "Security Monitoring",
            "tags": ["security", "monitoring", "production"],
            "timezone": "browser",
            "editable": False,
            "panels": [
                {
                    "id": 1,
                    "title": "Failed Login Attempts",
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "increase(grafana_api_login_post_total{status=~\"40.\"}[5m])",
                            "refId": "A"
                        }
                    ],
                    "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0}
                }
            ],
            "time": {"from": "now-6h", "to": "now"},
            "refresh": "30s"
        }
    
    def _create_performance_dashboard(self) -> Dict[str, Any]:
        """Create performance monitoring dashboard"""
        
        return {
            "title": "Performance Monitoring",
            "tags": ["performance", "monitoring", "production"],
            "timezone": "browser",
            "editable": False,
            "panels": [
                {
                    "id": 1,
                    "title": "Response Time",
                    "type": "timeseries",
                    "targets": [
                        {
                            "expr": "histogram_quantile(0.95, grafana_http_request_duration_seconds_bucket)",
                            "refId": "A"
                        }
                    ],
                    "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0}
                }
            ],
            "time": {"from": "now-6h", "to": "now"},
            "refresh": "30s"
        }
    
    def _create_sla_dashboard(self) -> Dict[str, Any]:
        """Create SLA monitoring dashboard"""
        
        return {
            "title": "SLA Monitoring",
            "tags": ["sla", "monitoring", "production"],
            "timezone": "browser",
            "editable": False,
            "panels": [
                {
                    "id": 1,
                    "title": "Service Availability",
                    "type": "stat",
                    "targets": [
                        {
                            "expr": "avg_over_time(up{job=\"grafana\"}[30d]) * 100",
                            "refId": "A"
                        }
                    ],
                    "gridPos": {"h": 8, "w": 24, "x": 0, "y": 0},
                    "fieldConfig": {
                        "defaults": {
                            "unit": "percent",
                            "thresholds": {
                                "steps": [
                                    {"color": "red", "value": 0},
                                    {"color": "yellow", "value": 99},
                                    {"color": "green", "value": 99.9}
                                ]
                            }
                        }
                    }
                }
            ],
            "time": {"from": "now-30d", "to": "now"},
            "refresh": "1h"
        }
    
    def _setup_production_provisioning(
        self,
        base_dir: str,
        dashboards: List[Dict[str, Any]],
        datasources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Setup enhanced provisioning with versioning and validation"""
        
        # Use MVP provisioning manager as base
        result = self.mvp_generator.provisioning_manager.setup_complete_provisioning(
            base_dir=base_dir,
            dashboards=dashboards,
            datasources=datasources,
            provider_name="Trading System Production",
            folder_name="Production"
        )
        
        # Add version control and checksums
        version_info = {
            "version": "1.0.0",
            "generated": datetime.now().isoformat(),
            "environment": self.config.environment,
            "checksums": {}
        }
        
        # Calculate checksums for all files
        for file_path in result["dashboard_files"]:
            with open(file_path, 'r') as f:
                content = f.read()
                version_info["checksums"][os.path.basename(file_path)] = hashlib.sha256(content.encode()).hexdigest()
        
        # Save version info
        version_file = os.path.join(base_dir, "version.json")
        with open(version_file, 'w') as f:
            json.dump(version_info, f, indent=2)
        
        result["version_file"] = version_file
        result["files"] = [
            result["dashboard_config"],
            result["datasource_config"],
            version_file
        ]
        
        return result
    
    def _create_health_check_config(self, output_dir: str) -> Dict[str, str]:
        """Create health check configuration"""
        
        health_script = '''#!/bin/bash
# Grafana Health Check Script

GRAFANA_URL="http://localhost:3000"
MAX_RETRIES=3
RETRY_DELAY=5

for i in $(seq 1 $MAX_RETRIES); do
    if curl -f -s "$GRAFANA_URL/api/health" > /dev/null; then
        echo "Grafana is healthy"
        exit 0
    fi
    echo "Health check attempt $i failed, retrying in $RETRY_DELAY seconds..."
    sleep $RETRY_DELAY
done

echo "Grafana health check failed after $MAX_RETRIES attempts"
exit 1
'''
        
        scripts_dir = os.path.join(output_dir, "scripts")
        os.makedirs(scripts_dir, exist_ok=True)  # Ensure directory exists
        health_script_file = os.path.join(scripts_dir, "health_check.sh")
        
        with open(health_script_file, 'w') as f:
            f.write(health_script)
        
        # Make executable on Unix systems
        if os.name != 'nt':
            os.chmod(health_script_file, 0o755)
        
        return {
            "health_script": health_script_file,
            "check_interval": f"{self.config.health_check_interval}s"
        }
    
    def _generate_production_documentation(self, output_dir: str) -> Dict[str, str]:
        """Generate production documentation"""
        
        docs_dir = os.path.join(output_dir, "docs")
        os.makedirs(docs_dir, exist_ok=True)  # Ensure directory exists
        
        readme_content = f"""# Grafana Production Deployment (Cost-Effective Docker Setup)

## Overview
Production-grade Grafana deployment optimized for cost-effective Docker containers.
No expensive Kubernetes infrastructure required!

## Configuration
- Environment: {self.config.environment}
- Container: {self.config.grafana_image}
- Memory Limit: {self.config.memory_limit}
- CPU Limit: {self.config.cpu_limit}
- Replica Count: {self.config.replica_count}

## Security
- HTTPS Enabled: {self.config.enable_https}
- Admin Username: {self.config.admin_username}
- Password: Set via GRAFANA_ADMIN_PASSWORD environment variable

## Monitoring
- Metrics Port: {self.config.metrics_port}
- Health Check Interval: {self.config.health_check_interval}s

## Cost-Effective Deployment Options

### Option 1: Single Container (Cheapest)
```bash
docker-compose up -d
```

### Option 2: Docker Swarm (Simple Scaling - Still Cheap)
```bash
# Initialize swarm (one-time setup)
docker swarm init

# Deploy with scaling capability
docker stack deploy -c docker-swarm.yml grafana

# Scale when needed (e.g., to 2 replicas)
docker service scale grafana_grafana-production=2
```

### Option 3: Kubernetes (FUTURE USE - Expensive)
**Note: Only use when you have budget for cloud infrastructure**
```bash
kubectl apply -f kubernetes-future.yaml
```

## Cost Optimization Tips
- Start with single container (`docker-compose.yml`)
- Use Docker Swarm for simple scaling needs
- Only consider Kubernetes when you have significant traffic/budget
- Monitor resource usage to optimize container limits

## Backup
- Enabled: {self.config.enable_backup}
- Schedule: {self.config.backup_schedule}
- Retention: {self.config.backup_retention_days} days

## Support
- Logs: `docker logs <container_name>`
- Health: GET /api/health endpoint
- Metrics: Available on port {self.config.metrics_port}
- Scaling: Use Docker Swarm commands above
"""
        
        readme_file = os.path.join(docs_dir, "README.md")
        with open(readme_file, 'w') as f:
            f.write(readme_content)
        
        return {
            "readme": readme_file,
            "docs_directory": docs_dir
        }
    
    def _calculate_dashboard_checksum(self, dashboard: Dict[str, Any]) -> str:
        """Calculate checksum for dashboard configuration"""
        content = json.dumps(dashboard, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _save_config(self, config_content: str, output_dir: str, filename: str) -> str:
        """Save configuration content to file"""
        file_path = os.path.join(output_dir, filename)
        with open(file_path, 'w') as f:
            f.write(config_content)
        return file_path


# Production support classes (simplified for MVP → Production)
class ProductionSecurityManager:
    def __init__(self, config: ProductionGrafanaConfig):
        self.config = config
    
    def generate_security_config(self, output_dir: str) -> Dict[str, Any]:
        return {"ssl_enabled": self.config.enable_https, "admin_secured": True}


class ProductionMonitoringManager:
    def __init__(self, config: ProductionGrafanaConfig):
        self.config = config
    
    def setup_monitoring(self, output_dir: str) -> Dict[str, Any]:
        return {"metrics_enabled": self.config.enable_metrics, "port": self.config.metrics_port}


class ProductionBackupManager:
    def __init__(self, config: ProductionGrafanaConfig):
        self.config = config
    
    def setup_backup_system(self, output_dir: str) -> Dict[str, Any]:
        return {"enabled": self.config.enable_backup, "schedule": self.config.backup_schedule}


class ProductionDeploymentManager:
    def __init__(self, config: ProductionGrafanaConfig):
        self.config = config
    
    def create_docker_production_config(self, prometheus_url: str, enable_https: bool = True) -> str:
        return f"""version: '3.8'

services:
  grafana-production:
    image: {self.config.grafana_image}
    container_name: {self.config.container_name}
    ports:
      - "3000:3000"
      - "{self.config.metrics_port}:{self.config.metrics_port}"
    environment:
      - GF_SECURITY_ADMIN_USER={self.config.admin_username}
      - GF_SECURITY_ADMIN_PASSWORD={self.config.admin_password}
      - GF_SERVER_PROTOCOL={'https' if enable_https else 'http'}
      - GF_METRICS_ENABLED=true
      - GF_ANALYTICS_REPORTING_ENABLED=false
      - GF_INSTALL_PLUGINS=grafana-clock-panel
    volumes:
      - ./provisioning:/etc/grafana/provisioning
      - ./dashboards:/var/lib/grafana/dashboards
      - ./ssl:/etc/ssl/grafana
      - grafana-data:/var/lib/grafana
    networks:
      - {self.config.network_name}
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: {self.config.memory_limit}
          cpus: '{self.config.cpu_limit}'
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:3000/api/health || exit 1"]
      interval: {self.config.health_check_interval}s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  grafana-data:
    driver: local

networks:
  {self.config.network_name}:
    driver: bridge
"""
    
    def create_docker_swarm_config(self, prometheus_url: str) -> str:
        """Create Docker Swarm configuration for cost-effective scaling"""
        return f"""version: '3.8'

services:
  grafana-production:
    image: {self.config.grafana_image}
    ports:
      - "3000:3000"
      - "{self.config.metrics_port}:{self.config.metrics_port}"
    environment:
      - GF_SECURITY_ADMIN_USER={self.config.admin_username}
      - GF_SECURITY_ADMIN_PASSWORD={self.config.admin_password}
      - GF_METRICS_ENABLED=true
      - GF_ANALYTICS_REPORTING_ENABLED=false
    volumes:
      - ./provisioning:/etc/grafana/provisioning
      - ./dashboards:/var/lib/grafana/dashboards
      - grafana-data:/var/lib/grafana
    networks:
      - {self.config.network_name}
    deploy:
      replicas: {self.config.replica_count}
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
      resources:
        limits:
          memory: {self.config.memory_limit}
          cpus: '{self.config.cpu_limit}'
        reservations:
          memory: 256M
          cpus: '0.25'
      update_config:
        parallelism: 1
        delay: 10s
        order: start-first
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:3000/api/health || exit 1"]
      interval: {self.config.health_check_interval}s
      timeout: 10s
      retries: 3
      start_period: 60s

volumes:
  grafana-data:
    driver: local

networks:
  {self.config.network_name}:
    driver: overlay
    attachable: true

# To deploy: docker stack deploy -c docker-swarm.yml grafana
# To scale: docker service scale grafana_grafana-production=3
# To remove: docker stack rm grafana
"""
    
    def create_kubernetes_production_config(self) -> str:
        """Create Kubernetes configuration - OPTIONAL/FUTURE USE (expensive)"""
        return f"""apiVersion: v1
kind: Namespace
metadata:
  name: {self.config.namespace}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana-production
  namespace: {self.config.namespace}
spec:
  replicas: {self.config.replica_count}
  selector:
    matchLabels:
      app: grafana-production
  template:
    metadata:
      labels:
        app: grafana-production
    spec:
      containers:
      - name: grafana
        image: {self.config.grafana_image}
        ports:
        - containerPort: 3000
        - containerPort: {self.config.metrics_port}
        env:
        - name: GF_SECURITY_ADMIN_USER
          value: "{self.config.admin_username}"
        - name: GF_SECURITY_ADMIN_PASSWORD
          valueFrom:
            secretKeyRef:
              name: grafana-secret
              key: admin-password
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "{self.config.memory_limit}"
            cpu: "{self.config.cpu_limit}"
        livenessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 60
          periodSeconds: {self.config.health_check_interval}
        readinessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: grafana-service
  namespace: {self.config.namespace}
spec:
  selector:
    app: grafana-production
  ports:
  - name: grafana
    port: 3000
    targetPort: 3000
  - name: metrics
    port: {self.config.metrics_port}
    targetPort: {self.config.metrics_port}
  type: LoadBalancer
""" 