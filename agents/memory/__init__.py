"""
Memory Layer Package for Multi-Agent Trading System

This package implements a three-layer memory system:
- STM (Short-Term Memory): Redis - recent market data (TTL 1 hour)
- LTM (Long-Term Memory): Redis - agent performance history and learned patterns (TTL 7 days)
- Episodic Memory: Qdrant - semantic search of historical scenarios and outcomes

The memory layer provides automatic memory management for BaseAgent instances,
including context building, storage, cleanup policies, and size limits.
"""

from .config import MemoryConfig, MemoryType
from .stm_manager import STMManager
from .ltm_manager import LTMManager
from .episodic_manager import EpisodicMemoryManager
from .cleanup_manager import MemoryCleanupManager
from .memory_layer import MemoryLayer
from .embedding_utils import generate_scenario_embedding

__all__ = [
    "MemoryConfig",
    "MemoryType",
    "STMManager",
    "LTMManager", 
    "EpisodicMemoryManager",
    "MemoryCleanupManager",
    "MemoryLayer",
    "generate_scenario_embedding"
]

__version__ = "1.0.0" 