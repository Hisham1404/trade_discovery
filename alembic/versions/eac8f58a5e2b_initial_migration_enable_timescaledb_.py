"""Initial migration: Enable TimescaleDB extension

Revision ID: eac8f58a5e2b
Revises: 
Create Date: 2025-06-28 08:58:22.623594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eac8f58a5e2b'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Enable TimescaleDB extension and set up the database for time-series data."""
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")
    
    # Create a function to check if TimescaleDB is properly installed
    op.execute("""
        CREATE OR REPLACE FUNCTION check_timescaledb_installation()
        RETURNS TEXT AS $$
        BEGIN
            -- Check if TimescaleDB extension is installed
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                RETURN 'TimescaleDB extension is installed and ready.';
            ELSE
                RETURN 'TimescaleDB extension is not installed.';
            END IF;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Remove TimescaleDB setup (Note: Extension removal requires manual intervention)."""
    # Drop the check function
    op.execute("DROP FUNCTION IF EXISTS check_timescaledb_installation();")
    
    # Note: We don't drop the TimescaleDB extension here as it may be used by other databases
    # and requires manual intervention to safely remove. The extension should be dropped manually if needed:
    # DROP EXTENSION IF EXISTS timescaledb CASCADE;
