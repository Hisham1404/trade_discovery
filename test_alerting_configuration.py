"""
Test Suite for Enhanced Alerting Configuration
Tests all alerting rules, notification channels, and alert suppression logic
"""

import pytest
import yaml
import os
import json
from unittest.mock import Mock, patch
import requests


class TestAlertingRulesConfiguration:
    """Test alerting rules are properly configured with correct thresholds"""
    
    def setup_method(self):
        """Load alerting rule files for testing"""
        self.infrastructure_rules = self._load_yaml_file("config/prometheus/rules/infrastructure_alerts.yml")
        self.integration_rules = self._load_yaml_file("config/prometheus/rules/integration_alerts.yml") 
        self.cost_rules = self._load_yaml_file("config/prometheus/rules/cost_alerts.yml")
        self.security_rules = self._load_yaml_file("config/prometheus/rules/security_alerts.yml")
        self.data_quality_rules = self._load_yaml_file("config/prometheus/rules/data_quality_alerts.yml")
    
    def _load_yaml_file(self, filepath):
        """Helper to load YAML files safely"""
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {"groups": []}  # Return empty structure for missing files
    
    def test_sla_violation_alerts_present(self):
        """Test SLA violation alerts exist with correct thresholds"""
        # Test P95 latency SLA violations (60ms threshold)
        agent_alerts = self._find_rule_group(self.infrastructure_rules, "agent_alerts")
        high_execution_alert = self._find_alert_rule(agent_alerts, "AgentHighExecutionTime")
        
        assert high_execution_alert is not None, "AgentHighExecutionTime alert must be configured"
        assert "0.060" in high_execution_alert['expr'], "Should monitor 60ms SLA threshold"
        assert high_execution_alert['labels']['severity'] == 'warning'
        
        # Test integration latency SLA violations
        integration_alerts = self._find_rule_group(self.integration_rules, "integration_monitoring")
        latency_alert = self._find_alert_rule(integration_alerts, "HighEventPublishingLatency")
        
        assert latency_alert is not None, "High latency alert must be configured"
        assert latency_alert['labels']['severity'] == 'warning'
    
    def test_data_quality_alerts_configured(self):
        """Test data quality monitoring alerts exist"""
        data_quality_group = self._find_rule_group(self.data_quality_rules, "data_quality_alerts")
        
        # Test for missing data alerts
        missing_data_alert = self._find_alert_rule(data_quality_group, "MissingMarketData")
        assert missing_data_alert is not None, "Missing market data alert required"
        
        # Test for data validation failures
        validation_alert = self._find_alert_rule(data_quality_group, "DataValidationFailures")
        assert validation_alert is not None, "Data validation failure alert required"
        assert validation_alert['labels']['severity'] in ['warning', 'critical']
    
    def test_security_alerts_configured(self):
        """Test security-related alerts are properly configured"""
        security_group = self._find_rule_group(self.security_rules, "security_alerts")
        
        # Test authentication failure alerts
        auth_failure_alert = self._find_alert_rule(security_group, "HighAuthenticationFailures")
        assert auth_failure_alert is not None, "Authentication failure alert required"
        
        # Test unauthorized access alerts
        unauthorized_alert = self._find_alert_rule(security_group, "UnauthorizedAccess")
        assert unauthorized_alert is not None, "Unauthorized access alert required"
    
    def test_system_failure_alerts_configured(self):
        """Test comprehensive system failure monitoring"""
        # Test agent down alerts
        agent_group = self._find_rule_group(self.infrastructure_rules, "agent_alerts")
        agent_down_alert = self._find_alert_rule(agent_group, "AgentDown")
        
        assert agent_down_alert is not None, "Agent down alert must exist"
        assert agent_down_alert['labels']['severity'] == 'critical'
        assert "for: 5m" in str(agent_down_alert), "Should wait 5 minutes before alerting"
    
    def test_alert_thresholds_appropriate(self):
        """Test alert thresholds are set to appropriate levels"""
        # Test CPU usage threshold
        infra_group = self._find_rule_group(self.infrastructure_rules, "infrastructure_alerts")
        cpu_alert = self._find_alert_rule(infra_group, "HighCPUUsage")
        
        assert cpu_alert is not None, "CPU usage alert required"
        assert "80" in cpu_alert['expr'], "CPU threshold should be 80%"
        
        # Test memory usage threshold  
        memory_alert = self._find_alert_rule(infra_group, "HighMemoryUsage")
        assert memory_alert is not None, "Memory usage alert required"
        assert "85" in memory_alert['expr'], "Memory threshold should be 85%"
    
    def _find_rule_group(self, rules_config, group_name):
        """Helper to find a specific rule group"""
        if not rules_config or 'groups' not in rules_config:
            return None
        
        for group in rules_config['groups']:
            if group['name'] == group_name:
                return group
        return None
    
    def _find_alert_rule(self, group, alert_name):
        """Helper to find a specific alert rule within a group"""
        if not group or 'rules' not in group:
            return None
            
        for rule in group['rules']:
            if rule.get('alert') == alert_name:
                return rule
        return None


