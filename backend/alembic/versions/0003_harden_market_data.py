"""Harden Phase 2 market-data persistence and audit configuration changes."""

from alembic import op
import sqlalchemy as sa


revision = "0003_harden_market_data"
down_revision = "0002_market_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admin_account.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_events_admin_id", "audit_events", ["admin_id"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_provider", "audit_events", ["provider"])
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])

    op.add_column("stock_snapshot", sa.Column("provider", sa.String(16), nullable=False, server_default="IBKR"))
    op.add_column("stock_snapshot", sa.Column("delayed", sa.Boolean(), nullable=True))
    op.alter_column("stock_snapshot", "provider", server_default=None)
    op.create_index("ix_stock_snapshot_provider", "stock_snapshot", ["provider"])
    op.create_index("ix_stock_snapshot_provider_symbol_timestamp", "stock_snapshot", ["provider", "symbol", "timestamp"])

    op.add_column("option_snapshot", sa.Column("contract_id", sa.String(256), nullable=True))
    op.execute("UPDATE option_snapshot SET contract_id = provider || ':LEGACY:' || id::text WHERE contract_id IS NULL")
    op.alter_column("option_snapshot", "contract_id", nullable=False)
    op.add_column("option_snapshot", sa.Column("delayed", sa.Boolean(), nullable=True))
    op.create_index("ix_option_snapshot_contract_id", "option_snapshot", ["contract_id"])
    op.create_index("ix_option_snapshot_provider_contract_timestamp", "option_snapshot", ["provider", "contract_id", "timestamp"])
    op.create_index("ix_option_snapshot_symbol_expiry_timestamp", "option_snapshot", ["symbol", "expiry", "timestamp"])
    op.create_check_constraint("option_snapshot_positive_strike", "option_snapshot", "strike > 0")


def downgrade() -> None:
    op.drop_constraint("option_snapshot_positive_strike", "option_snapshot", type_="check")
    op.drop_index("ix_option_snapshot_symbol_expiry_timestamp", table_name="option_snapshot")
    op.drop_index("ix_option_snapshot_provider_contract_timestamp", table_name="option_snapshot")
    op.drop_index("ix_option_snapshot_contract_id", table_name="option_snapshot")
    op.drop_column("option_snapshot", "delayed")
    op.drop_column("option_snapshot", "contract_id")

    op.drop_index("ix_stock_snapshot_provider_symbol_timestamp", table_name="stock_snapshot")
    op.drop_index("ix_stock_snapshot_provider", table_name="stock_snapshot")
    op.drop_column("stock_snapshot", "delayed")
    op.drop_column("stock_snapshot", "provider")

    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_provider", table_name="audit_events")
    op.drop_index("ix_audit_events_action", table_name="audit_events")
    op.drop_index("ix_audit_events_admin_id", table_name="audit_events")
    op.drop_table("audit_events")
