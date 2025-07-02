#!/usr/bin/env python3
"""
Monitoring Configuration Validation Script
Validates Docker Compose and configuration files without requiring running containers
"""

import yaml
import json
import os
from pathlib import Path
from typing import Dict, List, Tuple

def validate_docker_compose() -> Tuple[bool, List[str]]:
    """Validate Docker Compose monitoring file"""
    errors = []
    
    compose_file = Path("docker-compose.monitoring.yml")
    if not compose_file.exists():
        errors.append("❌ docker-compose.monitoring.yml not found")
        return False, errors
    
    try:
        with open(compose_file, 'r') as f:
            compose_config = yaml.safe_load(f)
        
        # Check required services
        required_services = ['prometheus', 'grafana', 'jaeger']
        services = compose_config.get('services', {})
        
        for service in required_services:
            if service not in services:
                errors.append(f"❌ Missing required service: {service}")
            else:
                print(f"✅ Service '{service}' configured")
        
        # Check networks
        if 'networks' in compose_config:
            print("✅ Networks configured")
        else:
            errors.append("❌ No networks defined")
        
        # Check volumes
        if 'volumes' in compose_config:
            print("✅ Volumes configured")
        
        print("✅ Docker Compose file is valid YAML")
        
    except yaml.YAMLError as e:
        errors.append(f"❌ Invalid YAML in docker-compose.monitoring.yml: {e}")
    
    return len(errors) == 0, errors

def validate_prometheus_config() -> Tuple[bool, List[str]]:
    """Validate Prometheus configuration"""
    errors = []
    
    prometheus_file = Path("config/prometheus/prometheus.yml")
    if not prometheus_file.exists():
        errors.append("❌ config/prometheus/prometheus.yml not found")
        return False, errors
    
    try:
        with open(prometheus_file, 'r') as f:
            prometheus_config = yaml.safe_load(f)
        
        # Check required sections
        required_sections = ['global', 'scrape_configs']
        for section in required_sections:
            if section not in prometheus_config:
                errors.append(f"❌ Missing section in prometheus.yml: {section}")
            else:
                print(f"✅ Prometheus section '{section}' found")
        
        # Check scrape interval
        global_config = prometheus_config.get('global', {})
        scrape_interval = global_config.get('scrape_interval', '15s')
        if scrape_interval in ['5s', '10s', '15s', '30s', '60s']:
            print(f"✅ Prometheus scrape interval: {scrape_interval}")
        else:
            errors.append(f"❌ Invalid scrape interval: {scrape_interval}")
        
        # Check scrape configs
        scrape_configs = prometheus_config.get('scrape_configs', [])
        if len(scrape_configs) > 0:
            print(f"✅ Prometheus has {len(scrape_configs)} scrape jobs configured")
        else:
            errors.append("❌ No scrape configs defined")
        
    except yaml.YAMLError as e:
        errors.append(f"❌ Invalid YAML in prometheus.yml: {e}")
    
    return len(errors) == 0, errors

def validate_grafana_config() -> Tuple[bool, List[str]]:
    """Validate Grafana configuration"""
    errors = []
    
    datasources_file = Path("config/grafana/provisioning/datasources.yml")
    if not datasources_file.exists():
        errors.append("❌ config/grafana/provisioning/datasources.yml not found")
        return False, errors
    
    try:
        with open(datasources_file, 'r') as f:
            datasources_config = yaml.safe_load(f)
        
        # Check datasources
        datasources = datasources_config.get('datasources', [])
        if len(datasources) == 0:
            errors.append("❌ No datasources configured in Grafana")
            return False, errors
        
        # Check for Prometheus datasource
        prometheus_ds = [ds for ds in datasources if ds.get('type') == 'prometheus']
        if len(prometheus_ds) > 0:
            prometheus_url = prometheus_ds[0].get('url', '')
            if 'prometheus' in prometheus_url or '9090' in prometheus_url:
                print(f"✅ Grafana Prometheus datasource: {prometheus_url}")
            else:
                errors.append(f"❌ Invalid Prometheus datasource URL: {prometheus_url}")
        else:
            errors.append("❌ No Prometheus datasource configured in Grafana")
        
        # Check for Jaeger datasource
        jaeger_ds = [ds for ds in datasources if ds.get('type') == 'jaeger']
        if len(jaeger_ds) > 0:
            jaeger_url = jaeger_ds[0].get('url', '')
            print(f"✅ Grafana Jaeger datasource: {jaeger_url}")
        
        print(f"✅ Grafana has {len(datasources)} datasources configured")
        
    except yaml.YAMLError as e:
        errors.append(f"❌ Invalid YAML in datasources.yml: {e}")
    
    return len(errors) == 0, errors

def validate_directory_structure() -> Tuple[bool, List[str]]:
    """Validate required directory structure"""
    errors = []
    
    required_dirs = [
        "config/prometheus",
        "config/grafana/provisioning/datasources",
        "config/grafana/provisioning/dashboards"
    ]
    
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists() and path.is_dir():
            print(f"✅ Directory exists: {dir_path}")
        else:
            errors.append(f"❌ Missing directory: {dir_path}")
    
    return len(errors) == 0, errors

def main():
    """Main validation function"""
    print("🔍 MONITORING CONFIGURATION VALIDATION")
    print("=" * 50)
    
    all_valid = True
    all_errors = []
    
    # Validate directory structure
    print("\n📁 Validating Directory Structure...")
    dirs_valid, dir_errors = validate_directory_structure()
    all_valid &= dirs_valid
    all_errors.extend(dir_errors)
    
    # Validate Docker Compose
    print("\n🐳 Validating Docker Compose Configuration...")
    compose_valid, compose_errors = validate_docker_compose()
    all_valid &= compose_valid
    all_errors.extend(compose_errors)
    
    # Validate Prometheus
    print("\n📊 Validating Prometheus Configuration...")
    prometheus_valid, prometheus_errors = validate_prometheus_config()
    all_valid &= prometheus_valid
    all_errors.extend(prometheus_errors)
    
    # Validate Grafana
    print("\n📈 Validating Grafana Configuration...")
    grafana_valid, grafana_errors = validate_grafana_config()
    all_valid &= grafana_valid
    all_errors.extend(grafana_errors)
    
    # Summary
    print("\n" + "=" * 50)
    if all_valid:
        print("🎉 ALL VALIDATIONS PASSED!")
        print("✅ Monitoring infrastructure configuration is ready")
        print("✅ All configuration files are valid")
        print("✅ Directory structure is correct")
        print("\n🚀 Ready for deployment with:")
        print("   docker-compose -f docker-compose.monitoring.yml up -d")
        return 0
    else:
        print("❌ VALIDATION FAILED!")
        print(f"Found {len(all_errors)} error(s):")
        for error in all_errors:
            print(f"   {error}")
        return 1

if __name__ == "__main__":
    exit(main()) 