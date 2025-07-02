"""
Episodic Memory Manager

This module manages episodic memory using Qdrant for semantic storage and search
of historical trading scenarios, outcomes, and contextual information.
"""

import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Union
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from .config import MemoryConfig
from .embedding_utils import generate_scenario_embedding, generate_query_embedding

logger = logging.getLogger(__name__)


class EpisodicMemoryManager:
    """
    Manages episodic memory using Qdrant for semantic search and storage.
    
    Stores:
    - Historical trading scenarios with outcomes
    - Market condition patterns and their results
    - Agent decision contexts and consequences
    - Long-term strategic insights
    """
    
    def __init__(self, config: MemoryConfig, qdrant_client: Optional[AsyncQdrantClient] = None):
        """
        Initialize episodic memory manager.
        
        Args:
            config: Memory configuration
            qdrant_client: Optional pre-configured Qdrant client
        """
        self.config = config
        self._qdrant_client = qdrant_client
        self._initialized = False
        
    async def initialize(self) -> None:
        """Initialize Qdrant connection and create collection if needed."""
        if self._initialized:
            return
            
        if self._qdrant_client is None:
            self._qdrant_client = AsyncQdrantClient(
                url=self.config.qdrant_url,
                api_key=self.config.qdrant_api_key,
                timeout=self.config.connection_timeout
            )
        
        # Test connection and create collection
        try:
            # Check if collection exists
            collections = await self._qdrant_client.get_collections()
            collection_names = [c.name for c in collections.collections]
            
            if self.config.qdrant_collection_name not in collection_names:
                await self._create_collection()
                logger.info(f"Created episodic memory collection: {self.config.qdrant_collection_name}")
            else:
                logger.info(f"Episodic memory collection exists: {self.config.qdrant_collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant for episodic memory: {e}")
            raise
            
        self._initialized = True
    
    async def _create_collection(self) -> None:
        """Create the episodic memory collection with proper configuration."""
        await self._qdrant_client.create_collection(
            collection_name=self.config.qdrant_collection_name,
            vectors_config=VectorParams(
                size=self.config.embedding_dimension,
                distance=Distance.COSINE
            )
        )
    
    async def store_scenario(self, scenario_id: str, scenario_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """
        Store a trading scenario in episodic memory.
        
        Args:
            scenario_id: Unique identifier for the scenario
            scenario_data: Complete scenario data including market conditions, actions, outcomes
            max_retries: Maximum retry attempts
            
        Returns:
            bool: True if stored successfully
            
        Raises:
            RuntimeError: If storage fails after retries
        """
        if not self._initialized:
            await self.initialize()
        
        for attempt in range(max_retries):
            try:
                # Generate embedding for the scenario
                embedding = generate_scenario_embedding(scenario_data, self.config.embedding_model)
                
                # Add metadata
                enhanced_scenario = {
                    **scenario_data,
                    "scenario_id": scenario_id,
                    "stored_at": time.time(),
                    "embedding_model": self.config.embedding_model
                }
                
                # Create point for storage
                point = PointStruct(
                    id=scenario_id,
                    vector=embedding,
                    payload=enhanced_scenario
                )
                
                # Store in Qdrant
                await self._qdrant_client.upsert(
                    collection_name=self.config.qdrant_collection_name,
                    points=[point]
                )
                
                logger.debug(f"Stored scenario {scenario_id} in episodic memory")
                return True
                
            except Exception as e:
                logger.warning(f"Episodic storage attempt {attempt + 1} failed for {scenario_id}: {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to store scenario {scenario_id} after {max_retries} attempts")
                    raise RuntimeError(f"Episodic storage failed: {e}")
                await asyncio.sleep(0.1 * (attempt + 1))
        
        return False
    
    async def search_similar_scenarios(
        self, 
        query_conditions: Dict[str, Any], 
        limit: int = 10, 
        min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar trading scenarios based on market conditions.
        
        Args:
            query_conditions: Market conditions to search for
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold
            
        Returns:
            List[Dict[str, Any]]: List of similar scenarios with scores
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Generate query embedding
            query_embedding = generate_query_embedding(query_conditions, self.config.embedding_model)
            
            # Search in Qdrant
            search_results = await self._qdrant_client.search(
                collection_name=self.config.qdrant_collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=min_score
            )
            
            # Format results
            similar_scenarios = []
            for result in search_results:
                scenario = {
                    "scenario_id": result.id,
                    "similarity_score": result.score,
                    "payload": result.payload
                }
                similar_scenarios.append(scenario)
            
            logger.debug(f"Found {len(similar_scenarios)} similar scenarios")
            return similar_scenarios
            
        except Exception as e:
            logger.error(f"Failed to search similar scenarios: {e}")
            return []
    
    async def get_scenario_by_id(self, scenario_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific scenario by ID.
        
        Args:
            scenario_id: Unique scenario identifier
            
        Returns:
            Optional[Dict[str, Any]]: Scenario data or None if not found
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            results = await self._qdrant_client.retrieve(
                collection_name=self.config.qdrant_collection_name,
                ids=[scenario_id]
            )
            
            if results and len(results) > 0:
                return results[0].payload
            return None
            
        except Exception as e:
            logger.error(f"Failed to retrieve scenario {scenario_id}: {e}")
            return None
    
    async def search_by_outcome(
        self, 
        outcome_criteria: Dict[str, Any], 
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search scenarios by outcome criteria (e.g., successful trades, high PnL).
        
        Args:
            outcome_criteria: Criteria for filtering outcomes
            limit: Maximum number of results
            
        Returns:
            List[Dict[str, Any]]: Scenarios matching outcome criteria
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Build filter conditions
            filter_conditions = []
            
            for key, value in outcome_criteria.items():
                if isinstance(value, (int, float)):
                    # For numeric values, we'll do exact match
                    # In production, you'd want range filters
                    filter_conditions.append(
                        FieldCondition(key=f"outcomes.{key}", match=MatchValue(value=value))
                    )
                elif isinstance(value, str):
                    filter_conditions.append(
                        FieldCondition(key=f"outcomes.{key}", match=MatchValue(value=value))
                    )
            
            if not filter_conditions:
                return []
            
            # Search with filter
            search_results = await self._qdrant_client.scroll(
                collection_name=self.config.qdrant_collection_name,
                scroll_filter=Filter(must=filter_conditions),
                limit=limit
            )
            
            scenarios = []
            for result in search_results[0]:  # scroll returns (points, next_page_offset)
                scenario = {
                    "scenario_id": result.id,
                    "payload": result.payload
                }
                scenarios.append(scenario)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Failed to search by outcome: {e}")
            return []
    
    async def get_recent_scenarios(self, hours: int = 24, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recently stored scenarios.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of scenarios to return
            
        Returns:
            List[Dict[str, Any]]: Recent scenarios
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            cutoff_time = time.time() - (hours * 3600)
            
            # Filter by stored_at timestamp
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="stored_at",
                        range={
                            "gte": cutoff_time
                        }
                    )
                ]
            )
            
            search_results = await self._qdrant_client.scroll(
                collection_name=self.config.qdrant_collection_name,
                scroll_filter=filter_condition,
                limit=limit
            )
            
            scenarios = []
            for result in search_results[0]:
                scenario = {
                    "scenario_id": result.id,
                    "payload": result.payload
                }
                scenarios.append(scenario)
            
            # Sort by stored_at timestamp (newest first)
            scenarios.sort(key=lambda x: x["payload"].get("stored_at", 0), reverse=True)
            
            return scenarios
            
        except Exception as e:
            logger.error(f"Failed to get recent scenarios: {e}")
            return []
    
    async def delete_scenario(self, scenario_id: str) -> bool:
        """
        Delete a specific scenario.
        
        Args:
            scenario_id: Scenario ID to delete
            
        Returns:
            bool: True if deleted successfully
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            await self._qdrant_client.delete(
                collection_name=self.config.qdrant_collection_name,
                points_selector=[scenario_id]
            )
            logger.debug(f"Deleted scenario {scenario_id} from episodic memory")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete scenario {scenario_id}: {e}")
            return False
    
    async def cleanup_old_scenarios(self, days: int = 30) -> int:
        """
        Clean up scenarios older than specified days.
        
        Args:
            days: Number of days to keep scenarios
            
        Returns:
            int: Number of scenarios deleted
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            cutoff_time = time.time() - (days * 24 * 3600)
            
            # Find old scenarios
            filter_condition = Filter(
                must=[
                    FieldCondition(
                        key="stored_at",
                        range={
                            "lt": cutoff_time
                        }
                    )
                ]
            )
            
            old_scenarios = await self._qdrant_client.scroll(
                collection_name=self.config.qdrant_collection_name,
                scroll_filter=filter_condition,
                limit=10000  # Large limit to get all old scenarios
            )
            
            if not old_scenarios[0]:
                return 0
            
            # Delete old scenarios
            old_ids = [scenario.id for scenario in old_scenarios[0]]
            
            await self._qdrant_client.delete(
                collection_name=self.config.qdrant_collection_name,
                points_selector=old_ids
            )
            
            logger.info(f"Cleaned up {len(old_ids)} old scenarios from episodic memory")
            return len(old_ids)
            
        except Exception as e:
            logger.error(f"Failed to cleanup old scenarios: {e}")
            return 0
    
    async def enforce_size_limits(self) -> int:
        """
        Enforce size limits by removing oldest scenarios.
        
        Returns:
            int: Number of scenarios removed
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Get collection info
            collection_info = await self._qdrant_client.get_collection(self.config.qdrant_collection_name)
            current_count = collection_info.points_count
            
            if current_count <= self.config.max_episodic_size:
                return 0
            
            # Calculate how many to remove
            to_remove = current_count - self.config.max_episodic_size
            
            # Get oldest scenarios (sorted by stored_at)
            oldest_scenarios = await self._qdrant_client.scroll(
                collection_name=self.config.qdrant_collection_name,
                limit=to_remove,
                order_by=["stored_at"]  # Ascending order (oldest first)
            )
            
            if not oldest_scenarios[0]:
                return 0
            
            # Delete oldest scenarios
            oldest_ids = [scenario.id for scenario in oldest_scenarios[0]]
            
            await self._qdrant_client.delete(
                collection_name=self.config.qdrant_collection_name,
                points_selector=oldest_ids
            )
            
            logger.info(f"Removed {len(oldest_ids)} oldest scenarios to enforce size limit")
            return len(oldest_ids)
            
        except Exception as e:
            logger.error(f"Failed to enforce episodic size limits: {e}")
            return 0
    
    async def get_memory_usage(self) -> Dict[str, Any]:
        """
        Get current episodic memory usage statistics.
        
        Returns:
            Dict[str, Any]: Memory usage statistics
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            collection_info = await self._qdrant_client.get_collection(self.config.qdrant_collection_name)
            current_count = collection_info.points_count
            
            # Calculate usage percentage
            usage_percentage = (current_count / self.config.max_episodic_size) * 100 if self.config.max_episodic_size > 0 else 0
            
            # Determine status
            if current_count > self.config.max_episodic_size:
                status = "over_limit"
            elif usage_percentage > 80:
                status = "warning"
            else:
                status = "healthy"
            
            return {
                "type": "episodic",
                "collection_name": self.config.qdrant_collection_name,
                "total_scenarios": current_count,
                "limit": self.config.max_episodic_size,
                "usage_percentage": usage_percentage,
                "status": status,
                "embedding_dimension": self.config.embedding_dimension,
                "embedding_model": self.config.embedding_model
            }
            
        except Exception as e:
            logger.error(f"Failed to get episodic memory usage: {e}")
            return {
                "type": "episodic",
                "status": "error",
                "error": str(e)
            }
    
    async def clear_all(self) -> bool:
        """
        Clear all episodic memory data (for testing/maintenance).
        
        Returns:
            bool: True if successful
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Delete the collection and recreate it
            await self._qdrant_client.delete_collection(self.config.qdrant_collection_name)
            await self._create_collection()
            logger.info("Cleared all episodic memory data")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear episodic memory: {e}")
            return False
    
    async def close(self) -> None:
        """Close Qdrant connection."""
        if self._qdrant_client:
            await self._qdrant_client.close()
            logger.info("Episodic memory Qdrant connection closed")
