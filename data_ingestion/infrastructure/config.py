"""Configuration Management for Data Ingestion Infrastructure"""

import os
from typing import Dict, Any


class DataIngestionConfig:
    """Centralized configuration for data ingestion infrastructure"""
    
    def __init__(self):
        self.environment = os.getenv('ENVIRONMENT', 'development')
        self.debug = os.getenv('DEBUG', 'True').lower() == 'true'
        self.project_root = os.getcwd()
        self.data_dir = os.path.join(self.project_root, 'data')
        self.logs_dir = os.path.join(self.project_root, 'logs')
    
    @property
    def pulsar_config(self) -> Dict[str, Any]:
        """Get Pulsar configuration"""
        return {
            'service_url': os.getenv('PULSAR_SERVICE_URL', 'pulsar://localhost:6650'),
            'connection_timeout': int(os.getenv('PULSAR_CONNECTION_TIMEOUT', '30')),
            'operation_timeout': int(os.getenv('PULSAR_OPERATION_TIMEOUT', '30')),
            'max_connections_per_broker': int(os.getenv('PULSAR_MAX_CONNECTIONS', '1')),
            'keep_alive_interval': int(os.getenv('PULSAR_KEEP_ALIVE', '30')),
            'max_retries': int(os.getenv('PULSAR_MAX_RETRIES', '3')),
            'retry_delay': float(os.getenv('PULSAR_RETRY_DELAY', '1.0')),
        }
    
    @property
    def elasticsearch_config(self) -> Dict[str, Any]:
        """Get Elasticsearch configuration"""
        hosts_str = os.getenv('ELASTICSEARCH_HOSTS', 'http://localhost:9200')
        hosts = [host.strip() for host in hosts_str.split(',') if host.strip()]
        
        return {
            'hosts': hosts,
            'timeout': int(os.getenv('ELASTICSEARCH_TIMEOUT', '30')),
            'max_retries': int(os.getenv('ELASTICSEARCH_MAX_RETRIES', '3')),
            'retry_on_timeout': True,
            'sniff_on_start': True,
            'sniff_on_connection_fail': True,
            'sniffer_timeout': 60,
            'http_compress': True,
        }
    
    @property
    def validation_config(self) -> Dict[str, Any]:
        """Get Great Expectations validation configuration"""
        context_root = os.getenv('GX_CONTEXT_DIR', os.path.join(self.data_dir, 'great_expectations'))
        
        return {
            'context_root_dir': context_root,
        } 