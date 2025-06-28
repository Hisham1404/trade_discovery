"""
Base repository class providing common database operations.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.orm import DeclarativeBase

from app.core.database import get_db_session

# Type variable for model classes
ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class BaseRepository(Generic[ModelType], ABC):
    """
    Base repository class with common CRUD operations.
    
    Provides a consistent interface for database operations across all entities.
    """
    
    def __init__(self, model_class: type[ModelType]):
        self.model_class = model_class
    
    async def create(self, **kwargs) -> ModelType:
        """
        Create a new entity.
        
        Args:
            **kwargs: Entity attributes
            
        Returns:
            Created entity instance
        """
        async with get_db_session() as session:
            instance = self.model_class(**kwargs)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance
    
    async def get_by_id(self, entity_id: str) -> Optional[ModelType]:
        """
        Get entity by ID.
        
        Args:
            entity_id: Unique identifier
            
        Returns:
            Entity instance if found, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(self.model_class).where(self.model_class.id == entity_id)
            )
            return result.scalar_one_or_none()
    
    async def get_all(self, limit: int = 100, offset: int = 0) -> List[ModelType]:
        """
        Get all entities with pagination.
        
        Args:
            limit: Maximum number of entities to return
            offset: Number of entities to skip
            
        Returns:
            List of entity instances
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(self.model_class).limit(limit).offset(offset)
            )
            return list(result.scalars().all())
    
    async def update_by_id(self, entity_id: str, **kwargs) -> Optional[ModelType]:
        """
        Update entity by ID.
        
        Args:
            entity_id: Unique identifier
            **kwargs: Fields to update
            
        Returns:
            Updated entity instance if found, None otherwise
        """
        async with get_db_session() as session:
            # Update the entity
            result = await session.execute(
                update(self.model_class)
                .where(self.model_class.id == entity_id)
                .values(**kwargs)
                .returning(self.model_class)
            )
            updated_entity = result.scalar_one_or_none()
            
            if updated_entity:
                await session.commit()
                await session.refresh(updated_entity)
            
            return updated_entity
    
    async def delete_by_id(self, entity_id: str) -> bool:
        """
        Delete entity by ID.
        
        Args:
            entity_id: Unique identifier
            
        Returns:
            True if entity was deleted, False if not found
        """
        async with get_db_session() as session:
            result = await session.execute(
                delete(self.model_class).where(self.model_class.id == entity_id)
            )
            deleted_count = result.rowcount
            
            if deleted_count > 0:
                await session.commit()
                return True
            
            return False
    
    async def count(self, **filters) -> int:
        """
        Count entities with optional filters.
        
        Args:
            **filters: Filter conditions
            
        Returns:
            Count of entities matching filters
        """
        async with get_db_session() as session:
            query = select(func.count(self.model_class.id))
            
            # Apply filters
            for field, value in filters.items():
                if hasattr(self.model_class, field):
                    query = query.where(getattr(self.model_class, field) == value)
            
            result = await session.execute(query)
            return result.scalar() or 0
    
    async def exists(self, entity_id: str) -> bool:
        """
        Check if entity exists by ID.
        
        Args:
            entity_id: Unique identifier
            
        Returns:
            True if entity exists, False otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(func.count(self.model_class.id))
                .where(self.model_class.id == entity_id)
            )
            count = result.scalar() or 0
            return count > 0
    
    async def bulk_create(self, entities_data: List[Dict[str, Any]]) -> List[ModelType]:
        """
        Create multiple entities in a single transaction.
        
        Args:
            entities_data: List of dictionaries with entity attributes
            
        Returns:
            List of created entity instances
        """
        async with get_db_session() as session:
            instances = [self.model_class(**data) for data in entities_data]
            session.add_all(instances)
            await session.commit()
            
            # Refresh all instances
            for instance in instances:
                await session.refresh(instance)
            
            return instances
    
    async def execute_raw_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Execute raw SQL query for TimescaleDB-specific operations.
        
        Args:
            query: Raw SQL query
            params: Query parameters
            
        Returns:
            Query result
        """
        async with get_db_session() as session:
            result = await session.execute(text(query), params or {})
            await session.commit()
            return result
    
    async def get_with_session(self, session: AsyncSession, entity_id: str) -> Optional[ModelType]:
        """
        Get entity by ID using provided session.
        Useful for transactions across multiple repositories.
        
        Args:
            session: Database session
            entity_id: Unique identifier
            
        Returns:
            Entity instance if found, None otherwise
        """
        result = await session.execute(
            select(self.model_class).where(self.model_class.id == entity_id)
        )
        return result.scalar_one_or_none()
    
    async def create_with_session(self, session: AsyncSession, **kwargs) -> ModelType:
        """
        Create entity using provided session.
        Useful for transactions across multiple repositories.
        
        Args:
            session: Database session
            **kwargs: Entity attributes
            
        Returns:
            Created entity instance
        """
        instance = self.model_class(**kwargs)
        session.add(instance)
        await session.flush()  # Flush to get ID without committing
        await session.refresh(instance)
        return instance 