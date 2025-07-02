"""
Short-Term Memory (STM) Manager

This module manages short-term memory using Redis for storing recent market data,
signals, and other time-sensitive information with a 1-hour TTL.
"""

import json
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Union
import redis.asyncio as redis
from .config import MemoryConfig

logger = logging.getLogger(__name__)


class STMManager:
    """
    Manages short-term memory using Redis with 1-hour TTL.
    
    Stores:
    - Recent market data (prices, volumes, indicators)
    - Recent trading signals from agents
    - Real-time analysis results
    - Temporary session data
    """
    
    def __init__(self, config: MemoryConfig, redis_client: Optional[redis.Redis] = None):
        """
        Initialize STM manager.
        
        Args:
            config: Memory configuration
            redis_client: Optional pre-configured Redis client
        """
        self.config = config
        self._redis_client = redis_client
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize Redis connection and verify connectivity."""
        if self._initialized:
            return
            
        if self._redis_client is None:
            self._redis_client = redis.Redis.from_url(
                self.config.redis_url,
                decode_responses=self.config.redis_decode_responses,
                socket_timeout=self.config.connection_timeout,
                socket_connect_timeout=self.config.connection_timeout
            )
        
        # Test connection
        try:
            await self._redis_client.ping()
            logger.info("STM Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis for STM: {e}")
            raise
            
        self._initialized = True
    
    async def store_market_data(self, symbol: str, data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Store market data for a symbol with TTL.
        
        Args:
            symbol: Trading symbol (e.g., 'RELIANCE')
            data: Market data dictionary
            max_retries: Maximum retry attempts
            
        Returns:
            bool: True if stored successfully
            
        Raises:
            RuntimeError: If storage fails after retries
        """
        if not self._initialized:
            await self.initialize()
        
        key = f"stm:market_data:{symbol}"
        timestamp = time.time()
        
        # Add metadata
        stored_data = {
            **data,
            "stored_at": timestamp,
            "symbol": symbol
        }
        
        for attempt in range(max_retries):
            try:
                await self._redis_client.setex(
                    key,
                    self.config.stm_ttl_seconds,
                    json.dumps(stored_data)
                )
                logger.debug(f"Stored market data for {symbol} in STM")
                return True
                
            except Exception as e:
                logger.warning(f"STM storage attempt {attempt + 1} failed for {symbol}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to store market data for {symbol} after {max_retries} attempts")
                    raise RuntimeError(f"STM storage failed: {e}")
                await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
        
        return False
    
    async def get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve market data for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Optional[Dict[str, Any]]: Market data or None if not found
        """
        if not self._initialized:
            await self.initialize()
        
        key = f"stm:market_data:{symbol}"
        
        try:
            data = await self._redis_client.get(key)
            if data:
                return json.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve market data for {symbol}: {e}")
            return None
    
    async def store_signal(self, agent_name: str, signal_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Store a trading signal from an agent.
        
        Args:
            agent_name: Name of the agent generating the signal
            signal_data: Signal data dictionary
            max_retries: Maximum retry attempts
            
        Returns:
            bool: True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        timestamp = int(time.time() * 1000)  # Millisecond precision
        key = f"stm:signals:{agent_name}:{timestamp}"
        
        # Add metadata
        stored_signal = {
            **signal_data,
            "agent": agent_name,
            "stored_at": timestamp / 1000,
            "timestamp": timestamp
        }
        
        for attempt in range(max_retries):
            try:
                await self._redis_client.setex(
                    key,
                    self.config.stm_ttl_seconds,
                    json.dumps(stored_signal)
                )
                logger.debug(f"Stored signal from {agent_name} in STM")
                return True
                
            except Exception as e:
                logger.warning(f"STM signal storage attempt {attempt + 1} failed for {agent_name}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to store signal from {agent_name} after {max_retries} attempts")
                    raise RuntimeError(f"STM signal storage failed: {e}")
                await asyncio.sleep(0.1 * (attempt + 1))
        
        return False
    
    async def get_recent_signals(self, agent_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve recent signals, optionally filtered by agent.
        
        Args:
            agent_name: Optional agent name filter
            limit: Maximum number of signals to return
            
        Returns:
            List[Dict[str, Any]]: List of recent signals
        """
        if not self._initialized:
            await self.initialize()
        
        pattern = f"stm:signals:{agent_name}:*" if agent_name else "stm:signals:*"
        
        try:
            keys = await self._redis_client.keys(pattern)
            if not keys:
                return []
            
            # Sort keys by timestamp (descending)
            keys.sort(reverse=True)
            
            # Limit results
            keys = keys[:limit]
            
            # Get all signal data
            if keys:
                signals_data = await self._redis_client.mget(keys)
                signals = []
                
                for data in signals_data:
                    if data:
                        try:
                            signal = json.loads(data)
                            signals.append(signal)
                        except json.JSONDecodeError:
                            continue
                
                return signals
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to retrieve recent signals: {e}")
            return []
    
    async def store_analysis_result(self, agent_name: str, symbol: str, result: Dict[str, Any]) -> bool:
        """
        Store analysis result from an agent.
        
        Args:
            agent_name: Name of the analyzing agent
            symbol: Trading symbol
            result: Analysis result dictionary
            
        Returns:
            bool: True if stored successfully
        """
        timestamp = int(time.time() * 1000)
        key = f"stm:analysis:{agent_name}:{symbol}:{timestamp}"
        
        stored_result = {
            **result,
            "agent": agent_name,
            "symbol": symbol,
            "stored_at": timestamp / 1000,
            "timestamp": timestamp
        }
        
        try:
            await self._redis_client.setex(
                key,
                self.config.stm_ttl_seconds,
                json.dumps(stored_result)
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to store analysis result: {e}")
            return False
    
    async def get_recent_analysis(self, agent_name: str, symbol: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent analysis results from an agent.
        
        Args:
            agent_name: Name of the agent
            symbol: Optional symbol filter
            limit: Maximum number of results
            
        Returns:
            List[Dict[str, Any]]: Recent analysis results
        """
        if not self._initialized:
            await self.initialize()
        
        pattern = f"stm:analysis:{agent_name}:{symbol}:*" if symbol else f"stm:analysis:{agent_name}:*"
        
        try:
            keys = await self._redis_client.keys(pattern)
            if not keys:
                return []
            
            # Sort by timestamp
            keys.sort(reverse=True)
            keys = keys[:limit]
            
            if keys:
                results_data = await self._redis_client.mget(keys)
                results = []
                
                for data in results_data:
                    if data:
                        try:
                            result = json.loads(data)
                            results.append(result)
                        except json.JSONDecodeError:
                            continue
                
                return results
            
            return []
            
        except Exception as e:
            logger.error(f"Failed to retrieve analysis results: {e}")
            return []
    
    async def cleanup_expired(self) -> int:
        """
        Clean up expired keys that don't have TTL set.
        
        Returns:
            int: Number of keys cleaned up
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get all STM keys
            stm_keys = await self._redis_client.keys("stm:*")
            if not stm_keys:
                return 0
            
            cleaned_count = 0
            
            # Check TTL for each key
            for key in stm_keys:
                ttl = await self._redis_client.ttl(key)
                if ttl == -1:  # Key exists but has no TTL
                    await self._redis_client.delete(key)
                    cleaned_count += 1
                    logger.debug(f"Cleaned up expired STM key: {key}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired STM keys")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired STM keys: {e}")
            return 0
    
    async def enforce_size_limits(self) -> int:
        """
        Enforce size limits by removing oldest entries.
        
        Returns:
            int: Number of keys removed
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Check current size
            current_size = await self._redis_client.dbsize()
            
            if current_size <= self.config.max_stm_size:
                return 0
            
            # Get all STM keys
            stm_keys = await self._redis_client.keys("stm:*")
            
            if len(stm_keys) <= self.config.max_stm_size:
                return 0
            
            # Sort keys to find oldest (this is a simple approach)
            # In production, you might want more sophisticated aging
            stm_keys.sort()
            
            # Remove oldest keys
            keys_to_remove = len(stm_keys) - self.config.max_stm_size
            oldest_keys = stm_keys[:keys_to_remove]
            
            if oldest_keys:
                await self._redis_client.delete(*oldest_keys)
                logger.info(f"Removed {len(oldest_keys)} oldest STM keys to enforce size limit")
                return len(oldest_keys)
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to enforce STM size limits: {e}")
            return 0
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get current memory usage statistics.
        
        Returns:
            Dict[str, Any]: Memory usage statistics
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get database size
            total_keys = await self._redis_client.dbsize()
            
            # Get STM-specific keys
            stm_keys = await self._redis_client.keys("stm:*")
            stm_key_count = len(stm_keys)
            
            # Calculate usage percentage
            usage_percentage = (stm_key_count / self.config.max_stm_size) * 100 if self.config.max_stm_size > 0 else 0
            
            # Determine status
            if stm_key_count > self.config.max_stm_size:
                status = "over_limit"
            elif usage_percentage > 80:
                status = "warning"
            else:
                status = "healthy"
            
            return {
                "type": "stm",
                "total_redis_keys": total_keys,
                "stm_keys": stm_key_count,
                "limit": self.config.max_stm_size,
                "usage_percentage": usage_percentage,
                "status": status,
                "ttl_seconds": self.config.stm_ttl_seconds
            }
            
        except Exception as e:
            logger.error(f"Failed to get STM memory usage: {e}")
            return {
                "type": "stm",
                "status": "error",
                "error": str(e)
            }
    
    async def clear_all(self) -> bool:
        """
        Clear all STM data (for testing/maintenance).
        
        Returns:
            bool: True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            stm_keys = await self._redis_client.keys("stm:*")
            if stm_keys:
                await self._redis_client.delete(*stm_keys)
                logger.info(f"Cleared {len(stm_keys)} STM keys")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear STM data: {e}")
            return False
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.aclose()
            logger.info("STM Redis connection closed") 