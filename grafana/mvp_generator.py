"""
MVP Generator Module

Main coordinator for Grafana dashboard and configuration generation.
Provides the primary interface for creating complete Grafana setups.
"""

import os
import time
from typing import Dict, List, Any, Optional

from .dashboard_config import MVPDashboardBuilder
from .datasource_config import MVPPrometheusDataSource
from .panels import MVPTimeSeriesPanel, MVPStatPanel, MVPPanelGrid
from .provisioning import MVPProvisioningManager
from .trading_dashboards import (
    MVPTradingOverviewDashboard,
    MVPSignalMetricsDashboard,
    MVPAgentMetricsDashboard,
    MVPSystemMetricsDashboard
)
from .config import MVPGrafanaConfig


class MVPGrafanaGenerator:
    """MVP Grafana Generator - Main coordination class"""
    
    def __init__(self):
        self.dashboard_builder = MVPDashboardBuilder()
        self.datasource = MVPPrometheusDataSource()
        self.provisioning_manager = MVPProvisioningManager()
        self.config_manager = MVPGrafanaConfig()
        
        # Pre-built dashboard templates
        self.trading_overview = MVPTradingOverviewDashboard()
        self.signal_metrics = MVPSignalMetricsDashboard()
        self.agent_metrics = MVPAgentMetricsDashboard()
        self.system_metrics = MVPSystemMetricsDashboard()
    
    def generate_complete_config(
        self,
        output_dir: str,
        prometheus_url: str = "http://localhost:9090",
        include_docker: bool = True,
        include_kubernetes: bool = False
    ) -> Dict[str, Any]:
        """Generate complete Grafana configuration"""
        
        # Create directory structure
        directories = self.config_manager.create_directory_structure(output_dir)
        
        # Create datasource configuration
        prometheus_config = self.datasource.create_config(
            name="Prometheus",
            url=prometheus_url
        )
        
        # Generate pre-built dashboards
        dashboards = self._create_default_dashboards()
        
        # Setup provisioning
        provisioning_result = self.provisioning_manager.setup_complete_provisioning(
            base_dir=output_dir,
            dashboards=dashboards,
            datasources=[prometheus_config]
        )
        
        # Generate additional configs if requested
        additional_configs = []
        
        if include_docker:
            docker_config = self.config_manager.create_docker_compose_config(
                prometheus_url=prometheus_url
            )
            docker_file = self.config_manager.save_docker_config(docker_config, output_dir)
            additional_configs.append(docker_file)
        
        if include_kubernetes:
            k8s_config = self.config_manager.create_kubernetes_config()
            k8s_file = self.config_manager.save_kubernetes_config(k8s_config, output_dir)
            additional_configs.append(k8s_file)
        
        return {
            "success": True,
            "output_directory": output_dir,
            "directories": directories,
            "dashboards_created": len(dashboards),
            "provisioning_files": [
                provisioning_result["dashboard_config"],
                provisioning_result["datasource_config"]
            ],
            "dashboard_files": provisioning_result["dashboard_files"],
            "additional_configs": additional_configs,
            "prometheus_url": prometheus_url
        }
    
    def create_dashboards_for_metrics(self, metrics: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Create dashboards based on available metrics"""
        
        dashboards = []
        
        # Group metrics by type
        metric_groups = self._group_metrics_by_type(metrics)
        
        # Create dashboard for each group
        for group_name, group_metrics in metric_groups.items():
            dashboard = self._create_metrics_dashboard(group_name, group_metrics)
            dashboards.append(dashboard)
        
        return dashboards
    
    def create_basic_dashboard(
        self,
        title: str,
        metrics_count: int = 4,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a basic dashboard with test panels"""
        
        if tags is None:
            tags = ["test", "generated"]
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(title=title, tags=tags)
        
        # Create panels
        panels = []
        grid = MVPPanelGrid()
        timeseries_panel = MVPTimeSeriesPanel()
        stat_panel = MVPStatPanel()
        
        for i in range(metrics_count):
            if i % 2 == 0:
                # Time series panel
                panel = timeseries_panel.create_panel(
                    title=f"Metric {i+1}",
                    prometheus_query=f"test_metric_{i+1}",
                    panel_id=i+1,
                    width=12,
                    height=8
                )
            else:
                # Stat panel
                panel = stat_panel.create_panel(
                    title=f"Stat {i+1}",
                    prometheus_query=f"test_stat_{i+1}",
                    panel_id=i+1,
                    width=6,
                    height=8
                )
            
            # Position panel
            panel["gridPos"] = grid.add_panel(panel["gridPos"]["w"], panel["gridPos"]["h"])
            panels.append(panel)
        
        dashboard["panels"] = panels
        return dashboard
    
    def _create_default_dashboards(self) -> List[Dict[str, Any]]:
        """Create default set of trading dashboards"""
        
        dashboards = []
        
        # Trading overview dashboard
        overview = self.trading_overview.create_dashboard()
        dashboards.append(overview)
        
        # Signal metrics dashboard
        signals = self.signal_metrics.create_dashboard()
        dashboards.append(signals)
        
        # Agent metrics dashboard
        agents = self.agent_metrics.create_dashboard()
        dashboards.append(agents)
        
        # System metrics dashboard
        system = self.system_metrics.create_dashboard()
        dashboards.append(system)
        
        return dashboards
    
    def _group_metrics_by_type(self, metrics: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
        """Group metrics by their type or category"""
        
        groups = {
            "signals": [],
            "agents": [],
            "system": [],
            "trading": [],
            "other": []
        }
        
        for metric in metrics:
            metric_name = metric.get("metric_name", "").lower()
            
            if "signal" in metric_name:
                groups["signals"].append(metric)
            elif "agent" in metric_name:
                groups["agents"].append(metric)
            elif any(word in metric_name for word in ["system", "cpu", "memory", "uptime"]):
                groups["system"].append(metric)
            elif any(word in metric_name for word in ["trading", "market", "price"]):
                groups["trading"].append(metric)
            else:
                groups["other"].append(metric)
        
        # Remove empty groups
        return {k: v for k, v in groups.items() if v}
    
    def _create_metrics_dashboard(self, group_name: str, metrics: List[Dict[str, str]]) -> Dict[str, Any]:
        """Create a dashboard for a specific group of metrics"""
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(
            title=f"{group_name.title()} Metrics",
            tags=[group_name, "auto-generated"]
        )
        
        # Create panels for each metric
        panels = []
        grid = MVPPanelGrid()
        timeseries_panel = MVPTimeSeriesPanel()
        stat_panel = MVPStatPanel()
        
        for i, metric in enumerate(metrics):
            metric_name = metric["metric_name"]
            metric_type = metric.get("metric_type", "gauge")
            description = metric.get("description", "")
            
            if metric_type in ["counter", "histogram"]:
                # Use time series for counters and histograms
                query = f"rate({metric_name}[5m])" if metric_type == "counter" else metric_name
                panel = timeseries_panel.create_panel(
                    title=description or metric_name.replace("_", " ").title(),
                    prometheus_query=query,
                    panel_id=i+1,
                    width=12,
                    height=8
                )
            else:
                # Use stat for gauges
                panel = stat_panel.create_panel(
                    title=description or metric_name.replace("_", " ").title(),
                    prometheus_query=metric_name,
                    panel_id=i+1,
                    width=6,
                    height=8
                )
            
            # Position panel
            panel["gridPos"] = grid.add_panel(panel["gridPos"]["w"], panel["gridPos"]["h"])
            panels.append(panel)
        
        dashboard["panels"] = panels
        return dashboard
    
    def create_custom_dashboard(
        self,
        title: str,
        panels_config: List[Dict[str, Any]],
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create a custom dashboard with specified panels"""
        
        if tags is None:
            tags = ["custom"]
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(title=title, tags=tags)
        
        # Create panels based on configuration
        panels = []
        grid = MVPPanelGrid()
        timeseries_panel = MVPTimeSeriesPanel()
        stat_panel = MVPStatPanel()
        
        for i, panel_config in enumerate(panels_config):
            panel_type = panel_config.get("type", "timeseries")
            panel_title = panel_config.get("title", f"Panel {i+1}")
            panel_query = panel_config.get("query", "up")
            panel_width = panel_config.get("width", 12)
            panel_height = panel_config.get("height", 8)
            
            if panel_type == "stat":
                panel = stat_panel.create_panel(
                    title=panel_title,
                    prometheus_query=panel_query,
                    panel_id=i+1,
                    width=panel_width,
                    height=panel_height
                )
            else:
                panel = timeseries_panel.create_panel(
                    title=panel_title,
                    prometheus_query=panel_query,
                    panel_id=i+1,
                    width=panel_width,
                    height=panel_height
                )
            
            # Position panel
            panel["gridPos"] = grid.add_panel(panel_width, panel_height)
            panels.append(panel)
        
        dashboard["panels"] = panels
        return dashboard
    
    def validate_configuration(self, config_dir: str) -> Dict[str, Any]:
        """Validate generated configuration"""
        
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "files_checked": []
        }
        
        # Check required directories exist
        required_dirs = [
            "provisioning",
            "provisioning/dashboards",
            "provisioning/datasources",
            "dashboards"
        ]
        
        for dir_name in required_dirs:
            dir_path = os.path.join(config_dir, dir_name)
            if not os.path.exists(dir_path):
                validation_result["valid"] = False
                validation_result["errors"].append(f"Missing directory: {dir_name}")
        
        # Check provisioning files exist
        provisioning_files = [
            "provisioning/dashboards/dashboards.yml",
            "provisioning/datasources/datasources.yml"
        ]
        
        for file_name in provisioning_files:
            file_path = os.path.join(config_dir, file_name)
            if os.path.exists(file_path):
                validation_result["files_checked"].append(file_name)
            else:
                validation_result["valid"] = False
                validation_result["errors"].append(f"Missing file: {file_name}")
        
        # Check dashboard files exist
        dashboards_dir = os.path.join(config_dir, "dashboards")
        if os.path.exists(dashboards_dir):
            dashboard_files = [f for f in os.listdir(dashboards_dir) if f.endswith('.json')]
            if not dashboard_files:
                validation_result["warnings"].append("No dashboard files found")
            else:
                validation_result["files_checked"].extend([f"dashboards/{f}" for f in dashboard_files])
        
        return validation_result 