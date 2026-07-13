"""Add an independent seconds-based intraday interval.

Revision ID: 0012_intraday_interval_seconds
Revises: 0011_market_collection_runs
"""

from alembic import op
import sqlalchemy as sa

revision = "0012_intraday_interval_seconds"
down_revision = "0011_market_collection_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_collection_runs", sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"))


def downgrade() -> None:
    op.drop_column("market_collection_runs", "interval_seconds")
