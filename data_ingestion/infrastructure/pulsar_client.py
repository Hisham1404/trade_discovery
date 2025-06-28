"""
Pulsar Client Manager for Real-time Data Ingestion

This module provides a robust Pulsar client management system with:
- Connection pooling and retry mechanisms
- Producer and consumer creation and management
- Health checks and monitoring
- Graceful error handling and recovery

Based on Apache Pulsar Python client documentation and best practices.
"""

import pulsar
import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import threading
from contextlib import contextmanager


logger = logging.getLogger(__name__)


@dataclass
class PulsarConfig:
    """Configuration for Pulsar client connection"""
    service_url: str = 'pulsar://localhost:6650'
    connection_timeout: int = 30  # seconds
    operation_timeout: int = 30   # seconds
    max_connections_per_broker: int = 1
    keep_alive_interval: int = 30  # seconds
    max_retries: int = 3
    retry_delay: float = 1.0  # seconds
    authentication: Optional[Dict[str, Any]] = None
    tls_enabled: bool = False
    tls_trust_certs_file_path: Optional[str] = None
    tls_allow_insecure_connection: bool = False


class PulsarManager:
    """
    Manages Pulsar client connections with robust error handling and retry mechanisms.
    
    Provides centralized management of Pulsar producers and consumers with:
    - Automatic connection retry with exponential backoff
    - Connection pooling for optimal resource utilization
    - Health monitoring and recovery
    - Thread-safe operations
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Pulsar manager with configuration.
        
        Args:
            config: Dictionary containing Pulsar configuration parameters
        """
        self.config = PulsarConfig(**config)
        self._client: Optional[pulsar.Client] = None
        self._producers: Dict[str, pulsar.Producer] = {}
        self._consumers: Dict[str, pulsar.Consumer] = {}
        self._lock = threading.RLock()
        
        logger.info(f"Initializing PulsarManager with service URL: {self.config.service_url}")
    
    def get_client(self, max_retries: Optional[int] = None) -> pulsar.Client:
        """
        Get or create Pulsar client with automatic retry mechanism.
        
        Args:
            max_retries: Maximum number of connection retry attempts
            
        Returns:
            pulsar.Client: Connected Pulsar client instance
            
        Raises:
            Exception: If connection fails after all retry attempts
        """
        if self._client is not None:
            return self._client
        
        with self._lock:
            if self._client is not None:  # Double-checked locking
                return self._client
            
            max_retries = max_retries or self.config.max_retries
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    logger.info(f"Attempting to connect to Pulsar (attempt {attempt + 1}/{max_retries + 1})")
                    
                    # Build client configuration
                    client_config = {
                        'connection_timeout_ms': self.config.connection_timeout * 1000,
                        'operation_timeout_seconds': self.config.operation_timeout,
                        'max_connections_per_broker': self.config.max_connections_per_broker,
                        'keep_alive_interval_seconds': self.config.keep_alive_interval,
                    }
                    
                    # Add TLS configuration if enabled
                    if self.config.tls_enabled:
                        client_config.update({
                            'tls_trust_certs_file_path': self.config.tls_trust_certs_file_path,
                            'tls_allow_insecure_connection': self.config.tls_allow_insecure_connection,
                        })
                    
                    # Add authentication if provided
                    if self.config.authentication:
                        client_config['authentication'] = self._create_authentication()
                    
                    # Create client instance
                    self._client = pulsar.Client(self.config.service_url, **client_config)
                    
                    logger.info("Successfully connected to Pulsar")
                    return self._client
                    
                except Exception as e:
                    last_exception = e
                    logger.warning(f"Pulsar connection attempt {attempt + 1} failed: {e}")
                    
                    if attempt < max_retries:
                        delay = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                        logger.info(f"Retrying in {delay} seconds...")
                        time.sleep(delay)
            
            # All attempts failed
            error_msg = f"Failed to connect to Pulsar after {max_retries + 1} attempts"
            logger.error(f"{error_msg}. Last error: {last_exception}")
            raise Exception(f"{error_msg}") from last_exception
    
    def _create_authentication(self) -> pulsar.Authentication:
        """Create Pulsar authentication object based on configuration."""
        auth_config = self.config.authentication
        auth_type = auth_config.get('type', '').lower()
        
        if auth_type == 'tls':
            return pulsar.AuthenticationTLS(
                auth_config['cert_file'],
                auth_config['key_file']
            )
        elif auth_type == 'oauth2':
            return pulsar.AuthenticationOauth2(auth_config['params'])
        elif auth_type == 'basic':
            return pulsar.AuthenticationBasic(
                auth_config['username'],
                auth_config['password']
            )
        else:
            raise ValueError(f"Unsupported authentication type: {auth_type}")
    
    def create_producer(self, topic: str, **kwargs) -> pulsar.Producer:
        """
        Create or get existing Pulsar producer for the specified topic.
        
        Args:
            topic: Pulsar topic name
            **kwargs: Additional producer configuration options
            
        Returns:
            pulsar.Producer: Producer instance for the topic
        """
        with self._lock:
            if topic in self._producers:
                return self._producers[topic]
            
            client = self.get_client()
            
            # Default producer configuration
            producer_config = {
                'topic': topic,
                'send_timeout_millis': 30000,
                'block_if_queue_full': True,
                'batching_enabled': True,
                'compression_type': pulsar.CompressionType.LZ4,
                **kwargs
            }
            
            try:
                producer = client.create_producer(**producer_config)
                self._producers[topic] = producer
                
                logger.info(f"Created producer for topic: {topic}")
                return producer
                
            except Exception as e:
                logger.error(f"Failed to create producer for topic {topic}: {e}")
                raise
    
    def create_consumer(self, topic: str, subscription: str, **kwargs) -> pulsar.Consumer:
        """
        Create or get existing Pulsar consumer for the specified topic and subscription.
        
        Args:
            topic: Pulsar topic name
            subscription: Subscription name
            **kwargs: Additional consumer configuration options
            
        Returns:
            pulsar.Consumer: Consumer instance for the topic
        """
        consumer_key = f"{topic}:{subscription}"
        
        with self._lock:
            if consumer_key in self._consumers:
                return self._consumers[consumer_key]
            
            client = self.get_client()
            
            # Default consumer configuration
            consumer_config = {
                'topic': topic,
                'subscription_name': subscription,
                'consumer_type': pulsar.ConsumerType.Exclusive,
                'subscription_type': pulsar.SubscriptionType.Exclusive,
                'receiver_queue_size': 1000,
                **kwargs
            }
            
            try:
                consumer = client.subscribe(**consumer_config)
                self._consumers[consumer_key] = consumer
                
                logger.info(f"Created consumer for topic: {topic}, subscription: {subscription}")
                return consumer
                
            except Exception as e:
                logger.error(f"Failed to create consumer for topic {topic}, subscription {subscription}: {e}")
                raise
    
    def health_check(self) -> bool:
        """
        Perform health check on Pulsar connection.
        
        Returns:
            bool: True if connection is healthy, False otherwise
        """
        try:
            if self._client is None:
                return False
            
            # Create a test producer to verify connection
            test_topic = "__health_check_topic__"
            producer = self._client.create_producer(test_topic)
            producer.close()
            
            logger.debug("Pulsar health check passed")
            return True
            
        except Exception as e:
            logger.warning(f"Pulsar health check failed: {e}")
            return False
    
    def get_topic_stats(self, topic: str) -> Dict[str, Any]:
        """
        Get statistics for a specific topic.
        
        Args:
            topic: Topic name to get statistics for
            
        Returns:
            Dict[str, Any]: Topic statistics
        """
        try:
            # Note: This is a placeholder - actual implementation would depend on
            # Pulsar admin API integration or client-side metrics collection
            stats = {
                'topic': topic,
                'producers_count': len([p for t, p in self._producers.items() if t == topic]),
                'consumers_count': len([c for tc, c in self._consumers.items() if tc.split(':')[0] == topic]),
                'connection_status': 'connected' if self._client else 'disconnected'
            }
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get stats for topic {topic}: {e}")
            return {}
    
    @contextmanager
    def producer_context(self, topic: str, **kwargs):
        """
        Context manager for Pulsar producer with automatic cleanup.
        
        Args:
            topic: Topic name
            **kwargs: Producer configuration
            
        Yields:
            pulsar.Producer: Producer instance
        """
        producer = None
        try:
            producer = self.create_producer(topic, **kwargs)
            yield producer
        finally:
            if producer and topic not in self._producers:
                # Only close if it's not cached
                try:
                    producer.close()
                except Exception as e:
                    logger.warning(f"Error closing producer for topic {topic}: {e}")
    
    @contextmanager
    def consumer_context(self, topic: str, subscription: str, **kwargs):
        """
        Context manager for Pulsar consumer with automatic cleanup.
        
        Args:
            topic: Topic name
            subscription: Subscription name
            **kwargs: Consumer configuration
            
        Yields:
            pulsar.Consumer: Consumer instance
        """
        consumer = None
        consumer_key = f"{topic}:{subscription}"
        try:
            consumer = self.create_consumer(topic, subscription, **kwargs)
            yield consumer
        finally:
            if consumer and consumer_key not in self._consumers:
                # Only close if it's not cached
                try:
                    consumer.close()
                except Exception as e:
                    logger.warning(f"Error closing consumer for topic {topic}, subscription {subscription}: {e}")
    
    def close(self):
        """
        Close all producers, consumers, and the client connection.
        Performs graceful cleanup of all resources.
        """
        with self._lock:
            logger.info("Shutting down PulsarManager...")
            
            # Close all producers
            for topic, producer in self._producers.items():
                try:
                    producer.close()
                    logger.debug(f"Closed producer for topic: {topic}")
                except Exception as e:
                    logger.warning(f"Error closing producer for topic {topic}: {e}")
            
            # Close all consumers
            for consumer_key, consumer in self._consumers.items():
                try:
                    consumer.close()
                    logger.debug(f"Closed consumer: {consumer_key}")
                except Exception as e:
                    logger.warning(f"Error closing consumer {consumer_key}: {e}")
            
            # Close client
            if self._client:
                try:
                    self._client.close()
                    logger.info("Closed Pulsar client")
                except Exception as e:
                    logger.warning(f"Error closing Pulsar client: {e}")
            
            # Clear references
            self._producers.clear()
            self._consumers.clear()
            self._client = None
            
            logger.info("PulsarManager shutdown complete")
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.close() 