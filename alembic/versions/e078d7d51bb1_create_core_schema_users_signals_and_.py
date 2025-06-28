"""Create core schema - users, signals, and market data tables

Revision ID: e078d7d51bb1
Revises: eac8f58a5e2b
Create Date: 2025-06-28 08:59:39.574756

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e078d7d51bb1'
down_revision: Union[str, None] = 'eac8f58a5e2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create core schema for the Discovery Cluster trading platform."""
    
    # Create custom types (Enums)
    op.execute("CREATE TYPE signal_direction AS ENUM ('long', 'short');")
    op.execute("CREATE TYPE signal_status AS ENUM ('pending', 'active', 'filled', 'cancelled', 'expired');")
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.dialects.postgresql.UUID(), nullable=False, comment='Unique user identifier'),
        sa.Column('email', sa.String(length=255), nullable=False, comment='User email address'),
        sa.Column('phone', sa.String(length=20), nullable=False, comment='Indian phone number with country code'),
        sa.Column('password_hash', sa.String(length=255), nullable=False, comment='Bcrypt hashed password'),
        sa.Column('full_name', sa.String(length=100), nullable=False, comment='User full name'),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True, comment='Whether user account is active'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, default=False, comment='Whether user has verified email/phone'),
        sa.Column('verification_code', sa.String(length=6), nullable=True, comment='6-digit verification code'),
        sa.Column('verification_code_expires', sa.DateTime(timezone=True), nullable=True, comment='Verification code expiration time'),
        sa.Column('totp_secret', sa.String(length=32), nullable=True, comment='TOTP secret for 2FA'),
        sa.Column('is_2fa_enabled', sa.Boolean(), nullable=False, default=False, comment='Whether 2FA is enabled'),
        sa.Column('backup_codes', sa.dialects.postgresql.ARRAY(sa.String()), nullable=True, comment='2FA backup codes'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Account creation timestamp'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True, comment='Last update timestamp'),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True, comment='Last login timestamp'),
        sa.PrimaryKeyConstraint('id'),
        comment='User authentication and profile data'
    )
    
    # Create indexes for users table
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_phone', 'users', ['phone'], unique=True)
    
    # Create signals table
    op.create_table(
        'signals',
        sa.Column('id', sa.dialects.postgresql.UUID(), nullable=False, comment='Unique signal identifier'),
        sa.Column('symbol', sa.String(length=20), nullable=False, comment='Stock symbol (e.g., RELIANCE, TCS)'),
        sa.Column('direction', sa.Enum('long', 'short', name='signal_direction'), nullable=False, comment='Signal direction: long or short'),
        sa.Column('confidence', sa.Numeric(precision=3, scale=2), nullable=False, comment='Confidence score between 0.00 and 1.00'),
        sa.Column('stop_loss', sa.Numeric(precision=10, scale=2), nullable=True, comment='Stop loss price level'),
        sa.Column('target', sa.Numeric(precision=10, scale=2), nullable=True, comment='Target price level'),
        sa.Column('entry_price', sa.Numeric(precision=10, scale=2), nullable=True, comment='Suggested entry price'),
        sa.Column('generating_agent', sa.String(length=100), nullable=False, comment='Name of the AI agent that generated this signal'),
        sa.Column('rationale', sa.Text(), nullable=True, comment='Human-readable explanation of the signal'),
        sa.Column('shap_values', sa.dialects.postgresql.JSONB(), nullable=True, comment='SHAP explainability values for feature importance'),
        sa.Column('technical_indicators', sa.dialects.postgresql.JSONB(), nullable=True, comment='Technical analysis indicators used'),
        sa.Column('status', sa.Enum('pending', 'active', 'filled', 'cancelled', 'expired', name='signal_status'), nullable=False, default='pending', comment='Current signal status'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Signal generation timestamp'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, comment='Signal expiration timestamp'),
        sa.Column('filled_at', sa.DateTime(timezone=True), nullable=True, comment='Timestamp when signal was filled'),
        sa.Column('filled_price', sa.Numeric(precision=10, scale=2), nullable=True, comment='Actual fill price'),
        sa.Column('pnl', sa.Numeric(precision=12, scale=4), nullable=True, comment='Profit/Loss realized'),
        sa.PrimaryKeyConstraint('id'),
        comment='Trading signals generated by AI agents'
    )
    
    # Create indexes for signals table
    op.create_index('ix_signals_symbol', 'signals', ['symbol'])
    op.create_index('ix_signals_generating_agent', 'signals', ['generating_agent'])
    op.create_index('ix_signals_status', 'signals', ['status'])
    op.create_index('ix_signals_created_at', 'signals', ['created_at'])
    op.create_index('idx_signals_symbol_time', 'signals', ['symbol', 'created_at'])
    op.create_index('idx_signals_agent_time', 'signals', ['generating_agent', 'created_at'])
    op.create_index('idx_signals_status_created', 'signals', ['status', 'created_at'])
    
    # Create market_ticks table
    op.create_table(
        'market_ticks',
        sa.Column('symbol', sa.String(length=20), nullable=False, comment='Stock symbol'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, comment='Market data timestamp'),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False, comment='Current price'),
        sa.Column('volume', sa.dialects.postgresql.BIGINT(), nullable=True, comment='Trading volume'),
        sa.Column('bid', sa.Numeric(precision=10, scale=2), nullable=True, comment='Bid price'),
        sa.Column('ask', sa.Numeric(precision=10, scale=2), nullable=True, comment='Ask price'),
        sa.Column('high', sa.Numeric(precision=10, scale=2), nullable=True, comment='Day high'),
        sa.Column('low', sa.Numeric(precision=10, scale=2), nullable=True, comment='Day low'),
        sa.Column('open_price', sa.Numeric(precision=10, scale=2), nullable=True, comment='Opening price'),
        sa.Column('close_price', sa.Numeric(precision=10, scale=2), nullable=True, comment='Previous close price'),
        sa.Column('exchange', sa.String(length=10), nullable=True, comment='Exchange identifier (NSE, BSE)'),
        sa.PrimaryKeyConstraint('symbol', 'timestamp'),
        comment='Real-time market data ticks for TimescaleDB'
    )
    
    # Create indexes for market_ticks table
    op.create_index('idx_market_ticks_symbol_time', 'market_ticks', ['symbol', 'timestamp'])
    op.create_index('idx_market_ticks_time', 'market_ticks', ['timestamp'])
    
    # Create agent_performance table
    op.create_table(
        'agent_performance',
        sa.Column('id', sa.dialects.postgresql.UUID(), nullable=False, comment='Unique performance record identifier'),
        sa.Column('agent_name', sa.String(length=100), nullable=False, comment='Name of the AI agent'),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False, comment='Performance measurement period start'),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False, comment='Performance measurement period end'),
        sa.Column('total_signals', sa.Integer(), nullable=False, default=0, comment='Total signals generated in period'),
        sa.Column('successful_signals', sa.Integer(), nullable=False, default=0, comment='Number of profitable signals'),
        sa.Column('total_pnl', sa.Numeric(precision=15, scale=4), nullable=False, default=0.0, comment='Total profit/loss'),
        sa.Column('win_rate', sa.Numeric(precision=5, scale=4), nullable=False, default=0.0, comment='Win rate as percentage (0.0000 to 1.0000)'),
        sa.Column('avg_confidence', sa.Numeric(precision=3, scale=2), nullable=False, default=0.0, comment='Average confidence score'),
        sa.Column('sharpe_ratio', sa.Numeric(precision=8, scale=4), nullable=True, comment='Risk-adjusted return metric'),
        sa.Column('max_drawdown', sa.Numeric(precision=8, scale=4), nullable=True, comment='Maximum drawdown percentage'),
        sa.Column('metrics_detail', sa.dialects.postgresql.JSONB(), nullable=True, comment='Additional performance metrics'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Record creation timestamp'),
        sa.PrimaryKeyConstraint('id'),
        comment='AI agent performance tracking and metrics'
    )
    
    # Create indexes for agent_performance table
    op.create_index('ix_agent_performance_agent_name', 'agent_performance', ['agent_name'])
    op.create_index('ix_agent_performance_created_at', 'agent_performance', ['created_at'])
    op.create_index('idx_agent_perf_name_period', 'agent_performance', ['agent_name', 'period_start', 'period_end'])
    
    # TimescaleDB: Convert market_ticks to hypertable with 1-day chunks
    op.execute("""
        SELECT create_hypertable(
            'market_ticks', 
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
    """)
    
    # TimescaleDB: Add 7-year retention policy for market_ticks
    op.execute("""
        SELECT add_retention_policy(
            'market_ticks', 
            INTERVAL '7 years',
            if_not_exists => TRUE
        );
    """)
    
    # Add check constraints for data validation
    op.create_check_constraint(
        'ck_signals_confidence',
        'signals',
        'confidence >= 0.00 AND confidence <= 1.00'
    )
    
    op.create_check_constraint(
        'ck_agent_performance_win_rate',
        'agent_performance',
        'win_rate >= 0.0000 AND win_rate <= 1.0000'
    )
    
    # Add triggers to automatically update updated_at columns
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    op.execute("""
        CREATE TRIGGER update_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
    """)


