"""
Dashboard Configuration Module

MVP implementation for creating and validating Grafana dashboard JSON configurations.
Provides basic dashboard building and validation capabilities.
"""

import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime


class MVPDashboardBuilder:
    """MVP Dashboard Builder for basic dashboard creation"""
    
    def __init__(self):
        self.schema_version = 39  # Current Grafana schema version
    
    def create_basic_dashboard(
        self, 
        title: str, 
        tags: List[str], 
        uid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a basic dashboard configuration"""
        
        # Validate inputs
        if title is None:
            raise TypeError("Dashboard title cannot be None")
        if not title or title.strip() == "":
            raise ValueError("Dashboard title cannot be empty")
        
        dashboard = {
            "id": None,  # Will be assigned by Grafana
            "uid": uid or self._generate_uid(),
            "title": title,
            "tags": tags,
            "timezone": "browser",
            "editable": True,
            "graphTooltip": 0,  # No shared crosshair
            "panels": [],
            "time": {
                "from": "now-6h",
                "to": "now"
            },
            "timepicker": {
                "refresh_intervals": [
                    "5s", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "2h", "1d"
                ]
            },
            "templating": {
                "list": []
            },
            "annotations": {
                "list": []
            },
            "refresh": "30s",
            "schemaVersion": self.schema_version,
            "version": 0,
            "links": []
        }
        
        return dashboard
    
    def create_dashboard_with_panels(self, panel_count: int, title: str = "Multi-Panel Dashboard") -> Dict[str, Any]:
        """Create a dashboard with multiple test panels"""
        dashboard = self.create_basic_dashboard(title=title, tags=["test", "multi-panel"])
        
        # Add test panels
        for i in range(panel_count):
            panel = {
                "id": i + 1,
                "title": f"Test Panel {i + 1}",
                "type": "timeseries",
                "gridPos": {
                    "h": 8,
                    "w": 12,
                    "x": (i % 2) * 12,
                    "y": (i // 2) * 8
                },
                "targets": [],
                "options": {}
            }
            dashboard["panels"].append(panel)
        
        return dashboard
    
    def _generate_uid(self) -> str:
        """Generate a unique identifier for dashboard"""
        return str(uuid.uuid4())[:8]  # Short UID
    
    def add_panel_to_dashboard(self, dashboard: Dict[str, Any], panel: Dict[str, Any]) -> Dict[str, Any]:
        """Add a panel to an existing dashboard"""
        dashboard["panels"].append(panel)
        return dashboard
    
    def set_time_range(self, dashboard: Dict[str, Any], from_time: str, to_time: str) -> Dict[str, Any]:
        """Set the time range for a dashboard"""
        dashboard["time"] = {
            "from": from_time,
            "to": to_time
        }
        return dashboard
    
    def add_template_variable(self, dashboard: Dict[str, Any], variable: Dict[str, Any]) -> Dict[str, Any]:
        """Add a template variable to dashboard"""
        dashboard["templating"]["list"].append(variable)
        return dashboard


class MVPDashboardValidator:
    """MVP Dashboard Validator for basic validation"""
    
    def __init__(self):
        self.required_fields = [
            "title", "tags", "panels", "time", "timezone", "editable"
        ]
    
    def validate_dashboard(self, dashboard: Dict[str, Any]) -> bool:
        """Validate basic dashboard structure"""
        try:
            # Check required fields
            for field in self.required_fields:
                if field not in dashboard:
                    return False
            
            # Validate field types
            if not isinstance(dashboard["title"], str):
                return False
            if not isinstance(dashboard["tags"], list):
                return False
            if not isinstance(dashboard["panels"], list):
                return False
            if not isinstance(dashboard["time"], dict):
                return False
            if not isinstance(dashboard["timezone"], str):
                return False
            if not isinstance(dashboard["editable"], bool):
                return False
            
            # Validate time structure
            time_obj = dashboard["time"]
            if "from" not in time_obj or "to" not in time_obj:
                return False
            
            return True
            
        except Exception:
            return False
    
    def validate_panel(self, panel: Dict[str, Any]) -> bool:
        """Validate basic panel structure"""
        try:
            required_panel_fields = ["id", "title", "type"]
            
            for field in required_panel_fields:
                if field not in panel:
                    return False
            
            # Validate panel types
            if not isinstance(panel["id"], int):
                return False
            if not isinstance(panel["title"], str):
                return False
            if not isinstance(panel["type"], str):
                return False
            
            return True
            
        except Exception:
            return False
    
    def get_validation_errors(self, dashboard: Dict[str, Any]) -> List[str]:
        """Get detailed validation errors"""
        errors = []
        
        # Check required fields
        for field in self.required_fields:
            if field not in dashboard:
                errors.append(f"Missing required field: {field}")
        
        # Check panel validation
        if "panels" in dashboard:
            for i, panel in enumerate(dashboard["panels"]):
                if not self.validate_panel(panel):
                    errors.append(f"Invalid panel at index {i}")
        
        return errors 