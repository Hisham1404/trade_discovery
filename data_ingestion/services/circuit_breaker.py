import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any
import logging

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for handling API failures.
    
    Prevents cascading failures by failing fast when a service is
    experiencing issues. Automatically attempts recovery after a timeout.
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        half_open_max_calls: int = 3,
        expected_exception: type = Exception
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening
            recovery_timeout: Seconds to wait before trying half-open
            half_open_max_calls: Max calls to test in half-open state
            expected_exception: Exception type to count as failure
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exception = expected_exception
        
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        
        # Statistics
        self._total_requests = 0
        self._total_failures = 0
        self._state_changes = []
    
    @property
    def current_state(self) -> str:
        """Get current circuit breaker state."""
        return self._state.value
    
    @property
    def failure_count(self) -> int:
        """Get current failure count."""
        return self._failure_count
    
    @property
    def success_count(self) -> int:
        """Get current success count in half-open state."""
        return self._success_count
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Original exception if function fails
        """
        async with self._lock:
            await self._check_state()
            
            if self._state == CircuitBreakerState.OPEN:
                raise CircuitBreakerError("Circuit breaker is open")
            
            self._total_requests += 1
        
        try:
            # Execute the function
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Record success
            await self._record_success()
            return result
            
        except self.expected_exception as e:
            # Record failure
            await self._record_failure()
            raise e
    
    async def _check_state(self) -> None:
        """Check and update circuit breaker state."""
        if self._state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                await self._move_to_half_open()
        elif self._state == CircuitBreakerState.HALF_OPEN:
            if self._success_count >= self.half_open_max_calls:
                await self._move_to_closed()
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return False
        return time.time() - self._last_failure_time >= self.recovery_timeout
    
    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
                logger.debug(f"Circuit breaker success in half-open: {self._success_count}/{self.half_open_max_calls}")
                
                if self._success_count >= self.half_open_max_calls:
                    await self._move_to_closed()
            elif self._state == CircuitBreakerState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = 0
    
    async def _record_failure(self) -> None:
        """Record a failed call."""
        async with self._lock:
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.time()
            
            logger.warning(f"Circuit breaker failure recorded: {self._failure_count}/{self.failure_threshold}")
            
            if self._state == CircuitBreakerState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    await self._move_to_open()
            elif self._state == CircuitBreakerState.HALF_OPEN:
                # Any failure in half-open goes back to open
                await self._move_to_open()
    
    async def _move_to_open(self) -> None:
        """Move circuit breaker to open state."""
        old_state = self._state
        self._state = CircuitBreakerState.OPEN
        self._half_open_calls = 0
        self._success_count = 0
        
        self._record_state_change(old_state, self._state)
        logger.warning(f"Circuit breaker opened after {self._failure_count} failures")
    
    async def _move_to_half_open(self) -> None:
        """Move circuit breaker to half-open state."""
        old_state = self._state
        self._state = CircuitBreakerState.HALF_OPEN
        self._half_open_calls = 0
        self._success_count = 0
        
        self._record_state_change(old_state, self._state)
        logger.info("Circuit breaker moved to half-open state")
    
    async def _move_to_closed(self) -> None:
        """Move circuit breaker to closed state."""
        old_state = self._state
        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        
        self._record_state_change(old_state, self._state)
        logger.info("Circuit breaker closed - service recovered")
    
    def _record_state_change(self, old_state: CircuitBreakerState, new_state: CircuitBreakerState) -> None:
        """Record state change for monitoring."""
        self._state_changes.append({
            'timestamp': time.time(),
            'from_state': old_state.value,
            'to_state': new_state.value,
            'failure_count': self._failure_count
        })
        
        # Keep only last 100 state changes
        if len(self._state_changes) > 100:
            self._state_changes = self._state_changes[-100:]
    
    def get_statistics(self) -> dict:
        """
        Get circuit breaker statistics.
        
        Returns:
            Dictionary with statistics
        """
        return {
            'state': self._state.value,
            'failure_count': self._failure_count,
            'success_count': self._success_count,
            'total_requests': self._total_requests,
            'total_failures': self._total_failures,
            'failure_rate': self._total_failures / max(self._total_requests, 1),
            'last_failure_time': self._last_failure_time,
            'time_since_last_failure': time.time() - self._last_failure_time if self._last_failure_time else None,
            'state_changes': len(self._state_changes),
            'recent_state_changes': self._state_changes[-5:] if self._state_changes else []
        }
    
    async def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        async with self._lock:
            old_state = self._state
            await self._move_to_closed()
            logger.info(f"Circuit breaker manually reset from {old_state.value}")
    
    async def force_open(self) -> None:
        """Manually force circuit breaker to open state."""
        async with self._lock:
            old_state = self._state
            await self._move_to_open()
            logger.warning(f"Circuit breaker manually forced open from {old_state.value}")
    
    # Context manager support
    async def __aenter__(self):
        """Async context manager entry."""
        async with self._lock:
            await self._check_state()
            
            if self._state == CircuitBreakerState.OPEN:
                raise CircuitBreakerError("Circuit breaker is open")
            
            self._total_requests += 1
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if exc_type is None:
            # Success
            await self._record_success()
        elif isinstance(exc_val, self.expected_exception):
            # Expected failure
            await self._record_failure()
        # Unexpected exceptions are not counted as failures
        
        return False  # Don't suppress exceptions
    
    # Synchronous context manager support
    def __enter__(self):
        """Synchronous context manager entry."""
        # Check state synchronously (simplified)
        if self._state == CircuitBreakerState.OPEN:
            if not self._should_attempt_reset():
                raise CircuitBreakerError("Circuit breaker is open")
        
        self._total_requests += 1
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Synchronous context manager exit."""
        # Run the async methods in a simple way for sync context
        if exc_type is None:
            # Success - reset failure count if in closed state
            if self._state == CircuitBreakerState.CLOSED:
                self._failure_count = 0
            elif self._state == CircuitBreakerState.HALF_OPEN:
                self._success_count += 1
        elif isinstance(exc_val, self.expected_exception):
            # Failure
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitBreakerState.CLOSED and self._failure_count >= self.failure_threshold:
                self._state = CircuitBreakerState.OPEN
                logger.warning(f"Circuit breaker opened after {self._failure_count} failures")
            elif self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                logger.warning("Circuit breaker reopened due to failure in half-open state")
        
        return False  # Don't suppress exceptions


