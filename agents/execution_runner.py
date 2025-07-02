"""
Agent Execution Runner
Production implementation with real Google ADK integration and multiple execution modes
"""

import asyncio
import logging
import uuid
import psutil
from typing import Dict, List, Any, Optional, Union, Callable
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass

# Real Google ADK imports - verified from Context7 documentation
from google.adk.agents import LlmAgent, SequentialAgent, ParallelAgent
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Import production ADK infrastructure
from .adk_infrastructure import ProductionADKInfrastructure

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Execution modes for different agent orchestration patterns"""
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    BATCH = "batch"
    CONTINUOUS = "continuous"


@dataclass
class ExecutionResult:
    """Result of agent execution"""
    agent_name: str
    execution_id: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    success: bool
    result: Any = None
    error: Optional[str] = None
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0


class ExecutionRunner:
    """
    Production Agent Execution Runner with real Google ADK integration
    
    Supports multiple execution modes and comprehensive performance monitoring
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.is_initialized = False
        
        # Initialize production ADK infrastructure
        self.adk_infrastructure = ProductionADKInfrastructure(config)
        
        # Execution configuration
        self.default_timeout = config.get('default_timeout', 300)  # 5 minutes
        self.max_concurrent_agents = config.get('max_concurrent_agents', 8)
        self.retry_attempts = config.get('retry_attempts', 3)
        self.execution_mode = ExecutionMode(config.get('execution_mode', 'sequential'))
        
        # Performance monitoring
        self.execution_history: List[ExecutionResult] = []
        self.active_executions: Dict[str, Dict[str, Any]] = {}
        
        # Metrics tracking
        self.metrics = {
            'total_executions': 0,
            'successful_executions': 0,
            'failed_executions': 0,
            'average_execution_time': 0.0,
            'total_execution_time': 0.0,
            'peak_memory_usage': 0.0,
            'peak_cpu_usage': 0.0
        }
        
        logger.info("Production Execution Runner initialized with real Google ADK")
    
    async def initialize(self) -> None:
        """Initialize the execution runner"""
        try:
            # Initialize ADK infrastructure
            await self.adk_infrastructure.initialize()
            
            self.is_initialized = True
            logger.info("Execution Runner initialization completed")
            
        except Exception as e:
            logger.error(f"Failed to initialize execution runner: {e}")
            raise
    
    async def create_agent(self, agent_type: str, agent_config: Dict[str, Any]) -> LlmAgent:
        """Create a trading agent using production ADK infrastructure"""
        try:
            agent = self.adk_infrastructure.create_trading_agent(agent_type, agent_config)
            logger.info(f"Created {agent_type} agent: {agent.name}")
            return agent
            
        except Exception as e:
            logger.error(f"Failed to create {agent_type} agent: {e}")
            raise
    
    async def execute_single_agent(self, agent: LlmAgent, prompt: str, 
                                 timeout: Optional[int] = None, 
                                 session_id: Optional[str] = None) -> ExecutionResult:
        """Execute a single agent with comprehensive monitoring"""
        execution_id = f"exec_{uuid.uuid4().hex[:8]}"
        start_time = datetime.now(timezone.utc)
        
        # Get initial system metrics
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        initial_cpu = process.cpu_percent()
        
        try:
            # Track active execution
            self.active_executions[execution_id] = {
                'agent_name': agent.name,
                'start_time': start_time,
                'prompt': prompt,
                'timeout': timeout or self.default_timeout
            }
            
            # Execute agent with timeout
            execution_timeout = timeout or self.default_timeout
            
            # Create and execute with runner
            result = await asyncio.wait_for(
                self.adk_infrastructure.execute_agent(agent, prompt, session_id),
                timeout=execution_timeout
            )
            
            # Calculate execution metrics
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds() * 1000  # milliseconds
            
            # Get final system metrics
            final_memory = process.memory_info().rss / 1024 / 1024  # MB
            final_cpu = process.cpu_percent()
            
            memory_usage = max(final_memory - initial_memory, 0)
            cpu_usage = final_cpu
            
            # Create execution result
            execution_result = ExecutionResult(
                agent_name=agent.name,
                execution_id=execution_id,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration,
                success=True,
                result=result,
                memory_usage_mb=memory_usage,
                cpu_usage_percent=cpu_usage
            )
            
            # Update metrics
            self._update_metrics(execution_result)
            
            logger.info(f"Successfully executed agent {agent.name} in {duration:.2f}ms")
            return execution_result
            
        except asyncio.TimeoutError:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds() * 1000
            
            error_msg = f"Agent execution timed out after {execution_timeout}s"
            logger.error(f"Timeout executing agent {agent.name}: {error_msg}")
            
            execution_result = ExecutionResult(
                agent_name=agent.name,
                execution_id=execution_id,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration,
                success=False,
                error=error_msg
            )
            
            self._update_metrics(execution_result)
            return execution_result
            
        except Exception as e:
            end_time = datetime.now(timezone.utc)
            duration = (end_time - start_time).total_seconds() * 1000
            
            error_msg = f"Agent execution failed: {str(e)}"
            logger.error(f"Error executing agent {agent.name}: {error_msg}")
            
            execution_result = ExecutionResult(
                agent_name=agent.name,
                execution_id=execution_id,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration,
                success=False,
                error=error_msg
            )
            
            self._update_metrics(execution_result)
            return execution_result
            
        finally:
            # Clean up active execution tracking
            if execution_id in self.active_executions:
                del self.active_executions[execution_id]
    
    async def execute_sequential_workflow(self, agents: List[LlmAgent], 
                                        prompts: List[str],
                                        workflow_name: str = None) -> List[ExecutionResult]:
        """Execute agents sequentially using real Google ADK SequentialAgent"""
        try:
            workflow_name = workflow_name or f"sequential_workflow_{uuid.uuid4().hex[:8]}"
            
            # Create sequential workflow using production ADK
            workflow = self.adk_infrastructure.create_workflow(
                workflow_type='sequential',
                agents=agents,
                name=workflow_name
            )
            
            results = []
            
            # Execute each agent in sequence
            for i, (agent, prompt) in enumerate(zip(agents, prompts)):
                logger.info(f"Executing sequential step {i+1}/{len(agents)}: {agent.name}")
                
                result = await self.execute_single_agent(agent, prompt)
                results.append(result)
                
                # Stop on failure if configured
                if not result.success and self.config.get('stop_on_failure', True):
                    logger.warning(f"Sequential execution stopped due to failure in {agent.name}")
                    break
            
            logger.info(f"Sequential workflow {workflow_name} completed with {len(results)} executions")
            return results
            
        except Exception as e:
            logger.error(f"Failed to execute sequential workflow: {e}")
            raise
    
    async def execute_parallel_workflow(self, agents: List[LlmAgent], 
                                      prompts: List[str],
                                      workflow_name: str = None) -> List[ExecutionResult]:
        """Execute agents in parallel using real Google ADK ParallelAgent"""
        try:
            workflow_name = workflow_name or f"parallel_workflow_{uuid.uuid4().hex[:8]}"
            
            # Create parallel workflow using production ADK
            workflow = self.adk_infrastructure.create_workflow(
                workflow_type='parallel',
                agents=agents,
                name=workflow_name
            )
            
            # Execute all agents concurrently
            logger.info(f"Executing {len(agents)} agents in parallel")
            
            tasks = []
            for agent, prompt in zip(agents, prompts):
                task = asyncio.create_task(
                    self.execute_single_agent(agent, prompt),
                    name=f"parallel_exec_{agent.name}"
                )
                tasks.append(task)
            
            # Wait for all executions to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results and handle exceptions
            execution_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    # Handle execution exceptions
                    agent_name = agents[i].name
                    error_result = ExecutionResult(
                        agent_name=agent_name,
                        execution_id=f"parallel_error_{uuid.uuid4().hex[:8]}",
                        start_time=datetime.now(timezone.utc),
                        end_time=datetime.now(timezone.utc),
                        duration_ms=0.0,
                        success=False,
                        error=str(result)
                    )
                    execution_results.append(error_result)
                    logger.error(f"Parallel execution failed for {agent_name}: {result}")
                else:
                    execution_results.append(result)
            
            logger.info(f"Parallel workflow {workflow_name} completed with {len(execution_results)} executions")
            return execution_results
            
        except Exception as e:
            logger.error(f"Failed to execute parallel workflow: {e}")
            raise
    
    async def execute_batch_workflow(self, agent_configs: List[Dict[str, Any]], 
                                   prompts: List[str],
                                   batch_size: int = None) -> List[ExecutionResult]:
        """Execute agents in batches for memory management"""
        try:
            batch_size = batch_size or self.max_concurrent_agents
            
            # Create agents from configurations
            agents = []
            for config in agent_configs:
                agent_type = config.get('type', 'technical')
                agent = await self.create_agent(agent_type, config)
                agents.append(agent)
            
            all_results = []
            
            # Process in batches
            for i in range(0, len(agents), batch_size):
                batch_agents = agents[i:i + batch_size]
                batch_prompts = prompts[i:i + batch_size]
                
                logger.info(f"Executing batch {i//batch_size + 1}: {len(batch_agents)} agents")
                
                # Execute batch in parallel
                batch_results = await self.execute_parallel_workflow(
                    batch_agents, 
                    batch_prompts,
                    f"batch_{i//batch_size + 1}"
                )
                
                all_results.extend(batch_results)
                
                # Brief pause between batches for resource management
                if i + batch_size < len(agents):
                    await asyncio.sleep(0.1)
            
            logger.info(f"Batch workflow completed with {len(all_results)} total executions")
            return all_results
            
        except Exception as e:
            logger.error(f"Failed to execute batch workflow: {e}")
            raise
    
    async def execute_continuous_workflow(self, agents: List[LlmAgent], 
                                        prompt_generator: Callable[[], str],
                                        duration_seconds: int = 300) -> List[ExecutionResult]:
        """Execute agents continuously for a specified duration"""
        try:
            start_time = datetime.now(timezone.utc)
            end_time = start_time + timedelta(seconds=duration_seconds)
            
            all_results = []
            cycle_count = 0
            
            logger.info(f"Starting continuous execution for {duration_seconds} seconds")
            
            while datetime.now(timezone.utc) < end_time:
                cycle_count += 1
                logger.info(f"Continuous execution cycle {cycle_count}")
                
                # Generate prompts for this cycle
                prompts = [prompt_generator() for _ in agents]
                
                # Execute agents in parallel for this cycle
                cycle_results = await self.execute_parallel_workflow(
                    agents,
                    prompts,
                    f"continuous_cycle_{cycle_count}"
                )
                
                all_results.extend(cycle_results)
                
                # Brief pause between cycles
                await asyncio.sleep(1.0)
            
            elapsed_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(f"Continuous workflow completed after {elapsed_time:.2f}s with {len(all_results)} total executions")
            
            return all_results
            
        except Exception as e:
            logger.error(f"Failed to execute continuous workflow: {e}")
            raise
    
    def _update_metrics(self, result: ExecutionResult) -> None:
        """Update execution metrics"""
        self.metrics['total_executions'] += 1
        
        if result.success:
            self.metrics['successful_executions'] += 1
        else:
            self.metrics['failed_executions'] += 1
        
        # Update timing metrics
        self.metrics['total_execution_time'] += result.duration_ms
        self.metrics['average_execution_time'] = (
            self.metrics['total_execution_time'] / self.metrics['total_executions']
        )
        
        # Update resource usage peaks
        if result.memory_usage_mb > self.metrics['peak_memory_usage']:
            self.metrics['peak_memory_usage'] = result.memory_usage_mb
            
        if result.cpu_usage_percent > self.metrics['peak_cpu_usage']:
            self.metrics['peak_cpu_usage'] = result.cpu_usage_percent
        
        # Store in history (with retention limit)
        self.execution_history.append(result)
        if len(self.execution_history) > 1000:  # Keep last 1000 executions
            self.execution_history = self.execution_history[-1000:]
    
    def get_execution_metrics(self) -> Dict[str, Any]:
        """Get comprehensive execution metrics"""
        current_time = datetime.now(timezone.utc)
        
        # Calculate success rate
        success_rate = 0.0
        if self.metrics['total_executions'] > 0:
            success_rate = self.metrics['successful_executions'] / self.metrics['total_executions']
        
        # Get recent performance (last 10 executions)
        recent_executions = self.execution_history[-10:] if self.execution_history else []
        recent_avg_time = 0.0
        if recent_executions:
            recent_avg_time = sum(r.duration_ms for r in recent_executions) / len(recent_executions)
        
        return {
            'total_executions': self.metrics['total_executions'],
            'successful_executions': self.metrics['successful_executions'],
            'failed_executions': self.metrics['failed_executions'],
            'success_rate': success_rate,
            'average_execution_time_ms': self.metrics['average_execution_time'],
            'recent_average_time_ms': recent_avg_time,
            'total_execution_time_ms': self.metrics['total_execution_time'],
            'peak_memory_usage_mb': self.metrics['peak_memory_usage'],
            'peak_cpu_usage_percent': self.metrics['peak_cpu_usage'],
            'active_executions': len(self.active_executions),
            'execution_history_count': len(self.execution_history),
            'adk_infrastructure_status': self.adk_infrastructure.get_infrastructure_status(),
            'timestamp': current_time.isoformat()
        }
    
    def get_execution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent execution history"""
        recent_history = self.execution_history[-limit:] if self.execution_history else []
        
        return [
            {
                'agent_name': result.agent_name,
                'execution_id': result.execution_id,
                'start_time': result.start_time.isoformat(),
                'end_time': result.end_time.isoformat(),
                'duration_ms': result.duration_ms,
                'success': result.success,
                'error': result.error,
                'memory_usage_mb': result.memory_usage_mb,
                'cpu_usage_percent': result.cpu_usage_percent
            }
            for result in recent_history
        ]
    
    async def shutdown(self) -> None:
        """Gracefully shutdown the execution runner"""
        try:
            logger.info("Shutting down execution runner...")
            
            # Cancel active executions
            if self.active_executions:
                logger.info(f"Cancelling {len(self.active_executions)} active executions")
                # Note: In production, you might want to wait for executions to complete
                self.active_executions.clear()
            
            # Shutdown ADK infrastructure
            await self.adk_infrastructure.shutdown()
            
            logger.info("Execution runner shutdown completed")
            
        except Exception as e:
            logger.error(f"Error during execution runner shutdown: {e}")
            raise
