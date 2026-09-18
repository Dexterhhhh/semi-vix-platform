"""Persist market-data identity and result method metadata.

Revision ID: 0014_market_data_identity
Revises: 0013_custom_indices
"""

from alembic import op
import sqlalchemy as sa


revision = "0014_market_data_identity"
down_revision = "0013_custom_indices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("option_snapshot", "stock_snapshot"):
        op.add_column(table_name, sa.Column("feed", sa.String(32), nullable=True))
        op.add_column(
            table_name,
            sa.Column("price_type", sa.String(32), nullable=False, server_default="unknown"),
        )
        op.add_column(
            table_name,
            sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.add_column(table_name, sa.Column("batch_id", sa.String(64), nullable=True))
        op.create_index(f"ix_{table_name}_batch_id", table_name, ["batch_id"])
        op.execute(
            sa.text(f"UPDATE {table_name} SET received_at = timestamp WHERE received_at IS NULL")
        )
        op.alter_column(table_name, "received_at", nullable=False)

    op.add_column(
        "svix_history",
        sa.Column("calculation_method", sa.String(32), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "svix_history",
        sa.Column("market_data_quality", sa.String(32), nullable=False, server_default="unknown"),
    )
    for table_name in ("svix_daily", "custom_index_daily"):
        op.add_column(table_name, sa.Column("open_timestamp", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table_name, sa.Column("close_timestamp", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    for table_name in ("custom_index_daily", "svix_daily"):
        op.drop_column(table_name, "close_timestamp")
        op.drop_column(table_name, "open_timestamp")
    op.drop_column("svix_history", "market_data_quality")
    op.drop_column("svix_history", "calculation_method")
    for table_name in ("stock_snapshot", "option_snapshot"):
        op.drop_index(f"ix_{table_name}_batch_id", table_name=table_name)
        op.drop_column(table_name, "batch_id")
        op.drop_column(table_name, "received_at")
        op.drop_column(table_name, "price_type")
        op.drop_column(table_name, "feed")