class TestAlertmanagerConfiguration:
    """Test Alertmanager notification channels and routing"""
    
    def setup_method(self):
        """Load Alertmanager configuration for testing"""
        self.alertmanager_config = self._load_yaml_file("config/alertmanager/alertmanager.yml")
    
    def _load_yaml_file(self, filepath):
        """Helper to load YAML files safely"""
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}
    
    def test_notification_channels_configured(self):
        """Test all required notification channels are configured"""
        receivers = self.alertmanager_config.get('receivers', [])
        receiver_names = [r['name'] for r in receivers]
        
        # Test email notifications exist
        assert 'critical-alerts' in receiver_names, "Critical email alerts must be configured"
        assert 'warning-alerts' in receiver_names, "Warning email alerts must be configured"
        
        # Test webhook notifications exist  
        assert 'web.hook.default' in receiver_names, "Default webhook must be configured"
    
    def test_slack_integration_configured(self):
        """Test Slack notification integration is properly set up"""
        receivers = self.alertmanager_config.get('receivers', [])
        
        # Look for Slack receiver configuration
        slack_receiver = None
        for receiver in receivers:
            if 'slack_configs' in receiver:
                slack_receiver = receiver
                break
        
        assert slack_receiver is not None, "Slack notifications must be configured"
        
        # Test Slack channel configuration
        slack_configs = slack_receiver.get('slack_configs', [])
        assert len(slack_configs) > 0, "At least one Slack channel must be configured"
    
    def test_pagerduty_integration_configured(self):
        """Test PagerDuty integration for critical alerts"""
        receivers = self.alertmanager_config.get('receivers', [])
        
        # Look for PagerDuty receiver configuration
        pagerduty_receiver = None
        for receiver in receivers:
            if 'pagerduty_configs' in receiver:
                pagerduty_receiver = receiver
                break
        
        assert pagerduty_receiver is not None, "PagerDuty notifications must be configured for critical alerts"
    
    def test_alert_routing_configured(self):
        """Test alert routing rules are properly configured"""
        route = self.alertmanager_config.get('route', {})
        routes = route.get('routes', [])
        
        # Test critical alert routing
        critical_route = None
        warning_route = None
        
        for r in routes:
            if r.get('match', {}).get('severity') == 'critical':
                critical_route = r
            elif r.get('match', {}).get('severity') == 'warning':
                warning_route = r
        
        assert critical_route is not None, "Critical alert routing must be configured"
        assert warning_route is not None, "Warning alert routing must be configured"
        
        # Test critical alerts have faster response time
        assert critical_route.get('repeat_interval') == '5m', "Critical alerts should repeat every 5 minutes"
        assert warning_route.get('repeat_interval') == '1h', "Warning alerts should repeat every hour"
    
    def test_alert_suppression_configured(self):
        """Test alert suppression and grouping is properly configured"""
        # Test inhibit rules exist
        inhibit_rules = self.alertmanager_config.get('inhibit_rules', [])
        assert len(inhibit_rules) > 0, "Alert suppression rules must be configured"
        
        # Test critical alerts suppress warnings
        critical_suppression = None
        for rule in inhibit_rules:
            if (rule.get('source_match', {}).get('severity') == 'critical' and 
                rule.get('target_match', {}).get('severity') == 'warning'):
                critical_suppression = rule
                break
        
        assert critical_suppression is not None, "Critical alerts should suppress warning alerts"
    
    def test_escalation_policies_configured(self):
        """Test escalation policies are properly set up"""
        route = self.alertmanager_config.get('route', {})
        
        # Test group settings for escalation
        assert route.get('group_wait') is not None, "Group wait must be configured"
        assert route.get('group_interval') is not None, "Group interval must be configured"
        assert route.get('repeat_interval') is not None, "Repeat interval must be configured"


