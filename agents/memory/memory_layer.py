"""
Unified Memory Layer

This module provides a unified interface for all memory operations,
coordinating STM, LTM, and episodic memory for BaseAgent integration.
"""

import logging
import asyncio
import time
import uuid
from typing import Dict, List, Any, Optional, Union
import redis.asyncio as redis
from qdrant_client import AsyncQdrantClient

from .config import MemoryConfig, MemoryType
from .stm_manager import STMManager
from .ltm_manager import LTMManager
from .episodic_manager import EpisodicMemoryManager
from .cleanup_manager import MemoryCleanupManager

logger = logging.getLogger(__name__)


class MemoryLayer:
    """
    Unified memory layer that coordinates all memory types and provides
    automatic memory management for trading agents.
    
    Features:
    - Single interface for all memory operations
    - Automatic context building from all memory types
    - Memory lifecycle management
    - Background cleanup and maintenance
    - BaseAgent integration support
    """
    
    def __init__(
        self, 
        config: Optional[MemoryConfig] = None,
        redis_client: Optional[redis.Redis] = None,
        qdrant_client: Optional[AsyncQdrantClient] = None
    ):
        """
        Initialize unified memory layer.
        
        Args:
            config: Memory configuration (defaults to MemoryConfig())
            redis_client: Optional pre-configured Redis client
            qdrant_client: Optional pre-configured Qdrant client
        """
        self.config = config or MemoryConfig()
        self._initialized = False
        
        # Initialize individual memory managers
        self.stm_manager = STMManager(self.config, redis_client)
        self.ltm_manager = LTMManager(self.config, redis_client)
        self.episodic_manager = EpisodicMemoryManager(self.config, qdrant_client)
        
        # Initialize cleanup manager
        self.cleanup_manager = MemoryCleanupManager(
            self.config,
            self.stm_manager,
            self.ltm_manager,
            self.episodic_manager
        )
        
        # Background cleanup task
        self._cleanup_task = None
        
    async def initialize(self) -> None:
        """Initialize all memory components."""
        if self._initialized:
            return
            
        logger.info("Initializing unified memory layer")
        
        # Initialize all managers
        await self.stm_manager.initialize()
        await self.ltm_manager.initialize()
        await self.episodic_manager.initialize()
        await self.cleanup_manager.initialize()
        
        # Start background cleanup
        self._cleanup_task = asyncio.create_task(
            self.cleanup_manager.start_periodic_cleanup()
        )
        
        self._initialized = True
        logger.info("Memory layer initialization complete")
    
    async def build_agent_context(
        self, 
        agent_name: str, 
        current_market_conditions: Dict[str, Any],
        context_window_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Build comprehensive memory context for an agent.
        
        Args:
            agent_name: Name of the requesting agent
            current_market_conditions: Current market state for similarity search
            context_window_hours: Hours of recent data to include
            
        Returns:
            Dict[str, Any]: Comprehensive memory context
        """
        if not self._initialized:
            await self.initialize()
        
        context = {
            "agent": agent_name,
            "timestamp": time.time(),
            "current_market_conditions": current_market_conditions,
            "memory_context": {}
        }
        
        try:
            # Gather context from all memory types in parallel
            context_tasks = [
                self._get_stm_context(agent_name, context_window_hours),
                self._get_ltm_context(agent_name),
                self._get_episodic_context(current_market_conditions)
            ]
            
            stm_context, ltm_context, episodic_context = await asyncio.gather(
                *context_tasks, return_exceptions=True
            )
            
            # Process results
            context["memory_context"]["stm"] = stm_context if not isinstance(stm_context, Exception) else {"error": str(stm_context)}
            context["memory_context"]["ltm"] = ltm_context if not isinstance(ltm_context, Exception) else {"error": str(ltm_context)}
            context["memory_context"]["episodic"] = episodic_context if not isinstance(episodic_context, Exception) else {"error": str(episodic_context)}
            
            logger.debug(f"Built memory context for {agent_name}")
            
        except Exception as e:
            logger.error(f"Failed to build agent context for {agent_name}: {e}")
            context["memory_context"]["error"] = str(e)
        
        return context
    
    async def _get_stm_context(self, agent_name: str, hours: int) -> Dict[str, Any]:
        """Get STM context for agent."""
        try:
            # Get recent signals from this agent
            recent_signals = await self.stm_manager.get_recent_signals(agent_name, limit=20)
            
            # Get recent analysis results
            recent_analysis = await self.stm_manager.get_recent_analysis(agent_name, limit=10)
            
            # Get recent market data for all symbols this agent has analyzed
            symbols = set()
            for signal in recent_signals:
                if "symbol" in signal:
                    symbols.add(signal["symbol"])
            
            market_data = {}
            for symbol in symbols:
                data = await self.stm_manager.get_market_data(symbol)
                if data:
                    market_data[symbol] = data
            
            return {
                "recent_signals": recent_signals,
                "recent_analysis": recent_analysis,
                "market_data": market_data,
                "signal_count": len(recent_signals),
                "analysis_count": len(recent_analysis)
            }
            
        except Exception as e:
            logger.error(f"Failed to get STM context: {e}")
            return {"error": str(e)}
    
    async def _get_ltm_context(self, agent_name: str) -> Dict[str, Any]:
        """Get LTM context for agent."""
        try:
            # Get performance history
            performance_history = await self.ltm_manager.get_performance_history(agent_name, days=7)
            
            # Get performance statistics
            performance_stats = await self.ltm_manager.get_performance_statistics(agent_name, days=7)
            
            # Get similar patterns based on agent's specialty
            patterns = await self.ltm_manager.get_similar_patterns("*", min_success_rate=0.6, limit=10)
            
            # Get relevant market insights
            insights = await self.ltm_manager.get_market_insights(limit=5)
            
            return {
                "performance_history": performance_history,
                "performance_statistics": performance_stats,
                "relevant_patterns": patterns,
                "market_insights": insights,
                "history_days": 7
            }
            
        except Exception as e:
            logger.error(f"Failed to get LTM context: {e}")
            return {"error": str(e)}
    
    async def _get_episodic_context(self, market_conditions: Dict[str, Any]) -> Dict[str, Any]:
        """Get episodic memory context based on current market conditions."""
        try:
            # Search for similar scenarios
            similar_scenarios = await self.episodic_manager.search_similar_scenarios(
                market_conditions, 
                limit=5, 
                min_score=0.7
            )
            
            # Get recent scenarios for context
            recent_scenarios = await self.episodic_manager.get_recent_scenarios(hours=48, limit=10)
            
            return {
                "similar_scenarios": similar_scenarios,
                "recent_scenarios": recent_scenarios,
                "similarity_threshold": 0.7,
                "scenarios_found": len(similar_scenarios)
            }
            
        except Exception as e:
            logger.error(f"Failed to get episodic context: {e}")
            return {"error": str(e)}
    
    async def store_agent_analysis(
        self, 
        agent_name: str, 
        analysis_data: Dict[str, Any],
        create_scenario: bool = True
    ) -> bool:
        """
        Store agent analysis results across appropriate memory layers.
        
        Args:
            agent_name: Name of the agent
            analysis_data: Complete analysis including market conditions, signals, reasoning
            create_scenario: Whether to create an episodic scenario
            
        Returns:
            bool: True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            storage_tasks = []
            
            # Store in STM if it contains a signal
            if "signal" in analysis_data:
                storage_tasks.append(
                    self.stm_manager.store_signal(agent_name, analysis_data)
                )
            
            # Store analysis results in STM
            symbol = analysis_data.get("symbol", "unknown")
            storage_tasks.append(
                self.stm_manager.store_analysis_result(agent_name, symbol, analysis_data)
            )
            
            # Store performance data in LTM if confidence/accuracy is available
            if "confidence" in analysis_data or "accuracy" in analysis_data:
                performance_data = {
                    "accuracy": analysis_data.get("accuracy", analysis_data.get("confidence", 0)),
                    "total_signals": 1,
                    "successful_signals": 1 if analysis_data.get("accuracy", 0) > 0.5 else 0,
                    "symbol": symbol,
                    "analysis_type": analysis_data.get("analysis_type", "signal_generation")
                }
                storage_tasks.append(
                    self.ltm_manager.store_performance(agent_name, performance_data)
                )
            
            # Create episodic scenario if requested and sufficient data is available
            if create_scenario and "market_conditions" in analysis_data:
                scenario_id = f"{agent_name}_{symbol}_{int(time.time() * 1000)}"
                scenario_data = {
                    "agent": agent_name,
                    "symbol": symbol,
                    "market_conditions": analysis_data["market_conditions"],
                    "action_taken": {
                        "signal": analysis_data.get("signal", "HOLD"),
                        "confidence": analysis_data.get("confidence", 0),
                        "reasoning": analysis_data.get("reasoning", "")
                    },
                    "agent_analysis": analysis_data,
                    "timestamp": time.time()
                }
                
                storage_tasks.append(
                    self.episodic_manager.store_scenario(scenario_id, scenario_data)
                )
            
            # Execute all storage operations
            results = await asyncio.gather(*storage_tasks, return_exceptions=True)
            
            # Check if any failed
            failures = [r for r in results if isinstance(r, Exception) or r is False]
            
            if failures:
                logger.warning(f"Some storage operations failed for {agent_name}: {len(failures)} failures")
                return False
            
            logger.debug(f"Stored analysis for {agent_name} across {len(storage_tasks)} memory layers")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store agent analysis for {agent_name}: {e}")
            return False
    
    async def store_trading_outcome(
        self, 
        scenario_id: str, 
        outcome_data: Dict[str, Any]
    ) -> bool:
        """
        Store trading outcome and update episodic memory.
        
        Args:
            scenario_id: ID of the original scenario
            outcome_data: Trading outcome data (PnL, execution time, etc.)
            
        Returns:
            bool: True if stored successfully
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get the original scenario
            scenario = await self.episodic_manager.get_scenario_by_id(scenario_id)
            
            if not scenario:
                logger.warning(f"Scenario {scenario_id} not found for outcome update")
                return False
            
            # Update scenario with outcome
            updated_scenario = {
                **scenario,
                "outcome": outcome_data,
                "outcome_recorded_at": time.time(),
                "completed": True
            }
            
            # Store updated scenario
            success = await self.episodic_manager.store_scenario(scenario_id, updated_scenario)
            
            if success:
                # Also update LTM with pattern learning if successful trade
                if outcome_data.get("pnl", 0) > 0:
                    pattern_data = {
                        "market_conditions": scenario.get("market_conditions", {}),
                        "action": scenario.get("action_taken", {}),
                        "outcome": outcome_data,
                        "success_rate": 1.0,  # This trade was successful
                        "agent": scenario.get("agent", "unknown")
                    }
                    
                    pattern_name = f"successful_{scenario.get('agent', 'unknown')}_pattern"
                    await self.ltm_manager.store_pattern(pattern_name, pattern_data)
                
                logger.debug(f"Stored outcome for scenario {scenario_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to store trading outcome for {scenario_id}: {e}")
            return False
    
    async def get_memory_health(self) -> Dict[str, Any]:
        """
        Get overall memory system health.
        
        Returns:
            Dict[str, Any]: Health report
        """
        if not self._initialized:
            await self.initialize()
        
        return await self.cleanup_manager.check_memory_health()
    
    async def get_memory_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive memory usage statistics.
        
        Returns:
            Dict[str, Any]: Memory statistics
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get usage from all memory types
            stm_usage = await self.stm_manager.get_memory_usage()
            ltm_usage = await self.ltm_manager.get_memory_usage()
            episodic_usage = await self.episodic_manager.get_memory_usage()
            
            return {
                "timestamp": time.time(),
                "memory_types": {
                    "stm": stm_usage,
                    "ltm": ltm_usage,
                    "episodic": episodic_usage
                },
                "overall_health": await self.get_memory_health()
            }
            
        except Exception as e:
            logger.error(f"Failed to get memory statistics: {e}")
            return {"error": str(e), "timestamp": time.time()}
    
    async def cleanup_memory(self) -> Dict[str, Any]:
        """
        Trigger manual memory cleanup.
        
        Returns:
            Dict[str, Any]: Cleanup results
        """
        if not self._initialized:
            await self.initialize()
        
        return await self.cleanup_manager.run_full_cleanup()
    
    async def clear_all_memory(self) -> Dict[str, Any]:
        """
        Clear all memory (for testing/maintenance).
        
        Returns:
            Dict[str, Any]: Clear operation results
        """
        if not self._initialized:
            await self.initialize()
        
        return await self.cleanup_manager.clear_all_memory()
    
    async def close(self) -> None:
        """Close all memory connections and cleanup background tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all managers
        await self.stm_manager.close()
        await self.ltm_manager.close()
        await self.episodic_manager.close()
        
        logger.info("Memory layer closed")
    
    # Convenience methods for direct access to specific memory types
    
    async def store_market_data(self, symbol: str, data: Dict[str, Any]) -> bool:
        """Store market data in STM."""
        if not self._initialized:
            await self.initialize()
        return await self.stm_manager.store_market_data(symbol, data)
    
    async def get_market_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get market data from STM."""
        if not self._initialized:
            await self.initialize()
        return await self.stm_manager.get_market_data(symbol)
    
    async def store_performance(self, agent_name: str, performance_data: Dict[str, Any]) -> bool:
        """Store performance data in LTM."""
        if not self._initialized:
            await self.initialize()
        return await self.ltm_manager.store_performance(agent_name, performance_data)
    
    async def get_performance_statistics(self, agent_name: str, days: int = 7) -> Dict[str, Any]:
        """Get performance statistics from LTM."""
        if not self._initialized:
            await self.initialize()
        return await self.ltm_manager.get_performance_statistics(agent_name, days)
    
    async def search_similar_scenarios(
        self, 
        market_conditions: Dict[str, Any], 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for similar scenarios in episodic memory."""
        if not self._initialized:
            await self.initialize()
        return await self.episodic_manager.search_similar_scenarios(market_conditions, limit)
