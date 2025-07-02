"""
Datasource Configuration Module

MVP implementation for creating Prometheus datasource configurations
and generating provisioning YAML files.
"""

import yaml
import re
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse


class MVPPrometheusDataSource:
    """MVP Prometheus DataSource configuration"""
    
    def __init__(self):
        self.datasource_type = "prometheus"
        self.api_version = 1
    
    def create_config(
        self, 
        name: str, 
        url: str, 
        is_default: bool = True,
        basic_auth: bool = False,
        basic_auth_user: str = "",
        basic_auth_password: str = ""
    ) -> Dict[str, Any]:
        """Create Prometheus datasource configuration"""
        
        # Validate URL
        if not self._validate_url(url):
            raise ValueError(f"Invalid URL: {url}")
        
        config = {
            "name": name,
            "type": self.datasource_type,
            "access": "proxy",
            "url": url,
            "isDefault": is_default,
            "editable": True,
            "jsonData": {
                "httpMethod": "POST",
                "manageAlerts": True,
                "prometheusType": "Prometheus",
                "prometheusVersion": "2.40.0",
                "timeInterval": "15s",
                "incrementalQuerying": False
            }
        }
        
        # Add basic auth if enabled
        if basic_auth:
            config["basicAuth"] = True
            config["basicAuthUser"] = basic_auth_user
            config["secureJsonData"] = {
                "basicAuthPassword": basic_auth_password
            }
        
        return config
    
    def generate_provisioning_yaml(self, datasources: List[Dict[str, Any]]) -> str:
        """Generate provisioning YAML for datasources"""
        
        # Convert datasource configs to full format
        full_datasources = []
        for ds in datasources:
            if "type" not in ds:
                # Simple format - convert to full
                full_config = self.create_config(
                    name=ds["name"],
                    url=ds["url"],
                    is_default=ds.get("isDefault", True)
                )
            else:
                # Already full format
                full_config = ds
            
            full_datasources.append(full_config)
        
        # Create provisioning structure
        provisioning_config = {
            "apiVersion": self.api_version,
            "datasources": full_datasources
        }
        
        # Generate YAML
        yaml_content = yaml.dump(provisioning_config, default_flow_style=False, sort_keys=False)
        return yaml_content
    
    def create_prometheus_config(
        self,
        name: str = "Prometheus",
        url: str = "http://localhost:9090",
        scrape_interval: str = "15s",
        query_timeout: str = "60s",
        enable_alerting: bool = True
    ) -> Dict[str, Any]:
        """Create a comprehensive Prometheus datasource configuration"""
        
        config = self.create_config(name=name, url=url)
        
        # Add advanced settings
        config["jsonData"].update({
            "timeInterval": scrape_interval,
            "queryTimeout": query_timeout,
            "manageAlerts": enable_alerting,
            "cacheLevel": "High",
            "disableRecordingRules": False,
            "incrementalQueryOverlapWindow": "10m"
        })
        
        return config
    
    def _validate_url(self, url: str) -> bool:
        """Validate URL format"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False
    
    def create_multiple_datasources(self, configs: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Create multiple datasource configurations"""
        datasources = []
        
        for i, config in enumerate(configs):
            ds_config = self.create_config(
                name=config["name"],
                url=config["url"],
                is_default=(i == 0)  # First one is default
            )
            datasources.append(ds_config)
        
        return datasources
    
    def add_custom_headers(self, config: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """Add custom HTTP headers to datasource configuration"""
        if "jsonData" not in config:
            config["jsonData"] = {}
        
        for i, (header_name, header_value) in enumerate(headers.items(), 1):
            config["jsonData"][f"httpHeaderName{i}"] = header_name
            if "secureJsonData" not in config:
                config["secureJsonData"] = {}
            config["secureJsonData"][f"httpHeaderValue{i}"] = header_value
        
        return config
    
    def enable_exemplars(self, config: Dict[str, Any], trace_datasource_uid: str) -> Dict[str, Any]:
        """Enable exemplars configuration for tracing integration"""
        if "jsonData" not in config:
            config["jsonData"] = {}
        
        config["jsonData"]["exemplarTraceIdDestinations"] = [
            {
                "datasourceUid": trace_datasource_uid,
                "name": "traceID"
            }
        ]
        
        return config 