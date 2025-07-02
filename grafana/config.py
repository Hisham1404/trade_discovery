"""
Configuration Module

MVP implementation for managing Grafana configuration files
and directory structures.
"""

import os
from typing import Dict, List, Any, Optional
from pathlib import Path


class MVPGrafanaConfig:
    """MVP Grafana Configuration manager"""
    
    def __init__(self):
        self.default_ports = {
            "http": 3000,
            "grpc": 9095
        }
        self.default_paths = {
            "data": "/var/lib/grafana",
            "logs": "/var/log/grafana",
            "plugins": "/var/lib/grafana/plugins",
            "provisioning": "/etc/grafana/provisioning"
        }
    
    def generate_ini_config(
        self,
        provisioning_path: str,
        data_path: str,
        logs_path: str,
        http_port: int = 3000,
        domain: str = "localhost",
        enable_anonymous: bool = False
    ) -> str:
        """Generate Grafana INI configuration"""
        
        config_content = f"""[default]
# Default settings

[paths]
# Paths for data storage
data = {data_path}
logs = {logs_path}
plugins = /var/lib/grafana/plugins
provisioning = {provisioning_path}

[server]
# Server settings
http_port = {http_port}
domain = {domain}
root_url = http://{domain}:{http_port}/
serve_from_sub_path = false

[database]
# Database settings (default SQLite)
type = sqlite3
host = 127.0.0.1:3306
name = grafana
user = root
password =
url =
path = grafana.db

[session]
# Session settings
provider = file
provider_config = sessions
cookie_name = grafana_sess
cookie_secure = false
session_life_time = 86400

[analytics]
# Analytics settings
reporting_enabled = false
check_for_updates = false

[security]
# Security settings
admin_user = admin
admin_password = admin
secret_key = SW2YcwTIb9zpOOhoPsMm
login_remember_days = 7
cookie_username = grafana_user
cookie_remember_name = grafana_remember

[snapshots]
# Snapshots
external_enabled = false

[dashboards]
# Dashboard settings
versions_to_keep = 20

[auth]
# Authentication
disable_login_form = false
disable_signout_menu = false

[auth.anonymous]
# Anonymous access
enabled = {str(enable_anonymous).lower()}
org_name = Main Org.
org_role = Viewer

[log]
# Logging
mode = console file
level = info

[log.console]
level = info
format = console

[log.file]
level = info
format = text
log_rotate = true
max_lines = 1000000
max_size_shift = 28
daily_rotate = true
max_days = 7

[alerting]
# Alerting
enabled = true
execute_alerts = true

[explore]
# Explore
enabled = true

[metrics]
# Internal metrics
enabled = true
interval_seconds = 10

[tracing]
# Tracing
enabled = false
"""
        
        return config_content
    
    def create_directory_structure(self, base_dir: str) -> Dict[str, str]:
        """Create required directory structure for Grafana"""
        
        directories = {
            "base": base_dir,
            "provisioning": os.path.join(base_dir, "provisioning"),
            "provisioning_dashboards": os.path.join(base_dir, "provisioning", "dashboards"),
            "provisioning_datasources": os.path.join(base_dir, "provisioning", "datasources"),
            "provisioning_plugins": os.path.join(base_dir, "provisioning", "plugins"),
            "dashboards": os.path.join(base_dir, "dashboards"),
            "data": os.path.join(base_dir, "data"),
            "logs": os.path.join(base_dir, "logs"),
            "plugins": os.path.join(base_dir, "plugins")
        }
        
        # Create all directories
        for name, path in directories.items():
            os.makedirs(path, exist_ok=True)
        
        return directories
    
    def save_ini_config(self, config_content: str, config_dir: str, filename: str = "grafana.ini") -> str:
        """Save INI configuration to file"""
        
        # Ensure config directory exists
        os.makedirs(config_dir, exist_ok=True)
        
        # Create full file path
        file_path = os.path.join(config_dir, filename)
        
        try:
            # Write INI config
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(config_content)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to save INI config: {str(e)}")
    
    def create_docker_compose_config(
        self,
        grafana_image: str = "grafana/grafana:latest",
        prometheus_url: str = "http://prometheus:9090",
        grafana_port: int = 3000,
        admin_password: str = "admin"
    ) -> str:
        """Create Docker Compose configuration for Grafana"""
        
        docker_compose = f"""version: '3.8'

services:
  grafana:
    image: {grafana_image}
    container_name: trading-grafana
    ports:
      - "{grafana_port}:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD={admin_password}
      - GF_PATHS_PROVISIONING=/etc/grafana/provisioning
      - GF_AUTH_ANONYMOUS_ENABLED=false
      - GF_ANALYTICS_REPORTING_ENABLED=false
      - GF_ANALYTICS_CHECK_FOR_UPDATES=false
    volumes:
      - ./provisioning:/etc/grafana/provisioning
      - ./dashboards:/var/lib/grafana/dashboards
      - grafana-data:/var/lib/grafana
    networks:
      - trading-network
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://localhost:3000/api/health || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

volumes:
  grafana-data:
    driver: local

networks:
  trading-network:
    driver: bridge
"""
        
        return docker_compose
    
    def create_kubernetes_config(
        self,
        namespace: str = "trading-system",
        grafana_image: str = "grafana/grafana:latest",
        service_port: int = 3000
    ) -> str:
        """Create Kubernetes configuration for Grafana"""
        
        k8s_config = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {namespace}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-config
  namespace: {namespace}
