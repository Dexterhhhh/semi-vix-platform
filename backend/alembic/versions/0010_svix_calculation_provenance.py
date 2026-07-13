"""Persist SVIX calculation provenance.

Revision ID: 0010_svix_calculation_provenance
Revises: 0009_alpaca_provider
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_svix_calculation_provenance"
down_revision = "0009_alpaca_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing history was produced by the historical fallback path, therefore
    # the conservative backfill value is estimated=True.
    op.add_column("svix_history", sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("svix_history", sa.Column("source_feed", sa.String(length=64), nullable=True))
    op.add_column("svix_daily", sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("svix_daily", sa.Column("source_feed", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("svix_daily", "source_feed")
    op.drop_column("svix_daily", "estimated")
    op.drop_column("svix_history", "source_feed")
    op.drop_column("svix_history", "estimated")