def downgrade() -> None:
    """Remove core schema and all related objects."""
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_users_updated_at ON users;")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    
    # Drop check constraints
    op.drop_constraint('ck_agent_performance_win_rate', 'agent_performance', type_='check')
    op.drop_constraint('ck_signals_confidence', 'signals', type_='check')
    
    # Drop indexes (explicit drops for clarity)
    op.drop_index('idx_agent_perf_name_period', 'agent_performance')
    op.drop_index('ix_agent_performance_created_at', 'agent_performance')
    op.drop_index('ix_agent_performance_agent_name', 'agent_performance')
    
    op.drop_index('idx_market_ticks_time', 'market_ticks')
    op.drop_index('idx_market_ticks_symbol_time', 'market_ticks')
    
    op.drop_index('idx_signals_status_created', 'signals')
    op.drop_index('idx_signals_agent_time', 'signals')
    op.drop_index('idx_signals_symbol_time', 'signals')
    op.drop_index('ix_signals_created_at', 'signals')
    op.drop_index('ix_signals_status', 'signals')
    op.drop_index('ix_signals_generating_agent', 'signals')
    op.drop_index('ix_signals_symbol', 'signals')
    
    op.drop_index('ix_users_phone', 'users')
    op.drop_index('ix_users_email', 'users')
    
    # Drop tables (in reverse dependency order)
    op.drop_table('agent_performance')
    op.drop_table('market_ticks')
    op.drop_table('signals')
    op.drop_table('users')
    
    # Drop custom types
    op.execute("DROP TYPE IF EXISTS signal_status;")
    op.execute("DROP TYPE IF EXISTS signal_direction;")
