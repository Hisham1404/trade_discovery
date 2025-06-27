-- Discovery Cluster Database Initialization
-- Trading Signal Generation Platform

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- Create schemas
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS monitoring;
CREATE SCHEMA IF NOT EXISTS agents;

-- Set timezone
SET timezone = 'Asia/Kolkata';

-- Create basic tables structure (will be expanded in future tasks)

-- Trading signals table (time-series)
CREATE TABLE IF NOT EXISTS trading.signals (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    signal_type VARCHAR(20) NOT NULL, -- 'BUY', 'SELL', 'HOLD'
    confidence DECIMAL(5,4) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    price DECIMAL(12,4) NOT NULL,
    volume BIGINT,
    agent_id VARCHAR(50) NOT NULL,
    rationale TEXT,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('trading.signals', 'timestamp', if_not_exists => TRUE);

-- Market data table (time-series)
CREATE TABLE IF NOT EXISTS trading.market_data (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    symbol VARCHAR(20) NOT NULL,
    open_price DECIMAL(12,4) NOT NULL,
    high_price DECIMAL(12,4) NOT NULL,
    low_price DECIMAL(12,4) NOT NULL,
    close_price DECIMAL(12,4) NOT NULL,
    volume BIGINT NOT NULL,
    source VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('trading.market_data', 'timestamp', if_not_exists => TRUE);

-- Agents performance tracking
CREATE TABLE IF NOT EXISTS agents.performance (
    id BIGSERIAL PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    accuracy DECIMAL(5,4),
    precision_score DECIMAL(5,4),
    recall DECIMAL(5,4),
    sharpe_ratio DECIMAL(8,4),
    total_signals BIGINT DEFAULT 0,
    successful_signals BIGINT DEFAULT 0,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('agents.performance', 'timestamp', if_not_exists => TRUE);

-- System monitoring events
CREATE TABLE IF NOT EXISTS monitoring.events (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    component VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL, -- 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
    message TEXT NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Convert to hypertable
SELECT create_hypertable('monitoring.events', 'timestamp', if_not_exists => TRUE);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_signals_symbol_timestamp ON trading.signals (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_agent_timestamp ON trading.signals (agent_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp ON trading.market_data (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_agent_performance_timestamp ON agents.performance (agent_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_monitoring_events_component ON monitoring.events (component, timestamp DESC);

-- Create sample data for testing
INSERT INTO trading.signals (symbol, signal_type, confidence, price, agent_id, rationale) 
VALUES 
    ('RELIANCE', 'BUY', 0.85, 2450.50, 'technical_agent_001', 'RSI oversold, bullish divergence detected'),
    ('TCS', 'HOLD', 0.72, 3920.25, 'fundamental_agent_001', 'Strong fundamentals, waiting for better entry'),
    ('INFY', 'SELL', 0.78, 1580.75, 'technical_agent_001', 'Breaking support, volume confirmation')
ON CONFLICT DO NOTHING;

INSERT INTO monitoring.events (event_type, component, severity, message, metadata)
VALUES 
    ('STARTUP', 'database', 'INFO', 'Discovery Cluster database initialized successfully', '{"version": "1.0.0"}'),
    ('SCHEMA_CREATED', 'database', 'INFO', 'TimescaleDB hypertables created', '{"tables": 4}')
ON CONFLICT DO NOTHING;

-- Create user for application
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user WITH LOGIN PASSWORD 'app_secure_password';
    END IF;
END
$$;

-- Grant permissions
GRANT USAGE ON SCHEMA trading TO app_user;
GRANT USAGE ON SCHEMA monitoring TO app_user;
GRANT USAGE ON SCHEMA agents TO app_user;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA trading TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA monitoring TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA agents TO app_user;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA trading TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA monitoring TO app_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA agents TO app_user;

-- Set default permissions for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA trading GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA monitoring GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA agents GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user;

\echo 'Discovery Cluster database initialized successfully!' 