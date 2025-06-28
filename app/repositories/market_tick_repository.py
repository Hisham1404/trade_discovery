"""
Market tick repository for high-frequency market data operations.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from decimal import Decimal
from sqlalchemy import select, and_, desc, asc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import MarketTick
from app.core.database import get_db_session
from .base_repository import BaseRepository


class MarketTickRepository(BaseRepository[MarketTick]):
    """
    Repository for MarketTick entity with TimescaleDB-optimized operations.
    Handles high-frequency market data with efficient bulk operations.
    """
    
    def __init__(self):
        super().__init__(MarketTick)
    
    async def create_tick(
        self,
        symbol: str,
        timestamp: datetime,
        price: float,
        volume: Optional[int] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        high: Optional[float] = None,
        low: Optional[float] = None,
        open_price: Optional[float] = None,
        close_price: Optional[float] = None,
        exchange: Optional[str] = None
    ) -> MarketTick:
        """
        Create a new market tick.
        
        Args:
            symbol: Stock symbol
            timestamp: Market data timestamp
            price: Current price
            volume: Trading volume
            bid: Bid price
            ask: Ask price
            high: Day high price
            low: Day low price
            open_price: Opening price
            close_price: Previous close price
            exchange: Exchange identifier
            
        Returns:
            Created market tick instance
        """
        async with get_db_session() as session:
            tick = MarketTick(
                symbol=symbol,
                timestamp=timestamp,
                price=Decimal(str(price)),
                volume=volume,
                bid=Decimal(str(bid)) if bid else None,
                ask=Decimal(str(ask)) if ask else None,
                high=Decimal(str(high)) if high else None,
                low=Decimal(str(low)) if low else None,
                open_price=Decimal(str(open_price)) if open_price else None,
                close_price=Decimal(str(close_price)) if close_price else None,
                exchange=exchange
            )
            
            session.add(tick)
            await session.commit()
            await session.refresh(tick)
            return tick
    
    async def bulk_insert_ticks(self, ticks_data: List[Dict[str, Any]]) -> int:
        """
        Bulk insert market ticks for high-frequency data ingestion.
        
        Args:
            ticks_data: List of tick data dictionaries
            
        Returns:
            Number of ticks inserted
        """
        if not ticks_data:
            return 0
        
        async with get_db_session() as session:
            # Convert price fields to Decimal for database storage
            processed_ticks = []
            for tick_data in ticks_data:
                processed_tick = tick_data.copy()
                
                # Convert numeric fields to Decimal
                for field in ['price', 'bid', 'ask', 'high', 'low', 'open_price', 'close_price']:
                    if field in processed_tick and processed_tick[field] is not None:
                        processed_tick[field] = Decimal(str(processed_tick[field]))
                
                processed_ticks.append(processed_tick)
            
            # Create MarketTick instances
            tick_instances = [MarketTick(**tick_data) for tick_data in processed_ticks]
            
            session.add_all(tick_instances)
            await session.commit()
            
            return len(tick_instances)
    
    async def get_latest_tick(self, symbol: str) -> Optional[MarketTick]:
        """
        Get the most recent tick for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Latest market tick if found, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketTick)
                .where(MarketTick.symbol == symbol)
                .order_by(desc(MarketTick.timestamp))
                .limit(1)
            )
            return result.scalar_one_or_none()
    
    async def get_ticks_in_range(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        limit: int = 1000,
        offset: int = 0
    ) -> List[MarketTick]:
        """
        Get market ticks for a symbol within a time range.
        
        Args:
            symbol: Stock symbol
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of ticks to return
            offset: Number of ticks to skip
            
        Returns:
            List of market ticks in the time range
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketTick)
                .where(and_(
                    MarketTick.symbol == symbol,
                    MarketTick.timestamp >= start_time,
                    MarketTick.timestamp <= end_time
                ))
                .order_by(asc(MarketTick.timestamp))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_recent_ticks(
        self,
        symbol: str,
        minutes: int = 60,
        limit: int = 1000
    ) -> List[MarketTick]:
        """
        Get recent ticks for a symbol within the last N minutes.
        
        Args:
            symbol: Stock symbol
            minutes: Number of minutes to look back
            limit: Maximum number of ticks to return
            
        Returns:
            List of recent market ticks
        """
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketTick)
                .where(and_(
                    MarketTick.symbol == symbol,
                    MarketTick.timestamp >= cutoff_time
                ))
                .order_by(desc(MarketTick.timestamp))
                .limit(limit)
            )
            return list(result.scalars().all())
    
    async def get_ohlcv_data(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        interval: str = "1m"  # 1m, 5m, 15m, 1h, 1d
    ) -> List[Dict[str, Any]]:
        """
        Get OHLCV (Open, High, Low, Close, Volume) data using TimescaleDB time_bucket.
        
        Args:
            symbol: Stock symbol
            start_time: Start of time range
            end_time: End of time range
            interval: Time bucket interval (1m, 5m, 15m, 1h, 1d)
            
        Returns:
            List of OHLCV data points
        """
        # Map intervals to PostgreSQL intervals
        interval_map = {
            "1m": "1 minute",
            "5m": "5 minutes", 
            "15m": "15 minutes",
            "30m": "30 minutes",
            "1h": "1 hour",
            "4h": "4 hours",
            "1d": "1 day"
        }
        
        pg_interval = interval_map.get(interval, "1 minute")
        
        async with get_db_session() as session:
            query = f"""
                SELECT 
                    time_bucket('{pg_interval}', timestamp) AS bucket,
                    FIRST(price, timestamp) as open,
                    MAX(price) as high,
                    MIN(price) as low,
                    LAST(price, timestamp) as close,
                    SUM(volume) as volume,
                    COUNT(*) as tick_count
                FROM market_ticks
                WHERE symbol = :symbol
                AND timestamp >= :start_time
                AND timestamp <= :end_time
                GROUP BY bucket
                ORDER BY bucket ASC
            """
            
            result = await session.execute(
                text(query),
                {
                    "symbol": symbol,
                    "start_time": start_time,
                    "end_time": end_time
                }
            )
            
            return [
                {
                    "timestamp": row.bucket,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "volume": int(row.volume) if row.volume else 0,
                    "tick_count": row.tick_count
                }
                for row in result.fetchall()
            ]
    
    async def get_volume_weighted_average_price(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> Optional[float]:
        """
        Calculate Volume Weighted Average Price (VWAP) for a time period.
        
        Args:
            symbol: Stock symbol
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            VWAP value if data exists, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.sum(MarketTick.price * MarketTick.volume).label("total_value"),
                    func.sum(MarketTick.volume).label("total_volume")
                )
                .where(and_(
                    MarketTick.symbol == symbol,
                    MarketTick.timestamp >= start_time,
                    MarketTick.timestamp <= end_time,
                    MarketTick.volume.isnot(None),
                    MarketTick.volume > 0
                ))
            )
            
            row = result.first()
            
            if row and row.total_volume and row.total_volume > 0:
                return float(row.total_value / row.total_volume)
            
            return None
    
    async def get_price_statistics(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> Dict[str, Any]:
        """
        Get price statistics for a symbol in a time range.
        
        Args:
            symbol: Stock symbol
            start_time: Start of time range
            end_time: End of time range
            
        Returns:
            Dictionary with price statistics
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.count(MarketTick.timestamp).label("tick_count"),
                    func.min(MarketTick.price).label("min_price"),
                    func.max(MarketTick.price).label("max_price"),
                    func.avg(MarketTick.price).label("avg_price"),
                    func.stddev(MarketTick.price).label("price_stddev"),
                    func.sum(MarketTick.volume).label("total_volume")
                )
                .where(and_(
                    MarketTick.symbol == symbol,
                    MarketTick.timestamp >= start_time,
                    MarketTick.timestamp <= end_time
                ))
            )
            
            row = result.first()
            
            if row and row.tick_count > 0:
                return {
                    "symbol": symbol,
                    "start_time": start_time,
                    "end_time": end_time,
                    "tick_count": row.tick_count,
                    "min_price": float(row.min_price),
                    "max_price": float(row.max_price),
                    "avg_price": float(row.avg_price),
                    "price_range": float(row.max_price - row.min_price),
                    "price_stddev": float(row.price_stddev) if row.price_stddev else 0.0,
                    "total_volume": int(row.total_volume) if row.total_volume else 0
                }
            
            return {
                "symbol": symbol,
                "start_time": start_time,
                "end_time": end_time,
                "tick_count": 0,
                "min_price": 0.0,
                "max_price": 0.0,
                "avg_price": 0.0,
                "price_range": 0.0,
                "price_stddev": 0.0,
                "total_volume": 0
            }
    
    async def get_active_symbols(self, hours: int = 24) -> List[str]:
        """
        Get symbols that have had trading activity in the last N hours.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of active symbol names
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        async with get_db_session() as session:
            result = await session.execute(
                select(MarketTick.symbol)
                .where(MarketTick.timestamp >= cutoff_time)
                .distinct()
                .order_by(MarketTick.symbol)
            )
            return [row.symbol for row in result.fetchall()]
    
    async def get_tick_count_by_symbol(
        self,
        start_time: datetime,
        end_time: datetime,
        limit: int = 50
    ) -> List[Tuple[str, int]]:
        """
        Get tick counts by symbol for a time period.
        
        Args:
            start_time: Start of time range
            end_time: End of time range
            limit: Maximum number of symbols to return
            
        Returns:
            List of tuples (symbol, tick_count) ordered by count desc
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    MarketTick.symbol,
                    func.count(MarketTick.timestamp).label("tick_count")
                )
                .where(and_(
                    MarketTick.timestamp >= start_time,
                    MarketTick.timestamp <= end_time
                ))
                .group_by(MarketTick.symbol)
                .order_by(desc(func.count(MarketTick.timestamp)))
                .limit(limit)
            )
            
            return [(row.symbol, row.tick_count) for row in result.fetchall()]
    
    async def cleanup_old_ticks(self, days: int = 30) -> int:
        """
        Delete market ticks older than specified days.
        Note: Usually handled by TimescaleDB retention policies.
        
        Args:
            days: Number of days to retain
            
        Returns:
            Number of ticks deleted
        """
        cutoff_time = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Use TimescaleDB's efficient delete for old data
            result = await session.execute(
                text("DELETE FROM market_ticks WHERE timestamp < :cutoff_time"),
                {"cutoff_time": cutoff_time}
            )
            deleted_count = result.rowcount or 0
            await session.commit()
            
            return deleted_count 