from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.database import Base
from app.database.types import UTCDateTime


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminAccount(Base):
    __tablename__ = "admin_account"
    __table_args__ = (CheckConstraint("id = 1", name="single_admin_account"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    username: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)


class AdminSecurity(Base):
    __tablename__ = "admin_security"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_account.id", ondelete="CASCADE"), nullable=False, unique=True)
    totp_secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    backup_codes_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class SystemSettings(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class SessionRecord(Base):
    __tablename__ = "sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    secret_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    account_identifier_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("admin_account.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow, index=True)


class OptionSnapshot(Base):
    __tablename__ = "option_snapshot"
    __table_args__ = (
        CheckConstraint("strike > 0", name="option_snapshot_positive_strike"),
        Index("ix_option_snapshot_provider_contract_timestamp", "provider", "contract_id", "timestamp"),
        Index("ix_option_snapshot_symbol_timestamp", "symbol", "timestamp"),
        Index("ix_option_snapshot_symbol_expiry_timestamp", "symbol", "expiry", "timestamp"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    contract_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    expiry: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    option_type: Mapped[str] = mapped_column(String(4), nullable=False)
    bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ask: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    open_interest: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    implied_volatility: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    delayed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)


class StockSnapshot(Base):
    __tablename__ = "stock_snapshot"
    __table_args__ = (
        Index("ix_stock_snapshot_provider_symbol_timestamp", "provider", "symbol", "timestamp"),
        Index("ix_stock_snapshot_symbol_timestamp", "symbol", "timestamp"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    bid: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ask: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    delayed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)


class SVIXHistory(Base):
    __tablename__ = "svix_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, unique=True, index=True)
    svix: Mapped[float] = mapped_column(Float, nullable=False)
    core_vol: Mapped[float] = mapped_column(Float, nullable=False)
    memory_vol: Mapped[float] = mapped_column(Float, nullable=False)
    ai_vol: Mapped[float] = mapped_column(Float, nullable=False)
    calculation_quality: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)


class CalculationJob(Base):
    __tablename__ = "calculation_jobs"
    __table_args__ = (Index("ix_calculation_jobs_status_created_at", "status", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="HISTORICAL_SVIX")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    frequency: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=utcnow)
    started_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
