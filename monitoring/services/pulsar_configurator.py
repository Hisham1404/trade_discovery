"""
Pulsar Configuration Service
Manages namespaces, topics, schemas, and policies for the trading signal system
"""

import logging
import asyncio
import json
from typing import List, Dict, Optional
from dataclasses import dataclass
import pulsar
from pulsar.admin import PulsarAdmin

logger = logging.getLogger(__name__)

@dataclass
class TopicConfig:
    """Configuration for a Pulsar topic"""
    name: str
    namespace: str = "trading-signals"
    tenant: str = "public"
    partitions: int = 4
    retention_days: int = 7
    ttl_hours: int = 24
    schema_type: str = "JSON"

@dataclass
class SignalSchema:
    """JSON schema for trading signals"""
    type: str = "record"
    name: str = "TradingSignal"
    fields: List[Dict] = None
    
    def __post_init__(self):
        if self.fields is None:
            self.fields = [
                {"name": "signal_id", "type": "string"},
                {"name": "agent_type", "type": "string"},
                {"name": "symbol", "type": "string"},
                {"name": "signal_type", "type": "string"},
                {"name": "confidence", "type": "double"},
                {"name": "target_price", "type": ["null", "double"]},
                {"name": "stop_loss", "type": ["null", "double"]},
                {"name": "timestamp", "type": "long"},
                {"name": "metadata", "type": "map", "values": "string"}
            ]

