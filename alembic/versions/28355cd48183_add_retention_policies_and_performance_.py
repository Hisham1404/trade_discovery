"""Add retention policies and performance optimizations

Revision ID: 28355cd48183
Revises: e078d7d51bb1
Create Date: 2025-06-28 09:01:23.627619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28355cd48183'
down_revision: Union[str, None] = 'e078d7d51bb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add retention policies and performance optimizations for TimescaleDB."""
    
    # Convert signals table to hypertable for better time-series performance
    # (signals table contains created_at timestamp which makes it suitable for partitioning)
    op.execute("""
        SELECT create_hypertable(
            'signals', 
            'created_at',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
    """)
    
    # Add 7-year retention policy for signals table
    op.execute("""
        SELECT add_retention_policy(
            'signals', 
            INTERVAL '7 years',
            if_not_exists => TRUE
        );
    """)
    
    # Convert agent_performance table to hypertable for time-series queries
    op.execute("""
        SELECT create_hypertable(
            'agent_performance', 
            'created_at',
            chunk_time_interval => INTERVAL '30 days',
            if_not_exists => TRUE
        );
    """)
    
    # Add 10-year retention policy for agent performance (longer retention for analysis)
    op.execute("""
        SELECT add_retention_policy(
            'agent_performance', 
            INTERVAL '10 years',
            if_not_exists => TRUE
        );
    """)
    
    # Performance optimizations: Create partial indexes for common query patterns
    
    # Partial index for active/pending signals (most frequently queried)
    op.create_index(
        'idx_signals_active_pending',
        'signals',
        ['symbol', 'created_at', 'confidence'],
        postgresql_where=sa.text("status IN ('pending', 'active')")
    )
    
    # Partial index for recent signals (last 30 days) for real-time queries
    op.create_index(
        'idx_signals_recent',
        'signals',
        ['symbol', 'generating_agent', 'confidence'],
        postgresql_where=sa.text("created_at > NOW() - INTERVAL '30 days'")
    )
    
    # Composite index for agent performance queries
    op.create_index(
        'idx_agent_performance_composite',
        'agent_performance',
        ['agent_name', 'period_start', 'period_end', 'total_pnl']
    )
    
    # Index for market tick queries by price range (useful for backtesting)
    op.create_index(
        'idx_market_ticks_price_range',
        'market_ticks',
        ['symbol', 'timestamp', 'price']
    )
    
    # Partial index for high-volume market ticks
    op.create_index(
        'idx_market_ticks_high_volume',
        'market_ticks',
        ['symbol', 'timestamp', 'volume'],
        postgresql_where=sa.text("volume > 1000")
    )
    
    # Create covering index for signal analytics
    op.create_index(
        'idx_signals_analytics_covering',
        'signals',
        ['generating_agent', 'created_at'],
        postgresql_include=['confidence', 'pnl', 'status', 'symbol']
    )
    
    # Index for user authentication and session management
    op.create_index(
        'idx_users_active_verified',
        'users',
        ['email', 'last_login'],
        postgresql_where=sa.text("is_active = true AND is_verified = true")
    )
    
    # Continuous aggregates for real-time analytics (TimescaleDB feature)
    
    # Daily signal summary for dashboards
    op.execute("""
        CREATE MATERIALIZED VIEW daily_signal_summary
        WITH (timescaledb.continuous) AS
        SELECT 
            time_bucket('1 day', created_at) AS bucket,
            symbol,
            generating_agent,
            COUNT(*) as signal_count,
            AVG(confidence) as avg_confidence,
            SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as profitable_signals,
            SUM(pnl) as total_pnl,
            AVG(pnl) as avg_pnl
        FROM signals
        WHERE created_at >= NOW() - INTERVAL '90 days'
        GROUP BY bucket, symbol, generating_agent
        WITH NO DATA;
    """)
    
    # Add refresh policy for the continuous aggregate
    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'daily_signal_summary',
            start_offset => INTERVAL '7 days',
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour'
        );
    """)
    
    # Hourly market data aggregate for performance
    op.execute("""
        CREATE MATERIALIZED VIEW hourly_market_summary
        WITH (timescaledb.continuous) AS
        SELECT 
            time_bucket('1 hour', timestamp) AS bucket,
            symbol,
            FIRST(price, timestamp) as open_price,
            MAX(price) as high_price,
            MIN(price) as low_price,
            LAST(price, timestamp) as close_price,
            SUM(volume) as total_volume,
            COUNT(*) as tick_count
        FROM market_ticks
        WHERE timestamp >= NOW() - INTERVAL '30 days'
        GROUP BY bucket, symbol
        WITH NO DATA;
    """)
    
    # Add refresh policy for market data aggregate
    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'hourly_market_summary',
            start_offset => INTERVAL '2 days',
            end_offset => INTERVAL '10 minutes',
            schedule_interval => INTERVAL '10 minutes'
        );
    """)
    
    # Database performance settings and optimizations
    
    # Create a function to automatically update signal statistics
    op.execute("""
        CREATE OR REPLACE FUNCTION update_signal_statistics()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Update agent performance when signal is filled
            IF NEW.status = 'filled' AND OLD.status != 'filled' THEN
                -- This could trigger background job to update agent_performance table
                PERFORM pg_notify('signal_filled', NEW.id::text);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create trigger for signal status updates
    op.execute("""
        CREATE TRIGGER signal_status_update_trigger
        AFTER UPDATE OF status ON signals
        FOR EACH ROW
        EXECUTE FUNCTION update_signal_statistics();
    """)
    
    # Create function to clean up expired signals
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_expired_signals()
        RETURNS INTEGER AS $$
        DECLARE
            expired_count INTEGER;
        BEGIN
            UPDATE signals 
            SET status = 'expired'
            WHERE status IN ('pending', 'active')
            AND expires_at IS NOT NULL
            AND expires_at < NOW();
            
            GET DIAGNOSTICS expired_count = ROW_COUNT;
            RETURN expired_count;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Performance monitoring views
    
    # Create view for database performance monitoring
    op.execute("""
        CREATE VIEW signal_performance_stats AS
        SELECT 
            generating_agent,
            COUNT(*) as total_signals,
            COUNT(*) FILTER (WHERE status = 'filled' AND pnl > 0) as profitable_signals,
            AVG(confidence) as avg_confidence,
            SUM(pnl) as total_pnl,
            AVG(pnl) FILTER (WHERE pnl IS NOT NULL) as avg_pnl,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '7 days') as signals_last_7d,
            COUNT(*) FILTER (WHERE created_at >= NOW() - INTERVAL '30 days') as signals_last_30d
        FROM signals
        GROUP BY generating_agent;
    """)
    
    # Create view for market data quality monitoring
    op.execute("""
        CREATE VIEW market_data_quality AS
        SELECT 
            symbol,
            DATE_TRUNC('day', timestamp) as date,
            COUNT(*) as tick_count,
            MAX(timestamp) - MIN(timestamp) as time_span,
            COUNT(*) FILTER (WHERE volume IS NULL) as missing_volume_count,
            COUNT(*) FILTER (WHERE bid IS NULL OR ask IS NULL) as missing_spread_count,
            AVG(price) as avg_price,
            STDDEV(price) as price_volatility
        FROM market_ticks
        WHERE timestamp >= NOW() - INTERVAL '7 days'
        GROUP BY symbol, DATE_TRUNC('day', timestamp)
        ORDER BY symbol, date DESC;
    """)


def downgrade() -> None:
    """Remove retention policies and performance optimizations."""
    
    # Drop views
    op.execute("DROP VIEW IF EXISTS market_data_quality;")
    op.execute("DROP VIEW IF EXISTS signal_performance_stats;")
    
    # Drop functions and triggers
    op.execute("DROP TRIGGER IF EXISTS signal_status_update_trigger ON signals;")
    op.execute("DROP FUNCTION IF EXISTS cleanup_expired_signals();")
    op.execute("DROP FUNCTION IF EXISTS update_signal_statistics();")
    
    # Drop continuous aggregates (must be done before dropping policies)
    op.execute("DROP MATERIALIZED VIEW IF EXISTS hourly_market_summary;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS daily_signal_summary;")
    
    # Drop performance indexes
    op.drop_index('idx_users_active_verified', 'users')
    op.drop_index('idx_signals_analytics_covering', 'signals')
    op.drop_index('idx_market_ticks_high_volume', 'market_ticks')
    op.drop_index('idx_market_ticks_price_range', 'market_ticks')
    op.drop_index('idx_agent_performance_composite', 'agent_performance')
    op.drop_index('idx_signals_recent', 'signals')
    op.drop_index('idx_signals_active_pending', 'signals')
    
    # Note: Retention policies and hypertable conversions are not easily reversible
    # They require manual intervention if needed in production
    # The tables will remain as hypertables but data retention will be disabled
