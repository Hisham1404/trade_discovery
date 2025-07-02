"""add_audit_logging_and_compliance_tables

Revision ID: 043cbdce6519
Revises: 28355cd48183
Create Date: 2025-07-02 12:49:08.963962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '043cbdce6519'
down_revision: Union[str, None] = '28355cd48183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create audit_log_metadata table for immutable audit logging
    op.create_table(
        'audit_log_metadata',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('action_type', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=True),
        sa.Column('service_id', sa.String(), nullable=True),
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('resource_id', sa.String(), nullable=True),
        sa.Column('resource_type', sa.String(), nullable=True),
        sa.Column('content_hash', sa.String(), nullable=False),
        sa.Column('s3_object_key', sa.String(), nullable=False),
        sa.Column('previous_hash', sa.String(), nullable=True),
        sa.Column('entry_hash', sa.String(), nullable=False),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for audit_log_metadata
    op.create_index('ix_audit_log_metadata_timestamp', 'audit_log_metadata', ['timestamp'])
    op.create_index('ix_audit_log_metadata_action_type', 'audit_log_metadata', ['action_type'])
    op.create_index('ix_audit_log_metadata_user_id', 'audit_log_metadata', ['user_id'])
    op.create_index('ix_audit_log_metadata_service_id', 'audit_log_metadata', ['service_id'])
    op.create_index('ix_audit_log_metadata_ip_address', 'audit_log_metadata', ['ip_address'])
    op.create_index('ix_audit_log_metadata_resource_id', 'audit_log_metadata', ['resource_id'])
    op.create_index('ix_audit_log_metadata_resource_type', 'audit_log_metadata', ['resource_type'])
    op.create_index('ix_audit_log_metadata_content_hash', 'audit_log_metadata', ['content_hash'])
    op.create_index('ix_audit_log_metadata_entry_hash', 'audit_log_metadata', ['entry_hash'])
    op.create_index('ix_audit_log_metadata_retention_until', 'audit_log_metadata', ['retention_until'])
    op.create_index('ix_audit_log_metadata_action_timestamp', 'audit_log_metadata', ['action_type', 'timestamp'])
    op.create_index('ix_audit_log_metadata_user_timestamp', 'audit_log_metadata', ['user_id', 'timestamp'])
    op.create_index('ix_audit_log_metadata_resource_timestamp', 'audit_log_metadata', ['resource_id', 'timestamp'])
    
    # Create compliance_reports table for SEBI compliance reports
    op.create_table(
        'compliance_reports',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('report_type', sa.String(), nullable=False),
        sa.Column('report_format', sa.String(), nullable=False),
        sa.Column('start_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('end_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generated_by', sa.String(), nullable=True),
        sa.Column('s3_object_key', sa.String(), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('report_hash', sa.String(), nullable=False),
        sa.Column('retention_until', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for compliance_reports
    op.create_index('ix_compliance_reports_report_type', 'compliance_reports', ['report_type'])
    op.create_index('ix_compliance_reports_start_date', 'compliance_reports', ['start_date'])
    op.create_index('ix_compliance_reports_end_date', 'compliance_reports', ['end_date'])
    op.create_index('ix_compliance_reports_generated_at', 'compliance_reports', ['generated_at'])
    op.create_index('ix_compliance_reports_generated_by', 'compliance_reports', ['generated_by'])
    op.create_index('ix_compliance_reports_retention_until', 'compliance_reports', ['retention_until'])
    op.create_index('ix_compliance_reports_type_date', 'compliance_reports', ['report_type', 'start_date', 'end_date'])


def downgrade() -> None:
    # Drop compliance_reports table and indexes
    op.drop_index('ix_compliance_reports_type_date', 'compliance_reports')
    op.drop_index('ix_compliance_reports_retention_until', 'compliance_reports')
    op.drop_index('ix_compliance_reports_generated_by', 'compliance_reports')
    op.drop_index('ix_compliance_reports_generated_at', 'compliance_reports')
    op.drop_index('ix_compliance_reports_end_date', 'compliance_reports')
    op.drop_index('ix_compliance_reports_start_date', 'compliance_reports')
    op.drop_index('ix_compliance_reports_report_type', 'compliance_reports')
    op.drop_table('compliance_reports')
    
    # Drop audit_log_metadata table and indexes
    op.drop_index('ix_audit_log_metadata_resource_timestamp', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_user_timestamp', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_action_timestamp', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_retention_until', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_entry_hash', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_content_hash', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_resource_type', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_resource_id', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_ip_address', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_service_id', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_user_id', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_action_type', 'audit_log_metadata')
    op.drop_index('ix_audit_log_metadata_timestamp', 'audit_log_metadata')
    op.drop_table('audit_log_metadata')
