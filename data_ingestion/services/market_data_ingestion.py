import asyncio
import json
import time
import hashlib
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any, Union
import logging
from collections import defaultdict, deque

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from .rate_limiter import RateLimiter, AdaptiveRateLimiter
from .circuit_breaker import CircuitBreaker, CircuitBreakerError
from ..infrastructure.pulsar_client import PulsarManager
from ..infrastructure.elasticsearch_client import ElasticsearchManager

logger = logging.getLogger(__name__)


class MarketDataIngestionService:
    """
    Comprehensive NSE/BSE Market Data Ingestion Service.
    
    Features:
    - Real-time WebSocket data streaming
    - Historical data fetching (bhavcopies)
    - Options chain data retrieval
    - Rate limiting and circuit breaker protection
    - Data transformation and normalization
    - Deduplication logic
    - Performance monitoring
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        pulsar_manager: PulsarManager,
        elasticsearch_manager: ElasticsearchManager
    ):
        """
        Initialize the market data ingestion service.
        
        Args:
            config: Configuration dictionary
            pulsar_manager: Pulsar message broker manager
            elasticsearch_manager: Elasticsearch manager for indexing
        """
        self.config = config
        self.pulsar_manager = pulsar_manager
        self.elasticsearch_manager = elasticsearch_manager
        
        # Initialize rate limiters
        self.nse_rate_limiter = AdaptiveRateLimiter(
            calls=config['nse']['rate_limit']['calls'],
            period=config['nse']['rate_limit']['period'],
            min_calls=1,
            max_calls=config['nse']['rate_limit']['calls'] * 2
        )
        
        self.bse_rate_limiter = AdaptiveRateLimiter(
            calls=config['bse']['rate_limit']['calls'],
            period=config['bse']['rate_limit']['period'],
            min_calls=1,
            max_calls=config['bse']['rate_limit']['calls'] * 2
        )
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config['circuit_breaker']['failure_threshold'],
            recovery_timeout=config['circuit_breaker']['recovery_timeout'],
            half_open_max_calls=config['circuit_breaker']['half_open_max_calls'],
            expected_exception=(aiohttp.ClientError, WebSocketException)
        )
        
        # Connection management
        self.websocket_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.http_sessions: Dict[str, aiohttp.ClientSession] = {}
        self.is_running = False
        self._background_tasks: List[asyncio.Task] = []
        
        # Data deduplication
        self._data_cache: Dict[str, Dict] = {}
        self._cache_expiry = 300  # 5 minutes
        
        # Performance monitoring
        self._metrics = {
            'api_call_latency': defaultdict(list),
            'websocket_message_count': defaultdict(int),
            'data_processing_time': deque(maxlen=1000),
            'errors': defaultdict(int),
            'successful_requests': defaultdict(int)
        }
        
        # Producers cache
        self._producers: Dict[str, Any] = {}
    
    async def start(self) -> None:
        """Start the market data ingestion service."""
        if self.is_running:
            logger.warning("Service is already running")
            return
        
        logger.info("Starting Market Data Ingestion Service")
        
        # Initialize HTTP sessions
        await self._initialize_http_sessions()
        
        # Start background tasks
        await self._start_background_tasks()
        
        self.is_running = True
        logger.info("Market Data Ingestion Service started successfully")
    
    async def stop(self) -> None:
        """Stop the market data ingestion service."""
        if not self.is_running:
            logger.warning("Service is not running")
            return
        
        logger.info("Stopping Market Data Ingestion Service")
        
        # Stop background tasks
        await self._stop_background_tasks()
        
        # Close WebSocket connections
        for exchange, websocket in self.websocket_connections.items():
            try:
                await websocket.close()
                logger.info(f"Closed WebSocket connection for {exchange}")
            except Exception as e:
                logger.error(f"Error closing WebSocket for {exchange}: {e}")
        
        # Close HTTP sessions
        for exchange, session in self.http_sessions.items():
            try:
                await session.close()
                logger.info(f"Closed HTTP session for {exchange}")
            except Exception as e:
                logger.error(f"Error closing HTTP session for {exchange}: {e}")
        
        # Close producers
        for topic, producer in self._producers.items():
            try:
                await producer.close()
                logger.info(f"Closed Pulsar producer for {topic}")
            except Exception as e:
                logger.error(f"Error closing producer for {topic}: {e}")
        
        self.websocket_connections.clear()
        self.http_sessions.clear()
        self._producers.clear()
        self.is_running = False
        
        logger.info("Market Data Ingestion Service stopped")
    
    async def _initialize_http_sessions(self) -> None:
        """Initialize HTTP sessions for API calls."""
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=10)
        
        # NSE session
        self.http_sessions['nse'] = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=30),
            headers={'User-Agent': 'MarketDataIngestion/1.0'}
        )
        
        # BSE session
        self.http_sessions['bse'] = aiohttp.ClientSession(
            timeout=timeout,
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=30),
            headers={'User-Agent': 'MarketDataIngestion/1.0'}
        )
    
    async def _start_background_tasks(self) -> None:
        """Start background tasks for data ingestion."""
        # WebSocket connections for real-time data
        for exchange in ['nse', 'bse']:
            task = asyncio.create_task(self._maintain_websocket_connection(exchange))
            self._background_tasks.append(task)
        
        # Scheduled historical data downloads
        task = asyncio.create_task(self._scheduled_historical_downloads())
        self._background_tasks.append(task)
        
        # Performance metrics collection
        task = asyncio.create_task(self._metrics_collection_loop())
        self._background_tasks.append(task)
        
        # Cache cleanup
        task = asyncio.create_task(self._cache_cleanup_loop())
        self._background_tasks.append(task)
    
    async def _stop_background_tasks(self) -> None:
        """Stop all background tasks."""
        for task in self._background_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        
        self._background_tasks.clear()
    
    async def connect_websocket(self, exchange: str) -> None:
        """
        Establish WebSocket connection for an exchange.
        
        Args:
            exchange: Exchange name ('nse' or 'bse')
        """
        if exchange not in self.config:
            raise ValueError(f"Unknown exchange: {exchange}")
        
        websocket_url = self.config[exchange]['websocket_url']
        
        try:
            logger.info(f"Connecting to {exchange} WebSocket: {websocket_url}")
            
            websocket = await websockets.connect(
                websocket_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            self.websocket_connections[exchange] = websocket
            logger.info(f"Successfully connected to {exchange} WebSocket")
            
            # Send subscription message if configured
            symbols = self.config[exchange].get('symbols', [])
            if symbols:
                subscription_msg = {
                    'action': 'subscribe',
                    'symbols': symbols
                }
                await websocket.send(json.dumps(subscription_msg))
                logger.info(f"Subscribed to {len(symbols)} symbols on {exchange}")
            
        except Exception as e:
            logger.error(f"Failed to connect to {exchange} WebSocket: {e}")
            raise
    
    async def _maintain_websocket_connection(self, exchange: str) -> None:
        """
        Maintain WebSocket connection with automatic reconnection.
        
        Args:
            exchange: Exchange name
        """
        retry_count = 0
        max_retries = 5
        base_delay = 1
        
        while self.is_running:
            try:
                if exchange not in self.websocket_connections:
                    await self.connect_websocket(exchange)
                
                await self.process_real_time_data(exchange)
                retry_count = 0  # Reset on successful processing
                
            except ConnectionClosed:
                logger.warning(f"{exchange} WebSocket connection closed")
                self.websocket_connections.pop(exchange, None)
                
                if retry_count < max_retries:
                    delay = base_delay * (2 ** retry_count)
                    logger.info(f"Reconnecting to {exchange} WebSocket in {delay}s (attempt {retry_count + 1})")
                    await asyncio.sleep(delay)
                    retry_count += 1
                else:
                    logger.error(f"Max retries exceeded for {exchange} WebSocket")
                    break
                    
            except Exception as e:
                logger.error(f"Error in {exchange} WebSocket connection: {e}")
                self.websocket_connections.pop(exchange, None)
                
                if retry_count < max_retries:
                    delay = base_delay * (2 ** retry_count)
                    await asyncio.sleep(delay)
                    retry_count += 1
                else:
                    break
    
    async def process_real_time_data(self, exchange: str) -> None:
        """
        Process real-time data from WebSocket.
        
        Args:
            exchange: Exchange name
        """
        if exchange not in self.websocket_connections:
            raise ValueError(f"No WebSocket connection for {exchange}")
        
        websocket = self.websocket_connections[exchange]
        
        try:
            async for message in websocket:
                start_time = time.time()
                
                try:
                    # Parse message
                    if isinstance(message, str):
                        data = json.loads(message)
                    else:
                        data = json.loads(message.decode('utf-8'))
                    
                    # Transform data based on exchange
                    if exchange == 'nse':
                        transformed_data = self.transform_nse_data(data)
                    elif exchange == 'bse':
                        transformed_data = self.transform_bse_data(data)
                    else:
                        continue
                    
                    # Check for duplicates
                    if self.is_duplicate(transformed_data):
                        continue
                    
                    # Send to Pulsar
                    await self._send_to_pulsar('live_quotes', transformed_data)
                    
                    # Index in Elasticsearch
                    await self._index_in_elasticsearch('market_data', transformed_data)
                    
                    # Update metrics
                    self._metrics['websocket_message_count'][exchange] += 1
                    
                    processing_time = (time.time() - start_time) * 1000
                    self._metrics['data_processing_time'].append(processing_time)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from {exchange}: {e}")
                    self._metrics['errors'][f'{exchange}_json_decode'] += 1
                    
                except Exception as e:
                    logger.error(f"Error processing {exchange} message: {e}")
                    self._metrics['errors'][f'{exchange}_processing'] += 1
                    
        except ConnectionClosed:
            logger.info(f"{exchange} WebSocket connection closed")
            raise
        except Exception as e:
            logger.error(f"Error in {exchange} real-time data processing: {e}")
            raise
    
    async def fetch_market_data(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """
        Fetch market data for a specific symbol via REST API.
        
        Args:
            exchange: Exchange name
            symbol: Symbol to fetch
            
        Returns:
            Market data dictionary
        """
        rate_limiter = self.nse_rate_limiter if exchange == 'nse' else self.bse_rate_limiter
        
        # Check rate limit
        if not await rate_limiter.acquire():
            logger.warning(f"Rate limit exceeded for {exchange}")
            await rate_limiter.wait_until_allowed()
        
        # Make API call with circuit breaker protection
        async with self.circuit_breaker:
            return await self._make_api_call(exchange, symbol)
    
    async def _make_api_call(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """
        Make HTTP API call to fetch market data.
        
        Args:
            exchange: Exchange name
            symbol: Symbol to fetch
            
        Returns:
            API response data
        """
        session = self.http_sessions[exchange]
        base_url = self.config[exchange]['rest_api_url']
        url = f"{base_url}/quote/{symbol}"
        
        start_time = time.time()
        
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Record success metrics
                latency = (time.time() - start_time) * 1000
                self.record_api_call_latency(exchange, latency)
                self._metrics['successful_requests'][exchange] += 1
                
                # Update rate limiter
                rate_limiter = self.nse_rate_limiter if exchange == 'nse' else self.bse_rate_limiter
                await rate_limiter.record_success()
                
                return data
                
        except aiohttp.ClientResponseError as e:
            if e.status == 429:  # Rate limited
                rate_limiter = self.nse_rate_limiter if exchange == 'nse' else self.bse_rate_limiter
                await rate_limiter.record_rate_limit_hit()
                logger.warning(f"Rate limited by {exchange} API")
            
            self._metrics['errors'][f'{exchange}_api_{e.status}'] += 1
            raise
            
        except Exception as e:
            self._metrics['errors'][f'{exchange}_api_error'] += 1
            rate_limiter = self.nse_rate_limiter if exchange == 'nse' else self.bse_rate_limiter
            await rate_limiter.record_failure()
            raise
    
    async def fetch_historical_data(self, exchange: str, date_obj: date) -> Dict[str, Any]:
        """
        Fetch historical data (bhavcopies) for a specific date.
        
        Args:
            exchange: Exchange name
            date_obj: Date for historical data
            
        Returns:
            Historical data dictionary
        """
        session = self.http_sessions[exchange]
        base_url = self.config[exchange]['rest_api_url']
        
        # Format date for API
        date_str = date_obj.strftime('%Y-%m-%d')
        url = f"{base_url}/historical/{date_str}"
        
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Send to Pulsar
                await self._send_to_pulsar('historical', {
                    'exchange': exchange,
                    'date': date_str,
                    'data': data
                })
                
                return data
                
        except Exception as e:
            logger.error(f"Error fetching historical data for {exchange} on {date_str}: {e}")
            raise
    
    async def fetch_options_chain(self, exchange: str, symbol: str) -> Dict[str, Any]:
        """
        Fetch options chain data for a symbol.
        
        Args:
            exchange: Exchange name
            symbol: Underlying symbol
            
        Returns:
            Options chain data
        """
        session = self.http_sessions[exchange]
        base_url = self.config[exchange]['rest_api_url']
        url = f"{base_url}/options/{symbol}"
        
        try:
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Send to Pulsar
                await self._send_to_pulsar('options_chain', {
                    'exchange': exchange,
                    'symbol': symbol,
                    'timestamp': datetime.now().isoformat(),
                    'data': data
                })
                
                return data
                
        except Exception as e:
            logger.error(f"Error fetching options chain for {symbol} on {exchange}: {e}")
            raise
    
    def transform_nse_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform NSE data to standardized format.
        
        Args:
            raw_data: Raw NSE data
            
        Returns:
            Transformed data
        """
        return {
            'symbol': raw_data.get('symbol'),
            'price': raw_data.get('lastPrice'),
            'change': raw_data.get('change'),
            'change_percent': raw_data.get('pChange'),
            'volume': raw_data.get('totalTradedVolume'),
            'timestamp': self._parse_nse_timestamp(raw_data.get('lastUpdateTime')),
            'exchange': 'NSE',
            'open': raw_data.get('open'),
            'high': raw_data.get('dayHigh'),
            'low': raw_data.get('dayLow'),
            'previous_close': raw_data.get('previousClose'),
            'raw_data': raw_data
        }
    
    def transform_bse_data(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform BSE data to standardized format.
        
        Args:
            raw_data: Raw BSE data
            
        Returns:
            Transformed data
        """
        return {
            'symbol': raw_data.get('SC_NAME'),
            'price': raw_data.get('LAST_PRICE'),
            'change': raw_data.get('NET_CHNG'),
            'change_percent': raw_data.get('PER_CHNG'),
            'volume': raw_data.get('NO_OF_SHRS'),
            'timestamp': self._parse_bse_timestamp(raw_data.get('TIME_STAMP')),
            'exchange': 'BSE',
            'open': raw_data.get('OPEN_PRICE'),
            'high': raw_data.get('HIGH_PRICE'),
            'low': raw_data.get('LOW_PRICE'),
            'previous_close': raw_data.get('PREV_CL_PR'),
            'code': raw_data.get('SC_CODE'),
            'raw_data': raw_data
        }
    
    def _parse_nse_timestamp(self, timestamp_str: str) -> str:
        """Parse NSE timestamp format."""
        if not timestamp_str:
            return datetime.now().isoformat()
        
        try:
            # NSE format: "15-Jan-2024 10:30:00"
            dt = datetime.strptime(timestamp_str, "%d-%b-%Y %H:%M:%S")
            return dt.isoformat()
        except:
            return datetime.now().isoformat()
    
    def _parse_bse_timestamp(self, timestamp_str: str) -> str:
        """Parse BSE timestamp format."""
        if not timestamp_str:
            return datetime.now().isoformat()
        
        try:
            # BSE format: "2024-01-15 10:30:00"
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            return dt.isoformat()
        except:
            return datetime.now().isoformat()
    
    def is_duplicate(self, data: Dict[str, Any]) -> bool:
        """
        Check if data is a duplicate.
        
        Args:
            data: Data to check
            
        Returns:
            True if duplicate, False otherwise
        """
        # Create hash of key fields
        key_fields = [
            data.get('symbol', ''),
            data.get('price', 0),
            data.get('timestamp', ''),
            data.get('exchange', '')
        ]
        
        data_hash = hashlib.md5(str(key_fields).encode()).hexdigest()
        
        current_time = time.time()
        
        # Check if we've seen this data recently
        if data_hash in self._data_cache:
            cache_time = self._data_cache[data_hash]['timestamp']
            if current_time - cache_time < self._cache_expiry:
                return True
        
        # Store in cache
        self._data_cache[data_hash] = {
            'data': data,
            'timestamp': current_time
        }
        
        return False
    
    async def run_scheduled_historical_download(self) -> None:
        """Run scheduled historical data download."""
        yesterday = datetime.now().date() - timedelta(days=1)
        
        for exchange in ['nse', 'bse']:
            try:
                await self.fetch_historical_data(exchange, yesterday)
                logger.info(f"Downloaded historical data for {exchange} on {yesterday}")
            except Exception as e:
                logger.error(f"Failed to download historical data for {exchange}: {e}")
    
    async def _scheduled_historical_downloads(self) -> None:
        """Background task for scheduled historical downloads."""
        while self.is_running:
            try:
                # Run at 6 AM daily
                now = datetime.now()
                next_run = now.replace(hour=6, minute=0, second=0, microsecond=0)
                
                if now >= next_run:
                    next_run += timedelta(days=1)
                
                sleep_seconds = (next_run - now).total_seconds()
                await asyncio.sleep(sleep_seconds)
                
                if self.is_running:
                    await self.run_scheduled_historical_download()
                    
            except Exception as e:
                logger.error(f"Error in scheduled historical downloads: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error
    
    async def _send_to_pulsar(self, topic_key: str, data: Dict[str, Any]) -> None:
        """
        Send data to Pulsar topic.
        
        Args:
            topic_key: Topic key from config
            data: Data to send
        """
        topic_name = self.config['pulsar_topics'][topic_key]
        
        if topic_name not in self._producers:
            self._producers[topic_name] = await self.pulsar_manager.get_producer(topic_name)
        
        producer = self._producers[topic_name]
        message = json.dumps(data, default=str).encode('utf-8')
        
        await producer.send_async(message)
    
    async def _index_in_elasticsearch(self, index_name: str, data: Dict[str, Any]) -> None:
        """
        Index data in Elasticsearch.
        
        Args:
            index_name: Index name
            data: Data to index
        """
        try:
            await self.elasticsearch_manager.index_document(index_name, data)
        except Exception as e:
            logger.error(f"Error indexing data in Elasticsearch: {e}")
    
    async def _metrics_collection_loop(self) -> None:
        """Background task for metrics collection."""
        while self.is_running:
            try:
                # Log performance metrics every 5 minutes
                await asyncio.sleep(300)
                
                if self.is_running:
                    metrics = self.get_performance_metrics()
                    logger.info(f"Performance metrics: {metrics}")
                    
            except Exception as e:
                logger.error(f"Error in metrics collection: {e}")
                await asyncio.sleep(60)
    
    async def _cache_cleanup_loop(self) -> None:
        """Background task for cache cleanup."""
        while self.is_running:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                if self.is_running:
                    current_time = time.time()
                    expired_keys = []
                    
                    for key, entry in self._data_cache.items():
                        if current_time - entry['timestamp'] > self._cache_expiry:
                            expired_keys.append(key)
                    
                    for key in expired_keys:
                        del self._data_cache[key]
                    
                    if expired_keys:
                        logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
                        
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
                await asyncio.sleep(60)
    
    def record_api_call_latency(self, exchange: str, latency_ms: float) -> None:
        """Record API call latency."""
        self._metrics['api_call_latency'][exchange].append(latency_ms)
        
        # Keep only last 1000 measurements
        if len(self._metrics['api_call_latency'][exchange]) > 1000:
            self._metrics['api_call_latency'][exchange] = self._metrics['api_call_latency'][exchange][-1000:]
    
    def record_websocket_message_count(self, exchange: str, count: int) -> None:
        """Record WebSocket message count."""
        self._metrics['websocket_message_count'][exchange] += count
    
    def record_data_processing_time(self, time_ms: float) -> None:
        """Record data processing time."""
        self._metrics['data_processing_time'].append(time_ms)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get performance metrics.
        
        Returns:
            Performance metrics dictionary
        """
        return {
            'api_call_latency': dict(self._metrics['api_call_latency']),
            'websocket_message_count': dict(self._metrics['websocket_message_count']),
            'data_processing_time': list(self._metrics['data_processing_time']),
            'errors': dict(self._metrics['errors']),
            'successful_requests': dict(self._metrics['successful_requests']),
            'cache_size': len(self._data_cache),
            'is_running': self.is_running,
            'active_connections': list(self.websocket_connections.keys()),
            'circuit_breaker_stats': self.circuit_breaker.get_statistics(),
            'rate_limiter_stats': {
                'nse': self.nse_rate_limiter.get_adaptation_stats(),
                'bse': self.bse_rate_limiter.get_adaptation_stats()
            }
        } 