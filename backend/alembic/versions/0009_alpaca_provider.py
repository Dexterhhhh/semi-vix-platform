"""Add Alpaca market-data feed selection.

Revision ID: 0009_alpaca_provider
Revises: 0008_data_lifecycle
"""

from alembic import op
import sqlalchemy as sa

revision = "0009_alpaca_provider"
down_revision = "0008_data_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_credentials", sa.Column("data_feed", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_credentials", "data_feed")
