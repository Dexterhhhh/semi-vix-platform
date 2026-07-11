"""Add persistence for calculated SVIX history."""

from alembic import op
import sqlalchemy as sa


revision = "0005_svix_history"
down_revision = "0004_snapshot_query_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "svix_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, unique=True),
        sa.Column("svix", sa.Float(), nullable=False),
        sa.Column("core_vol", sa.Float(), nullable=False),
        sa.Column("memory_vol", sa.Float(), nullable=False),
        sa.Column("ai_vol", sa.Float(), nullable=False),
        sa.Column("calculation_quality", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_svix_history_timestamp", "svix_history", ["timestamp"])


def downgrade() -> None:
    op.drop_index("ix_svix_history_timestamp", table_name="svix_history")
    op.drop_table("svix_history")
