"""Persist provider connection settings.

Revision ID: 0007_provider_conn
Revises: 0006_calculation_jobs
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_provider_conn"
down_revision = "0006_calculation_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_credentials", sa.Column("host", sa.String(length=255), nullable=True))
    op.add_column("provider_credentials", sa.Column("port", sa.Integer(), nullable=True))
    op.add_column("provider_credentials", sa.Column("client_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("provider_credentials", "client_id")
    op.drop_column("provider_credentials", "port")
    op.drop_column("provider_credentials", "host")