class PulsarConfigurator:
    """Manages Pulsar configuration for the trading system"""
    
    def __init__(self, service_url: str = "pulsar://localhost:6650", 
                 admin_url: str = "http://localhost:8080"):
        self.service_url = service_url
        self.admin_url = admin_url
        self.admin_client = None
        self.client = None
        
        # Define agent topics
        self.agent_topics = [
            TopicConfig("technical-agent"),
            TopicConfig("fundamental-agent"),
            TopicConfig("sentiment-agent"),
            TopicConfig("momentum-agent"),
            TopicConfig("mean-reversion-agent"),
            TopicConfig("volatility-agent"),
            TopicConfig("risk-agent")
        ]
    
    async def initialize(self) -> bool:
        """Initialize Pulsar admin and client connections"""
        try:
            self.admin_client = PulsarAdmin(self.admin_url)
            self.client = pulsar.Client(self.service_url)
            logger.info(f"Connected to Pulsar at {self.service_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Pulsar: {e}")
            return False
    
    async def create_namespace(self, namespace: str = "trading-signals", 
                             tenant: str = "public") -> bool:
        """Create the trading-signals namespace"""
        try:
            namespace_name = f"{tenant}/{namespace}"
            
            # Check if namespace exists
            try:
                existing_namespaces = self.admin_client.namespaces().get_namespaces(tenant)
                if namespace_name in existing_namespaces:
                    logger.info(f"Namespace {namespace_name} already exists")
                    return True
            except Exception:
                # Namespace doesn't exist, continue with creation
                pass
            
            # Create namespace
            self.admin_client.namespaces().create_namespace(namespace_name)
            
            # Set namespace policies
            policies = {
                "retention_size_in_mb": -1,
                "retention_time_in_minutes": 7 * 24 * 60,  # 7 days
                "max_producers_per_topic": 10,
                "max_consumers_per_topic": 10,
                "max_consumers_per_subscription": 10,
                "message_ttl_in_seconds": 24 * 60 * 60,  # 24 hours
                "max_unacked_messages_per_consumer": 1000
            }
            
            self.admin_client.namespaces().set_retention(namespace_name, policies)
            logger.info(f"Created namespace {namespace_name} with retention policies")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create namespace {namespace}: {e}")
            return False
    
    async def create_topic(self, topic_config: TopicConfig) -> bool:
        """Create a partitioned topic with schema"""
        try:
            topic_name = f"persistent://{topic_config.tenant}/{topic_config.namespace}/{topic_config.name}"
            
            # Create partitioned topic
            self.admin_client.topics().create_partitioned_topic(
                topic_name, topic_config.partitions
            )
            
            # Set topic schema
            schema = SignalSchema()
            schema_info = pulsar.schema.JsonSchema(
                record_cls=None,
                schema_definition=json.dumps({
                    "type": schema.type,
                    "name": schema.name,
                    "fields": schema.fields
                })
            )
            
            # Apply schema to topic
            self.admin_client.schemas().create_schema(topic_name, schema_info)
            
            # Set topic policies
            self.admin_client.topics().set_retention(
                topic_name,
                retention_time_in_minutes=topic_config.retention_days * 24 * 60,
                retention_size_in_mb=-1
            )
            
            logger.info(f"Created topic {topic_name} with {topic_config.partitions} partitions")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create topic {topic_config.name}: {e}")
            return False
    
    async def setup_all_topics(self) -> bool:
        """Set up all agent topics with proper configuration"""
        try:
            # First create the namespace
            if not await self.create_namespace():
                return False
            
            # Create all agent topics
            for topic_config in self.agent_topics:
                if not await self.create_topic(topic_config):
                    logger.error(f"Failed to create topic {topic_config.name}")
                    return False
            
            logger.info(f"Successfully created {len(self.agent_topics)} agent topics")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup topics: {e}")
            return False
    
    def get_producer_config(self, agent_type: str) -> Dict:
        """Get optimized producer configuration for agents"""
        return {
            "topic": f"persistent://public/trading-signals/{agent_type}",
            "producer_name": f"{agent_type}-producer",
            "send_timeout_millis": 30000,
            "batching_enabled": True,
            "batching_max_messages": 100,
            "batching_max_publish_delay_ms": 10,
            "compression_type": pulsar.CompressionType.LZ4,
            "max_pending_messages": 1000,
            "block_if_queue_full": True
        }
    
    def get_consumer_config(self, agent_type: str, subscription_name: str) -> Dict:
        """Get optimized consumer configuration for monitoring"""
        return {
            "topic": f"persistent://public/trading-signals/{agent_type}",
            "subscription_name": subscription_name,
            "consumer_type": pulsar.ConsumerType.Shared,
            "receiver_queue_size": 100,
            "max_total_receiver_queue_size_across_partitions": 1000,
            "consumer_name": f"{agent_type}-monitor-consumer"
        }
    
    async def validate_setup(self) -> Dict[str, bool]:
        """Validate that all topics and configurations are working"""
        results = {}
        
        try:
            # Check namespace
            namespace_name = "public/trading-signals"
            try:
                namespaces = self.admin_client.namespaces().get_namespaces("public")
                results["namespace_exists"] = namespace_name in namespaces
            except Exception as e:
                results["namespace_exists"] = False
                logger.error(f"Failed to check namespace: {e}")
            
            # Check each topic
            for topic_config in self.agent_topics:
                topic_name = f"persistent://public/trading-signals/{topic_config.name}"
                try:
                    stats = self.admin_client.topics().get_stats(topic_name)
                    results[f"topic_{topic_config.name}"] = True
                except Exception as e:
                    results[f"topic_{topic_config.name}"] = False
                    logger.error(f"Failed to validate topic {topic_config.name}: {e}")
            
            # Test producer/consumer creation
            try:
                test_producer = self.client.create_producer(
                    "persistent://public/trading-signals/technical-agent"
                )
                test_producer.close()
                results["producer_test"] = True
            except Exception as e:
                results["producer_test"] = False
                logger.error(f"Failed to create test producer: {e}")
            
            try:
                test_consumer = self.client.subscribe(
                    "persistent://public/trading-signals/technical-agent",
                    "validation-test",
                    consumer_type=pulsar.ConsumerType.Shared
                )
                test_consumer.close()
                results["consumer_test"] = True
            except Exception as e:
                results["consumer_test"] = False
                logger.error(f"Failed to create test consumer: {e}")
            
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            results["validation_error"] = str(e)
        
        return results
    
    async def get_topic_stats(self) -> Dict[str, Dict]:
        """Get statistics for all topics"""
        stats = {}
        
        for topic_config in self.agent_topics:
            topic_name = f"persistent://public/trading-signals/{topic_config.name}"
            try:
                topic_stats = self.admin_client.topics().get_stats(topic_name)
                stats[topic_config.name] = {
                    "msg_rate_in": topic_stats.msgRateIn,
                    "msg_rate_out": topic_stats.msgRateOut,
                    "msg_throughput_in": topic_stats.msgThroughputIn,
                    "msg_throughput_out": topic_stats.msgThroughputOut,
                    "storage_size": topic_stats.storageSize,
                    "publishers": len(topic_stats.publishers),
                    "subscriptions": len(topic_stats.subscriptions)
                }
            except Exception as e:
                logger.error(f"Failed to get stats for {topic_config.name}: {e}")
                stats[topic_config.name] = {"error": str(e)}
        
        return stats
    
    async def cleanup(self):
        """Clean up connections"""
        try:
            if self.client:
                self.client.close()
            if self.admin_client:
                self.admin_client.close()
            logger.info("Cleaned up Pulsar connections")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# Singleton instance for application use
pulsar_configurator = PulsarConfigurator()

async def initialize_pulsar() -> bool:
    """Initialize Pulsar configuration for the application"""
    if await pulsar_configurator.initialize():
        return await pulsar_configurator.setup_all_topics()
    return False

async def get_pulsar_stats() -> Dict[str, Dict]:
    """Get current Pulsar topic statistics"""
    return await pulsar_configurator.get_topic_stats() 