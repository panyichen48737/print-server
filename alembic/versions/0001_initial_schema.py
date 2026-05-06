"""Initial schema — matches the manual CREATE TABLE in repository.py.

Revision ID: 0001
Revises: None
Create Date: 2026-05-07
"""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None


def upgrade() -> None:
    op.create_table(
        'jobs',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('filename', sa.Text(), nullable=False),
        sa.Column('filepath', sa.Text(), nullable=False),
        sa.Column('file_size', sa.Integer(), server_default='0'),
        sa.Column('file_type', sa.Text(), server_default=''),
        sa.Column('status', sa.Text(), nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text(), server_default=''),
        sa.Column('printer_name', sa.Text(), server_default=''),
        sa.Column('copies', sa.Integer(), server_default='1'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('duplex', sa.Integer(), server_default='0'),
        sa.Column('color', sa.Integer(), server_default='1'),
        sa.Column('paper_size', sa.Text(), server_default="'A4'"),
        sa.Column('source', sa.Text(), server_default="'api'"),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
    )
    op.create_index('idx_jobs_status', 'jobs', ['status'])
    op.create_index('idx_jobs_created', 'jobs', ['created_at'])


def downgrade() -> None:
    op.drop_index('idx_jobs_status', table_name='jobs')
    op.drop_index('idx_jobs_created', table_name='jobs')
    op.drop_table('jobs')
