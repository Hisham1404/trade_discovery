"""
Production-Grade Signal Generation and Explainability Engine

Enterprise implementation with:
- Circuit breakers and fault tolerance
- Performance monitoring and Prometheus metrics
- Rate limiting and resource protection
- Security validation and input sanitization
- Health checks and observability
- Structured logging with correlation IDs
- Memory management and optimization
- Timeout handling and graceful degradation
- Connection pooling and resource management
"""

import asyncio
import logging
import time
import json
import gc
import psutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import numpy as np

import shap
import pulsar
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, Gauge, generate_latest

from .generator import SignalGenerator
from monitoring.services.logging_config import AgentLogger

logger = logging.getLogger(__name__)


@dataclass
class ProductionConfig:
    """Production configuration for Signal Generator"""
    pulsar_url: str = 'pulsar://pulsar:6650'
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout: int = 60
    rate_limit_requests_per_minute: int = 120
    rate_limit_burst_capacity: int = 20
    max_input_size: int = 1048576  # 1MB
    shap_timeout_seconds: float = 10.0
    aggregation_timeout_seconds: float = 30.0
    max_concurrent_signals: int = 50
    memory_threshold_mb: int = 512
    health_check_interval: int = 30


@dataclass
class CircuitBreakerState:
    """Circuit breaker state management"""
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    failure_threshold: int = 5
    recovery_timeout: int = 60
    half_open_max_calls: int = 3
    half_open_calls: int = 0


@dataclass
class RateLimitState:
    """Rate limiting state management"""
    requests: deque = field(default_factory=lambda: deque(maxlen=1000))
    max_requests_per_minute: int = 120
    burst_capacity: int = 20
    current_burst: int = 0


class ProductionCircuitBreaker:
    """Production-grade circuit breaker for Signal Generator"""
    
    def __init__(self, config: ProductionConfig):
        self.state = CircuitBreakerState(
            failure_threshold=config.circuit_breaker_failure_threshold,
            recovery_timeout=config.circuit_breaker_recovery_timeout
        )
        
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            if self.state.state == "OPEN":
                if self._should_attempt_reset():
                    self.state.state = "HALF_OPEN"
                    self.state.half_open_calls = 0
                else:
                    raise Exception(f"Signal generator circuit breaker OPEN. Last failure: {self.state.last_failure_time}")
            
            if self.state.state == "HALF_OPEN" and self.state.half_open_calls >= self.state.half_open_max_calls:
                raise Exception("Signal generator circuit breaker HALF_OPEN call limit exceeded")
            
            try:
                result = await func(*args, **kwargs)
                self._record_success()
                return result
            except Exception as e:
                self._record_failure()
                raise
        
        return wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        if not self.state.last_failure_time:
            return True
        
        time_since_failure = (datetime.now(timezone.utc) - self.state.last_failure_time).total_seconds()
        return time_since_failure >= self.state.recovery_timeout
    
    def _record_success(self):
        """Record successful operation"""
        if self.state.state == "HALF_OPEN":
            self.state.half_open_calls += 1
            if self.state.half_open_calls >= self.state.half_open_max_calls:
                self.state.state = "CLOSED"
                self.state.failure_count = 0
        elif self.state.state == "CLOSED":
            self.state.failure_count = max(0, self.state.failure_count - 1)
    
    def _record_failure(self):
        """Record failed operation"""
        self.state.failure_count += 1
        self.state.last_failure_time = datetime.now(timezone.utc)
        
        if self.state.failure_count >= self.state.failure_threshold:
            self.state.state = "OPEN"
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state"""
        return {
            'state': self.state.state,
            'failure_count': self.state.failure_count,
            'last_failure_time': self.state.last_failure_time.isoformat() if self.state.last_failure_time else None,
            'failure_threshold': self.state.failure_threshold
        }


class ProductionRateLimiter:
    """Production-grade rate limiter for signal processing"""
    
    def __init__(self, config: ProductionConfig):
        self.state = RateLimitState(
            max_requests_per_minute=config.rate_limit_requests_per_minute,
            burst_capacity=config.rate_limit_burst_capacity
        )
    
    async def check_rate_limit(self, identifier: str = "signal_processing") -> bool:
        """Check if request is within rate limits"""
        current_time = time.time()
        
        # Clean old requests (older than 1 minute)
        cutoff_time = current_time - 60
        while self.state.requests and self.state.requests[0] < cutoff_time:
            self.state.requests.popleft()
        
        # Check rate limit
        if len(self.state.requests) >= self.state.max_requests_per_minute:
            # Check burst capacity
            if self.state.current_burst >= self.state.burst_capacity:
                return False
            else:
                self.state.current_burst += 1
        
        # Add current request
        self.state.requests.append(current_time)
        
        # Reset burst counter if we're back under normal limits
        if len(self.state.requests) < self.state.max_requests_per_minute:
            self.state.current_burst = 0
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get current rate limit status"""
        current_time = time.time()
        cutoff_time = current_time - 60
        recent_requests = sum(1 for req_time in self.state.requests if req_time > cutoff_time)
        
        return {
            'requests_in_last_minute': recent_requests,
            'max_requests_per_minute': self.state.max_requests_per_minute,
            'burst_capacity': self.state.burst_capacity,
            'current_burst_usage': self.state.current_burst,
            'rate_limit_remaining': max(0, self.state.max_requests_per_minute - recent_requests)
        }