class MultiServiceCircuitBreaker:
    """
    Circuit breaker that manages multiple services.
    
    Useful for managing circuit breakers for NSE, BSE, and other APIs
    independently while providing a unified interface.
    """
    
    def __init__(self, default_config: dict = None):
        """
        Initialize multi-service circuit breaker.
        
        Args:
            default_config: Default configuration for new circuit breakers
        """
        self.default_config = default_config or {
            'failure_threshold': 5,
            'recovery_timeout': 60,
            'half_open_max_calls': 3
        }
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
    
    def get_breaker(self, service_name: str, config: dict = None) -> CircuitBreaker:
        """
        Get or create circuit breaker for a service.
        
        Args:
            service_name: Name of the service
            config: Optional configuration override
            
        Returns:
            CircuitBreaker instance
        """
        if service_name not in self.circuit_breakers:
            breaker_config = {**self.default_config}
            if config:
                breaker_config.update(config)
            
            self.circuit_breakers[service_name] = CircuitBreaker(**breaker_config)
        
        return self.circuit_breakers[service_name]
    
    async def call(self, service_name: str, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker for specific service.
        
        Args:
            service_name: Name of the service
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
        """
        breaker = self.get_breaker(service_name)
        return await breaker.call(func, *args, **kwargs)
    
    def get_all_statistics(self) -> dict:
        """Get statistics for all circuit breakers."""
        return {
            service: breaker.get_statistics()
            for service, breaker in self.circuit_breakers.items()
        }
    
    async def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self.circuit_breakers.values():
            await breaker.reset()
    
    async def reset_service(self, service_name: str) -> None:
        """Reset circuit breaker for specific service."""
        if service_name in self.circuit_breakers:
            await self.circuit_breakers[service_name].reset() 