"""Market-data infrastructure."""
from alembic import op
import sqlalchemy as sa

revision = "0002_market_data"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("provider_credentials", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("provider", sa.String(16), nullable=False, unique=True), sa.Column("api_key_encrypted", sa.Text()), sa.Column("secret_encrypted", sa.Text()), sa.Column("account_identifier_encrypted", sa.Text()), sa.Column("enabled", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("option_snapshot", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False), sa.Column("provider", sa.String(16), nullable=False), sa.Column("symbol", sa.String(16), nullable=False), sa.Column("expiry", sa.DateTime(timezone=True), nullable=False), sa.Column("strike", sa.Float(), nullable=False), sa.Column("option_type", sa.String(4), nullable=False), sa.Column("bid", sa.Float()), sa.Column("ask", sa.Float()), sa.Column("last", sa.Float()), sa.Column("volume", sa.Integer()), sa.Column("open_interest", sa.Integer()), sa.Column("implied_volatility", sa.Float()))
    op.create_table("stock_snapshot", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False), sa.Column("symbol", sa.String(16), nullable=False), sa.Column("price", sa.Float()), sa.Column("bid", sa.Float()), sa.Column("ask", sa.Float()), sa.Column("volume", sa.Integer()))


def downgrade() -> None:
    op.drop_table("stock_snapshot")
    op.drop_table("option_snapshot")
    op.drop_table("provider_credentials")