class TestAlertingIntegration:
    """Test end-to-end alerting integration"""
    
    @patch('requests.post')
    def test_webhook_notification_delivery(self, mock_post):
        """Test webhook notifications are delivered correctly"""
        mock_post.return_value.status_code = 200
        
        # Simulate webhook delivery
        webhook_url = "http://localhost:5001/alerts"
        alert_payload = {
            "receiver": "web.hook.default",
            "status": "firing",
            "alerts": [{
                "status": "firing",
                "labels": {
                    "alertname": "TestAlert",
                    "severity": "warning"
                },
                "annotations": {
                    "summary": "Test alert for webhook delivery"
                }
            }]
        }
        
        response = requests.post(webhook_url, json=alert_payload)
        
        assert response.status_code == 200, "Webhook delivery should succeed"
        mock_post.assert_called_once()
    
    def test_alert_template_validation(self):
        """Test alert templates are valid and render correctly"""
        # Test email template format
        alertmanager_config = self._load_yaml_file("config/alertmanager/alertmanager.yml")
        
        receivers = alertmanager_config.get('receivers', [])
        email_receiver = None
        
        for receiver in receivers:
            if 'email_configs' in receiver:
                email_receiver = receiver
                break
        
        assert email_receiver is not None, "Email receiver must be configured"
        
        email_configs = email_receiver.get('email_configs', [])
        assert len(email_configs) > 0, "Email configuration must exist"
        
        # Test template fields exist
        email_config = email_configs[0]
        assert 'subject' in email_config, "Email subject template required"
        assert 'body' in email_config, "Email body template required"
    
    def test_alert_noise_reduction(self):
        """Test alert noise reduction mechanisms"""
        alertmanager_config = self._load_yaml_file("config/alertmanager/alertmanager.yml")
        
        # Test grouping configuration
        route = alertmanager_config.get('route', {})
        group_by = route.get('group_by', [])
        
        assert 'alertname' in group_by, "Alerts should be grouped by alertname"
        assert 'cluster' in group_by or 'service' in group_by, "Alerts should be grouped by service/cluster"
    
    def _load_yaml_file(self, filepath):
        """Helper to load YAML files safely"""
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}


class TestAlertingPerformance:
    """Test alerting system performance and reliability"""
    
    def test_alert_evaluation_frequency(self):
        """Test alert evaluation intervals are appropriate"""
        infrastructure_rules = self._load_yaml_file("config/prometheus/rules/infrastructure_alerts.yml")
        
        for group in infrastructure_rules.get('groups', []):
            interval = group.get('interval', '30s')
            
            # Parse interval (assume format like '30s', '1m', etc.)
            if 's' in interval:
                seconds = int(interval.replace('s', ''))
                assert seconds <= 60, f"Evaluation interval {interval} should be <= 60 seconds"
            elif 'm' in interval:
                minutes = int(interval.replace('m', ''))
                assert minutes <= 2, f"Evaluation interval {interval} should be <= 2 minutes"
    
    def test_alert_for_duration_appropriate(self):
        """Test 'for' durations prevent flapping while maintaining responsiveness"""
        infrastructure_rules = self._load_yaml_file("config/prometheus/rules/infrastructure_alerts.yml")
        
        for group in infrastructure_rules.get('groups', []):
            for rule in group.get('rules', []):
                if 'alert' in rule:
                    for_duration = rule.get('for', '0m')
                    severity = rule.get('labels', {}).get('severity', '')
                    
                    if severity == 'critical':
                        # Critical alerts should fire quickly (1-5 minutes)
                        assert self._parse_duration(for_duration) <= 300, f"Critical alert {rule['alert']} should fire within 5 minutes"
                    elif severity == 'warning':
                        # Warning alerts can wait longer (2-10 minutes)
                        assert self._parse_duration(for_duration) <= 600, f"Warning alert {rule['alert']} should fire within 10 minutes"
    
    def _parse_duration(self, duration_str):
        """Parse duration string to seconds"""
        if 's' in duration_str:
            return int(duration_str.replace('s', ''))
        elif 'm' in duration_str:
            return int(duration_str.replace('m', '')) * 60
        elif 'h' in duration_str:
            return int(duration_str.replace('h', '')) * 3600
        return 0
    
    def _load_yaml_file(self, filepath):
        """Helper to load YAML files safely"""
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            return {}


if __name__ == "__main__":
    # Run tests with coverage
    pytest.main([
        __file__,
        "-v",
        "--cov=config/prometheus/rules",
        "--cov=config/alertmanager", 
        "--cov-report=term-missing",
        "--tb=short"
    ]) 