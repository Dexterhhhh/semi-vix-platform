"""Initial security schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("admin_account", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(128), nullable=False, unique=True), sa.Column("password_hash", sa.String(512), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_login", sa.DateTime(timezone=True)), sa.CheckConstraint("id = 1", name="single_admin_account"))
    op.create_table("admin_security", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_account.id", ondelete="CASCADE"), nullable=False, unique=True), sa.Column("totp_secret_encrypted", sa.Text()), sa.Column("mfa_enabled", sa.Boolean(), nullable=False), sa.Column("backup_codes_encrypted", sa.Text()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("system_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("key", sa.String(128), nullable=False, unique=True), sa.Column("value", sa.Text(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("sessions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("refresh_token_hash", sa.String(128), nullable=False, unique=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ip_address", sa.String(64)))


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("system_settings")
    op.drop_table("admin_security")
    op.drop_table("admin_account")
