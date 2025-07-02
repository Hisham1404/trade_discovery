"""
Grafana Dashboard Configuration Package

MVP and Production implementations for creating and managing Grafana dashboards
for the Trade Discovery platform.

Provides both MVP (basic functionality) and Production (enterprise-grade) interfaces
with full backward compatibility.
"""

__version__ = "1.0.0"
__author__ = "Trade Discovery Team"

# Import MVP components (original interface)
from .mvp_generator import MVPGrafanaGenerator
from .dashboard_config import MVPDashboardBuilder, MVPDashboardValidator
from .datasource_config import MVPPrometheusDataSource
from .panels import MVPTimeSeriesPanel, MVPStatPanel, MVPPanelGrid
from .provisioning import MVPDashboardProvisioning
from .trading_dashboards import MVPTradingOverviewDashboard, MVPSignalMetricsDashboard
from .config import MVPGrafanaConfig

# Import Production components (enhanced interface)
from .production_generator import (
    ProductionGrafanaGenerator, 
    ProductionGrafanaConfig,
    ProductionSecurityManager,
    ProductionMonitoringManager,
    ProductionBackupManager,
    ProductionDeploymentManager
)

# Backward compatibility aliases - Production components available as MVP names
GrafanaGenerator = ProductionGrafanaGenerator  # Main production interface
GrafanaConfig = ProductionGrafanaConfig        # Production configuration

# MVP interface preserved for existing code
__all__ = [
    # MVP Interface (backward compatibility)
    'MVPGrafanaGenerator',
    'MVPDashboardBuilder',
    'MVPDashboardValidator', 
    'MVPPrometheusDataSource',
    'MVPTimeSeriesPanel',
    'MVPStatPanel',
    'MVPPanelGrid',
    'MVPDashboardProvisioning',
    'MVPTradingOverviewDashboard',
    'MVPSignalMetricsDashboard',
    'MVPGrafanaConfig',
    
    # Production Interface (recommended for new deployments)
    'ProductionGrafanaGenerator',
    'ProductionGrafanaConfig',
    'ProductionSecurityManager',
    'ProductionMonitoringManager',
    'ProductionBackupManager',
    'ProductionDeploymentManager',
    
    # Main Interface (aliased to production)
    'GrafanaGenerator',      # -> ProductionGrafanaGenerator
    'GrafanaConfig'          # -> ProductionGrafanaConfig
] 