from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    identifier: str
    password: str
    totp_code: str | None = None
    recovery_code: str | None = None
    device_name: str = "我的设备"


class TotpVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class ReauthRequest(BaseModel):
    password: str
    totp_code: str | None = None


class SessionCreate(BaseModel):
    kind: str = "AD_HOC"


class ItemInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    account_alias: str | None = Field(default=None, max_length=200)
    asset_type: str
    category: str = "OTHER"
    original_currency: str = "CNY"
    original_value: Decimal
    current_market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    unrealized_pl: Decimal | None = None
    quantity: Decimal | None = None
    interest_rate: Decimal | None = None
    maturity_date: date | None = None
    liquidity_level: str = "HIGH"
    is_liability: bool = False
    source: str = "MANUAL"
    status: str = "CONFIRMED"
    confidence: Decimal | None = None
    notes: str | None = None
    metadata_json: dict = Field(default_factory=dict)

    @field_validator("original_currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise ValueError("币种必须是三位 ISO 代码")
        return value

    @field_validator("asset_type", "category", "liquidity_level", "source", "status")
    @classmethod
    def normalize_enum(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator(
        "original_value", "current_market_value", "cost_basis", "unrealized_pl",
        "quantity", "interest_rate", mode="before",
    )
    @classmethod
    def normalize_decimal_input(cls, value):
        if isinstance(value, str):
            value = value.strip().replace(",", "").replace("，", "")
            return value or None
        return value


class ItemPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    account_alias: str | None = None
    asset_type: str | None = None
    category: str | None = None
    original_currency: str | None = None
    original_value: Decimal | None = None
    current_market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    unrealized_pl: Decimal | None = None
    quantity: Decimal | None = None
    interest_rate: Decimal | None = None
    maturity_date: date | None = None
    liquidity_level: str | None = None
    is_liability: bool | None = None
    status: str | None = None
    notes: str | None = None
    metadata_json: dict | None = None

    @field_validator(
        "original_value", "current_market_value", "cost_basis", "unrealized_pl",
        "quantity", "interest_rate", mode="before",
    )
    @classmethod
    def normalize_optional_decimal_input(cls, value):
        if isinstance(value, str):
            value = value.strip().replace(",", "").replace("，", "")
            return value or None
        return value


class ConfirmRequest(BaseModel):
    accept_stale_rates: bool = False
    idempotency_key: str = Field(min_length=8, max_length=120)


class GoalInput(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    goal_type: str
    target_cny: Decimal = Field(gt=0)
    due_date: date | None = None
    included_asset_types: list[str] = Field(default_factory=list)


class GoalUpdate(GoalInput):
    pass


class GoalPlanInput(BaseModel):
    monthly_income_cny: Decimal = Field(gt=0)
    monthly_fixed_expenses_cny: Decimal = Field(ge=0)
    monthly_safety_buffer_cny: Decimal = Field(default=Decimal("0"), ge=0)
    provider: str = "auto"
    depth: str = "complex"

    @field_validator("monthly_fixed_expenses_cny", "monthly_safety_buffer_cny")
    @classmethod
    def expenses_must_fit_income(cls, value: Decimal) -> Decimal:
        return value


class GoalPlanUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    monthly_income_cny: Decimal = Field(gt=0)
    monthly_fixed_expenses_cny: Decimal = Field(ge=0)
    monthly_safety_buffer_cny: Decimal = Field(default=Decimal("0"), ge=0)
    suggested_monthly_contribution_cny: Decimal = Field(ge=0)
    guidance: dict = Field(default_factory=dict)


class TrendInsightInput(BaseModel):
    metric: str = "net_worth_cny"
    provider: str = "auto"
    depth: str = "complex"


class AllocationInput(BaseModel):
    monthly_income_cny: Decimal = Field(gt=0)
    monthly_fixed_expenses_cny: Decimal = Field(ge=0)
    monthly_safety_buffer_cny: Decimal = Field(default=Decimal("0"), ge=0)
    strategy: str = "BALANCED"
    provider: str = "auto"
    depth: str = "complex"


class ActionItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=240)
    reason: str = ""
    expected_impact: str = ""
    risk: str = ""
    review_trigger: str = ""
    priority: str = "MEDIUM"
    goal_id: str | None = None
    due_date: date | None = None
    source: str = "MANUAL"


class ActionItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=240)
    reason: str | None = None
    expected_impact: str | None = None
    risk: str | None = None
    review_trigger: str | None = None
    priority: str | None = None
    status: str | None = None
    goal_id: str | None = None
    due_date: date | None = None


class AttributionAnswersInput(BaseModel):
    answers: list[dict] = Field(default_factory=list, max_length=3)


class FundingAllocationRow(BaseModel):
    asset_key: str = Field(min_length=8, max_length=64)
    goal_id: str
    amount_cny: Decimal = Field(ge=0)


class FundingAllocationInput(BaseModel):
    allocations: list[FundingAllocationRow] = Field(default_factory=list, max_length=500)


class FutureObligationInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    category: str = "OTHER"
    amount_cny: Decimal = Field(gt=0)
    due_date: date
    likelihood: str = "CERTAIN"
    goal_id: str | None = None
    notes: str = ""


class FutureObligationUpdate(FutureObligationInput):
    status: str = "UPCOMING"


class ConstitutionRuleInput(BaseModel):
    id: str | None = None
    rule_type: str
    title: str = Field(min_length=1, max_length=240)
    parameters: dict = Field(default_factory=dict)
    enabled: bool = True


class ConstitutionInput(BaseModel):
    rules: list[ConstitutionRuleInput] = Field(default_factory=list, max_length=30)


class FocusAcceptInput(BaseModel):
    recommendation: dict
    verification: dict = Field(default_factory=dict)


class SpendingProfileInput(BaseModel):
    monthly_income_cny: Decimal = Field(ge=0)
    monthly_essential_expenses_cny: Decimal = Field(ge=0)
    monthly_current_expenses_cny: Decimal = Field(ge=0)
    emergency_months: Decimal = Field(default=Decimal("6"), ge=1, le=24)

    @field_validator(
        "monthly_income_cny", "monthly_essential_expenses_cny",
        "monthly_current_expenses_cny", "emergency_months", mode="before",
    )
    @classmethod
    def normalize_spending_numbers(cls, value):
        return value.strip().replace(",", "").replace("，", "") if isinstance(value, str) else value


class SpendingPreviewInput(BaseModel):
    decision: str = Field(min_length=2, max_length=500)
    amount_cny: Decimal | None = Field(default=None, gt=0)
    category: str = "OTHER"
    planned_date: date | None = None

    @field_validator("amount_cny", mode="before")
    @classmethod
    def normalize_amount(cls, value):
        if isinstance(value, str):
            value = value.strip().replace(",", "").replace("，", "")
            return value or None
        return value


class SpendingRulingInput(SpendingPreviewInput):
    provider: str = "auto"
    depth: str = "complex"


class GoldQuoteInput(BaseModel):
    method: str
    price_per_gram_cny: Decimal = Field(gt=0)
    source: str
    quoted_at: datetime
    brand: str | None = None
    city: str | None = None
    notes: str | None = None


class GoldEstimateInput(BaseModel):
    weight_grams: Decimal = Field(gt=0)
    purity: Decimal = Field(gt=0, le=1)
    quote_id: str
    explicit_fees_cny: Decimal = Decimal("0")


class ScenarioInput(BaseModel):
    asset_type_shocks: dict[str, Decimal] = Field(default_factory=dict)
    currency_shocks: dict[str, Decimal] = Field(default_factory=dict)
    liability_change_pct: Decimal = Decimal("0")


class AssistantInput(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    depth: str = "ordinary"
    provider: str = "auto"


class AnnotationInput(BaseModel):
    event_at: datetime
    event_type: str
    label: str
    notes: str | None = None


class ScheduleInput(BaseModel):
    frequency: str = "MONTHLY"
    timezone: str = "Asia/Seoul"
    hour: int = Field(default=20, ge=0, le=23)
    minute: int = Field(default=0, ge=0, le=59)
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    weekday: int | None = Field(default=None, ge=0, le=6)
    custom_date: date | None = None
    remind_before_days: int = Field(default=1, ge=0, le=30)
    repeat_overdue_days: int = Field(default=2, ge=0, le=30)
    email_enabled: bool = True
    paused: bool = False

    @field_validator("frequency")
    @classmethod
    def validate_frequency(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"WEEKLY", "MONTHLY", "QUARTERLY", "SEMIANNUAL", "YEARLY", "CUSTOM"}:
            raise ValueError("不支持的清算周期")
        return value


class SettingsInput(BaseModel):
    region: str
    model_preference: str
    timezone: str
