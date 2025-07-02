"""
Production-Grade Meta-Cognitive Agent with K-Level Reasoning

Enterprise implementation with:
- Circuit breakers and error recovery
- Performance monitoring and metrics 
- Security and input validation
- Rate limiting and resource management
- Health checks and observability
- Prometheus metrics integration
- Structured logging with correlation IDs
- Memory management and optimization
- Timeout handling and graceful degradation
"""

import asyncio
import logging
import time
import json
import re
import hashlib
import gc
import psutil
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union
from collections import defaultdict, deque
from contextlib import asynccontextmanager
import numpy as np

from prometheus_client import Counter, Histogram, Gauge, generate_latest

from .base_agent import BaseAgent
from .performance_monitor import PerformanceMonitor, PerformanceAlert
from monitoring.services.logging_config import AgentLogger

# Configure logging
logger = logging.getLogger(__name__)


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
    max_requests_per_minute: int = 60
    burst_capacity: int = 10
    current_burst: int = 0


class ProductionCircuitBreaker:
    """Production-grade circuit breaker implementation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.state = CircuitBreakerState(
            failure_threshold=config.get('failure_threshold', 5),
            recovery_timeout=config.get('recovery_timeout', 60),
            half_open_max_calls=config.get('half_open_max_calls', 3)
        )
        
    def __call__(self, func):
        async def wrapper(*args, **kwargs):
            if self.state.state == "OPEN":
                if self._should_attempt_reset():
                    self.state.state = "HALF_OPEN"
                    self.state.half_open_calls = 0
                else:
                    raise Exception(f"Circuit breaker OPEN. Last failure: {self.state.last_failure_time}")
            
            if self.state.state == "HALF_OPEN" and self.state.half_open_calls >= self.state.half_open_max_calls:
                raise Exception("Circuit breaker HALF_OPEN call limit exceeded")
            
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
    """Production-grade rate limiter with burst capacity"""
    
    def __init__(self, config: Dict[str, Any]):
        self.state = RateLimitState(
            max_requests_per_minute=config.get('max_requests_per_minute', 60),
            burst_capacity=config.get('burst_capacity', 10)
        )
    
    async def check_rate_limit(self, identifier: str = "default") -> bool:
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
    
    def get_rate_limit_status(self) -> Dict[str, Any]:
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
    """Production-grade security and input validation"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.max_input_size = config.get('max_input_size', 1048576)  # 1MB
        self.sanitization_enabled = config.get('sanitization', True)
        
        # Security patterns to detect/sanitize
        self.malicious_patterns = [
            r'<script[^>]*>.*?</script>',  # XSS
            r'\$\{jndi:.*?\}',  # Log4j injection
            r'javascript:',  # JavaScript URLs
            r'data:text/html',  # Data URLs
            r'vbscript:',  # VBScript
            r'onload=',  # Event handlers
            r'onerror=',
            r'onclick=',
        ]
    
    async def validate_and_sanitize(self, input_data: Any) -> Any:
        """Validate and sanitize input data"""
        # Check input size
        input_str = json.dumps(input_data) if not isinstance(input_data, str) else input_data
        if len(input_str) > self.max_input_size:
            raise ValueError(f"Input size {len(input_str)} exceeds limit {self.max_input_size}")
        
        # Type validation
        if not isinstance(input_data, (dict, list, str, int, float, bool, type(None))):
            raise ValueError(f"Invalid input type: {type(input_data)}")
        
        # Sanitize if enabled
        if self.sanitization_enabled:
            return self._sanitize_recursive(input_data)
        
        return input_data
    
    def _sanitize_recursive(self, data: Any) -> Any:
        """Recursively sanitize data structure"""
        if isinstance(data, dict):
            return {key: self._sanitize_recursive(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._sanitize_recursive(item) for item in data]
        elif isinstance(data, str):
            return self._sanitize_string(data)
        else:
            return data
    
    def _sanitize_string(self, text: str) -> str:
        """Sanitize string content"""
        sanitized = text
        
        # Remove malicious patterns
        for pattern in self.malicious_patterns:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        # HTML encode dangerous characters
        sanitized = sanitized.replace('<', '&lt;').replace('>', '&gt;')
        sanitized = sanitized.replace('"', '&quot;').replace("'", '&#x27;')
        
        return sanitized


class ProductionMetaCognitiveAgent(BaseAgent):
    """
    Production-Grade Meta-Cognitive Agent with Enterprise Features
    
    Features:
    - Circuit breakers for fault tolerance
    - Rate limiting for resource protection
    - Security validation and sanitization
    - Performance monitoring and metrics
    - Health checks and observability
    - Graceful degradation and error recovery
    - Memory management and optimization
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.name = "ProductionMetaCognitiveAgent"
        self.version = "1.0.0"
        self.config = config or {}
        
        # Core configuration
        self.default_k_level = self.config.get('default_k_level', 2)
        self.max_k_level = self.config.get('max_k_level', 5)
        self.confidence_threshold = self.config.get('confidence_threshold', 0.7)
        
        # Production components (will be initialized in initialize())
        self.circuit_breaker = None
        self.rate_limiter = None
        self.security_validator = None
        self.performance_monitor = None
        self.agent_logger = None
        
        # Metrics
        self._setup_prometheus_metrics()
        
        # State tracking
        self.start_time = datetime.now(timezone.utc)
        self.is_initialized = False
        self.health_status = "initializing"
        
        # Performance tracking
        self.execution_history = deque(maxlen=1000)
        self.error_history = deque(maxlen=100)
        
        logger.info(f"Production Meta-Cognitive Agent created with config: {self.config.keys()}")
    
    def _setup_prometheus_metrics(self):
        """Setup Prometheus metrics collectors"""
        self.metrics = {
            'requests_total': Counter(
                'meta_cognitive_requests_total',
                'Total requests processed',
                ['operation', 'status', 'k_level']
            ),
            'request_duration': Histogram(
                'meta_cognitive_request_duration_seconds',
                'Request processing duration',
                ['operation', 'k_level']
            ),
            'k_level_usage': Counter(
                'meta_cognitive_k_level_usage',
                'K-level usage distribution',
                ['k_level']
            ),
            'errors_total': Counter(
                'meta_cognitive_errors_total',
                'Total errors by type',
                ['error_type', 'operation']
            ),
            'active_connections': Gauge(
                'meta_cognitive_active_connections',
                'Currently active connections'
            ),
            'memory_usage_bytes': Gauge(
                'meta_cognitive_memory_usage_bytes',
                'Current memory usage in bytes'
            ),
            'circuit_breaker_state': Gauge(
                'meta_cognitive_circuit_breaker_state',
                'Circuit breaker state (0=closed, 1=open, 2=half-open)'
            )
        }
    
    async def initialize(self) -> Dict[str, Any]:
        """Initialize production components"""
        try:
            start_time = time.time()
            
            # Initialize circuit breaker
            circuit_config = self.config.get('circuit_breaker', {})
            self.circuit_breaker = ProductionCircuitBreaker(circuit_config)
            
            # Initialize rate limiter
            rate_limit_config = self.config.get('rate_limiting', {})
            self.rate_limiter = ProductionRateLimiter(rate_limit_config)
            
            # Initialize security validator
            security_config = self.config.get('security', {})
            self.security_validator = ProductionSecurityValidator(security_config)
            
            # Initialize performance monitor
            monitoring_config = self.config.get('performance_monitoring', {})
            if monitoring_config.get('enabled', True):
                self.performance_monitor = PerformanceMonitor(monitoring_config)
                await self.performance_monitor.initialize()
            
            # Initialize structured logging
            logging_config = self.config.get('logging', {})
            self.agent_logger = AgentLogger(
                agent_type="meta_cognitive",
                agent_id=f"meta_cognitive_{int(time.time())}",
                config=logging_config
            )
            
            self.is_initialized = True
            self.health_status = "healthy"
            
            initialization_time = time.time() - start_time
            
            self.agent_logger.log_execution_time(initialization_time, "initialization")
            
            return {
                'status': 'initialized',
                'initialization_time': initialization_time,
                'components': {
                    'circuit_breaker': 'active',
                    'rate_limiter': 'active',
                    'security_validator': 'active',
                    'performance_monitor': 'active' if self.performance_monitor else 'disabled',
                    'structured_logging': 'active'
                },
                'health_status': self.health_status,
                'version': self.version
            }
            
        except Exception as e:
            self.health_status = "unhealthy"
            logger.error(f"Failed to initialize production agent: {e}")
            raise
    
    async def validate_and_sanitize_input(self, input_data: Any) -> Any:
        """Validate and sanitize input data"""
        if not self.security_validator:
            raise RuntimeError("Agent not initialized")
        
        return await self.security_validator.validate_and_sanitize(input_data)
    
    @asynccontextmanager
    async def performance_tracking(self, operation: str, k_level: int = None):
        """Context manager for performance tracking"""
        start_time = time.time()
        correlation_id = f"{operation}_{int(start_time * 1000)}"
        
        try:
            # Update active connections
            self.metrics['active_connections'].inc()
            
            yield correlation_id
            
            # Record success
            duration = time.time() - start_time
            self.metrics['request_duration'].labels(
                operation=operation, 
                k_level=str(k_level) if k_level else 'unknown'
            ).observe(duration)
            self.metrics['requests_total'].labels(
                operation=operation, 
                status='success',
                k_level=str(k_level) if k_level else 'unknown'
            ).inc()
            
            if k_level:
                self.metrics['k_level_usage'].labels(k_level=str(k_level)).inc()
            
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
            
            self.metrics['requests_total'].labels(
                operation=operation,
                status='error',
                k_level=str(k_level) if k_level else 'unknown'
            ).inc()
            
            # Log error
            if self.agent_logger:
                self.agent_logger.log_error(e, {
                    'operation': operation,
                    'correlation_id': correlation_id,
                    'k_level': k_level
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
    
    async def analyze_with_circuit_breaker(self, agent_outputs: Dict[str, Any], 
                                         market_conditions: Dict[str, Any] = None,
                                         correlation_id: str = None) -> Dict[str, Any]:
        """Perform analysis with circuit breaker protection"""
        if not self.circuit_breaker:
            raise RuntimeError("Agent not initialized")
        
        @self.circuit_breaker
        async def _protected_analysis():
            return await self._perform_analysis(agent_outputs, market_conditions, correlation_id)
        
        # Update circuit breaker state metric
        cb_state = self.circuit_breaker.get_state()
        state_value = {'CLOSED': 0, 'OPEN': 1, 'HALF_OPEN': 2}.get(cb_state['state'], 0)
        self.metrics['circuit_breaker_state'].set(state_value)
        
        return await _protected_analysis()
    
    async def _perform_analysis(self, agent_outputs: Dict[str, Any],
                              market_conditions: Dict[str, Any] = None,
                              correlation_id: str = None) -> Dict[str, Any]:
        """Internal analysis method"""
        # Validate and sanitize inputs
        validated_outputs = await self.validate_and_sanitize_input(agent_outputs)
        
        if market_conditions:
            validated_conditions = await self.validate_and_sanitize_input(market_conditions)
        else:
            validated_conditions = {}
        
        # Determine optimal K-level
        k_level = await self._calculate_optimal_k_level(validated_conditions)
        
        # Perform K-level analysis with timeout
        try:
            analysis_task = asyncio.create_task(
                self._k_level_analysis(validated_outputs, k_level)
            )
            
            # Set timeout based on K-level
            timeout = min(5.0, k_level * 0.5 + 0.5)  # 0.5s to 3s based on K-level
            result = await asyncio.wait_for(analysis_task, timeout=timeout)
            
        except asyncio.TimeoutError:
            logger.warning(f"Analysis timeout after {timeout}s for K-level {k_level}")
            # Fallback to simpler analysis
            result = await self._fallback_analysis(validated_outputs)
            result['status'] = 'timeout'
            result['timeout_seconds'] = timeout
        
        # Add metadata
        result.update({
            'correlation_id': correlation_id,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'agent_version': self.version,
            'processing_mode': 'production'
        })
        
        return result
    
    async def _calculate_optimal_k_level(self, market_conditions: Dict[str, Any]) -> int:
        """Calculate optimal K-level with resource constraints"""
        # Check memory pressure
        memory_pressure = await self._check_memory_pressure()
        if memory_pressure['memory_pressure']:
            return min(2, self.default_k_level)  # Limit K-level under memory pressure
        
        # Base calculation from market conditions
        volatility = market_conditions.get('volatility', 0.3)
        complexity = market_conditions.get('complexity_score', 0.5)
        
        base_k = 1 + int(volatility * 2) + int(complexity * 2)
        optimal_k = min(base_k, self.max_k_level)
        
        return max(1, optimal_k)
    
    async def _check_memory_pressure(self) -> Dict[str, Any]:
        """Check system memory pressure"""
        try:
            memory = psutil.virtual_memory()
            memory_pressure = memory.percent > 85  # Consider 85%+ as pressure
            
            return {
                'memory_pressure': memory_pressure,
                'memory_percent': memory.percent,
                'action': 'reduce_k_level' if memory_pressure else 'normal',
                'recommended_k_level': 2 if memory_pressure else self.default_k_level
            }
        except Exception as e:
            logger.warning(f"Failed to check memory pressure: {e}")
            return {
                'memory_pressure': False,
                'memory_percent': 0,
                'action': 'normal',
                'recommended_k_level': self.default_k_level
            }
    
    async def _k_level_analysis(self, agent_outputs: Dict[str, Any], k_level: int) -> Dict[str, Any]:
        """Perform K-level analysis"""
        if k_level == 1:
            return await self._k1_analysis(agent_outputs)
        elif k_level == 2:
            return await self._k2_analysis(agent_outputs)
        elif k_level >= 3:
            return await self._k3_plus_analysis(agent_outputs, k_level)
        else:
            return await self._k0_analysis(agent_outputs)
    
    async def _k1_analysis(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """K=1 level analysis (theory of mind)"""
        signals = [output.get('signal', 'HOLD') for output in agent_outputs.values()]
        confidences = [output.get('confidence', 0.5) for output in agent_outputs.values()]
        
        # Consensus calculation
        signal_counts = {signal: signals.count(signal) for signal in set(signals)}
        consensus_signal = max(signal_counts, key=signal_counts.get) if signal_counts else 'HOLD'
        consensus_strength = signal_counts.get(consensus_signal, 0) / len(signals) if signals else 0
        
        return {
            'meta_signal': consensus_signal,
            'confidence_score': np.mean(confidences) if confidences else 0.5,
            'k_level_used': 1,
            'consensus_strength': consensus_strength,
            'agent_count': len(agent_outputs),
            'reasoning_explanation': f'K=1 consensus analysis of {len(agent_outputs)} agents'
        }
    
    async def _k2_analysis(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """K=2 level analysis (meta-theory of mind)"""
        # Start with K=1 analysis
        k1_result = await self._k1_analysis(agent_outputs)
        
        # Add strategic considerations
        strategic_factors = []
        
        # Detect potential herding
        confidences = [output.get('confidence', 0.5) for output in agent_outputs.values()]
        if np.mean(confidences) > 0.8:
            strategic_factors.append('potential_herding')
        
        # Detect contrarian opportunities
        if k1_result['consensus_strength'] < 0.6:
            strategic_factors.append('contrarian_opportunity')
        
        # Adjust confidence based on strategic factors
        strategic_adjustment = -0.1 if 'potential_herding' in strategic_factors else 0.05
        adjusted_confidence = min(0.95, k1_result['confidence_score'] + strategic_adjustment)
        
        k1_result.update({
            'k_level_used': 2,
            'strategic_factors': strategic_factors,
            'confidence_score': adjusted_confidence,
            'reasoning_explanation': f'K=2 strategic analysis with factors: {strategic_factors}'
        })
        
        return k1_result
    
    async def _k3_plus_analysis(self, agent_outputs: Dict[str, Any], k_level: int) -> Dict[str, Any]:
        """K=3+ level analysis with complexity management"""
        # Start with K=2 analysis
        k2_result = await self._k2_analysis(agent_outputs)
        
        # Add higher-order considerations with graceful degradation
        if len(agent_outputs) > 10:
            # Large agent count - simplify analysis
            k2_result.update({
                'k_level_used': min(k_level, 3),
                'graceful_degradation': True,
                'reasoning_explanation': f'K={k_level} analysis simplified due to {len(agent_outputs)} agents'
            })
        else:
            # Full complexity analysis
            meta_meta_factors = ['recursive_belief_modeling', 'higher_order_game_theory']
            
            k2_result.update({
                'k_level_used': k_level,
                'meta_meta_factors': meta_meta_factors,
                'reasoning_explanation': f'K={k_level} recursive strategic analysis'
            })
        
        return k2_result
    
    async def _k0_analysis(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """K=0 level analysis (naive)"""
        if not agent_outputs:
            return {
                'meta_signal': 'HOLD',
                'confidence_score': 0.5,
                'k_level_used': 0,
                'reasoning_explanation': 'No agent outputs available'
            }
        
        # Simply take first agent's output
        first_agent_output = next(iter(agent_outputs.values()))
        
        return {
            'meta_signal': first_agent_output.get('signal', 'HOLD'),
            'confidence_score': first_agent_output.get('confidence', 0.5),
            'k_level_used': 0,
            'reasoning_explanation': 'K=0 naive analysis using first agent output'
        }
    
    async def _fallback_analysis(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Simple fallback analysis for error recovery"""
        return {
            'meta_signal': 'HOLD',
            'confidence_score': 0.5,
            'k_level_used': 0,
            'reasoning_explanation': 'Fallback analysis due to processing error',
            'status': 'fallback',
            'error_type': 'processing_timeout'
        }
    
    async def analyze_with_fallback(self, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        """Analysis with comprehensive fallback handling"""
        try:
            return await self.analyze_with_circuit_breaker(agent_outputs)
        except Exception as e:
            logger.warning(f"Primary analysis failed: {e}, using fallback")
            return await self._fallback_analysis(agent_outputs)
    
    async def full_meta_cognitive_analysis(self, agent_outputs: Dict[str, Any],
                                         market_conditions: Dict[str, Any] = None,
                                         max_k_level: int = None,
                                         timeout: float = None,
                                         correlation_id: str = None) -> Dict[str, Any]:
        """Complete production-grade meta-cognitive analysis"""
        if not self.is_initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")
        
        # Rate limiting check
        if not await self.rate_limiter.check_rate_limit():
            raise Exception("Rate limit exceeded")
        
        # Generate correlation ID if not provided
        if not correlation_id:
            correlation_id = f"meta_analysis_{int(time.time() * 1000)}"
        
        # Determine effective K-level
        effective_max_k = min(max_k_level or self.max_k_level, self.max_k_level)
        
        async with self.performance_tracking('full_analysis') as tracking_id:
            try:
                # Perform analysis with all protections
                result = await self.analyze_with_circuit_breaker(
                    agent_outputs, 
                    market_conditions or {},
                    correlation_id
                )
                
                # Add operational metadata
                result.update({
                    'rate_limit_status': self.rate_limiter.get_rate_limit_status(),
                    'circuit_breaker_status': self.circuit_breaker.get_state(),
                    'memory_status': await self._check_memory_pressure(),
                    'tracking_id': tracking_id
                })
                
                # Record execution in history
                self.execution_history.append({
                    'timestamp': datetime.now(timezone.utc),
                    'correlation_id': correlation_id,
                    'agent_count': len(agent_outputs),
                    'k_level': result.get('k_level_used', 0),
                    'status': 'success'
                })
                
                return result
                
            except Exception as e:
                # Comprehensive error handling
                error_result = {
                    'meta_signal': 'HOLD',
                    'confidence_score': 0.5,
                    'k_level_used': 1,
                    'status': 'error',
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'correlation_id': correlation_id,
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'agent_count': len(agent_outputs)
                }
                
                return error_result
    
    async def get_health_status(self) -> Dict[str, Any]:
        """Comprehensive health check"""
        current_time = datetime.now(timezone.utc)
        uptime = (current_time - self.start_time).total_seconds()
        
        # Component health
        components = {
            'k_level_engine': 'healthy' if self.is_initialized else 'unhealthy',
            'depth_controller': 'healthy' if self.is_initialized else 'unhealthy',
            'performance_monitor': 'healthy' if self.performance_monitor else 'disabled',
            'circuit_breaker': self.circuit_breaker.get_state()['state'] if self.circuit_breaker else 'disabled',
            'rate_limiter': 'healthy' if self.rate_limiter else 'disabled',
            'security_validator': 'healthy' if self.security_validator else 'disabled'
        }
        
        # Performance metrics
        recent_executions = [
            ex for ex in self.execution_history 
            if (current_time - ex['timestamp']).total_seconds() < 300  # Last 5 minutes
        ]
        
        success_rate = (
            len([ex for ex in recent_executions if ex['status'] == 'success']) / 
            len(recent_executions) if recent_executions else 1.0
        )
        
        avg_response_time = np.mean([
            ex.get('duration', 0.1) for ex in recent_executions
        ]) if recent_executions else 0.1
        
        error_rate = len(self.error_history) / max(len(self.execution_history), 1)
        
        # Overall health determination
        overall_health = 'healthy'
        if not self.is_initialized or success_rate < 0.95 or error_rate > 0.1:
            overall_health = 'degraded'
        if success_rate < 0.8 or error_rate > 0.2:
            overall_health = 'unhealthy'
        
        return {
            'status': overall_health,
            'timestamp': current_time.isoformat(),
            'version': self.version,
            'uptime_seconds': uptime,
            'components': components,
            'performance': {
                'success_rate': success_rate,
                'error_rate': error_rate,
                'average_response_time_ms': avg_response_time * 1000,
                'recent_executions_count': len(recent_executions)
            },
            'metrics': {
                'total_executions': len(self.execution_history),
                'total_errors': len(self.error_history),
                'memory_usage_mb': psutil.Process().memory_info().rss / 1024 / 1024
            }
        }
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get detailed performance metrics"""
        if self.performance_monitor:
            return await self.performance_monitor.generate_performance_report()
        
        # Fallback metrics from internal tracking
        recent_executions = list(self.execution_history)[-100:]  # Last 100
        
        return {
            'total_executions': len(self.execution_history),
            'successful_executions': len([ex for ex in recent_executions if ex['status'] == 'success']),
            'failed_executions': len([ex for ex in recent_executions if ex['status'] != 'success']),
            'success_rate': len([ex for ex in recent_executions if ex['status'] == 'success']) / max(len(recent_executions), 1),
            'latest_execution_time': recent_executions[-1].get('duration', 0) if recent_executions else 0,
            'memory_usage': psutil.Process().memory_info().rss / 1024 / 1024,  # MB
            'cpu_usage': psutil.cpu_percent()
        }
    
    async def get_prometheus_metrics(self) -> str:
        """Get Prometheus metrics in text format"""
        return generate_latest().decode('utf-8')
    
    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get active performance alerts"""
        if self.performance_monitor:
            alerts = await self.performance_monitor.check_performance_alerts()
            return [alert.__dict__ for alert in alerts]
        
        return []
    
    async def check_alert_conditions(self) -> List[Dict[str, Any]]:
        """Check for alert conditions"""
        alerts = []
        
        # Check recent performance
        recent_errors = [
            err for err in self.error_history
            if (datetime.now(timezone.utc) - err['timestamp']).total_seconds() < 300
        ]
        
        if len(recent_errors) > 5:
            alerts.append({
                'alert_type': 'high_error_rate',
                'severity': 'warning',
                'message': f'High error rate: {len(recent_errors)} errors in last 5 minutes',
                'threshold': 5,
                'current_value': len(recent_errors)
            })
        
        # Check memory usage
        memory_percent = psutil.virtual_memory().percent
        if memory_percent > 85:
            alerts.append({
                'alert_type': 'high_memory_usage',
                'severity': 'critical' if memory_percent > 95 else 'warning',
                'message': f'High memory usage: {memory_percent:.1f}%',
                'threshold': 85,
                'current_value': memory_percent
            })
        
        return alerts
    
    async def graceful_shutdown(self) -> Dict[str, Any]:
        """Perform graceful shutdown"""
        logger.info("Starting graceful shutdown")
        
        shutdown_start = time.time()
        
        try:
            # Stop accepting new requests
            self.health_status = "shutting_down"
            
            # Wait for active operations to complete (with timeout)
            active_count = self.metrics['active_connections']._value._value
            timeout = 30  # 30 second timeout
            
            while active_count > 0 and (time.time() - shutdown_start) < timeout:
                await asyncio.sleep(0.1)
                active_count = self.metrics['active_connections']._value._value
            
            # Force cleanup after timeout
            if active_count > 0:
                logger.warning(f"Forced shutdown with {active_count} active connections")
            
            # Cleanup resources
            if self.performance_monitor:
                await self.performance_monitor.stop_monitoring()
            
            # Clear caches and force garbage collection
            self.execution_history.clear()
            self.error_history.clear()
            gc.collect()
            
            shutdown_time = time.time() - shutdown_start
            
            logger.info(f"Graceful shutdown completed in {shutdown_time:.2f}s")
            
            return {
                'status': 'shutdown_complete',
                'shutdown_time': shutdown_time,
                'forced_connections': max(0, active_count)
            }
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            return {
                'status': 'shutdown_error',
                'error': str(e),
                'shutdown_time': time.time() - shutdown_start
            }
    
    async def generate_signal(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Main signal generation method for BaseAgent compatibility"""
        agent_outputs = market_data.get('agent_outputs', {})
        market_conditions = market_data.get('market_conditions', {})
        
        return await self.full_meta_cognitive_analysis(agent_outputs, market_conditions)


# For backward compatibility
MetaCognitiveAgent = ProductionMetaCognitiveAgent 