"""Add daily SVIX aggregates and maintenance audit records."""

from alembic import op
import sqlalchemy as sa

revision = "0008_data_lifecycle"
down_revision = "0007_provider_conn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "svix_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("svix_open", sa.Float(), nullable=False),
        sa.Column("svix_high", sa.Float(), nullable=False),
        sa.Column("svix_low", sa.Float(), nullable=False),
        sa.Column("svix_close", sa.Float(), nullable=False),
        sa.Column("core_close", sa.Float(), nullable=False),
        sa.Column("memory_close", sa.Float(), nullable=False),
        sa.Column("ai_close", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("min_calculation_quality", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("date"),
    )
    op.create_index("ix_svix_daily_date", "svix_daily", ["date"], unique=True)
    op.create_table(
        "data_maintenance_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("option_rows_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("history_rows_aggregated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("daily_rows_written", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_data_maintenance_runs_status", "data_maintenance_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_data_maintenance_runs_status", table_name="data_maintenance_runs")
    op.drop_table("data_maintenance_runs")
    op.drop_index("ix_svix_daily_date", table_name="svix_daily")
    op.drop_table("svix_daily")
