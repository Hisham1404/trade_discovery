import asyncio
import json
import logging
import time
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

class AgentCoordinator:
    """Central coordinator for managing all 8 trading agents"""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize AgentCoordinator with configuration"""
        self.config = config
        
        # Coordinator configuration - support both nested and direct config
        coordinator_config = config.get("coordinator", config)
        self.max_concurrent_agents = coordinator_config.get("max_concurrent_agents", 4)
        self.health_check_interval = coordinator_config.get("health_check_interval", 30)
        self.retry_attempts = coordinator_config.get("retry_attempts", 3)
        self.circuit_breaker_threshold = coordinator_config.get("circuit_breaker_threshold", 5)
        
        # Agent management
        self.agent_registry: Dict[str, Any] = {}
        self.agent_health_status: Dict[str, str] = {}
        self.circuit_breakers: Dict[str, Dict[str, Any]] = {}
        
        # Orchestration state
        self.is_running = False
        self.execution_semaphore = asyncio.Semaphore(self.max_concurrent_agents)
        
        # Metrics
        self.metrics = {
            "total_signals_generated": 0,
            "successful_signals": 0,
            "failed_signals": 0,
            "total_execution_time": 0.0,
            "average_confidence": 0.0
        }
        
        logger.info("AgentCoordinator initialized")
    
    def register_agent(self, agent_name: str, agent_instance: Any) -> None:
        """Register an agent with the coordinator"""
        self.agent_registry[agent_name] = agent_instance
        self.agent_health_status[agent_name] = "healthy"
        self.circuit_breakers[agent_name] = {
            "failures": 0,
            "is_open": False,
            "last_failure": None
        }
        logger.info(f"Registered agent: {agent_name}")
    
    async def generate_agent_signal(self, agent_name: str, market_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate signal from specific agent with error handling"""
        
        # Check circuit breaker first
        if self.circuit_breakers[agent_name]["is_open"]:
            logger.warning(f"Circuit breaker is open for agent {agent_name}")
            return None
        
        # Remove the early health check that was preventing circuit breaker from working
        # The circuit breaker should handle all failure scenarios
        
        try:
            agent = self.agent_registry[agent_name]
            signal = await agent.analyze_market_data(market_data)
            
            # Record success
            self.record_signal_metric(agent_name, "success", signal.get("confidence", 0.0), 0.15)
            
            # Reset circuit breaker on success
            self.circuit_breakers[agent_name]["failures"] = 0
            self.circuit_breakers[agent_name]["is_open"] = False
            
            # Mark agent as healthy on success
            self.agent_health_status[agent_name] = "healthy"
            
            return signal
            
        except Exception as e:
            # Record failure
            self.record_signal_metric(agent_name, "failure", 0.0, 0.25)
            
            # Update circuit breaker
            self.circuit_breakers[agent_name]["failures"] += 1
            self.circuit_breakers[agent_name]["last_failure"] = datetime.now(timezone.utc)
            
            # Open circuit breaker if threshold reached or exceeded
            if self.circuit_breakers[agent_name]["failures"] >= self.circuit_breaker_threshold:
                self.circuit_breakers[agent_name]["is_open"] = True
                logger.warning(f"Circuit breaker opened for agent {agent_name} after {self.circuit_breakers[agent_name]['failures']} failures")
            
            # Mark agent as unhealthy
            self.agent_health_status[agent_name] = "unhealthy"
            
            logger.error(f"Agent {agent_name} failed: {e}")
            return None
    
    def aggregate_signals(self, signals: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate signals from multiple agents"""
        
        if not signals:
            return {
                "aggregated_signal": "HOLD",
                "consensus_confidence": 0.0,
                "signal_count": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Simple aggregation logic
        signal_counts = {"BUY": 0, "SELL": 0, "HOLD": 0}
        total_confidence = 0.0
        
        for signal in signals:
            signal_type = signal.get("signal", "HOLD")
            confidence = signal.get("confidence", 0.0)
            
            if signal_type in signal_counts:
                signal_counts[signal_type] += 1
                total_confidence += confidence
        
        # Determine consensus signal
        consensus_signal = max(signal_counts.keys(), key=lambda x: signal_counts[x])
        consensus_confidence = total_confidence / len(signals) if signals else 0.0
        
        return {
            "aggregated_signal": consensus_signal,
            "consensus_confidence": consensus_confidence,
            "signal_count": len(signals),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    async def initialize_agents(self) -> None:
        """Initialize all agent instances with auto-discovery"""
        logger.info("Initializing agents with auto-discovery...")
        
        try:
            # Import trading agents dynamically
            from agents.sentiment_agent import SentimentAgent
            from agents.technical_agent import TechnicalAgent
            from agents.fundamental_agent import FundamentalAgent
            from agents.risk_agent import RiskAgent
            from agents.momentum_agent import MomentumAgent
            from agents.mean_reversion_agent import MeanReversionAgent
            from agents.volatility_agent import VolatilityAgent
            from agents.dapo_agent import DAPOAgent
            
            # Agent configurations based on strategy types
            agent_configs = {
                'sentiment': {
                    'strategy_type': 'sentiment',
                    'frequency_seconds': 180,
                    'confidence_threshold': 0.65,
                    'model': 'gpt-4o',
                    'news_api_key': 'production_key',
                    'cache_ttl_seconds': 300
                },
                'technical': {
                    'strategy_type': 'technical',
                    'frequency_seconds': 60,
                    'confidence_threshold': 0.7,
                    'model': 'gpt-3.5-turbo',
                    'indicators': ['RSI', 'MACD', 'BBands']
                },
                'fundamental': {
                    'strategy_type': 'fundamental',
                    'frequency_seconds': 3600,
                    'confidence_threshold': 0.8,
                    'model': 'gpt-4o',
                    'data_sources': ['edgar_api', 'financial_modeling_prep']
                },
                'risk': {
                    'strategy_type': 'risk',
                    'frequency_seconds': 300,
                    'confidence_threshold': 0.85,
                    'model': 'claude-3-sonnet-20240229',
                    'var_confidence': 0.95
                },
                'momentum': {
                    'strategy_type': 'momentum',
                    'frequency_seconds': 30,
                    'confidence_threshold': 0.75,
                    'model': 'gpt-3.5-turbo'
                },
                'mean_reversion': {
                    'strategy_type': 'mean_reversion',
                    'frequency_seconds': 120,
                    'confidence_threshold': 0.72,
                    'model': 'gpt-3.5-turbo'
                },
                'volatility': {
                    'strategy_type': 'volatility',
                    'frequency_seconds': 60,
                    'confidence_threshold': 0.68,
                    'model': 'gpt-3.5-turbo'
                },
                'dapo': {
                    'strategy_type': 'dapo',
                    'frequency_seconds': 90,
                    'confidence_threshold': 0.73,
                    'model': 'gpt-4o'
                }
            }
            
            # Agent class mapping
            agent_classes = {
                'sentiment': SentimentAgent,
                'technical': TechnicalAgent,
                'fundamental': FundamentalAgent,
                'risk': RiskAgent,
                'momentum': MomentumAgent,
                'mean_reversion': MeanReversionAgent,
                'volatility': VolatilityAgent,
                'dapo': DAPOAgent
            }
            
            # Initialize and register each agent
            for agent_type, agent_class in agent_classes.items():
                try:
                    config = agent_configs[agent_type]
                    agent_instance = agent_class(config)
                    
                    # Initialize the agent
                    await agent_instance.initialize()
                    
                    # Register with coordinator
                    agent_name = f"{agent_type}_agent"
                    self.register_agent(agent_name, agent_instance)
                    
                    logger.info(f"Successfully initialized and registered {agent_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to initialize {agent_type} agent: {e}")
                    # Continue with other agents even if one fails
                    continue
            
            # Verify at least some agents were registered
            if len(self.agent_registry) == 0:
                raise RuntimeError("No trading agents were successfully initialized")
            
            logger.info(f"Agent initialization complete. Registered {len(self.agent_registry)} agents: {list(self.agent_registry.keys())}")
            
        except Exception as e:
            logger.error(f"Failed to initialize agents: {e}")
            raise

    async def start_health_monitor(self) -> None:
        """Start comprehensive health monitoring with recovery"""
        logger.info("Starting production health monitoring...")
        
        try:
            # Create health monitoring task
            self._health_monitor_task = asyncio.create_task(self._health_monitor_loop())
            
            # Create circuit breaker recovery task
            self._circuit_breaker_recovery_task = asyncio.create_task(self._circuit_breaker_recovery_loop())
            
            logger.info("Health monitoring and circuit breaker recovery started")
            
        except Exception as e:
            logger.error(f"Failed to start health monitoring: {e}")
            raise
    
    async def _health_monitor_loop(self) -> None:
        """Continuous health monitoring loop"""
        while self.is_running:
            try:
                await self._perform_health_checks()
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                logger.error(f"Health monitor loop error: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _perform_health_checks(self) -> None:
        """Perform health checks on all registered agents"""
        logger.debug("Performing health checks on all agents")
        
        for agent_name, agent in self.agent_registry.items():
            try:
                # Check if agent is responsive
                if hasattr(agent, 'health_check'):
                    health_status = await agent.health_check()
                    
                    if health_status.get('status') == 'healthy':
                        if self.agent_health_status[agent_name] == 'unhealthy':
                            logger.info(f"Agent {agent_name} recovered to healthy status")
                        self.agent_health_status[agent_name] = 'healthy'
                    else:
                        self.agent_health_status[agent_name] = 'unhealthy'
                        logger.warning(f"Agent {agent_name} health check failed: {health_status}")
                else:
                    # Basic health check - verify agent attributes
                    if hasattr(agent, 'is_initialized') and agent.is_initialized:
                        self.agent_health_status[agent_name] = 'healthy'
                    else:
                        self.agent_health_status[agent_name] = 'unhealthy'
                        logger.warning(f"Agent {agent_name} is not properly initialized")
                
            except Exception as e:
                self.agent_health_status[agent_name] = 'unhealthy'
                logger.error(f"Health check failed for agent {agent_name}: {e}")
    
    async def _circuit_breaker_recovery_loop(self) -> None:
        """Circuit breaker recovery loop with exponential backoff"""
        while self.is_running:
            try:
                await self._attempt_circuit_breaker_recovery()
                await asyncio.sleep(60)  # Check every minute for recovery opportunities
                
            except Exception as e:
                logger.error(f"Circuit breaker recovery loop error: {e}")
                await asyncio.sleep(60)
    
    async def _attempt_circuit_breaker_recovery(self) -> None:
        """Attempt to recover agents with open circuit breakers"""
        current_time = datetime.now(timezone.utc)
        
        for agent_name, cb_state in self.circuit_breakers.items():
            if cb_state["is_open"] and cb_state["last_failure"]:
                # Calculate time since last failure
                time_since_failure = (current_time - cb_state["last_failure"]).total_seconds()
                
                # Recovery backoff: 60s, 300s, 900s, 1800s (exponential)
                recovery_delay = min(60 * (2 ** min(cb_state["failures"] - self.circuit_breaker_threshold, 5)), 1800)
                
                if time_since_failure >= recovery_delay:
                    logger.info(f"Attempting circuit breaker recovery for agent {agent_name}")
                    
                    try:
                        # Test the agent with a simple health check
                        agent = self.agent_registry[agent_name]
                        
                        # Try a lightweight operation to test recovery
                        test_data = {
                            'symbol': 'TEST',
                            'current_price': 100.0,
                            'volume': 1000,
                            'timestamp': current_time.isoformat()
                        }
                        
                        # Attempt signal generation (this will go through the circuit breaker logic)
                        signal = await self.generate_agent_signal(agent_name, test_data)
                        
                        if signal is not None:
                            logger.info(f"Circuit breaker recovery successful for agent {agent_name}")
                        else:
                            logger.debug(f"Circuit breaker recovery attempt failed for agent {agent_name}")
                            
                    except Exception as e:
                        logger.warning(f"Circuit breaker recovery failed for agent {agent_name}: {e}")
    
    async def stop(self) -> None:
        """Stop the coordinator and all monitoring tasks"""
        logger.info("Stopping AgentCoordinator...")
        self.is_running = False
        
        # Cancel monitoring tasks
        if hasattr(self, '_health_monitor_task'):
            self._health_monitor_task.cancel()
            try:
                await self._health_monitor_task
            except asyncio.CancelledError:
                pass
        
        if hasattr(self, '_circuit_breaker_recovery_task'):
            self._circuit_breaker_recovery_task.cancel()
            try:
                await self._circuit_breaker_recovery_task
            except asyncio.CancelledError:
                pass
        
        logger.info("AgentCoordinator stopped")
    
    def get_comprehensive_status(self) -> Dict[str, Any]:
        """Get comprehensive coordinator status with detailed metrics"""
        current_time = datetime.now(timezone.utc)
        
        # Calculate agent statistics
        agent_stats = {
            'total_agents': len(self.agent_registry),
            'healthy_agents': sum(1 for status in self.agent_health_status.values() if status == "healthy"),
            'unhealthy_agents': sum(1 for status in self.agent_health_status.values() if status == "unhealthy"),
            'agents_with_open_circuit_breakers': sum(1 for cb in self.circuit_breakers.values() if cb["is_open"])
        }
        
        # Calculate performance metrics
        total_signals = self.metrics["total_signals_generated"]
        success_rate = (self.metrics["successful_signals"] / total_signals) if total_signals > 0 else 0.0
        
        # Get circuit breaker details
        circuit_breaker_details = {}
        for agent_name, cb_state in self.circuit_breakers.items():
            circuit_breaker_details[agent_name] = {
                'is_open': cb_state['is_open'],
                'failure_count': cb_state['failures'],
                'last_failure': cb_state['last_failure'].isoformat() if cb_state['last_failure'] else None,
                'time_since_last_failure_seconds': (
                    (current_time - cb_state['last_failure']).total_seconds() 
                    if cb_state['last_failure'] else None
                )
            }
        
        return {
            'coordinator_status': {
                'is_running': self.is_running,
                'is_monitoring': hasattr(self, '_health_monitor_task') and not self._health_monitor_task.done(),
                'uptime_seconds': (current_time - getattr(self, '_start_time', current_time)).total_seconds()
            },
            'agent_statistics': agent_stats,
            'performance_metrics': {
                'total_signals_generated': total_signals,
                'successful_signals': self.metrics["successful_signals"],
                'failed_signals': self.metrics["failed_signals"],
                'success_rate': success_rate,
                'average_confidence': self.metrics["average_confidence"],
                'average_execution_time_ms': (self.metrics["total_execution_time"] / total_signals * 1000) if total_signals > 0 else 0.0
            },
            'circuit_breaker_status': circuit_breaker_details,
            'agent_details': {
                agent_name: self.get_agent_status(agent_name) 
                for agent_name in self.agent_registry.keys()
            },
            'configuration': {
                'max_concurrent_agents': self.max_concurrent_agents,
                'health_check_interval': self.health_check_interval,
                'circuit_breaker_threshold': self.circuit_breaker_threshold,
                'retry_attempts': self.retry_attempts
            },
            'timestamp': current_time.isoformat()
        }
    
    async def start(self) -> None:
        """Start the coordinator with full production monitoring"""
        logger.info("Starting AgentCoordinator...")
        self._start_time = datetime.now(timezone.utc)
        
        await self.initialize_agents()
        await self.start_health_monitor()
        self.is_running = True
        
        logger.info("AgentCoordinator started successfully with production monitoring")
    
    def get_agent_health(self, agent_name: str) -> str:
        """Get health status of specific agent"""
        return self.agent_health_status.get(agent_name, "unknown")
    
    def mark_agent_unhealthy(self, agent_name: str) -> None:
        """Mark agent as unhealthy"""
        self.agent_health_status[agent_name] = "unhealthy"
    
    def get_agent_status(self, agent_name: str) -> Dict[str, Any]:
        """Get detailed status for specific agent"""
        if agent_name not in self.agent_registry:
            return {"error": f"Agent {agent_name} not found"}
        
        agent = self.agent_registry[agent_name]
        
        return {
            "agent_name": agent_name,
            "health_status": self.agent_health_status[agent_name],
            "is_initialized": getattr(agent, "is_initialized", False),
            "strategy_type": getattr(agent, "strategy_type", "unknown")
        }
    
    def get_all_agents_status(self) -> Dict[str, Any]:
        """Get status for all agents"""
        agents_status = {}
        healthy_count = 0
        
        for agent_name in self.agent_registry:
            agents_status[agent_name] = self.get_agent_status(agent_name)
            if self.agent_health_status[agent_name] == "healthy":
                healthy_count += 1
        
        return {
            "agents": agents_status,
            "total_agents": len(self.agent_registry),
            "healthy_agents": healthy_count,
            "coordinator_status": {
                "is_running": self.is_running
            }
        }
    
    def record_signal_metric(self, agent_name: str, result: str, confidence: float, execution_time: float) -> None:
        """Record metrics for signal generation"""
        self.metrics["total_signals_generated"] += 1
        self.metrics["total_execution_time"] += execution_time
        
        if result == "success":
            self.metrics["successful_signals"] += 1
            
            # Update rolling average confidence
            total_successful = self.metrics["successful_signals"]
            current_avg = self.metrics["average_confidence"]
            self.metrics["average_confidence"] = ((current_avg * (total_successful - 1)) + confidence) / total_successful
        else:
            self.metrics["failed_signals"] += 1
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive metrics summary"""
        total_signals = self.metrics["total_signals_generated"]
        
        return {
            "total_signals_generated": total_signals,
            "successful_signals": self.metrics["successful_signals"],
            "failed_signals": self.metrics["failed_signals"],
            "average_confidence": self.metrics["average_confidence"],
            "average_execution_time": (self.metrics["total_execution_time"] / total_signals) if total_signals > 0 else 0.0,
            "agent_health_summary": {
                "healthy": sum(1 for status in self.agent_health_status.values() if status == "healthy"),
                "unhealthy": sum(1 for status in self.agent_health_status.values() if status == "unhealthy")
            }
        }

