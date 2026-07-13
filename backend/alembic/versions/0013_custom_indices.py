"""Add versioned custom volatility indices.

Revision ID: 0013_custom_indices
Revises: 0012_intraday_interval_seconds
"""

from alembic import op
import sqlalchemy as sa

revision = "0013_custom_indices"
down_revision = "0012_intraday_interval_seconds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("custom_indices", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(64), nullable=False), sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("missing_policy", sa.String(16), nullable=False, server_default="STRICT"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("custom_index_versions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("custom_index_id", sa.Integer(), sa.ForeignKey("custom_indices.id", ondelete="CASCADE"), nullable=False), sa.Column("version_number", sa.Integer(), nullable=False), sa.Column("name", sa.String(64), nullable=False), sa.Column("missing_policy", sa.String(16), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("custom_index_id", "version_number", name="uq_custom_index_version"))
    op.create_index("ix_custom_index_versions_custom_index_id", "custom_index_versions", ["custom_index_id"])
    op.create_table("custom_index_components", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("version_id", sa.Integer(), sa.ForeignKey("custom_index_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("symbol", sa.String(16), nullable=False), sa.Column("weight", sa.Float(), nullable=False), sa.CheckConstraint("weight > 0 AND weight <= 1", name="custom_index_component_weight_range"), sa.UniqueConstraint("version_id", "symbol", name="uq_custom_index_component_symbol"))
    op.create_index("ix_custom_index_components_version_id", "custom_index_components", ["version_id"])
    op.create_index("ix_custom_index_components_symbol", "custom_index_components", ["symbol"])
    op.create_table("custom_index_history", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("custom_index_id", sa.Integer(), sa.ForeignKey("custom_indices.id", ondelete="CASCADE"), nullable=False), sa.Column("version_id", sa.Integer(), sa.ForeignKey("custom_index_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False), sa.Column("value", sa.Float(), nullable=False), sa.Column("calculation_quality", sa.Float(), nullable=False), sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("source_feed", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("custom_index_id", "version_id", "timestamp", name="uq_custom_index_history_point"))
    op.create_index("ix_custom_index_history_timestamp", "custom_index_history", ["timestamp"])
    op.create_index("ix_custom_index_history_index_timestamp", "custom_index_history", ["custom_index_id", "timestamp"])
    op.create_table("custom_index_daily", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("custom_index_id", sa.Integer(), sa.ForeignKey("custom_indices.id", ondelete="CASCADE"), nullable=False), sa.Column("version_id", sa.Integer(), sa.ForeignKey("custom_index_versions.id", ondelete="CASCADE"), nullable=False), sa.Column("date", sa.Date(), nullable=False), sa.Column("value_open", sa.Float(), nullable=False), sa.Column("value_high", sa.Float(), nullable=False), sa.Column("value_low", sa.Float(), nullable=False), sa.Column("value_close", sa.Float(), nullable=False), sa.Column("sample_count", sa.Integer(), nullable=False), sa.Column("min_calculation_quality", sa.Float(), nullable=False), sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("source_feed", sa.String(64)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("custom_index_id", "version_id", "date", name="uq_custom_index_daily_point"))
    op.create_index("ix_custom_index_daily_index_date", "custom_index_daily", ["custom_index_id", "date"])


def downgrade() -> None:
    op.drop_table("custom_index_daily")
    op.drop_table("custom_index_history")
    op.drop_table("custom_index_components")
    op.drop_table("custom_index_versions")
    op.drop_table("custom_indices")
