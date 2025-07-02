"""
Trading-Specific Dashboard Module

MVP implementation for creating pre-configured dashboards
specific to trading system metrics and monitoring.
"""

from typing import Dict, List, Any
from .dashboard_config import MVPDashboardBuilder
from .panels import MVPTimeSeriesPanel, MVPStatPanel, MVPGaugePanel, MVPPanelGrid


class MVPTradingOverviewDashboard:
    """MVP Trading System Overview Dashboard"""
    
    def __init__(self):
        self.dashboard_builder = MVPDashboardBuilder()
        self.timeseries_panel = MVPTimeSeriesPanel()
        self.stat_panel = MVPStatPanel()
        self.gauge_panel = MVPGaugePanel()
        self.grid = MVPPanelGrid()
    
    def create_dashboard(self) -> Dict[str, Any]:
        """Create trading system overview dashboard"""
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(
            title="Trading System Overview",
            tags=["trading", "overview", "system"]
        )
        
        # Reset grid for proper positioning
        self.grid.reset_grid()
        
        # Create panels
        panels = []
        
        # 1. Signals Generated (Time Series)
        signals_panel = self.timeseries_panel.create_panel(
            title="Signals Generated",
            prometheus_query="rate(signals_generated_total[5m])",
            panel_id=1,
            width=12,
            height=8,
            unit="ops"
        )
        signals_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(signals_panel)
        
        # 2. Active Agents (Stat)
        agents_panel = self.stat_panel.create_panel(
            title="Active Agents",
            prometheus_query="trading_system_active_agents",
            panel_id=2,
            width=6,
            height=8,
            unit="short"
        )
        agents_panel["gridPos"] = self.grid.add_panel(6, 8)
        panels.append(agents_panel)
        
        # 3. System Uptime (Stat)
        uptime_panel = self.stat_panel.create_panel(
            title="System Uptime",
            prometheus_query="trading_system_uptime_seconds",
            panel_id=3,
            width=6,
            height=8,
            unit="s"
        )
        uptime_panel["gridPos"] = self.grid.add_panel(6, 8)
        panels.append(uptime_panel)
        
        # 4. Memory Usage (Gauge)
        memory_panel = self.gauge_panel.create_panel(
            title="Memory Usage",
            prometheus_query="trading_system_memory_usage_percent",
            panel_id=4,
            min_value=0,
            max_value=100,
            width=12,
            height=8
        )
        memory_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(memory_panel)
        
        # 5. Signal Processing Time (Time Series)
        processing_panel = self.timeseries_panel.create_panel(
            title="Signal Processing Time",
            prometheus_query="signal_processing_duration_seconds",
            panel_id=5,
            width=12,
            height=8,
            unit="s"
        )
        processing_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(processing_panel)
        
        # Add panels to dashboard
        dashboard["panels"] = panels
        
        return dashboard


class MVPSignalMetricsDashboard:
    """MVP Signal Metrics Dashboard"""
    
    def __init__(self):
        self.dashboard_builder = MVPDashboardBuilder()
        self.timeseries_panel = MVPTimeSeriesPanel()
        self.stat_panel = MVPStatPanel()
        self.grid = MVPPanelGrid()
    
    def create_dashboard(self) -> Dict[str, Any]:
        """Create signal metrics dashboard"""
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(
            title="Trading Signal Metrics",
            tags=["trading", "signals", "metrics"]
        )
        
        # Reset grid
        self.grid.reset_grid()
        
        # Create panels
        panels = []
        
        # 1. Signal Generation Rate (Time Series)
        rate_panel = self.timeseries_panel.create_panel(
            title="Signal Generation Rate",
            prometheus_query="rate(signals_generated_total[5m])",
            panel_id=1,
            width=12,
            height=8,
            unit="ops"
        )
        rate_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(rate_panel)
        
        # 2. Signal Confidence Distribution (Time Series)
        confidence_panel = self.timeseries_panel.create_panel(
            title="Signal Confidence Distribution",
            prometheus_query="histogram_quantile(0.95, signal_confidence_histogram)",
            panel_id=2,
            width=12,
            height=8,
            unit="percent"
        )
        confidence_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(confidence_panel)
        
        # 3. Signal Processing Time (Time Series)
        processing_panel = self.timeseries_panel.create_panel(
            title="Signal Processing Time",
            prometheus_query="signal_processing_duration_seconds",
            panel_id=3,
            width=12,
            height=8,
            unit="s"
        )
        processing_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(processing_panel)
        
        # 4. Signals by Agent (Time Series)
        agent_panel = self.timeseries_panel.create_multi_query_panel(
            title="Signals by Agent",
            queries=[
                {
                    "expr": "rate(signals_generated_total{agent_name=~\".*\"}[5m])",
                    "legend": "{{agent_name}}"
                }
            ],
            panel_id=4,
            width=12,
            height=8
        )
        agent_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(agent_panel)
        
        # Add panels to dashboard
        dashboard["panels"] = panels
        
        return dashboard