class ProductionSecurityValidator:
    """Production-grade security validator for signal data"""
    
    def __init__(self, config: ProductionConfig):
        self.max_input_size = config.max_input_size
        
        # Malicious patterns to detect
        self.dangerous_patterns = [
            r'<script[^>]*>.*?</script>',
            r'\$\{jndi:.*?\}',
            r'javascript:',
            r'data:text/html',
            r'eval\s*\(',
            r'exec\s*\(',
        ]
    
    async def validate_signal_data(self, signal_data: Any) -> Any:
        """Validate and sanitize signal data"""
        # Check input size
        input_str = json.dumps(signal_data) if not isinstance(signal_data, str) else signal_data
        if len(input_str) > self.max_input_size:
            raise ValueError(f"Signal data size {len(input_str)} exceeds limit {self.max_input_size}")
        
        # Type validation for signal data
        if isinstance(signal_data, dict):
            return self._validate_signal_dict(signal_data)
        elif isinstance(signal_data, list):
            return [await self.validate_signal_data(item) for item in signal_data]
        else:
            return signal_data
    
    def _validate_signal_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate signal dictionary structure"""
        validated = {}
        
        # Required fields for signals
        required_fields = ['symbol', 'direction', 'confidence']
        for field in required_fields:
            if field in data:
                validated[field] = self._sanitize_value(data[field])
        
        # Optional fields
        optional_fields = ['agent', 'target', 'stop_loss', 'technical_score', 'sentiment_score', 
                          'fundamental_score', 'risk_score', 'timestamp']
        for field in optional_fields:
            if field in data:
                validated[field] = self._sanitize_value(data[field])
        
        # Validate confidence range
        if 'confidence' in validated:
            confidence = validated['confidence']
            if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
                raise ValueError(f"Invalid confidence value: {confidence}")
        
        return validated
    
    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize individual values"""
        if isinstance(value, str):
            # Remove dangerous patterns
            sanitized = value
            for pattern in self.dangerous_patterns:
                sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
            return sanitized
        return value


