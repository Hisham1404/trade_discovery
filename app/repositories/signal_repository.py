"""
Signal repository for trading signal operations.
"""

from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from decimal import Decimal
from sqlalchemy import select, and_, or_, desc, asc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal, SignalStatus, SignalDirection
from app.core.database import get_db_session
from .base_repository import BaseRepository


class SignalRepository(BaseRepository[Signal]):
    """
    Repository for Signal entity with trading-specific operations.
    """
    
    def __init__(self):
        super().__init__(Signal)
    
    async def create_signal(
        self,
        symbol: str,
        direction: SignalDirection,
        confidence: float,
        generating_agent: str,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        entry_price: Optional[float] = None,
        rationale: Optional[str] = None,
        shap_values: Optional[Dict[str, Any]] = None,
        technical_indicators: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None
    ) -> Signal:
        """
        Create a new trading signal.
        
        Args:
            symbol: Stock symbol
            direction: Signal direction (long/short)
            confidence: Confidence score (0.0 to 1.0)
            generating_agent: Name of the AI agent
            stop_loss: Stop loss price level
            target: Target price level
            entry_price: Suggested entry price
            rationale: Human-readable explanation
            shap_values: SHAP explainability values
            technical_indicators: Technical analysis data
            expires_at: Signal expiration time
            
        Returns:
            Created signal instance
        """
        return await self.create(
            symbol=symbol,
            direction=direction,
            confidence=Decimal(str(confidence)),
            generating_agent=generating_agent,
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            target=Decimal(str(target)) if target else None,
            entry_price=Decimal(str(entry_price)) if entry_price else None,
            rationale=rationale,
            shap_values=shap_values,
            technical_indicators=technical_indicators,
            expires_at=expires_at
        )
    
    async def get_pending_signals(self, limit: int = 100, offset: int = 0) -> List[Signal]:
        """
        Get all pending signals.
        
        Args:
            limit: Maximum number of signals to return
            offset: Number of signals to skip
            
        Returns:
            List of pending signals
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Signal)
                .where(Signal.status == SignalStatus.PENDING)
                .order_by(desc(Signal.confidence), desc(Signal.created_at))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_active_signals(self, limit: int = 100, offset: int = 0) -> List[Signal]:
        """
        Get all active signals.
        
        Args:
            limit: Maximum number of signals to return
            offset: Number of signals to skip
            
        Returns:
            List of active signals
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Signal)
                .where(Signal.status == SignalStatus.ACTIVE)
                .order_by(desc(Signal.created_at))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_signals_by_symbol(
        self, 
        symbol: str, 
        limit: int = 100, 
        offset: int = 0,
        status: Optional[SignalStatus] = None
    ) -> List[Signal]:
        """
        Get signals for a specific symbol.
        
        Args:
            symbol: Stock symbol
            limit: Maximum number of signals to return
            offset: Number of signals to skip
            status: Optional status filter
            
        Returns:
            List of signals for the symbol
        """
        async with get_db_session() as session:
            query = select(Signal).where(Signal.symbol == symbol)
            
            if status:
                query = query.where(Signal.status == status)
            
            result = await session.execute(
                query.order_by(desc(Signal.created_at))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_signals_by_agent(
        self,
        agent_name: str,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Signal]:
        """
        Get signals generated by a specific agent.
        
        Args:
            agent_name: Name of the AI agent
            limit: Maximum number of signals to return
            offset: Number of signals to skip
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            List of signals from the agent
        """
        async with get_db_session() as session:
            query = select(Signal).where(Signal.generating_agent == agent_name)
            
            if start_date:
                query = query.where(Signal.created_at >= start_date)
            if end_date:
                query = query.where(Signal.created_at <= end_date)
            
            result = await session.execute(
                query.order_by(desc(Signal.created_at))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_high_confidence_signals(
        self,
        min_confidence: float = 0.8,
        limit: int = 50,
        offset: int = 0
    ) -> List[Signal]:
        """
        Get high-confidence signals above threshold.
        
        Args:
            min_confidence: Minimum confidence threshold
            limit: Maximum number of signals to return
            offset: Number of signals to skip
            
        Returns:
            List of high-confidence signals
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(Signal)
                .where(and_(
                    Signal.confidence >= Decimal(str(min_confidence)),
                    Signal.status.in_([SignalStatus.PENDING, SignalStatus.ACTIVE])
                ))
                .order_by(desc(Signal.confidence), desc(Signal.created_at))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_recent_signals(
        self,
        hours: int = 24,
        limit: int = 100,
        offset: int = 0
    ) -> List[Signal]:
        """
        Get signals created within the last N hours.
        
        Args:
            hours: Number of hours to look back
            limit: Maximum number of signals to return
            offset: Number of signals to skip
            
        Returns:
            List of recent signals
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        async with get_db_session() as session:
            result = await session.execute(
                select(Signal)
                .where(Signal.created_at >= cutoff_time)
                .order_by(desc(Signal.created_at))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def update_signal_status(
        self,
        signal_id: str,
        status: SignalStatus,
        filled_price: Optional[float] = None,
        pnl: Optional[float] = None
    ) -> Optional[Signal]:
        """
        Update signal status and optional fill data.
        
        Args:
            signal_id: Signal identifier
            status: New signal status
            filled_price: Actual fill price (for filled signals)
            pnl: Profit/Loss amount (for filled signals)
            
        Returns:
            Updated signal if successful, None otherwise
        """
        update_data = {"status": status}
        
        if status == SignalStatus.FILLED:
            update_data["filled_at"] = datetime.now()
            
            if filled_price is not None:
                update_data["filled_price"] = Decimal(str(filled_price))
            
            if pnl is not None:
                update_data["pnl"] = Decimal(str(pnl))
        
        return await self.update_by_id(signal_id, **update_data)
    
    async def expire_old_signals(self) -> int:
        """
        Mark expired signals as expired based on expires_at timestamp.
        
        Returns:
            Number of signals that were expired
        """
        async with get_db_session() as session:
            # Use the cleanup function from migration
            result = await session.execute(text("SELECT cleanup_expired_signals()"))
            expired_count = result.scalar() or 0
            return expired_count
    
    async def get_signal_performance_stats(self, agent_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get aggregated performance statistics for signals.
        
        Args:
            agent_name: Optional agent name filter
            
        Returns:
            Dictionary with performance statistics
        """
        async with get_db_session() as session:
            base_query = select(
                func.count(Signal.id).label("total_signals"),
                func.count(Signal.id).filter(Signal.status == SignalStatus.FILLED).label("filled_signals"),
                func.count(Signal.id).filter(
                    and_(Signal.status == SignalStatus.FILLED, Signal.pnl > 0)
                ).label("profitable_signals"),
                func.avg(Signal.confidence).label("avg_confidence"),
                func.sum(Signal.pnl).label("total_pnl"),
                func.avg(Signal.pnl).filter(Signal.pnl.isnot(None)).label("avg_pnl")
            )
            
            if agent_name:
                base_query = base_query.where(Signal.generating_agent == agent_name)
            
            result = await session.execute(base_query)
            row = result.first()
            
            if row:
                total_signals = row.total_signals or 0
                filled_signals = row.filled_signals or 0
                profitable_signals = row.profitable_signals or 0
                
                return {
                    "total_signals": total_signals,
                    "filled_signals": filled_signals,
                    "profitable_signals": profitable_signals,
                    "pending_signals": total_signals - filled_signals,
                    "win_rate": (profitable_signals / filled_signals) if filled_signals > 0 else 0.0,
                    "avg_confidence": float(row.avg_confidence or 0),
                    "total_pnl": float(row.total_pnl or 0),
                    "avg_pnl": float(row.avg_pnl or 0)
                }
            
            return {
                "total_signals": 0,
                "filled_signals": 0,
                "profitable_signals": 0,
                "pending_signals": 0,
                "win_rate": 0.0,
                "avg_confidence": 0.0,
                "total_pnl": 0.0,
                "avg_pnl": 0.0
            }
    
    async def get_daily_signal_counts(
        self,
        days: int = 30,
        agent_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get daily signal counts using TimescaleDB time_bucket function.
        
        Args:
            days: Number of days to look back
            agent_name: Optional agent name filter
            
        Returns:
            List of daily counts with dates
        """
        start_date = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            query = """
                SELECT 
                    time_bucket('1 day', created_at) AS day,
                    COUNT(*) as signal_count,
                    AVG(confidence) as avg_confidence,
                    COUNT(*) FILTER (WHERE status = 'filled' AND pnl > 0) as profitable_count
                FROM signals
                WHERE created_at >= :start_date
            """
            
            params = {"start_date": start_date}
            
            if agent_name:
                query += " AND generating_agent = :agent_name"
                params["agent_name"] = agent_name
            
            query += """
                GROUP BY day
                ORDER BY day DESC
            """
            
            result = await session.execute(text(query), params)
            
            return [
                {
                    "date": row.day,
                    "signal_count": row.signal_count,
                    "avg_confidence": float(row.avg_confidence or 0),
                    "profitable_count": row.profitable_count
                }
                for row in result.fetchall()
            ]
    
    async def get_symbol_performance(self, symbol: str) -> Dict[str, Any]:
        """
        Get performance statistics for a specific symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with symbol performance data
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.count(Signal.id).label("total_signals"),
                    func.count(Signal.id).filter(Signal.status == SignalStatus.FILLED).label("filled_signals"),
                    func.count(Signal.id).filter(
                        and_(Signal.status == SignalStatus.FILLED, Signal.pnl > 0)
                    ).label("profitable_signals"),
                    func.avg(Signal.confidence).label("avg_confidence"),
                    func.sum(Signal.pnl).label("total_pnl"),
                    func.max(Signal.pnl).label("max_pnl"),
                    func.min(Signal.pnl).label("min_pnl")
                ).where(Signal.symbol == symbol)
            )
            
            row = result.first()
            
            if row:
                filled_signals = row.filled_signals or 0
                profitable_signals = row.profitable_signals or 0
                
                return {
                    "symbol": symbol,
                    "total_signals": row.total_signals or 0,
                    "filled_signals": filled_signals,
                    "profitable_signals": profitable_signals,
                    "win_rate": (profitable_signals / filled_signals) if filled_signals > 0 else 0.0,
                    "avg_confidence": float(row.avg_confidence or 0),
                    "total_pnl": float(row.total_pnl or 0),
                    "max_pnl": float(row.max_pnl or 0),
                    "min_pnl": float(row.min_pnl or 0)
                }
            
            return {
                "symbol": symbol,
                "total_signals": 0,
                "filled_signals": 0,
                "profitable_signals": 0,
                "win_rate": 0.0,
                "avg_confidence": 0.0,
                "total_pnl": 0.0,
                "max_pnl": 0.0,
                "min_pnl": 0.0
            } 