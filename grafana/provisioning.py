"""
Provisioning Configuration Module

MVP implementation for creating Grafana provisioning configurations
for dashboards and datasources.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional


class MVPDashboardProvisioning:
    """MVP Dashboard Provisioning for file-based dashboard management"""
    
    def __init__(self):
        self.api_version = 1
        self.provider_type = "file"
    
    def generate_provisioning_yaml(
        self,
        provider_name: str,
        folder_name: str,
        dashboard_path: str,
        update_interval: int = 10,
        allow_ui_updates: bool = False,
        disable_deletion: bool = False
    ) -> str:
        """Generate dashboard provisioning YAML configuration"""
        
        provisioning_config = {
            "apiVersion": self.api_version,
            "providers": [
                {
                    "name": provider_name,
                    "type": self.provider_type,
                    "folder": folder_name,
                    "updateIntervalSeconds": update_interval,
                    "allowUiUpdates": allow_ui_updates,
                    "disableDeletion": disable_deletion,
                    "options": {
                        "path": dashboard_path
                    }
                }
            ]
        }
        
        yaml_content = yaml.dump(provisioning_config, default_flow_style=False, sort_keys=False)
        return yaml_content
    
    def save_dashboard(
        self,
        dashboard_data: Dict[str, Any],
        filename: str,
        output_dir: str
    ) -> str:
        """Save dashboard JSON to file"""
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        # Create full file path
        file_path = os.path.join(output_dir, filename)
        
        try:
            # Write dashboard JSON
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(dashboard_data, f, indent=2, ensure_ascii=False)
            
            return file_path
            
        except PermissionError:
            raise PermissionError(f"Permission denied writing to: {file_path}")
        except Exception as e:
            raise Exception(f"Failed to save dashboard: {str(e)}")
    
    def create_provider_config(
        self,
        name: str,
        folder: str,
        path: str,
        org_id: int = 1,
        folder_uid: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a single provider configuration"""
        
        provider = {
            "name": name,
            "orgId": org_id,
            "folder": folder,
            "type": self.provider_type,
            "disableDeletion": False,
            "updateIntervalSeconds": 10,
            "allowUiUpdates": False,
            "options": {
                "path": path
            }
        }
        
        if folder_uid:
            provider["folderUid"] = folder_uid
        
        return provider
    
    def create_multi_provider_config(self, providers: List[Dict[str, Any]]) -> str:
        """Create configuration with multiple providers"""
        
        provisioning_config = {
            "apiVersion": self.api_version,
            "providers": []
        }
        
        for provider_data in providers:
            provider = self.create_provider_config(**provider_data)
            provisioning_config["providers"].append(provider)
        
        yaml_content = yaml.dump(provisioning_config, default_flow_style=False, sort_keys=False)
        return yaml_content
    
    def save_provisioning_config(
        self,
        yaml_content: str,
        config_dir: str,
        filename: str = "dashboards.yml"
    ) -> str:
        """Save provisioning configuration to file"""
        
        # Ensure config directory exists
        os.makedirs(config_dir, exist_ok=True)
        
        # Create full file path
        file_path = os.path.join(config_dir, filename)
        
        try:
            # Write YAML config
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to save provisioning config: {str(e)}")
    
    def batch_save_dashboards(
        self,
        dashboards: List[Dict[str, Any]],
        output_dir: str,
        filename_prefix: str = "dashboard"
    ) -> List[str]:
        """Save multiple dashboards to files"""
        
        saved_files = []
        
        for i, dashboard in enumerate(dashboards):
            # Generate filename
            title = dashboard.get("title", f"Dashboard {i+1}")
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
            safe_title = safe_title.replace(' ', '-').lower()
            filename = f"{filename_prefix}-{safe_title}.json"
            
            # Save dashboard
            file_path = self.save_dashboard(dashboard, filename, output_dir)
            saved_files.append(file_path)
        
        return saved_files
    
    def create_folder_structure_config(
        self,
        base_path: str,
        enable_folder_from_filesystem: bool = True
    ) -> str:
        """Create configuration that uses filesystem folder structure"""
        
        provisioning_config = {
            "apiVersion": self.api_version,
            "providers": [
                {
                    "name": "default",
                    "type": self.provider_type,
                    "updateIntervalSeconds": 30,
                    "options": {
                        "path": base_path,
                        "foldersFromFilesStructure": enable_folder_from_filesystem
                    }
                }
            ]
        }
        
        yaml_content = yaml.dump(provisioning_config, default_flow_style=False, sort_keys=False)
        return yaml_content


