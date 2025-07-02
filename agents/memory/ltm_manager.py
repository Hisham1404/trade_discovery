"""
Long-Term Memory (LTM) Manager

This module manages long-term memory using Redis for storing agent performance history,
learned trading patterns, and strategic insights with a 7-day TTL.
"""

import json
import time
import logging
import asyncio
import statistics
from typing import Dict, List, Any, Optional, Union
from datetime import datetime, timedelta
import redis.asyncio as redis
from .config import MemoryConfig

logger = logging.getLogger(__name__)


class LTMManager:
    """
    Manages long-term memory using Redis with 7-day TTL.
    
    Stores:
    - Agent performance history and metrics
    - Learned trading patterns and their success rates
    - Strategic insights and market correlations
    - Historical backtesting results
    """
    
    def __init__(self, config: MemoryConfig, redis_client: Optional[redis.Redis] = None):
        """
        Initialize LTM manager.
        
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
            logger.info("LTM Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis for LTM: {e}")
            raise
            
        self._initialized = True
    
    async def store_performance(self, agent_name: str, performance_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Store agent performance data.
        
        Args:
            agent_name: Name of the agent
            performance_data: Performance metrics dictionary
            max_retries: Maximum retry attempts
            
        Returns:
            bool: True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        timestamp = int(time.time())
        date_key = datetime.fromtimestamp(timestamp).strftime("%Y%m%d")
        key = f"ltm:performance:{agent_name}:{date_key}:{timestamp}"
        
        # Add metadata
        stored_data = {
            **performance_data,
            "agent": agent_name,
            "stored_at": timestamp,
            "date": date_key
        }
        
        for attempt in range(max_retries):
            try:
                await self._redis_client.setex(
                    key,
                    self.config.ltm_ttl_seconds,
                    json.dumps(stored_data)
                )
                logger.debug(f"Stored performance data for {agent_name} in LTM")
                return True
                
            except Exception as e:
                logger.warning(f"LTM performance storage attempt {attempt + 1} failed for {agent_name}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to store performance for {agent_name} after {max_retries} attempts")
                    raise RuntimeError(f"LTM performance storage failed: {e}")
                await asyncio.sleep(0.1 * (attempt + 1))
        
        return False
    
    async def get_performance_history(self, agent_name: str, days: int = 7) -> List[Dict[str, Any]]:
        """
        Retrieve agent performance history.
        
        Args:
            agent_name: Name of the agent
            days: Number of days to look back
            
        Returns:
            List[Dict[str, Any]]: Performance history
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get all performance keys for the agent
            pattern = f"ltm:performance:{agent_name}:*"
            keys = await self._redis_client.keys(pattern)
            
            if not keys:
                return []
            
            # Filter keys by date range
            cutoff_timestamp = time.time() - (days * 24 * 3600)
            valid_keys = []
            
            for key in keys:
                # Extract timestamp from key
                parts = key.split(":")
                if len(parts) >= 4:
                    try:
                        key_timestamp = int(parts[-1])
                        if key_timestamp >= cutoff_timestamp:
                            valid_keys.append(key)
                    except ValueError:
                        continue
            
            if not valid_keys:
                return []
            
            # Sort by timestamp
            valid_keys.sort()
            
            # Get performance data
            performance_data = await self._redis_client.mget(valid_keys)
            history = []
            
            for data in performance_data:
                if data:
                    try:
                        perf = json.loads(data)
                        history.append(perf)
                    except json.JSONDecodeError:
                        continue
            
            return history
            
        except Exception as e:
            logger.error(f"Failed to retrieve performance history for {agent_name}: {e}")
            return []
    
    async def store_pattern(self, pattern_name: str, pattern_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Store a learned trading pattern.
        
        Args:
            pattern_name: Name/identifier of the pattern
            pattern_data: Pattern data and statistics
            max_retries: Maximum retry attempts
            
        Returns:
            bool: True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        timestamp = int(time.time())
        key = f"ltm:patterns:{pattern_name}:{timestamp}"
        
        # Add metadata
        stored_data = {
            **pattern_data,
            "pattern_name": pattern_name,
            "stored_at": timestamp,
            "last_updated": timestamp
        }
        
        for attempt in range(max_retries):
            try:
                await self._redis_client.setex(
                    key,
                    self.config.ltm_ttl_seconds,
                    json.dumps(stored_data)
                )
                logger.debug(f"Stored pattern {pattern_name} in LTM")
                return True
                
            except Exception as e:
                logger.warning(f"LTM pattern storage attempt {attempt + 1} failed for {pattern_name}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to store pattern {pattern_name} after {max_retries} attempts")
                    raise RuntimeError(f"LTM pattern storage failed: {e}")
                await asyncio.sleep(0.1 * (attempt + 1))
        
        return False
    
    async def get_similar_patterns(self, pattern_type: str, min_success_rate: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve similar patterns with filtering.
        
        Args:
            pattern_type: Type of pattern to search for
            min_success_rate: Minimum success rate filter
            limit: Maximum number of patterns to return
            
        Returns:
            List[Dict[str, Any]]: List of matching patterns
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get all pattern keys
            pattern = f"ltm:patterns:{pattern_type}:*" if pattern_type != "*" else "ltm:patterns:*"
            keys = await self._redis_client.keys(pattern)
            
            if not keys:
                return []
            
            # Sort by timestamp (newest first)
            keys.sort(reverse=True)
            
            # Get pattern data
            patterns_data = await self._redis_client.mget(keys)
            patterns = []
            
            for data in patterns_data:
                if data:
                    try:
                        pattern_obj = json.loads(data)
                        
                        # Apply success rate filter
                        success_rate = pattern_obj.get("success_rate", 0.0)
                        if success_rate >= min_success_rate:
                            patterns.append(pattern_obj)
                            
                        # Apply limit
                        if len(patterns) >= limit:
                            break
                            
                    except json.JSONDecodeError:
                        continue
            
            return patterns
            
        except Exception as e:
            logger.error(f"Failed to retrieve patterns: {e}")
            return []
    
    async def get_performance_statistics(self, agent_name: str, days: int = 7) -> Dict[str, Any]:
        """
        Calculate performance statistics for an agent.
        
        Args:
            agent_name: Name of the agent
            days: Number of days to analyze
            
        Returns:
            Dict[str, Any]: Performance statistics
        """
        try:
            history = await self.get_performance_history(agent_name, days)
            
            if not history:
                return {
                    "agent": agent_name,
                    "days_analyzed": days,
                    "data_points": 0,
                    "status": "no_data"
                }
            
            # Extract metrics
            accuracies = [h.get("accuracy", 0) for h in history if "accuracy" in h]
            total_signals = [h.get("total_signals", 0) for h in history if "total_signals" in h]
            successful_signals = [h.get("successful_signals", 0) for h in history if "successful_signals" in h]
            execution_times = [h.get("avg_execution_time", 0) for h in history if "avg_execution_time" in h]
            
            stats = {
                "agent": agent_name,
                "days_analyzed": days,
                "data_points": len(history),
                "period_start": min(h.get("stored_at", 0) for h in history),
                "period_end": max(h.get("stored_at", 0) for h in history),
            }
            
            # Calculate accuracy statistics
            if accuracies:
                stats.update({
                    "average_accuracy": statistics.mean(accuracies),
                    "median_accuracy": statistics.median(accuracies),
                    "accuracy_std": statistics.stdev(accuracies) if len(accuracies) > 1 else 0,
                    "best_accuracy": max(accuracies),
                    "worst_accuracy": min(accuracies)
                })
                
                # Calculate trend (simple linear trend)
                if len(accuracies) > 2:
                    recent_acc = statistics.mean(accuracies[-3:])  # Last 3 data points
                    early_acc = statistics.mean(accuracies[:3])    # First 3 data points
                    trend = "improving" if recent_acc > early_acc else "declining" if recent_acc < early_acc else "stable"
                    stats["trend"] = trend
            
            # Calculate signal statistics
            if total_signals:
                stats.update({
                    "total_signals": sum(total_signals),
                    "average_daily_signals": statistics.mean(total_signals),
                    "max_daily_signals": max(total_signals)
                })
            
            if successful_signals:
                stats["total_successful_signals"] = sum(successful_signals)
            
            # Calculate execution time statistics
            if execution_times:
                stats.update({
                    "average_execution_time": statistics.mean(execution_times),
                    "median_execution_time": statistics.median(execution_times),
                    "max_execution_time": max(execution_times),
                    "min_execution_time": min(execution_times)
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to calculate performance statistics for {agent_name}: {e}")
            return {
                "agent": agent_name,
                "days_analyzed": days,
                "status": "error",
                "error": str(e)
            }
    
    async def store_market_insight(self, insight_type: str, insight_data: Dict[str, Any]) -> bool:
        """
        Store market insights and correlations.
        
        Args:
            insight_type: Type of insight (e.g., 'correlation', 'trend', 'volatility_pattern')
            insight_data: Insight data dictionary
            
        Returns:
            bool: True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        timestamp = int(time.time())
        key = f"ltm:insights:{insight_type}:{timestamp}"
        
        stored_data = {
            **insight_data,
            "insight_type": insight_type,
            "stored_at": timestamp
        }
        
        try:
            await self._redis_client.setex(
                key,
                self.config.ltm_ttl_seconds,
                json.dumps(stored_data)
            )
            logger.debug(f"Stored market insight {insight_type} in LTM")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store market insight: {e}")
            return False
    
    async def get_market_insights(self, insight_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Retrieve market insights.
        
        Args:
            insight_type: Optional insight type filter
            limit: Maximum number of insights to return
            
        Returns:
            List[Dict[str, Any]]: Market insights
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            pattern = f"ltm:insights:{insight_type}:*" if insight_type else "ltm:insights:*"
            keys = await self._redis_client.keys(pattern)
            
            if not keys:
                return []
            
            # Sort by timestamp (newest first)
            keys.sort(reverse=True)
            keys = keys[:limit]
            
            # Get insight data
            insights_data = await self._redis_client.mget(keys)
            insights = []
            
            for data in insights_data:
                if data:
                    try:
                        insight = json.loads(data)
                        insights.append(insight)
                    except json.JSONDecodeError:
                        continue
            
            return insights
            
        except Exception as e:
            logger.error(f"Failed to retrieve market insights: {e}")
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
            # Get all LTM keys
            ltm_keys = await self._redis_client.keys("ltm:*")
            if not ltm_keys:
                return 0
            
            cleaned_count = 0
            
            # Check TTL for each key
            for key in ltm_keys:
                ttl = await self._redis_client.ttl(key)
                if ttl == -1:  # Key exists but has no TTL
                    await self._redis_client.delete(key)
                    cleaned_count += 1
                    logger.debug(f"Cleaned up expired LTM key: {key}")
            
            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} expired LTM keys")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired LTM keys: {e}")
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
            # Get all LTM keys
            ltm_keys = await self._redis_client.keys("ltm:*")
            
            if len(ltm_keys) <= self.config.max_ltm_size:
                return 0
            
            # Sort keys to find oldest
            ltm_keys.sort()
            
            # Remove oldest keys
            keys_to_remove = len(ltm_keys) - self.config.max_ltm_size
            oldest_keys = ltm_keys[:keys_to_remove]
            
            if oldest_keys:
                await self._redis_client.delete(*oldest_keys)
                logger.info(f"Removed {len(oldest_keys)} oldest LTM keys to enforce size limit")
                return len(oldest_keys)
            
            return 0
            
        except Exception as e:
            logger.error(f"Failed to enforce LTM size limits: {e}")
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
            # Get LTM-specific keys
            ltm_keys = await self._redis_client.keys("ltm:*")
            ltm_key_count = len(ltm_keys)
            
            # Calculate usage percentage
            usage_percentage = (ltm_key_count / self.config.max_ltm_size) * 100 if self.config.max_ltm_size > 0 else 0
            
            # Determine status
            if ltm_key_count > self.config.max_ltm_size:
                status = "over_limit"
            elif usage_percentage > 80:
                status = "warning"
            else:
                status = "healthy"
            
            return {
                "type": "ltm",
                "ltm_keys": ltm_key_count,
                "limit": self.config.max_ltm_size,
                "usage_percentage": usage_percentage,
                "status": status,
                "ttl_seconds": self.config.ltm_ttl_seconds
            }
            
        except Exception as e:
            logger.error(f"Failed to get LTM memory usage: {e}")
            return {
                "type": "ltm",
                "status": "error",
                "error": str(e)
            }
    
    async def clear_all(self) -> bool:
        """
        Clear all LTM data (for testing/maintenance).
        
        Returns:
            bool: True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            ltm_keys = await self._redis_client.keys("ltm:*")
            if ltm_keys:
                await self._redis_client.delete(*ltm_keys)
                logger.info(f"Cleared {len(ltm_keys)} LTM keys")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear LTM data: {e}")
            return False
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis_client:
            await self._redis_client.aclose()
            logger.info("LTM Redis connection closed") 