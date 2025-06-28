import asyncio
import time
from typing import Optional
from collections import deque


class RateLimiter:
    """
    Token bucket rate limiter for controlling API call frequency.
    
    Ensures we don't exceed specified API rate limits by implementing
    a sliding window rate limiting algorithm.
    """
    
    def __init__(self, calls: int, period: int):
        """
        Initialize rate limiter.
        
        Args:
            calls: Maximum number of calls allowed
            period: Time period in seconds for the rate limit
        """
        self.calls = calls
        self.period = period
        self.timestamps = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """
        Try to acquire permission to make an API call.
        
        Returns:
            True if call is allowed, False if rate limited
        """
        async with self._lock:
            current_time = time.time()
            
            # Remove timestamps older than the period
            while self.timestamps and current_time - self.timestamps[0] > self.period:
                self.timestamps.popleft()
            
            # Check if we're within the rate limit
            if len(self.timestamps) < self.calls:
                self.timestamps.append(current_time)
                return True
            
            return False
    
    async def wait_until_allowed(self) -> None:
        """
        Wait until a call is allowed (blocking version).
        
        This method will block until a slot becomes available.
        """
        while True:
            if await self.acquire():
                return
            
            # Calculate wait time until oldest call expires
            if self.timestamps:
                wait_time = self.period - (time.time() - self.timestamps[0])
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time, 0.1))  # Cap wait to 100ms
                else:
                    await asyncio.sleep(0.01)  # Small delay to prevent busy waiting
            else:
                await asyncio.sleep(0.01)
    
    def get_current_usage(self) -> dict:
        """
        Get current rate limiter usage statistics.
        
        Returns:
            Dictionary with usage information
        """
        current_time = time.time()
        
        # Clean up old timestamps
        while self.timestamps and current_time - self.timestamps[0] > self.period:
            self.timestamps.popleft()
        
        return {
            'current_calls': len(self.timestamps),
            'max_calls': self.calls,
            'period': self.period,
            'utilization_percent': (len(self.timestamps) / self.calls) * 100,
            'time_until_reset': self.period - (current_time - self.timestamps[0]) if self.timestamps else 0
        }
    
    def reset(self) -> None:
        """Reset the rate limiter, clearing all timestamps."""
        self.timestamps.clear()


class AdaptiveRateLimiter(RateLimiter):
    """
    Advanced rate limiter that adapts based on server responses.
    
    Can automatically adjust rate limits based on HTTP 429 responses
    or other rate limiting signals from the API.
    """
    
    def __init__(self, calls: int, period: int, min_calls: int = 1, max_calls: int = None):
        """
        Initialize adaptive rate limiter.
        
        Args:
            calls: Initial maximum number of calls allowed
            period: Time period in seconds for the rate limit
            min_calls: Minimum calls to allow (safety limit)
            max_calls: Maximum calls to allow (safety limit)
        """
        super().__init__(calls, period)
        self.initial_calls = calls
        self.min_calls = min_calls
        self.max_calls = max_calls or calls * 2
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        
    async def record_success(self) -> None:
        """Record a successful API call."""
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        
        # Gradually increase rate limit if we've had many successes
        if self.consecutive_successes >= 10 and self.calls < self.max_calls:
            self.calls = min(self.calls + 1, self.max_calls)
            self.consecutive_successes = 0
    
    async def record_rate_limit_hit(self) -> None:
        """Record that we hit a rate limit (HTTP 429)."""
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        
        # Reduce rate limit more aggressively
        reduction = max(1, self.calls // 4)  # Reduce by 25%
        self.calls = max(self.min_calls, self.calls - reduction)
    
    async def record_failure(self) -> None:
        """Record a failed API call (non-rate-limit)."""
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        
        # Slightly reduce rate limit on failures
        if self.consecutive_failures >= 5:
            self.calls = max(self.min_calls, self.calls - 1)
            self.consecutive_failures = 0
    
    def get_adaptation_stats(self) -> dict:
        """
        Get adaptation statistics.
        
        Returns:
            Dictionary with adaptation information
        """
        base_stats = self.get_current_usage()
        base_stats.update({
            'initial_calls': self.initial_calls,
            'consecutive_successes': self.consecutive_successes,
            'consecutive_failures': self.consecutive_failures,
            'adaptation_ratio': self.calls / self.initial_calls
        })
        return base_stats 