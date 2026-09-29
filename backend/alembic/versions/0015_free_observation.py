"""Add isolated free observation results and retain quote/trade provenance.

Revision ID: 0015_free_observation
Revises: 0014_market_data_identity
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_free_observation"
down_revision = "0014_market_data_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("option_snapshot", "stock_snapshot"):
        op.add_column(table, sa.Column("trade_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("market_collection_runs", sa.Column("batch_id", sa.String(64), nullable=True))
    op.add_column("market_collection_runs", sa.Column("calculation_status", sa.String(24), nullable=True))
    op.add_column("market_collection_runs", sa.Column("symbol_status", sa.Text(), nullable=True))
    op.add_column("market_collection_runs", sa.Column("collection_errors", sa.Text(), nullable=True))
    op.add_column("market_collection_runs", sa.Column("retry_after_seconds", sa.Integer(), nullable=True))
    op.create_unique_constraint("uq_market_collection_batch", "market_collection_runs", ["batch_id"])
    op.create_table("svix_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("valuation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("market_collection_runs.batch_id"), nullable=False),
        sa.Column("method_version", sa.String(64), nullable=False),
        sa.Column("svix", sa.Float()), sa.Column("core", sa.Float()),
        sa.Column("memory", sa.Float()), sa.Column("ai", sa.Float()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("coverage", sa.Float(), nullable=False),
        sa.Column("cached_coverage", sa.Float(), nullable=False),
        sa.Column("source_feed", sa.String(64)),
        sa.Column("details", sa.Text(), nullable=False),
        sa.UniqueConstraint("batch_id", "method_version", name="uq_svix_observation_batch_method"))
    op.create_index("ix_svix_observation_session_time", "svix_observations", ["session_date", "valuation_at"])
    op.create_table("svix_asset_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_date", sa.Date(), nullable=False),
        sa.Column("valuation_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("batch_id", sa.String(64), sa.ForeignKey("market_collection_runs.batch_id"), nullable=False),
        sa.Column("method_version", sa.String(64), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("volatility", sa.Float()),
        sa.Column("oldest_input_at", sa.DateTime(timezone=True)),
        sa.Column("newest_input_at", sa.DateTime(timezone=True)),
        sa.Column("term_method", sa.String(24)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.UniqueConstraint("batch_id", "method_version", "symbol", name="uq_svix_asset_batch_method_symbol"))
    op.create_index("ix_svix_asset_observations_session_date", "svix_asset_observations", ["session_date"])
    op.create_index("ix_svix_asset_observations_batch_id", "svix_asset_observations", ["batch_id"])
    op.create_table("svix_correlation_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assets", sa.String(256), nullable=False),
        sa.Column("matrix", sa.Text(), nullable=False),
        sa.UniqueConstraint("provider", "as_of", "assets", "available_at", name="uq_svix_corr_day_assets_time"))
    op.create_index("ix_svix_correlation_cache_as_of", "svix_correlation_cache", ["as_of"])


def downgrade() -> None:
    op.drop_table("svix_correlation_cache")
    op.drop_table("svix_asset_observations")
    op.drop_table("svix_observations")
    op.drop_constraint("uq_market_collection_batch", "market_collection_runs", type_="unique")
    for column in ("retry_after_seconds", "collection_errors", "symbol_status", "calculation_status", "batch_id"):
        op.drop_column("market_collection_runs", column)
    for table in ("stock_snapshot", "option_snapshot"):
        op.drop_column(table, "trade_timestamp")
