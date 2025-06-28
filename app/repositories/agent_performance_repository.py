"""
Agent performance repository for tracking AI agent metrics and performance.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from decimal import Decimal
from sqlalchemy import select, and_, desc, asc, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import AgentPerformance
from app.core.database import get_db_session
from .base_repository import BaseRepository


class AgentPerformanceRepository(BaseRepository[AgentPerformance]):
    """
    Repository for AgentPerformance entity with analytics operations.
    """
    
    def __init__(self):
        super().__init__(AgentPerformance)
    
    async def record_performance(
        self,
        agent_name: str,
        period_start: datetime,
        period_end: datetime,
        total_signals: int,
        successful_signals: int,
        total_pnl: float,
        win_rate: float,
        avg_confidence: float,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None,
        metrics_detail: Optional[Dict[str, Any]] = None
    ) -> AgentPerformance:
        """
        Record performance metrics for an AI agent.
        
        Args:
            agent_name: Name of the AI agent
            period_start: Performance measurement period start
            period_end: Performance measurement period end
            total_signals: Total signals generated
            successful_signals: Number of profitable signals
            total_pnl: Total profit/loss
            win_rate: Win rate percentage (0.0 to 1.0)
            avg_confidence: Average confidence score
            sharpe_ratio: Risk-adjusted return metric
            max_drawdown: Maximum drawdown percentage
            metrics_detail: Additional performance metrics
            
        Returns:
            Created performance record
        """
        return await self.create(
            agent_name=agent_name,
            period_start=period_start,
            period_end=period_end,
            total_signals=total_signals,
            successful_signals=successful_signals,
            total_pnl=Decimal(str(total_pnl)),
            win_rate=Decimal(str(win_rate)),
            avg_confidence=Decimal(str(avg_confidence)),
            sharpe_ratio=Decimal(str(sharpe_ratio)) if sharpe_ratio is not None else None,
            max_drawdown=Decimal(str(max_drawdown)) if max_drawdown is not None else None,
            metrics_detail=metrics_detail
        )
    
    async def get_agent_performance_history(
        self,
        agent_name: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[AgentPerformance]:
        """
        Get performance history for a specific agent.
        
        Args:
            agent_name: Name of the AI agent
            limit: Maximum number of records to return
            offset: Number of records to skip
            
        Returns:
            List of performance records for the agent
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(AgentPerformance)
                .where(AgentPerformance.agent_name == agent_name)
                .order_by(desc(AgentPerformance.period_end))
                .limit(limit)
                .offset(offset)
            )
            return list(result.scalars().all())
    
    async def get_latest_performance(self, agent_name: str) -> Optional[AgentPerformance]:
        """
        Get the most recent performance record for an agent.
        
        Args:
            agent_name: Name of the AI agent
            
        Returns:
            Latest performance record if found, None otherwise
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(AgentPerformance)
                .where(AgentPerformance.agent_name == agent_name)
                .order_by(desc(AgentPerformance.period_end))
                .limit(1)
            )
            return result.scalar_one_or_none()
    
    async def get_performance_in_period(
        self,
        agent_name: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[AgentPerformance]:
        """
        Get performance records for an agent within a date range.
        
        Args:
            agent_name: Name of the AI agent
            start_date: Start of date range
            end_date: End of date range
            
        Returns:
            List of performance records in the date range
        """
        async with get_db_session() as session:
            result = await session.execute(
                select(AgentPerformance)
                .where(and_(
                    AgentPerformance.agent_name == agent_name,
                    AgentPerformance.period_end >= start_date,
                    AgentPerformance.period_start <= end_date
                ))
                .order_by(desc(AgentPerformance.period_end))
            )
            return list(result.scalars().all())
    
    async def get_top_performing_agents(
        self,
        metric: str = "total_pnl",  # total_pnl, win_rate, sharpe_ratio
        days: int = 30,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top performing agents based on a specific metric.
        
        Args:
            metric: Performance metric to rank by
            days: Number of days to look back
            limit: Maximum number of agents to return
            
        Returns:
            List of top performing agents with their metrics
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            # Map metric names to database columns
            metric_map = {
                "total_pnl": func.sum(AgentPerformance.total_pnl),
                "win_rate": func.avg(AgentPerformance.win_rate),
                "sharpe_ratio": func.avg(AgentPerformance.sharpe_ratio),
                "avg_confidence": func.avg(AgentPerformance.avg_confidence)
            }
            
            order_column = metric_map.get(metric, func.sum(AgentPerformance.total_pnl))
            
            result = await session.execute(
                select(
                    AgentPerformance.agent_name,
                    func.sum(AgentPerformance.total_signals).label("total_signals"),
                    func.sum(AgentPerformance.successful_signals).label("successful_signals"),
                    func.sum(AgentPerformance.total_pnl).label("total_pnl"),
                    func.avg(AgentPerformance.win_rate).label("avg_win_rate"),
                    func.avg(AgentPerformance.avg_confidence).label("avg_confidence"),
                    func.avg(AgentPerformance.sharpe_ratio).label("avg_sharpe_ratio"),
                    func.avg(AgentPerformance.max_drawdown).label("avg_max_drawdown"),
                    func.count(AgentPerformance.id).label("record_count")
                )
                .where(AgentPerformance.period_end >= cutoff_date)
                .group_by(AgentPerformance.agent_name)
                .order_by(desc(order_column))
                .limit(limit)
            )
            
            return [
                {
                    "agent_name": row.agent_name,
                    "total_signals": row.total_signals or 0,
                    "successful_signals": row.successful_signals or 0,
                    "total_pnl": float(row.total_pnl or 0),
                    "avg_win_rate": float(row.avg_win_rate or 0),
                    "avg_confidence": float(row.avg_confidence or 0),
                    "avg_sharpe_ratio": float(row.avg_sharpe_ratio or 0) if row.avg_sharpe_ratio else None,
                    "avg_max_drawdown": float(row.avg_max_drawdown or 0) if row.avg_max_drawdown else None,
                    "record_count": row.record_count,
                    "ranking_metric": metric,
                    "ranking_value": float(getattr(row, f"total_{metric}" if metric == "pnl" else f"avg_{metric}", 0))
                }
                for row in result.fetchall()
            ]
    
    async def get_agent_comparison(
        self,
        agent_names: List[str],
        days: int = 30
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compare performance metrics across multiple agents.
        
        Args:
            agent_names: List of agent names to compare
            days: Number of days to look back
            
        Returns:
            Dictionary with agent performance comparisons
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    AgentPerformance.agent_name,
                    func.sum(AgentPerformance.total_signals).label("total_signals"),
                    func.sum(AgentPerformance.successful_signals).label("successful_signals"),
                    func.sum(AgentPerformance.total_pnl).label("total_pnl"),
                    func.avg(AgentPerformance.win_rate).label("avg_win_rate"),
                    func.avg(AgentPerformance.avg_confidence).label("avg_confidence"),
                    func.avg(AgentPerformance.sharpe_ratio).label("avg_sharpe_ratio"),
                    func.avg(AgentPerformance.max_drawdown).label("avg_max_drawdown")
                )
                .where(and_(
                    AgentPerformance.agent_name.in_(agent_names),
                    AgentPerformance.period_end >= cutoff_date
                ))
                .group_by(AgentPerformance.agent_name)
            )
            
            comparison = {}
            for row in result.fetchall():
                total_signals = row.total_signals or 0
                successful_signals = row.successful_signals or 0
                
                comparison[row.agent_name] = {
                    "total_signals": total_signals,
                    "successful_signals": successful_signals,
                    "failed_signals": total_signals - successful_signals,
                    "success_rate": (successful_signals / total_signals) if total_signals > 0 else 0.0,
                    "total_pnl": float(row.total_pnl or 0),
                    "avg_win_rate": float(row.avg_win_rate or 0),
                    "avg_confidence": float(row.avg_confidence or 0),
                    "avg_sharpe_ratio": float(row.avg_sharpe_ratio or 0) if row.avg_sharpe_ratio else None,
                    "avg_max_drawdown": float(row.avg_max_drawdown or 0) if row.avg_max_drawdown else None
                }
            
            return comparison
    
    async def compare_agents_performance(self, agent_names: List[str], days: int = 30) -> List[Dict[str, Any]]:
        """Alias for get_agent_comparison for backward compatibility with tests."""
        comparison_dict = await self.get_agent_comparison(agent_names, days)
        
        # Convert dict to list of dicts for test compatibility
        return [
            {"agent_name": agent, **metrics}
            for agent, metrics in comparison_dict.items()
        ]
    
    async def get_performance_trends(
        self,
        agent_name: str,
        days: int = 90
    ) -> List[Dict[str, Any]]:
        """
        Get performance trend data for an agent using TimescaleDB time_bucket.
        
        Args:
            agent_name: Name of the AI agent
            days: Number of days to look back
            
        Returns:
            List of performance trend data points
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            query = """
                SELECT 
                    time_bucket('7 days', period_end) AS week,
                    AVG(total_pnl) as avg_pnl,
                    AVG(win_rate) as avg_win_rate,
                    AVG(avg_confidence) as avg_confidence,
                    AVG(sharpe_ratio) as avg_sharpe_ratio,
                    SUM(total_signals) as total_signals,
                    SUM(successful_signals) as successful_signals
                FROM agent_performance
                WHERE agent_name = :agent_name
                AND period_end >= :cutoff_date
                GROUP BY week
                ORDER BY week ASC
            """
            
            result = await session.execute(
                text(query),
                {
                    "agent_name": agent_name,
                    "cutoff_date": cutoff_date
                }
            )
            
            return [
                {
                    "week": row.week.date(),
                    "avg_pnl": float(row.avg_pnl or 0),
                    "avg_win_rate": float(row.avg_win_rate or 0),
                    "avg_confidence": float(row.avg_confidence or 0),
                    "avg_sharpe_ratio": float(row.avg_sharpe_ratio or 0) if row.avg_sharpe_ratio else None,
                    "total_signals": int(row.total_signals or 0),
                    "successful_signals": int(row.successful_signals or 0)
                }
                for row in result.fetchall()
            ]
    
    async def get_agent_statistics(
        self,
        agent_name: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get comprehensive statistics for agents.
        
        Args:
            agent_name: Optional specific agent name, None for all agents
            days: Number of days to look back
            
        Returns:
            Dictionary with comprehensive agent statistics
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            base_query = select(
                func.count(AgentPerformance.id).label("record_count"),
                func.count(func.distinct(AgentPerformance.agent_name)).label("unique_agents"),
                func.sum(AgentPerformance.total_signals).label("total_signals"),
                func.sum(AgentPerformance.successful_signals).label("successful_signals"),
                func.sum(AgentPerformance.total_pnl).label("total_pnl"),
                func.avg(AgentPerformance.win_rate).label("avg_win_rate"),
                func.avg(AgentPerformance.avg_confidence).label("avg_confidence"),
                func.max(AgentPerformance.total_pnl).label("max_pnl"),
                func.min(AgentPerformance.total_pnl).label("min_pnl"),
                func.stddev(AgentPerformance.total_pnl).label("pnl_stddev")
            ).where(AgentPerformance.period_end >= cutoff_date)
            
            if agent_name:
                base_query = base_query.where(AgentPerformance.agent_name == agent_name)
            
            result = await session.execute(base_query)
            row = result.first()
            
            if row and row.record_count > 0:
                total_signals = row.total_signals or 0
                successful_signals = row.successful_signals or 0
                
                return {
                    "period_days": days,
                    "record_count": row.record_count,
                    "unique_agents": row.unique_agents if not agent_name else 1,
                    "total_signals": total_signals,
                    "successful_signals": successful_signals,
                    "failed_signals": total_signals - successful_signals,
                    "overall_success_rate": (successful_signals / total_signals) if total_signals > 0 else 0.0,
                    "total_pnl": float(row.total_pnl or 0),
                    "avg_win_rate": float(row.avg_win_rate or 0),
                    "avg_confidence": float(row.avg_confidence or 0),
                    "max_pnl": float(row.max_pnl or 0),
                    "min_pnl": float(row.min_pnl or 0),
                    "pnl_stddev": float(row.pnl_stddev or 0),
                    "agent_name": agent_name
                }
            
            return {
                "period_days": days,
                "record_count": 0,
                "unique_agents": 0,
                "total_signals": 0,
                "successful_signals": 0,
                "failed_signals": 0,
                "overall_success_rate": 0.0,
                "total_pnl": 0.0,
                "avg_win_rate": 0.0,
                "avg_confidence": 0.0,
                "max_pnl": 0.0,
                "min_pnl": 0.0,
                "pnl_stddev": 0.0,
                "agent_name": agent_name
            }
    
    async def get_underperforming_agents(
        self,
        min_win_rate: float = 0.4,
        min_signals: int = 10,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Identify underperforming agents that may need attention.
        
        Args:
            min_win_rate: Minimum acceptable win rate
            min_signals: Minimum number of signals to be considered
            days: Number of days to look back
            
        Returns:
            List of underperforming agents with their metrics
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    AgentPerformance.agent_name,
                    func.sum(AgentPerformance.total_signals).label("total_signals"),
                    func.sum(AgentPerformance.successful_signals).label("successful_signals"),
                    func.sum(AgentPerformance.total_pnl).label("total_pnl"),
                    func.avg(AgentPerformance.win_rate).label("avg_win_rate"),
                    func.avg(AgentPerformance.avg_confidence).label("avg_confidence")
                )
                .where(AgentPerformance.period_end >= cutoff_date)
                .group_by(AgentPerformance.agent_name)
                .having(and_(
                    func.sum(AgentPerformance.total_signals) >= min_signals,
                    func.avg(AgentPerformance.win_rate) < min_win_rate
                ))
                .order_by(asc(func.avg(AgentPerformance.win_rate)))
            )
            
            return [
                {
                    "agent_name": row.agent_name,
                    "total_signals": row.total_signals or 0,
                    "successful_signals": row.successful_signals or 0,
                    "total_pnl": float(row.total_pnl or 0),
                    "avg_win_rate": float(row.avg_win_rate or 0),
                    "avg_confidence": float(row.avg_confidence or 0),
                    "performance_issues": {
                        "below_min_win_rate": float(row.avg_win_rate or 0) < min_win_rate,
                        "negative_pnl": float(row.total_pnl or 0) < 0
                    }
                }
                for row in result.fetchall()
            ] 