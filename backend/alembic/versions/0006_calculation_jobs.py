"""Add persistent background calculation jobs."""

from alembic import op
import sqlalchemy as sa


revision = "0006_calculation_jobs"
down_revision = "0005_svix_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculation_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("frequency", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_calculation_jobs_status", "calculation_jobs", ["status"])
    op.create_index("ix_calculation_jobs_status_created_at", "calculation_jobs", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_calculation_jobs_status_created_at", table_name="calculation_jobs")
    op.drop_index("ix_calculation_jobs_status", table_name="calculation_jobs")
    op.drop_table("calculation_jobs")
