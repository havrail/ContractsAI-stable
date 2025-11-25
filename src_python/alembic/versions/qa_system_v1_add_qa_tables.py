"""Add QA fields and audit tables

Revision ID: qa_system_v1
Revises: b2341593c7f4
Create Date: 2025-11-25

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers, used by Alembic.
revision = 'qa_system_v1'
down_revision = 'b2341593c7f4'
branch_labels = None
depends_on = None


def upgrade():
    # Add QA fields to contracts table
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.add_column(sa.Column('needs_review', sa.Integer, default=0))
        batch_op.add_column(sa.Column('review_reason', sa.Text, nullable=True))
        batch_op.add_column(sa.Column('review_status', sa.String, default='pending'))
        batch_op.add_column(sa.Column('reviewed_by', sa.String, nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime, nullable=True))
        batch_op.add_column(sa.Column('validation_issues', sa.Integer, default=0))
        batch_op.add_column(sa.Column('validation_warnings', sa.Integer, default=0))
    
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('action_type', sa.String, nullable=False, index=True),
        sa.Column('entity_type', sa.String, nullable=False),
        sa.Column('entity_id', sa.Integer, nullable=True, index=True),
        sa.Column('user_id', sa.String, nullable=True, index=True),
        sa.Column('ip_address', sa.String, nullable=True),
        sa.Column('action_details', sa.Text, nullable=True),
        sa.Column('old_values', sa.Text, nullable=True),
        sa.Column('new_values', sa.Text, nullable=True),
        sa.Column('status', sa.String, default='success'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('timestamp', sa.DateTime, default=datetime.utcnow, index=True),
        sa.Column('session_id', sa.String, nullable=True),
        sa.Column('duration_ms', sa.Integer, nullable=True)
    )
    
    # Create export_versions table
    op.create_table(
        'export_versions',
        sa.Column('id', sa.Integer, primary_key=True, index=True),
        sa.Column('version_number', sa.Integer, nullable=False),
        sa.Column('export_path', sa.String, nullable=False),
        sa.Column('file_hash', sa.String, nullable=False, index=True),
        sa.Column('total_records', sa.Integer, default=0),
        sa.Column('record_hashes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime, default=datetime.utcnow, index=True),
        sa.Column('created_by', sa.String, nullable=True),
        sa.Column('notes', sa.Text, nullable=True)
    )


def downgrade():
    # Drop new tables
    op.drop_table('export_versions')
    op.drop_table('audit_logs')
    
    # Remove QA fields from contracts
    with op.batch_alter_table('contracts') as batch_op:
        batch_op.drop_column('validation_warnings')
        batch_op.drop_column('validation_issues')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('review_status')
        batch_op.drop_column('review_reason')
        batch_op.drop_column('needs_review')