class MVPDataSourceProvisioning:
    """MVP DataSource Provisioning for managing datasource configurations"""
    
    def __init__(self):
        self.api_version = 1
    
    def create_provisioning_config(
        self,
        datasources: List[Dict[str, Any]],
        delete_datasources: Optional[List[Dict[str, str]]] = None,
        prune: bool = False
    ) -> str:
        """Create datasource provisioning configuration"""
        
        config = {
            "apiVersion": self.api_version,
            "datasources": datasources
        }
        
        if delete_datasources:
            config["deleteDatasources"] = delete_datasources
        
        if prune:
            config["prune"] = prune
        
        yaml_content = yaml.dump(config, default_flow_style=False, sort_keys=False)
        return yaml_content
    
    def save_datasource_config(
        self,
        yaml_content: str,
        config_dir: str,
        filename: str = "datasources.yml"
    ) -> str:
        """Save datasource provisioning configuration"""
        
        # Ensure config directory exists
        os.makedirs(config_dir, exist_ok=True)
        
        # Create full file path
        file_path = os.path.join(config_dir, filename)
        
        try:
            # Write YAML config
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(yaml_content)
            
            return file_path
            
        except Exception as e:
            raise Exception(f"Failed to save datasource config: {str(e)}")


class MVPProvisioningManager:
    """MVP Provisioning Manager for coordinating all provisioning activities"""
    
    def __init__(self):
        self.dashboard_provisioning = MVPDashboardProvisioning()
        self.datasource_provisioning = MVPDataSourceProvisioning()
    
    def setup_complete_provisioning(
        self,
        base_dir: str,
        dashboards: List[Dict[str, Any]],
        datasources: List[Dict[str, Any]],
        provider_name: str = "Trading System",
        folder_name: str = "Trading"
    ) -> Dict[str, Any]:
        """Setup complete provisioning configuration"""
        
        # Create directory structure
        provisioning_dir = os.path.join(base_dir, "provisioning")
        dashboards_config_dir = os.path.join(provisioning_dir, "dashboards")
        datasources_config_dir = os.path.join(provisioning_dir, "datasources")
        dashboards_dir = os.path.join(base_dir, "dashboards")
        
        os.makedirs(dashboards_config_dir, exist_ok=True)
        os.makedirs(datasources_config_dir, exist_ok=True)
        os.makedirs(dashboards_dir, exist_ok=True)
        
        # Save dashboards
        dashboard_files = self.dashboard_provisioning.batch_save_dashboards(
            dashboards, dashboards_dir
        )
        
        # Create dashboard provisioning config
        dashboard_yaml = self.dashboard_provisioning.generate_provisioning_yaml(
            provider_name=provider_name,
            folder_name=folder_name,
            dashboard_path=dashboards_dir
        )
        
        dashboard_config_file = self.dashboard_provisioning.save_provisioning_config(
            dashboard_yaml, dashboards_config_dir
        )
        
        # Create datasource provisioning config  
        datasource_yaml = self.datasource_provisioning.create_provisioning_config(datasources)
        
        datasource_config_file = self.datasource_provisioning.save_datasource_config(
            datasource_yaml, datasources_config_dir, "prometheus.yml"
        )
        
        return {
            "provisioning_dir": provisioning_dir,
            "dashboard_files": dashboard_files,
            "dashboard_config": dashboard_config_file,
            "datasource_config": datasource_config_file,
            "directories_created": [
                provisioning_dir,
                dashboards_config_dir,
                datasources_config_dir,
                dashboards_dir
            ]
        } 