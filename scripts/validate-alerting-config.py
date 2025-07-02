#!/usr/bin/env python3
"""
Production Alerting Configuration Validator
Validates all alerting rules, notification channels, and configurations
"""

import yaml
import subprocess
import sys
import os
from pathlib import Path


class AlertingConfigValidator:
    """Validates alerting configuration for production readiness"""
    
    def __init__(self):
        self.config_dir = Path("config")
        self.prometheus_rules_dir = self.config_dir / "prometheus" / "rules"
        self.alertmanager_config = self.config_dir / "alertmanager" / "alertmanager.yml"
        self.errors = []
        self.warnings = []
    
    def validate_all(self):
        """Run all validation checks"""
        print("🔍 Validating Alerting Configuration...")
        
        self.validate_prometheus_rules()
        self.validate_alertmanager_config()
        self.validate_notification_channels()
        self.validate_alert_routing()
        
        return self.generate_report()
    
    def validate_prometheus_rules(self):
        """Validate Prometheus alerting rules syntax"""
        print("📊 Validating Prometheus rules...")
        
        rule_files = [
            "infrastructure_alerts.yml",
            "integration_alerts.yml", 
            "cost_alerts.yml",
            "security_alerts.yml",
            "data_quality_alerts.yml"
        ]
        
        for rule_file in rule_files:
            file_path = self.prometheus_rules_dir / rule_file
            if not file_path.exists():
                self.errors.append(f"Missing rule file: {rule_file}")
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    
                self._validate_rule_structure(config, rule_file)
                
                # Use promtool if available
                result = subprocess.run(
                    ["promtool", "check", "rules", str(file_path)],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    self.warnings.append(f"Promtool validation failed for {rule_file}: {result.stderr}")
                    
            except yaml.YAMLError as e:
                self.errors.append(f"YAML syntax error in {rule_file}: {e}")
            except Exception as e:
                self.warnings.append(f"Could not validate {rule_file}: {e}")
    
    def _validate_rule_structure(self, config, filename):
        """Validate rule structure and required fields"""
        if 'groups' not in config:
            self.errors.append(f"{filename}: Missing 'groups' section")
            return
            
        for group in config['groups']:
            if 'name' not in group:
                self.errors.append(f"{filename}: Group missing name")
                continue
                
            if 'rules' not in group:
                self.warnings.append(f"{filename}: Group {group['name']} has no rules")
                continue
                
            for rule in group['rules']:
                if 'alert' not in rule:
                    continue  # May be recording rule
                    
                required_fields = ['expr', 'labels', 'annotations']
                for field in required_fields:
                    if field not in rule:
                        self.errors.append(
                            f"{filename}: Alert {rule['alert']} missing {field}"
                        )
                
                # Check required annotations
                if 'annotations' in rule:
                    required_annotations = ['summary', 'description']
                    for annotation in required_annotations:
                        if annotation not in rule['annotations']:
                            self.warnings.append(
                                f"{filename}: Alert {rule['alert']} missing {annotation}"
                            )
    
    def validate_alertmanager_config(self):
        """Validate Alertmanager configuration"""
        print("📬 Validating Alertmanager configuration...")
        
        if not self.alertmanager_config.exists():
            self.errors.append("Missing Alertmanager configuration file")
            return
            
        try:
            with open(self.alertmanager_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
            # Validate required sections
            required_sections = ['global', 'route', 'receivers']
            for section in required_sections:
                if section not in config:
                    self.errors.append(f"Alertmanager config missing {section}")
            
            # Use amtool if available
            result = subprocess.run(
                ["amtool", "config", "check", str(self.alertmanager_config)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                self.warnings.append(f"Amtool validation failed: {result.stderr}")
                
        except yaml.YAMLError as e:
            self.errors.append(f"YAML syntax error in alertmanager.yml: {e}")
        except Exception as e:
            self.warnings.append(f"Could not validate alertmanager.yml: {e}")
    
    def validate_notification_channels(self):
        """Validate notification channel configurations"""
        print("📨 Validating notification channels...")
        
        try:
            with open(self.alertmanager_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except:
            return  # Already reported error
            
        receivers = config.get('receivers', [])
        
        # Check for required receivers
        required_receivers = [
            'critical-alerts',
            'warning-alerts', 
            'security-alerts',
            'data-quality-alerts'
        ]
        
        receiver_names = [r['name'] for r in receivers]
        for required in required_receivers:
            if required not in receiver_names:
                self.errors.append(f"Missing required receiver: {required}")
        
        # Validate receiver configurations
        for receiver in receivers:
            self._validate_receiver_config(receiver)
    
    def _validate_receiver_config(self, receiver):
        """Validate individual receiver configuration"""
        name = receiver.get('name', 'unnamed')
        
        # Check for at least one notification method
        notification_methods = [
            'email_configs', 'slack_configs', 'pagerduty_configs', 'webhook_configs'
        ]
        
        has_notification = any(method in receiver for method in notification_methods)
        if not has_notification and name != 'null':
            self.warnings.append(f"Receiver {name} has no notification methods")
        
        # Validate Slack configs
        if 'slack_configs' in receiver:
            for slack_config in receiver['slack_configs']:
                if 'api_url' not in slack_config:
                    self.errors.append(f"Slack config in {name} missing api_url")
                if 'channel' not in slack_config:
                    self.warnings.append(f"Slack config in {name} missing channel")
        
        # Validate PagerDuty configs
        if 'pagerduty_configs' in receiver:
            for pd_config in receiver['pagerduty_configs']:
                if 'routing_key' not in pd_config:
                    self.errors.append(f"PagerDuty config in {name} missing routing_key")
    
    def validate_alert_routing(self):
        """Validate alert routing configuration"""
        print("🚦 Validating alert routing...")
        
        try:
            with open(self.alertmanager_config, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
        except:
            return
            
        route = config.get('route', {})
        
        # Check default route configuration
        if 'receiver' not in route:
            self.errors.append("Default route missing receiver")
        
        # Validate sub-routes
        routes = route.get('routes', [])
        if not routes:
            self.warnings.append("No sub-routes configured")
        
        # Check for proper severity routing
        has_critical_route = False
        has_warning_route = False
        
        for subroute in routes:
            match = subroute.get('match', {})
            if match.get('severity') == 'critical':
                has_critical_route = True
            if match.get('severity') == 'warning':
                has_warning_route = True
        
        if not has_critical_route:
            self.warnings.append("No specific route for critical alerts")
        if not has_warning_route:
            self.warnings.append("No specific route for warning alerts")
    
    def generate_report(self):
        """Generate validation report"""
        print("\n" + "="*50)
        print("📋 ALERTING CONFIGURATION VALIDATION REPORT")
        print("="*50)
        
        if not self.errors and not self.warnings:
            print("✅ All validations passed! Configuration is production-ready.")
            return True
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  • {error}")
        
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  • {warning}")
        
        print(f"\n📊 Summary: {len(self.errors)} errors, {len(self.warnings)} warnings")
        
        if self.errors:
            print("❌ Configuration has critical issues that must be fixed.")
            return False
        else:
            print("⚠️  Configuration has warnings but is functional.")
            return True


def main():
    """Main validation function"""
    validator = AlertingConfigValidator()
    success = validator.validate_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main() 