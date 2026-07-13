"""Track market-hours collection runs.

Revision ID: 0011_market_collection_runs
Revises: 0010_svix_calculation_provenance
"""

from alembic import op
import sqlalchemy as sa

revision = "0011_market_collection_runs"
down_revision = "0010_svix_calculation_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_collection_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("stock_quotes_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("option_quotes_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_succeeded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbols_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_market_collection_runs_session_date", "market_collection_runs", ["session_date"])
    op.create_index("ix_market_collection_runs_status", "market_collection_runs", ["status"])
    op.create_index("ix_market_collection_session_started", "market_collection_runs", ["session_date", "started_at"])


def downgrade() -> None:
    op.drop_table("market_collection_runs")