class ProductionSignalGenerator(SignalGenerator):
    """
    Production-Grade Signal Generation Engine
    
    Enterprise implementation with:
    - Circuit breakers for fault tolerance
    - Rate limiting for resource protection
    - Security validation and sanitization
    - Performance monitoring and metrics
    - Health checks and observability
    - Graceful degradation and error recovery
    - Memory management and optimization
    """
    
    def __init__(self, db_session: Session, config: Optional[ProductionConfig] = None):
        # Initialize base generator with basic config
        basic_config = {'pulsar_url': config.pulsar_url if config else 'pulsar://pulsar:6650'}
        super().__init__(db_session, basic_config.get('pulsar_url'))
        
        self.name = "ProductionSignalGenerator"
        self.version = "1.0.0"
        self.config = config or ProductionConfig()
        
        # Production components (initialized in initialize())
        self.circuit_breaker = None
        self.rate_limiter = None
        self.security_validator = None
        self.agent_logger = None
        
        # Metrics
        self._setup_prometheus_metrics()
        
        # State tracking
        self.start_time = datetime.now(timezone.utc)
        self.is_initialized = False
        self.health_status = "initializing"
        
        # Performance tracking
        self.signal_history = deque(maxlen=1000)
        self.error_history = deque(maxlen=100)
        self.processing_semaphore = asyncio.Semaphore(self.config.max_concurrent_signals)
        
        logger.info(f"Production Signal Generator created")
    
    def _setup_prometheus_metrics(self):
        """Setup Prometheus metrics collectors"""
        self.metrics = {
            'signals_processed_total': Counter(
                'signal_generator_signals_processed_total',
                'Total signals processed',
                ['operation', 'status', 'symbol']
            ),
            'processing_duration': Histogram(
                'signal_generator_processing_duration_seconds',
                'Signal processing duration',
                ['operation']
            ),
            'shap_explanation_duration': Histogram(
                'signal_generator_shap_duration_seconds',
                'SHAP explanation generation duration'
            ),
            'pulsar_operations_total': Counter(
                'signal_generator_pulsar_operations_total',
                'Total Pulsar operations',
                ['operation', 'topic', 'status']
            ),
            'errors_total': Counter(
                'signal_generator_errors_total',
                'Total errors by type',
                ['error_type', 'operation']
            ),
            'active_connections': Gauge(
                'signal_generator_active_connections',
                'Currently active signal processing connections'
            ),
            'memory_usage_bytes': Gauge(
                'signal_generator_memory_usage_bytes',
                'Current memory usage in bytes'
            ),
            'circuit_breaker_state': Gauge(
                'signal_generator_circuit_breaker_state',
                'Circuit breaker state (0=closed, 1=open, 2=half-open)'
            ),
            'signals_per_minute': Gauge(
                'signal_generator_signals_per_minute',
                'Signals processed per minute'
            )
        }
    
    async def initialize(self) -> Dict[str, Any]:
        """Initialize production components"""
        try:
            start_time = time.time()
            
            # Initialize circuit breaker
            self.circuit_breaker = ProductionCircuitBreaker(self.config)
            
            # Initialize rate limiter
            self.rate_limiter = ProductionRateLimiter(self.config)
            
            # Initialize security validator
            self.security_validator = ProductionSecurityValidator(self.config)
            
            # Initialize structured logging
            self.agent_logger = AgentLogger(
                agent_type="signal_generator",
                agent_id=f"signal_gen_{int(time.time())}",
                config={}
            )
            
            self.is_initialized = True
            self.health_status = "healthy"
            
            initialization_time = time.time() - start_time
            
            logger.info(f"Production Signal Generator initialized in {initialization_time:.3f}s")
            
            return {
                'status': 'initialized',
                'initialization_time': initialization_time,
                'components': {
                    'circuit_breaker': 'active',
                    'rate_limiter': 'active',
                    'security_validator': 'active',
                    'structured_logging': 'active',
                    'prometheus_metrics': 'active'
                },
                'health_status': self.health_status,
                'version': self.version
            }
            
        except Exception as e:
            self.health_status = "unhealthy"
            logger.error(f"Failed to initialize production signal generator: {e}")
            raise
    
    @asynccontextmanager
    async def performance_tracking(self, operation: str, symbol: str = None):
        """Context manager for performance tracking"""
        start_time = time.time()
        correlation_id = f"{operation}_{int(start_time * 1000)}"
        
        try:
            # Update active connections
            self.metrics['active_connections'].inc()
            
            yield correlation_id
            
            # Record success
            duration = time.time() - start_time
            self.metrics['processing_duration'].labels(operation=operation).observe(duration)
            self.metrics['signals_processed_total'].labels(
                operation=operation, 
                status='success',
                symbol=symbol or 'unknown'
            ).inc()
            
            # Log performance
            if self.agent_logger:
                self.agent_logger.log_execution_time(duration, operation)
            
        except Exception as e:
            # Record error
            duration = time.time() - start_time
            error_type = type(e).__name__
            
            self.metrics['errors_total'].labels(
                error_type=error_type,
                operation=operation
            ).inc()
            
            self.metrics['signals_processed_total'].labels(
                operation=operation,
                status='error',
                symbol=symbol or 'unknown'
            ).inc()
            
            # Log error
            if self.agent_logger:
                self.agent_logger.log_error(e, {
                    'operation': operation,
                    'correlation_id': correlation_id,
                    'symbol': symbol
                })
            
            # Track error history
            self.error_history.append({
                'timestamp': datetime.now(timezone.utc),
                'error_type': error_type,
                'operation': operation,
                'message': str(e)
            })
            
            raise
        finally:
            # Update active connections
            self.metrics['active_connections'].dec()
            
            # Update memory usage
            process = psutil.Process()
            memory_bytes = process.memory_info().rss
            self.metrics['memory_usage_bytes'].set(memory_bytes)
    
    async def aggregate_agent_signals_with_protection(self, timeout_ms: int = None) -> List[Dict]:
        """Aggregate signals with circuit breaker protection"""
        if not self.circuit_breaker:
            raise RuntimeError("Signal generator not initialized")
        
        timeout_ms = timeout_ms or int(self.config.aggregation_timeout_seconds * 1000)
        
        @self.circuit_breaker
        async def _protected_aggregation():
            return await super().aggregate_agent_signals(timeout_ms)
        
        # Update circuit breaker state metric
        cb_state = self.circuit_breaker.get_state()
        state_value = {'CLOSED': 0, 'OPEN': 1, 'HALF_OPEN': 2}.get(cb_state['state'], 0)
        self.metrics['circuit_breaker_state'].set(state_value)
        
        return await _protected_aggregation()
    
    async def generate_shap_explanation_with_timeout(self, signal_data: Dict) -> Dict:
        """Generate SHAP explanation with timeout protection"""
        async with self.performance_tracking("shap_explanation"):
            try:
                # Apply timeout
                shap_task = asyncio.create_task(
                    asyncio.to_thread(super().generate_shap_explanation, signal_data)
                )
                
                result = await asyncio.wait_for(shap_task, timeout=self.config.shap_timeout_seconds)
                
                # Record SHAP timing
                if 'processing_time_ms' in result:
                    self.metrics['shap_explanation_duration'].observe(result['processing_time_ms'] / 1000)
                
                return result
                
            except asyncio.TimeoutError:
                logger.warning(f"SHAP explanation timed out after {self.config.shap_timeout_seconds}s")
                return {
                    'feature_importance': {name: 0.0 for name in self.feature_names},
                    'top_factors': [],
                    'timeout': True
                }
    
    async def process_signal_with_rate_limiting(self, signal_data: Dict) -> Optional[Dict]:
        """Process individual signal with rate limiting"""
        # Check rate limit
        if not await self.rate_limiter.check_rate_limit():
            logger.warning("Rate limit exceeded, dropping signal")
            self.metrics['errors_total'].labels(
                error_type='RateLimitExceeded',
                operation='process_signal'
            ).inc()
            return None
        
        # Validate and sanitize input
        try:
            validated_signal = await self.security_validator.validate_signal_data(signal_data)
        except ValueError as e:
            logger.warning(f"Signal validation failed: {e}")
            self.metrics['errors_total'].labels(
                error_type='ValidationError',
                operation='process_signal'
            ).inc()
            return None
        
        return validated_signal
    
    async def generate_and_store_signals_production(self, confidence_threshold: float = 0.6):
        """
        Production-grade signal generation pipeline with comprehensive protection
        """
        if not self.is_initialized:
            raise RuntimeError("Signal generator not initialized")
        
        async with self.processing_semaphore:
            async with self.performance_tracking("full_pipeline") as correlation_id:
                start_time = time.time()
                
                try:
                    # Step 1: Aggregate signals with protection
                    agent_signals = await self.aggregate_agent_signals_with_protection()
                    
                    if not agent_signals:
                        logger.info("No signals received from agents")
                        return
                    
                    # Step 2: Process signals with rate limiting and validation
                    validated_signals = []
                    for signal in agent_signals:
                        processed = await self.process_signal_with_rate_limiting(signal)
                        if processed:
                            validated_signals.append(processed)
                    
                    if not validated_signals:
                        logger.warning("No valid signals after validation")
                        return
                    
                    # Step 3: Group signals by symbol
                    symbol_signals = self._group_signals_by_symbol(validated_signals)
                    
                    # Step 4: Process each symbol with memory management
                    processed_count = 0
                    for symbol, signals in symbol_signals.items():
                        try:
                            # Check memory pressure
                            if await self._check_memory_pressure():
                                logger.warning("Memory pressure detected, triggering GC")
                                gc.collect()
                            
                            # Calculate composite confidence
                            confidence = self.calculate_composite_confidence(signals)
                            
                            # Filter by confidence threshold
                            if confidence <= confidence_threshold:
                                logger.debug(f"Signal for {symbol} filtered out (confidence: {confidence:.3f})")
                                continue
                            
                            # Use the first signal as base
                            base_signal = signals[0].copy()
                            base_signal['confidence'] = confidence
                            
                            # Generate SHAP explanation with timeout
                            shap_data = await self.generate_shap_explanation_with_timeout(base_signal)
                            
                            # Generate natural language explanation
                            explanation = self.generate_natural_language_explanation(base_signal, shap_data)
                            
                            # Prepare final signal data
                            final_signal = {
                                'symbol': symbol,
                                'direction': base_signal['direction'],
                                'confidence': confidence,
                                'target': base_signal.get('target'),
                                'stop_loss': base_signal.get('stop_loss'),
                                'explanation': explanation,
                                'shap_values': shap_data,
                                'correlation_id': correlation_id,
                                'processing_time_ms': (time.time() - start_time) * 1000
                            }
                            
                            # Store in database with error handling
                            try:
                                self._store_signal(final_signal)
                                processed_count += 1
                                
                                # Track successful signal
                                self.signal_history.append({
                                    'timestamp': datetime.now(timezone.utc),
                                    'symbol': symbol,
                                    'confidence': confidence,
                                    'status': 'success'
                                })
                                
                                logger.info(f"Generated signal for {symbol} with {confidence:.1%} confidence")
                                
                            except Exception as e:
                                logger.error(f"Failed to store signal for {symbol}: {e}")
                                self.metrics['errors_total'].labels(
                                    error_type='DatabaseError',
                                    operation='store_signal'
                                ).inc()
                                continue
                            
                        except Exception as e:
                            logger.error(f"Error processing signals for {symbol}: {e}")
                            self.metrics['errors_total'].labels(
                                error_type=type(e).__name__,
                                operation='process_symbol'
                            ).inc()
                            continue
                    
                    # Update throughput metrics
                    processing_time = (time.time() - start_time) * 1000
                    signals_per_minute = (processed_count / (processing_time / 1000)) * 60 if processing_time > 0 else 0
                    self.metrics['signals_per_minute'].set(signals_per_minute)
                    
                    logger.info(f"Signal generation pipeline completed: {processed_count} signals in {processing_time:.2f}ms")
                    
                except Exception as e:
                    logger.error(f"Error in signal generation pipeline: {e}")
                    self.metrics['errors_total'].labels(
                        error_type=type(e).__name__,
                        operation='full_pipeline'
                    ).inc()
                    raise
    
    async def _check_memory_pressure(self) -> bool:
        """Check if memory usage is too high"""
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        return memory_mb > self.config.memory_threshold_mb
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        current_time = datetime.now(timezone.utc)
        uptime = (current_time - self.start_time).total_seconds()
        
        # Component health
        components = {
            'signal_generator': 'healthy' if self.is_initialized else 'unhealthy',
            'pulsar_client': 'healthy' if self.pulsar_client else 'unhealthy',
            'circuit_breaker': self.circuit_breaker.get_state()['state'] if self.circuit_breaker else 'disabled',
            'rate_limiter': 'healthy' if self.rate_limiter else 'disabled',
            'security_validator': 'healthy' if self.security_validator else 'disabled'
        }
        
        # Performance metrics
        recent_signals = [
            sig for sig in self.signal_history 
            if (current_time - sig['timestamp']).total_seconds() < 300  # Last 5 minutes
        ]
        
        success_rate = (
            len([sig for sig in recent_signals if sig['status'] == 'success']) / 
            len(recent_signals) if recent_signals else 1.0
        )
        
        error_rate = len(self.error_history) / max(len(self.signal_history), 1)
        
        # Memory and resource status
        process = psutil.Process()
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        # Overall health determination
        overall_health = 'healthy'
        if not self.is_initialized or success_rate < 0.95 or error_rate > 0.1:
            overall_health = 'degraded'
        if success_rate < 0.8 or error_rate > 0.2 or memory_mb > self.config.memory_threshold_mb:
            overall_health = 'unhealthy'
        
        return {
            'status': overall_health,
            'uptime_seconds': uptime,
            'components': components,
            'performance': {
                'signals_processed_last_5min': len(recent_signals),
                'success_rate': success_rate,
                'error_rate': error_rate,
                'avg_confidence': np.mean([sig.get('confidence', 0) for sig in recent_signals]) if recent_signals else 0
            },
            'resources': {
                'memory_mb': memory_mb,
                'memory_threshold_mb': self.config.memory_threshold_mb,
                'memory_pressure': memory_mb > self.config.memory_threshold_mb,
                'active_connections': self.metrics['active_connections']._value.get()
            },
            'rate_limiting': self.rate_limiter.get_status() if self.rate_limiter else {},
            'circuit_breaker': self.circuit_breaker.get_state() if self.circuit_breaker else {},
            'recent_errors': list(self.error_history)[-5:] if self.error_history else []
        }
    
    async def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics in text format"""
        return generate_latest()
    
    async def graceful_shutdown(self) -> Dict[str, Any]:
        """Gracefully shutdown the signal generator"""
        start_time = time.time()
        
        try:
            # Wait for active processing to complete
            logger.info("Waiting for active signal processing to complete...")
            await asyncio.wait_for(
                self.processing_semaphore.acquire(), 
                timeout=30.0
            )
            
            # Close connections
            self.close()
            
            self.health_status = "shutdown"
            shutdown_time = time.time() - start_time
            
            logger.info(f"Production Signal Generator shutdown completed in {shutdown_time:.3f}s")
            
            return {
                'status': 'shutdown_complete',
                'shutdown_time': shutdown_time,
                'signals_processed_total': sum(1 for _ in self.signal_history),
                'errors_total': len(self.error_history)
            }
            
        except asyncio.TimeoutError:
            logger.warning("Graceful shutdown timed out, forcing shutdown")
            self.close()
            return {
                'status': 'forced_shutdown',
                'shutdown_time': time.time() - start_time
            } 