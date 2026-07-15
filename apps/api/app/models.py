from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def uuid4() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    role: Mapped[str] = mapped_column(String(20), default="OWNER")
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(Text)
    totp_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    recovery_code_hashes: Mapped[list[str]] = mapped_column(JSON, default=list)
    forced_password_change: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    region: Mapped[str] = mapped_column(String(20), default="UNKNOWN")
    model_preference: Mapped[str] = mapped_column(String(20), default="AUTO")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Seoul")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RefreshSession(Base):
    __tablename__ = "trusted_devices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(160), default="未知设备")
    user_agent: Mapped[str] = mapped_column(Text, default="")
    ip_hash: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="INFO")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ClearingSchedule(Base):
    __tablename__ = "clearing_schedules"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    frequency: Mapped[str] = mapped_column(String(30), default="MONTHLY")
    timezone: Mapped[str] = mapped_column(String(80), default="Asia/Seoul")
    hour: Mapped[int] = mapped_column(Integer, default=20)
    minute: Mapped[int] = mapped_column(Integer, default=0)
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remind_before_days: Mapped[int] = mapped_column(Integer, default=1)
    repeat_overdue_days: Mapped[int] = mapped_column(Integer, default=2)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ClearingSession(Base):
    __tablename__ = "clearing_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="AD_HOC")
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completeness: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    totals_json: Mapped[dict] = mapped_column(JSON, default=dict)
    fx_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    comparison_json: Mapped[dict] = mapped_column(JSON, default=dict)
    revision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), unique=True, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    items: Mapped[list["AssetItem"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class AssetItem(Base):
    __tablename__ = "asset_snapshot_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    session_id: Mapped[str] = mapped_column(ForeignKey("clearing_sessions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    account_alias: Mapped[str | None] = mapped_column(String(200), nullable=True)
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str] = mapped_column(String(40), default="OTHER")
    original_currency: Mapped[str] = mapped_column(String(3), default="CNY")
    original_value: Mapped[Decimal] = mapped_column(Numeric(30, 8))
    current_market_value: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    unrealized_pl: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    liquidity_level: Mapped[str] = mapped_column(String(20), default="HIGH")
    is_liability: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="MANUAL")
    status: Mapped[str] = mapped_column(String(30), default="CONFIRMED", index=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    value_cny: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    fx_rate_to_cny: Mapped[Decimal | None] = mapped_column(Numeric(30, 12), nullable=True)
    price_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    session: Mapped[ClearingSession] = relationship(back_populates="items")


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "rate_date"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), default="CNY")
    rate: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    source: Mapped[str] = mapped_column(String(200))
    rate_date: Mapped[date] = mapped_column(Date)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="CURRENT")


class GoldQuote(Base):
    __tablename__ = "gold_prices"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(30))
    price_per_gram_cny: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    source: Mapped[str] = mapped_column(String(200))
    quoted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Goal(Base):
    __tablename__ = "goals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    goal_type: Mapped[str] = mapped_column(String(40))
    target_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    included_asset_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GoalPlan(Base):
    __tablename__ = "goal_plans"
    __table_args__ = (UniqueConstraint("goal_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    monthly_income_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2))
    monthly_fixed_expenses_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2))
    monthly_safety_buffer_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2), default=Decimal("0"))
    calculation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    guidance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ActionItem(Base):
    __tablename__ = "financial_action_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240))
    reason: Mapped[str] = mapped_column(Text, default="")
    expected_impact: Mapped[str] = mapped_column(Text, default="")
    risk: Mapped[str] = mapped_column(Text, default="")
    review_trigger: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20), default="MEDIUM", index=True)
    status: Mapped[str] = mapped_column(String(20), default="TODO", index=True)
    source: Mapped[str] = mapped_column(String(40), default="MANUAL")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ClearingAttribution(Base):
    __tablename__ = "clearing_attributions"
    __table_args__ = (UniqueConstraint("session_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("clearing_sessions.id", ondelete="CASCADE"), index=True)
    previous_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    breakdown_json: Mapped[dict] = mapped_column(JSON, default=dict)
    questions_json: Mapped[list] = mapped_column(JSON, default=list)
    answers_json: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class GoalFundingAllocation(Base):
    __tablename__ = "goal_funding_allocations"
    __table_args__ = (UniqueConstraint("user_id", "goal_id", "asset_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), index=True)
    asset_key: Mapped[str] = mapped_column(String(64), index=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FutureObligation(Base):
    __tablename__ = "future_obligations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_id: Mapped[str | None] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(50), default="OTHER")
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2))
    due_date: Mapped[date] = mapped_column(Date)
    likelihood: Mapped[str] = mapped_column(String(20), default="CERTAIN")
    status: Mapped[str] = mapped_column(String(20), default="UPCOMING", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FinancialRule(Base):
    __tablename__ = "financial_constitution_rules"
    __table_args__ = (UniqueConstraint("user_id", "rule_type"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    rule_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(240))
    parameters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class FocusTask(Base):
    __tablename__ = "focus_tasks"
    __table_args__ = (UniqueConstraint("action_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action_id: Mapped[str] = mapped_column(ForeignKey("financial_action_items.id", ondelete="CASCADE"), index=True)
    source_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    verification_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductXray(Base):
    __tablename__ = "product_xrays"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    original_filename: Mapped[str] = mapped_column(String(240))
    content_type: Mapped[str] = mapped_column(String(120))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intended_amount_cny: Mapped[Decimal | None] = mapped_column(Numeric(30, 2), nullable=True)
    extraction_json: Mapped[dict] = mapped_column(JSON, default=dict)
    suitability_json: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SpendingProfile(Base):
    __tablename__ = "spending_profiles"
    __table_args__ = (UniqueConstraint("user_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    monthly_income_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2), default=0)
    monthly_essential_expenses_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2), default=0)
    monthly_current_expenses_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2), default=0)
    emergency_months: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=6)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SpendingDecision(Base):
    __tablename__ = "spending_decisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    decision_text: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(50), default="OTHER")
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(30, 2))
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    verdict: Mapped[str] = mapped_column(String(30), index=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    agent_json: Mapped[dict] = mapped_column(JSON, default=dict)
    provider: Mapped[str] = mapped_column(String(30), default="RULE_ENGINE")
    model: Mapped[str] = mapped_column(String(120), default="deterministic-spending-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ChartAnnotation(Base):
    __tablename__ = "asset_chart_annotations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class UploadedImage(Base):
    __tablename__ = "uploaded_images"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("clearing_sessions.id", ondelete="CASCADE"), index=True)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    original_filename: Mapped[str] = mapped_column(String(240))
    size_bytes: Mapped[int] = mapped_column(Integer)
    was_client_masked: Mapped[bool] = mapped_column(Boolean, default=False)
    deletion_status: Mapped[str] = mapped_column(String(30), default="PENDING")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_name: Mapped[str] = mapped_column(String(240), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="AVAILABLE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
