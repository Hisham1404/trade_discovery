"""
Panel Configuration Module

MVP implementation for creating different types of Grafana panels
and managing panel grid positioning.
"""

from typing import Dict, List, Any, Optional
import uuid


class MVPTimeSeriesPanel:
    """MVP Time Series Panel for displaying time-based metrics"""
    
    def __init__(self):
        self.panel_type = "timeseries"
        
    def create_panel(
        self,
        title: str,
        prometheus_query: str,
        panel_id: int,
        width: int = 12,
        height: int = 8,
        unit: str = "short",
        min_value: Optional[float] = None,
        max_value: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create a time series panel configuration"""
        
        panel = {
            "id": panel_id,
            "title": title,
            "type": self.panel_type,
            "gridPos": {
                "h": height,
                "w": width,
                "x": 0,
                "y": 0
            },
            "targets": [
                {
                    "expr": prometheus_query,
                    "interval": "",
                    "legendFormat": "",
                    "refId": "A"
                }
            ],
            "options": {
                "legend": {
                    "calcs": [],
                    "displayMode": "list",
                    "placement": "bottom",
                    "showLegend": True
                },
                "tooltip": {
                    "mode": "single",
                    "sort": "none"
                }
            },
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "palette-classic"
                    },
                    "custom": {
                        "axisLabel": "",
                        "axisPlacement": "auto",
                        "barAlignment": 0,
                        "drawStyle": "line",
                        "fillOpacity": 0,
                        "gradientMode": "none",
                        "hideFrom": {
                            "legend": False,
                            "tooltip": False,
                            "vis": False
                        },
                        "lineInterpolation": "linear",
                        "lineWidth": 1,
                        "pointSize": 5,
                        "scaleDistribution": {
                            "type": "linear"
                        },
                        "showPoints": "auto",
                        "spanNulls": False,
                        "stacking": {
                            "group": "A",
                            "mode": "none"
                        },
                        "thresholdsStyle": {
                            "mode": "off"
                        }
                    },
                    "unit": unit
                },
                "overrides": []
            }
        }
        
        # Add min/max values if specified
        if min_value is not None:
            panel["fieldConfig"]["defaults"]["min"] = min_value
        if max_value is not None:
            panel["fieldConfig"]["defaults"]["max"] = max_value
            
        return panel
    
    def create_multi_query_panel(
        self,
        title: str,
        queries: List[Dict[str, str]],
        panel_id: int,
        width: int = 12,
        height: int = 8
    ) -> Dict[str, Any]:
        """Create a time series panel with multiple queries"""
        
        panel = self.create_panel(title, "", panel_id, width, height)
        
        # Replace targets with multiple queries
        panel["targets"] = []
        for i, query in enumerate(queries):
            target = {
                "expr": query["expr"],
                "interval": query.get("interval", ""),
                "legendFormat": query.get("legend", ""),
                "refId": chr(65 + i)  # A, B, C, etc.
            }
            panel["targets"].append(target)
        
        return panel


class MVPStatPanel:
    """MVP Stat Panel for displaying single value metrics"""
    
    def __init__(self):
        self.panel_type = "stat"
    
    def create_panel(
        self,
        title: str,
        prometheus_query: str,
        panel_id: int,
        width: int = 6,
        height: int = 8,
        unit: str = "short",
        color_mode: str = "value"
    ) -> Dict[str, Any]:
        """Create a stat panel configuration"""
        
        panel = {
            "id": panel_id,
            "title": title,
            "type": self.panel_type,
            "gridPos": {
                "h": height,
                "w": width,
                "x": 0,
                "y": 0
            },
            "targets": [
                {
                    "expr": prometheus_query,
                    "interval": "",
                    "legendFormat": "",
                    "refId": "A"
                }
            ],
            "options": {
                "colorMode": color_mode,
                "graphMode": "area",
                "justifyMode": "auto",
                "orientation": "horizontal",
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": ""
                },
                "textMode": "auto"
            },
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "thresholds"
                    },
                    "custom": {
                        "hideFrom": {
                            "legend": False,
                            "tooltip": False,
                            "vis": False
                        }
                    },
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {
                                "color": "green",
                                "value": None
                            },
                            {
                                "color": "red",
                                "value": 80
                            }
                        ]
                    },
                    "unit": unit
                },
                "overrides": []
            }
        }
        
        return panel
    
    def add_thresholds(self, panel: Dict[str, Any], thresholds: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Add custom thresholds to stat panel"""
        panel["fieldConfig"]["defaults"]["thresholds"]["steps"] = thresholds
        return panel


class MVPGaugePanel:
    """MVP Gauge Panel for displaying metrics with visual gauge"""
    
    def __init__(self):
        self.panel_type = "gauge"
    
    def create_panel(
        self,
        title: str,
        prometheus_query: str,
        panel_id: int,
        min_value: float = 0,
        max_value: float = 100,
        width: int = 6,
        height: int = 8
    ) -> Dict[str, Any]:
        """Create a gauge panel configuration"""
        
        panel = {
            "id": panel_id,
            "title": title,
            "type": self.panel_type,
            "gridPos": {
                "h": height,
                "w": width,
                "x": 0,
                "y": 0
            },
            "targets": [
                {
                    "expr": prometheus_query,
                    "interval": "",
                    "legendFormat": "",
                    "refId": "A"
                }
            ],
            "options": {
                "orientation": "auto",
                "reduceOptions": {
                    "values": False,
                    "calcs": ["lastNotNull"],
                    "fields": ""
                },
                "showThresholdLabels": False,
                "showThresholdMarkers": True
            },
            "fieldConfig": {
                "defaults": {
                    "color": {
                        "mode": "thresholds"
                    },
                    "min": min_value,
                    "max": max_value,
                    "thresholds": {
                        "mode": "absolute",
                        "steps": [
                            {
                                "color": "green",
                                "value": None
                            },
                            {
                                "color": "yellow",
                                "value": max_value * 0.7
                            },
                            {
                                "color": "red", 
                                "value": max_value * 0.9
                            }
                        ]
                    }
                },
                "overrides": []
            }
        }
        
        return panel


class MVPPanelGrid:
    """MVP Panel Grid for managing panel positioning"""
    
    def __init__(self, grid_width: int = 24):
        self.grid_width = grid_width
        self.current_y = 0
        self.current_x = 0
        self.row_height = 0
        
    def add_panel(self, width: int, height: int) -> Dict[str, int]:
        """Add a panel and return its grid position"""
        
        # Check if panel fits in current row (using 24-grid system like Grafana)
        if self.current_x + width > 24:
            # Move to next row
            self.current_y += self.row_height
            self.current_x = 0
            self.row_height = 0
        
        # Set position
        position = {
            "x": self.current_x,
            "y": self.current_y,
            "w": width,
            "h": height
        }
        
        # Update current position
        self.current_x += width
        self.row_height = max(self.row_height, height)
        
        return position
    
    def reset_grid(self):
        """Reset grid positioning"""
        self.current_y = 0
        self.current_x = 0
        self.row_height = 0
    
    def position_panel(self, panel: Dict[str, Any], width: int, height: int) -> Dict[str, Any]:
        """Position a panel in the grid"""
        position = self.add_panel(width, height)
        panel["gridPos"] = position
        return panel
    
    def create_row_separator(self, title: str, row_id: int) -> Dict[str, Any]:
        """Create a row separator panel"""
        position = self.add_panel(self.grid_width, 1)
        
        row_panel = {
            "id": row_id,
            "title": title,
            "type": "row",
            "collapsed": False,
            "gridPos": position,
            "panels": []
        }
        
        return row_panel 