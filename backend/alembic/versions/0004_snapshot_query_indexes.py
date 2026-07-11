"""Add direct symbol/time indexes for historical snapshot queries."""

from alembic import op


revision = "0004_snapshot_query_indexes"
down_revision = "0003_harden_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_stock_snapshot_symbol_timestamp", "stock_snapshot", ["symbol", "timestamp"])
    op.create_index("ix_option_snapshot_symbol_timestamp", "option_snapshot", ["symbol", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_option_snapshot_symbol_timestamp", table_name="option_snapshot")
    op.drop_index("ix_stock_snapshot_symbol_timestamp", table_name="stock_snapshot")