data:
  grafana.ini: |
    [paths]
    data = /var/lib/grafana/
    logs = /var/log/grafana
    plugins = /var/lib/grafana/plugins
    provisioning = /etc/grafana/provisioning

    [server]
    http_port = 3000
    domain = localhost

    [analytics]
    reporting_enabled = false
    check_for_updates = false

    [auth.anonymous]
    enabled = false

    [log]
    mode = console
    level = info
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: {namespace}
  labels:
    app: grafana
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grafana
  template:
    metadata:
      labels:
        app: grafana
    spec:
      containers:
      - name: grafana
        image: {grafana_image}
        ports:
        - containerPort: 3000
        env:
        - name: GF_SECURITY_ADMIN_PASSWORD
          value: "admin"
        - name: GF_PATHS_PROVISIONING
          value: "/etc/grafana/provisioning"
        volumeMounts:
        - name: grafana-config
          mountPath: /etc/grafana/grafana.ini
          subPath: grafana.ini
        - name: grafana-provisioning
          mountPath: /etc/grafana/provisioning
        - name: grafana-data
          mountPath: /var/lib/grafana
        livenessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: grafana-config
        configMap:
          name: grafana-config
      - name: grafana-provisioning
        configMap:
          name: grafana-provisioning
      - name: grafana-data
        persistentVolumeClaim:
          claimName: grafana-pvc
---
apiVersion: v1
kind: Service
metadata:
  name: grafana-service
  namespace: {namespace}
spec:
  selector:
    app: grafana
  ports:
  - protocol: TCP
    port: {service_port}
    targetPort: 3000
  type: LoadBalancer
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: grafana-pvc
  namespace: {namespace}
spec:
  accessModes:
  - ReadWriteOnce
  resources:
    requests:
      storage: 10Gi
"""
        
        return k8s_config
    
    def save_docker_config(self, docker_compose_content: str, output_dir: str) -> str:
        """Save Docker Compose configuration"""
        
        file_path = os.path.join(output_dir, "docker-compose.yml")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(docker_compose_content)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to save Docker config: {str(e)}")
    
    def save_kubernetes_config(self, k8s_content: str, output_dir: str) -> str:
        """Save Kubernetes configuration"""
        
        file_path = os.path.join(output_dir, "grafana-k8s.yaml")
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(k8s_content)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to save Kubernetes config: {str(e)}") 