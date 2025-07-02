"""
Memory Cleanup Manager

This module coordinates cleanup policies across all memory layer types,
managing size limits, TTL cleanup, and maintenance operations.
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional
from .config import MemoryConfig, MemoryType
from .stm_manager import STMManager
from .ltm_manager import LTMManager
from .episodic_manager import EpisodicMemoryManager

logger = logging.getLogger(__name__)


class MemoryCleanupManager:
    """
    Coordinates cleanup operations across all memory layer types.
    
    Responsibilities:
    - Enforce size limits across all memory types
    - Perform TTL-based cleanup for Redis (STM/LTM)
    - Manage age-based cleanup for episodic memory
    - Generate cleanup reports and statistics
    - Schedule periodic maintenance operations
    """
    
    def __init__(
        self, 
        config: MemoryConfig,
        stm_manager: Optional[STMManager] = None,
        ltm_manager: Optional[LTMManager] = None,
        episodic_manager: Optional[EpisodicMemoryManager] = None
    ):
        """
        Initialize cleanup manager.
        
        Args:
            config: Memory configuration
            stm_manager: STM manager instance
            ltm_manager: LTM manager instance
            episodic_manager: Episodic memory manager instance
        """
        self.config = config
        self.stm_manager = stm_manager
        self.ltm_manager = ltm_manager
        self.episodic_manager = episodic_manager
        self._cleanup_running = False
        self._last_cleanup = {}
        
    async def initialize(self) -> None:
        """Initialize all memory managers if not already initialized."""
        if self.stm_manager:
            await self.stm_manager.initialize()
        if self.ltm_manager:
            await self.ltm_manager.initialize()
        if self.episodic_manager:
            await self.episodic_manager.initialize()
    
    async def run_full_cleanup(self) -> Dict[str, Any]:
        """
        Run comprehensive cleanup across all memory types.
        
        Returns:
            Dict[str, Any]: Cleanup report with statistics
        """
        if self._cleanup_running:
            logger.warning("Cleanup already in progress, skipping")
            return {"status": "skipped", "reason": "cleanup_in_progress"}
        
        self._cleanup_running = True
        start_time = time.time()
        cleanup_report = {
            "started_at": start_time,
            "status": "running",
            "operations": {}
        }
        
        try:
            # Initialize managers
            await self.initialize()
            
            # Run cleanup operations in parallel for efficiency
            cleanup_tasks = []
            
            if self.stm_manager:
                cleanup_tasks.append(self._cleanup_stm())
            if self.ltm_manager:
                cleanup_tasks.append(self._cleanup_ltm())
            if self.episodic_manager:
                cleanup_tasks.append(self._cleanup_episodic())
            
            # Execute all cleanup tasks
            cleanup_results = await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            # Process results
            memory_types = ["stm", "ltm", "episodic"]
            for i, result in enumerate(cleanup_results):
                if i < len(memory_types):
                    memory_type = memory_types[i]
                    if isinstance(result, Exception):
                        cleanup_report["operations"][memory_type] = {
                            "status": "error",
                            "error": str(result)
                        }
                    else:
                        cleanup_report["operations"][memory_type] = result
            
            # Calculate totals
            total_cleaned = sum(
                op.get("total_cleaned", 0) 
                for op in cleanup_report["operations"].values() 
                if isinstance(op, dict)
            )
            
            cleanup_report.update({
                "status": "completed",
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time,
                "total_items_cleaned": total_cleaned
            })
            
            # Update last cleanup times
            current_time = time.time()
            for memory_type in cleanup_report["operations"]:
                self._last_cleanup[memory_type] = current_time
            
            logger.info(f"Full cleanup completed in {cleanup_report['duration_seconds']:.2f}s, cleaned {total_cleaned} items")
            
        except Exception as e:
            cleanup_report.update({
                "status": "error",
                "error": str(e),
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time
            })
            logger.error(f"Full cleanup failed: {e}")
            
        finally:
            self._cleanup_running = False
        
        return cleanup_report
    
    async def _cleanup_stm(self) -> Dict[str, Any]:
        """
        Cleanup STM (Short-Term Memory).
        
        Returns:
            Dict[str, Any]: STM cleanup results
        """
        if not self.stm_manager:
            return {"status": "skipped", "reason": "no_stm_manager"}
        
        start_time = time.time()
        result = {
            "memory_type": "stm",
            "started_at": start_time,
            "operations": {}
        }
        
        try:
            # Clean expired keys
            expired_cleaned = await self.stm_manager.cleanup_expired()
            result["operations"]["expired_cleanup"] = {
                "items_cleaned": expired_cleaned,
                "status": "completed"
            }
            
            # Enforce size limits
            size_limited = await self.stm_manager.enforce_size_limits()
            result["operations"]["size_limit_enforcement"] = {
                "items_cleaned": size_limited,
                "status": "completed"
            }
            
            # Get memory usage after cleanup
            memory_usage = await self.stm_manager.get_memory_usage()
            result["memory_usage_after"] = memory_usage
            
            result.update({
                "status": "completed",
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time,
                "total_cleaned": expired_cleaned + size_limited
            })
            
        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e),
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time
            })
            
        return result
    
    async def _cleanup_ltm(self) -> Dict[str, Any]:
        """
        Cleanup LTM (Long-Term Memory).
        
        Returns:
            Dict[str, Any]: LTM cleanup results
        """
        if not self.ltm_manager:
            return {"status": "skipped", "reason": "no_ltm_manager"}
        
        start_time = time.time()
        result = {
            "memory_type": "ltm",
            "started_at": start_time,
            "operations": {}
        }
        
        try:
            # Clean expired keys
            expired_cleaned = await self.ltm_manager.cleanup_expired()
            result["operations"]["expired_cleanup"] = {
                "items_cleaned": expired_cleaned,
                "status": "completed"
            }
            
            # Enforce size limits
            size_limited = await self.ltm_manager.enforce_size_limits()
            result["operations"]["size_limit_enforcement"] = {
                "items_cleaned": size_limited,
                "status": "completed"
            }
            
            # Get memory usage after cleanup
            memory_usage = await self.ltm_manager.get_memory_usage()
            result["memory_usage_after"] = memory_usage
            
            result.update({
                "status": "completed",
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time,
                "total_cleaned": expired_cleaned + size_limited
            })
            
        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e),
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time
            })
            
        return result
    
    async def _cleanup_episodic(self) -> Dict[str, Any]:
        """
        Cleanup Episodic Memory.
        
        Returns:
            Dict[str, Any]: Episodic cleanup results
        """
        if not self.episodic_manager:
            return {"status": "skipped", "reason": "no_episodic_manager"}
        
        start_time = time.time()
        result = {
            "memory_type": "episodic",
            "started_at": start_time,
            "operations": {}
        }
        
        try:
            # Clean old scenarios (30 days default)
            old_cleaned = await self.episodic_manager.cleanup_old_scenarios(days=30)
            result["operations"]["old_scenarios_cleanup"] = {
                "items_cleaned": old_cleaned,
                "status": "completed"
            }
            
            # Enforce size limits
            size_limited = await self.episodic_manager.enforce_size_limits()
            result["operations"]["size_limit_enforcement"] = {
                "items_cleaned": size_limited,
                "status": "completed"
            }
            
            # Get memory usage after cleanup
            memory_usage = await self.episodic_manager.get_memory_usage()
            result["memory_usage_after"] = memory_usage
            
            result.update({
                "status": "completed",
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time,
                "total_cleaned": old_cleaned + size_limited
            })
            
        except Exception as e:
            result.update({
                "status": "error",
                "error": str(e),
                "completed_at": time.time(),
                "duration_seconds": time.time() - start_time
            })
            
        return result
    
    async def check_memory_health(self) -> Dict[str, Any]:
        """
        Check the health status of all memory layers.
        
        Returns:
            Dict[str, Any]: Health report for all memory types
        """
        await self.initialize()
        
        health_report = {
            "checked_at": time.time(),
            "overall_status": "healthy",
            "memory_types": {}
        }
        
        # Check each memory type
        memory_checks = []
        
        if self.stm_manager:
            memory_checks.append(("stm", self.stm_manager.get_memory_usage()))
        if self.ltm_manager:
            memory_checks.append(("ltm", self.ltm_manager.get_memory_usage()))
        if self.episodic_manager:
            memory_checks.append(("episodic", self.episodic_manager.get_memory_usage()))
        
        # Execute health checks
        for memory_type, check_coro in memory_checks:
            try:
                usage_stats = await check_coro
                health_report["memory_types"][memory_type] = usage_stats
                
                # Update overall status based on individual statuses
                if usage_stats.get("status") == "error":
                    health_report["overall_status"] = "error"
                elif usage_stats.get("status") == "over_limit" and health_report["overall_status"] != "error":
                    health_report["overall_status"] = "critical"
                elif usage_stats.get("status") == "warning" and health_report["overall_status"] not in ["error", "critical"]:
                    health_report["overall_status"] = "warning"
                    
            except Exception as e:
                health_report["memory_types"][memory_type] = {
                    "status": "error",
                    "error": str(e)
                }
                health_report["overall_status"] = "error"
        
        return health_report
    
    async def get_cleanup_recommendations(self) -> Dict[str, Any]:
        """
        Generate cleanup recommendations based on memory usage.
        
        Returns:
            Dict[str, Any]: Cleanup recommendations
        """
        health_report = await self.check_memory_health()
        
        recommendations = {
            "generated_at": time.time(),
            "recommendations": [],
            "urgent_actions": [],
            "scheduled_cleanup_needed": False
        }
        
        for memory_type, stats in health_report["memory_types"].items():
            status = stats.get("status", "unknown")
            usage_pct = stats.get("usage_percentage", 0)
            
            if status == "over_limit":
                recommendations["urgent_actions"].append({
                    "memory_type": memory_type,
                    "action": "immediate_cleanup",
                    "reason": f"{memory_type.upper()} is over its size limit",
                    "priority": "high"
                })
                recommendations["scheduled_cleanup_needed"] = True
                
            elif status == "warning" or usage_pct > 80:
                recommendations["recommendations"].append({
                    "memory_type": memory_type,
                    "action": "schedule_cleanup",
                    "reason": f"{memory_type.upper()} usage is {usage_pct:.1f}% (warning threshold)",
                    "priority": "medium"
                })
                recommendations["scheduled_cleanup_needed"] = True
                
            elif usage_pct > 60:
                recommendations["recommendations"].append({
                    "memory_type": memory_type,
                    "action": "monitor_usage",
                    "reason": f"{memory_type.upper()} usage is {usage_pct:.1f}%",
                    "priority": "low"
                })
        
        # Check if cleanup is overdue
        current_time = time.time()
        cleanup_interval = self.config.cleanup_interval_seconds
        
        for memory_type in ["stm", "ltm", "episodic"]:
            last_cleanup_time = self._last_cleanup.get(memory_type, 0)
            time_since_cleanup = current_time - last_cleanup_time
            
            if time_since_cleanup > cleanup_interval:
                recommendations["recommendations"].append({
                    "memory_type": memory_type,
                    "action": "schedule_cleanup",
                    "reason": f"Last cleanup was {time_since_cleanup / 3600:.1f} hours ago",
                    "priority": "medium"
                })
                recommendations["scheduled_cleanup_needed"] = True
        
        return recommendations
    
    async def start_periodic_cleanup(self, interval_seconds: Optional[int] = None) -> None:
        """
        Start periodic cleanup background task.
        
        Args:
            interval_seconds: Override default cleanup interval
        """
        interval = interval_seconds or self.config.cleanup_interval_seconds
        
        logger.info(f"Starting periodic cleanup every {interval} seconds")
        
        while True:
            try:
                await asyncio.sleep(interval)
                
                # Check if cleanup is needed
                recommendations = await self.get_cleanup_recommendations()
                
                if recommendations["scheduled_cleanup_needed"]:
                    logger.info("Periodic cleanup triggered by recommendations")
                    await self.run_full_cleanup()
                else:
                    logger.debug("Periodic cleanup check: no cleanup needed")
                    
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    async def clear_all_memory(self) -> Dict[str, Any]:
        """
        Clear all memory across all types (for testing/maintenance).
        
        Returns:
            Dict[str, Any]: Clear operation results
        """
        await self.initialize()
        
        results = {
            "cleared_at": time.time(),
            "operations": {}
        }
        
        # Clear each memory type
        if self.stm_manager:
            try:
                stm_result = await self.stm_manager.clear_all()
                results["operations"]["stm"] = {"status": "completed" if stm_result else "failed"}
            except Exception as e:
                results["operations"]["stm"] = {"status": "error", "error": str(e)}
        
        if self.ltm_manager:
            try:
                ltm_result = await self.ltm_manager.clear_all()
                results["operations"]["ltm"] = {"status": "completed" if ltm_result else "failed"}
            except Exception as e:
                results["operations"]["ltm"] = {"status": "error", "error": str(e)}
        
        if self.episodic_manager:
            try:
                episodic_result = await self.episodic_manager.clear_all()
                results["operations"]["episodic"] = {"status": "completed" if episodic_result else "failed"}
            except Exception as e:
                results["operations"]["episodic"] = {"status": "error", "error": str(e)}
        
        logger.info("Cleared all memory types")
        return results
