"""
Elasticsearch Client Manager for Real-time Data Ingestion

This module provides a robust Elasticsearch client management system with:
- Async client with connection pooling
- Index management and document indexing
- Health checks and monitoring
- Retry mechanisms and error handling

Based on Elasticsearch Python client documentation and best practices.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
import json
from datetime import datetime
import threading

try:
    from elasticsearch import AsyncElasticsearch
    from elasticsearch.exceptions import ConnectionError, NotFoundError, RequestError
except ImportError:
    # Fallback for testing or when elasticsearch is not installed
    AsyncElasticsearch = None
    ConnectionError = Exception
    NotFoundError = Exception  
    RequestError = Exception


logger = logging.getLogger(__name__)


@dataclass
class ElasticsearchConfig:
    """Configuration for Elasticsearch client connection"""
    hosts: List[str] = None
    timeout: int = 30
    max_retries: int = 3
    retry_on_timeout: bool = True
    sniff_on_start: bool = True
    sniff_on_connection_fail: bool = True
    sniffer_timeout: int = 60
    http_compress: bool = True
    verify_certs: bool = True
    ssl_context: Optional[Any] = None
    api_key: Optional[str] = None
    basic_auth: Optional[tuple] = None
    
    def __post_init__(self):
        if self.hosts is None:
            self.hosts = ['http://localhost:9200']


class ElasticsearchManager:
    """
    Manages Elasticsearch client connections with robust error handling and performance optimization.
    
    Provides centralized management of Elasticsearch operations with:
    - Async connection management with connection pooling
    - Index lifecycle management
    - Document indexing with bulk operations support
    - Health monitoring and recovery
    - Thread-safe operations
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Elasticsearch manager with configuration.
        
        Args:
            config: Dictionary containing Elasticsearch configuration parameters
        """
        self.config = ElasticsearchConfig(**config)
        self._client: Optional[AsyncElasticsearch] = None
        self._lock = threading.RLock()
        
        logger.info(f"Initializing ElasticsearchManager with hosts: {self.config.hosts}")
    
    def get_client(self) -> AsyncElasticsearch:
        """
        Get or create Elasticsearch async client.
        
        Returns:
            AsyncElasticsearch: Connected Elasticsearch client instance
            
        Raises:
            ImportError: If elasticsearch library is not installed
        """
        if AsyncElasticsearch is None:
            raise ImportError("elasticsearch library is required. Install with: pip install elasticsearch")
        
        if self._client is not None:
            return self._client
        
        with self._lock:
            if self._client is not None:  # Double-checked locking
                return self._client
            
            # Build client configuration
            client_config = {
                'hosts': self.config.hosts,
                'timeout': self.config.timeout,
                'max_retries': self.config.max_retries,
                'retry_on_timeout': self.config.retry_on_timeout,
                'sniff_on_start': self.config.sniff_on_start,
                'sniff_on_connection_fail': self.config.sniff_on_connection_fail,
                'sniffer_timeout': self.config.sniffer_timeout,
                'http_compress': self.config.http_compress,
                'verify_certs': self.config.verify_certs,
            }
            
            # Add authentication if provided
            if self.config.api_key:
                client_config['api_key'] = self.config.api_key
            elif self.config.basic_auth:
                client_config['basic_auth'] = self.config.basic_auth
            
            # Add SSL context if provided
            if self.config.ssl_context:
                client_config['ssl_context'] = self.config.ssl_context
            
            try:
                self._client = AsyncElasticsearch(**client_config)
                logger.info("Successfully initialized Elasticsearch client")
                return self._client
                
            except Exception as e:
                logger.error(f"Failed to initialize Elasticsearch client: {e}")
                raise
    
    async def health_check(self) -> bool:
        """
        Perform health check on Elasticsearch connection.
        
        Returns:
            bool: True if connection is healthy, False otherwise
        """
        try:
            client = self.get_client()
            result = await client.ping()
            
            if result:
                logger.debug("Elasticsearch health check passed")
                return True
            else:
                logger.warning("Elasticsearch ping returned False")
                return False
                
        except Exception as e:
            logger.warning(f"Elasticsearch health check failed: {e}")
            return False
    
    async def get_cluster_info(self) -> Dict[str, Any]:
        """
        Get Elasticsearch cluster information.
        
        Returns:
            Dict[str, Any]: Cluster information
        """
        try:
            client = self.get_client()
            info = await client.info()
            
            cluster_stats = {
                'cluster_name': info.get('cluster_name', 'unknown'),
                'version': info.get('version', {}).get('number', 'unknown'),
                'status': 'connected'
            }
            
            # Get cluster health
            try:
                health = await client.cluster.health()
                cluster_stats.update({
                    'health_status': health.get('status', 'unknown'),
                    'active_shards': health.get('active_shards', 0),
                    'number_of_nodes': health.get('number_of_nodes', 0)
                })
            except Exception as e:
                logger.warning(f"Could not fetch cluster health: {e}")
            
            return cluster_stats
            
        except Exception as e:
            logger.error(f"Failed to get cluster info: {e}")
            return {'status': 'disconnected', 'error': str(e)}
    
    async def create_index(self, index_name: str, mapping: Dict[str, Any]) -> bool:
        """
        Create Elasticsearch index with mapping.
        
        Args:
            index_name: Name of the index to create
            mapping: Index mapping configuration
            
        Returns:
            bool: True if index was created successfully, False otherwise
        """
        try:
            client = self.get_client()
            
            # Check if index already exists
            exists = await client.indices.exists(index=index_name)
            if exists:
                logger.info(f"Index {index_name} already exists")
                return True
            
            # Create index with mapping
            result = await client.indices.create(
                index=index_name,
                body=mapping
            )
            
            acknowledged = result.get('acknowledged', False)
            if acknowledged:
                logger.info(f"Successfully created index: {index_name}")
                return True
            else:
                logger.warning(f"Index creation for {index_name} was not acknowledged")
                return False
                
        except Exception as e:
            logger.error(f"Failed to create index {index_name}: {e}")
            return False
    
    async def index_document(self, index_name: str, document: Dict[str, Any], 
                           doc_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Index a single document in Elasticsearch.
        
        Args:
            index_name: Name of the index
            document: Document to index
            doc_id: Optional document ID
            
        Returns:
            Dict[str, Any]: Indexing result
        """
        try:
            client = self.get_client()
            
            # Add timestamp if not present
            if 'timestamp' not in document:
                document['timestamp'] = datetime.utcnow().isoformat()
            
            index_params = {
                'index': index_name,
                'body': document
            }
            
            if doc_id:
                index_params['id'] = doc_id
            
            result = await client.index(**index_params)
            
            logger.debug(f"Indexed document in {index_name}: {result.get('_id')}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to index document in {index_name}: {e}")
            raise
    
    async def bulk_index(self, index_name: str, documents: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Bulk index multiple documents in Elasticsearch.
        
        Args:
            index_name: Name of the index
            documents: List of documents to index
            
        Returns:
            Dict[str, Any]: Bulk indexing result
        """
        try:
            client = self.get_client()
            
            # Prepare bulk actions
            actions = []
            for doc in documents:
                # Add timestamp if not present
                if 'timestamp' not in doc:
                    doc['timestamp'] = datetime.utcnow().isoformat()
                
                action = {
                    '_index': index_name,
                    '_source': doc
                }
                actions.append(action)
            
            # Perform bulk indexing
            result = await client.bulk(body=actions)
            
            # Process results
            errors = []
            successful = 0
            
            for item in result.get('items', []):
                if 'index' in item:
                    if item['index'].get('status') in [200, 201]:
                        successful += 1
                    else:
                        errors.append(item['index'].get('error', 'Unknown error'))
            
            bulk_result = {
                'total': len(documents),
                'successful': successful,
                'errors': len(errors),
                'error_details': errors[:10] if errors else []  # Limit error details
            }
            
            logger.info(f"Bulk indexed {successful}/{len(documents)} documents in {index_name}")
            if errors:
                logger.warning(f"Bulk indexing had {len(errors)} errors")
            
            return bulk_result
            
        except Exception as e:
            logger.error(f"Failed to bulk index documents in {index_name}: {e}")
            raise
    
    async def search(self, index_name: str, query: Dict[str, Any], 
                    size: int = 10, from_: int = 0) -> Dict[str, Any]:
        """
        Search documents in Elasticsearch.
        
        Args:
            index_name: Name of the index to search
            query: Elasticsearch query DSL
            size: Number of results to return
            from_: Offset for pagination
            
        Returns:
            Dict[str, Any]: Search results
        """
        try:
            client = self.get_client()
            
            search_params = {
                'index': index_name,
                'body': query,
                'size': size,
                'from': from_
            }
            
            result = await client.search(**search_params)
            
            search_result = {
                'total': result['hits']['total']['value'],
                'documents': [hit['_source'] for hit in result['hits']['hits']],
                'took': result.get('took', 0)
            }
            
            logger.debug(f"Search in {index_name} returned {len(search_result['documents'])} results")
            return search_result
            
        except Exception as e:
            logger.error(f"Failed to search in {index_name}: {e}")
            raise
    
    async def delete_index(self, index_name: str) -> bool:
        """
        Delete an Elasticsearch index.
        
        Args:
            index_name: Name of the index to delete
            
        Returns:
            bool: True if index was deleted successfully, False otherwise
        """
        try:
            client = self.get_client()
            
            # Check if index exists
            exists = await client.indices.exists(index=index_name)
            if not exists:
                logger.info(f"Index {index_name} does not exist")
                return True
            
            # Delete index
            result = await client.indices.delete(index=index_name)
            
            acknowledged = result.get('acknowledged', False)
            if acknowledged:
                logger.info(f"Successfully deleted index: {index_name}")
                return True
            else:
                logger.warning(f"Index deletion for {index_name} was not acknowledged")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete index {index_name}: {e}")
            return False
    
    async def get_index_stats(self, index_name: str) -> Dict[str, Any]:
        """
        Get statistics for an Elasticsearch index.
        
        Args:
            index_name: Name of the index
            
        Returns:
            Dict[str, Any]: Index statistics
        """
        try:
            client = self.get_client()
            
            # Get index stats
            stats = await client.indices.stats(index=index_name)
            
            index_stats = {
                'index_name': index_name,
                'document_count': stats['_all']['total']['docs']['count'],
                'store_size_bytes': stats['_all']['total']['store']['size_in_bytes'],
                'status': 'active'
            }
            
            return index_stats
            
        except NotFoundError:
            return {
                'index_name': index_name,
                'status': 'not_found'
            }
        except Exception as e:
            logger.error(f"Failed to get stats for index {index_name}: {e}")
            return {
                'index_name': index_name,
                'status': 'error',
                'error': str(e)
            }
    
    def get_market_data_mapping(self) -> Dict[str, Any]:
        """
        Get Elasticsearch mapping for market data index.
        
        Returns:
            Dict[str, Any]: Market data index mapping
        """
        return {
            'mappings': {
                'properties': {
                    'timestamp': {
                        'type': 'date',
                        'format': 'strict_date_optional_time||epoch_millis'
                    },
                    'symbol': {
                        'type': 'keyword'
                    },
                    'price': {
                        'type': 'double'
                    },
                    'volume': {
                        'type': 'long'
                    },
                    'exchange': {
                        'type': 'keyword'
                    },
                    'market_cap': {
                        'type': 'double'
                    },
                    'sector': {
                        'type': 'keyword'
                    },
                    'change_percent': {
                        'type': 'double'
                    }
                }
            },
            'settings': {
                'number_of_shards': 1,
                'number_of_replicas': 1,
                'refresh_interval': '1s'
            }
        }
    
    def get_news_data_mapping(self) -> Dict[str, Any]:
        """
        Get Elasticsearch mapping for news data index.
        
        Returns:
            Dict[str, Any]: News data index mapping
        """
        return {
            'mappings': {
                'properties': {
                    'timestamp': {
                        'type': 'date',
                        'format': 'strict_date_optional_time||epoch_millis'
                    },
                    'title': {
                        'type': 'text',
                        'analyzer': 'standard',
                        'fields': {
                            'keyword': {
                                'type': 'keyword',
                                'ignore_above': 256
                            }
                        }
                    },
                    'content': {
                        'type': 'text',
                        'analyzer': 'standard'
                    },
                    'source': {
                        'type': 'keyword'
                    },
                    'author': {
                        'type': 'keyword'
                    },
                    'symbols': {
                        'type': 'keyword'
                    },
                    'sentiment_score': {
                        'type': 'double'
                    },
                    'language': {
                        'type': 'keyword'
                    },
                    'url': {
                        'type': 'keyword'
                    },
                    'published_at': {
                        'type': 'date'
                    }
                }
            },
            'settings': {
                'number_of_shards': 1,
                'number_of_replicas': 1,
                'refresh_interval': '5s'
            }
        }
    
    def get_social_media_mapping(self) -> Dict[str, Any]:
        """
        Get Elasticsearch mapping for social media data index.
        
        Returns:
            Dict[str, Any]: Social media data index mapping
        """
        return {
            'mappings': {
                'properties': {
                    'timestamp': {
                        'type': 'date',
                        'format': 'strict_date_optional_time||epoch_millis'
                    },
                    'platform': {
                        'type': 'keyword'
                    },
                    'user_id': {
                        'type': 'keyword'
                    },
                    'username': {
                        'type': 'keyword'
                    },
                    'content': {
                        'type': 'text',
                        'analyzer': 'standard'
                    },
                    'hashtags': {
                        'type': 'keyword'
                    },
                    'mentions': {
                        'type': 'keyword'
                    },
                    'symbols': {
                        'type': 'keyword'
                    },
                    'sentiment_score': {
                        'type': 'double'
                    },
                    'engagement_metrics': {
                        'type': 'object',
                        'properties': {
                            'likes': {'type': 'long'},
                            'shares': {'type': 'long'},
                            'comments': {'type': 'long'},
                            'views': {'type': 'long'}
                        }
                    },
                    'verified_user': {
                        'type': 'boolean'
                    },
                    'follower_count': {
                        'type': 'long'
                    }
                }
            },
            'settings': {
                'number_of_shards': 1,
                'number_of_replicas': 1,
                'refresh_interval': '10s'
            }
        }
    
    async def close(self):
        """
        Close Elasticsearch client connection.
        Performs graceful cleanup of resources.
        """
        with self._lock:
            if self._client:
                try:
                    await self._client.close()
                    logger.info("Closed Elasticsearch client")
                except Exception as e:
                    logger.warning(f"Error closing Elasticsearch client: {e}")
                finally:
                    self._client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit with cleanup"""
        await self.close() 