class MVPAgentMetricsDashboard:
    """MVP Agent Metrics Dashboard"""
    
    def __init__(self):
        self.dashboard_builder = MVPDashboardBuilder()
        self.timeseries_panel = MVPTimeSeriesPanel()
        self.stat_panel = MVPStatPanel()
        self.grid = MVPPanelGrid()
    
    def create_dashboard(self) -> Dict[str, Any]:
        """Create agent metrics dashboard"""
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(
            title="Agent Performance Metrics",
            tags=["trading", "agents", "performance"]
        )
        
        # Reset grid
        self.grid.reset_grid()
        
        # Create panels
        panels = []
        
        # 1. Agent Execution Rate
        execution_panel = self.timeseries_panel.create_panel(
            title="Agent Execution Rate",
            prometheus_query="rate(agent_executions_total[5m])",
            panel_id=1,
            width=12,
            height=8,
            unit="ops"
        )
        execution_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(execution_panel)
        
        # 2. Agent Execution Duration
        duration_panel = self.timeseries_panel.create_panel(
            title="Agent Execution Duration",
            prometheus_query="agent_execution_duration_seconds",
            panel_id=2,
            width=12,
            height=8,
            unit="s"
        )
        duration_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(duration_panel)
        
        # 3. Active Agents Count
        active_panel = self.stat_panel.create_panel(
            title="Active Agents",
            prometheus_query="sum(agent_executions_total)",
            panel_id=3,
            width=6,
            height=8,
            unit="short"
        )
        active_panel["gridPos"] = self.grid.add_panel(6, 8)
        panels.append(active_panel)
        
        # 4. Agent Success Rate
        success_panel = self.stat_panel.create_panel(
            title="Agent Success Rate",
            prometheus_query="rate(agent_executions_total{status=\"success\"}[5m]) / rate(agent_executions_total[5m]) * 100",
            panel_id=4,
            width=6,
            height=8,
            unit="percent"
        )
        success_panel["gridPos"] = self.grid.add_panel(6, 8)
        panels.append(success_panel)
        
        # Add panels to dashboard
        dashboard["panels"] = panels
        
        return dashboard


class MVPSystemMetricsDashboard:
    """MVP System Metrics Dashboard"""
    
    def __init__(self):
        self.dashboard_builder = MVPDashboardBuilder()
        self.timeseries_panel = MVPTimeSeriesPanel()
        self.gauge_panel = MVPGaugePanel()
        self.grid = MVPPanelGrid()
    
    def create_dashboard(self) -> Dict[str, Any]:
        """Create system metrics dashboard"""
        
        # Create base dashboard
        dashboard = self.dashboard_builder.create_basic_dashboard(
            title="System Performance Metrics",
            tags=["trading", "system", "performance"]
        )
        
        # Reset grid
        self.grid.reset_grid()
        
        # Create panels
        panels = []
        
        # 1. CPU Usage
        cpu_panel = self.gauge_panel.create_panel(
            title="CPU Usage",
            prometheus_query="trading_container_cpu_usage_percent",
            panel_id=1,
            min_value=0,
            max_value=100,
            width=6,
            height=8
        )
        cpu_panel["gridPos"] = self.grid.add_panel(6, 8)
        panels.append(cpu_panel)
        
        # 2. Memory Usage
        memory_panel = self.gauge_panel.create_panel(
            title="Memory Usage",
            prometheus_query="trading_system_memory_usage_percent",
            panel_id=2,
            min_value=0,
            max_value=100,
            width=6,
            height=8
        )
        memory_panel["gridPos"] = self.grid.add_panel(6, 8)
        panels.append(memory_panel)
        
        # 3. Network I/O
        network_panel = self.timeseries_panel.create_multi_query_panel(
            title="Network I/O",
            queries=[
                {
                    "expr": "rate(trading_container_network_rx_bytes_total[5m])",
                    "legend": "Received"
                },
                {
                    "expr": "rate(trading_container_network_tx_bytes_total[5m])",
                    "legend": "Transmitted"
                }
            ],
            panel_id=3,
            width=12,
            height=8
        )
        network_panel["gridPos"] = self.grid.add_panel(12, 8)
        panels.append(network_panel)
        
        # Add panels to dashboard
        dashboard["panels"] = panels
        
        return dashboard 