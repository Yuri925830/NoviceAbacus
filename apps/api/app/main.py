from __future__ import annotations

import asyncio
import calendar
import hashlib
import io
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import aiosmtplib
import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from email.message import EmailMessage
from fastapi import Cookie, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, desc, func, or_, select, update
from sqlalchemy.orm import Session

from .backups import backup_path, create_encrypted_backup, restore_encrypted_backup
from .config import get_settings
from .database import Base, SessionLocal, engine, get_db
from .financial import D, aggregate_ohlc, analyze_series, build_series, calculate_snapshot, compare_totals, money, run_scenario
from .models import (
    ActionItem, AssetItem, AuditLog, BackupRecord, ChartAnnotation, ClearingAttribution, ClearingSchedule,
    ClearingSession, FinancialRule, FocusTask, FutureObligation, Goal, GoalFundingAllocation, GoalPlan, GoldQuote,
    Notification, ProductXray, RefreshSession, SpendingDecision, SpendingProfile, UploadedImage, User, utcnow,
)
from .providers import FxProvider, GoldSpotProvider, OpenAIGatewayClient, ProviderError, QwenClient, StaleRateError, audit, normalize_agent_output
from .reports import as_csv_bytes, as_json_bytes, as_pdf_bytes, snapshot_payload
from .schemas import (
    ActionItemInput, ActionItemUpdate, AllocationInput, AnnotationInput, AssistantInput, AttributionAnswersInput,
    ConfirmRequest, ConstitutionInput, FocusAcceptInput, FundingAllocationInput, FutureObligationInput, FutureObligationUpdate,
    GoalInput, GoalPlanInput, GoalPlanUpdate,
    GoalUpdate, GoldEstimateInput, GoldQuoteInput,
    ItemInput, ItemPatch, LoginRequest, ReauthRequest, ScenarioInput, ScheduleInput, SessionCreate,
    SettingsInput, SpendingPreviewInput, SpendingProfileInput, SpendingRulingInput, TotpVerifyRequest, TrendInsightInput,
)
from .security import (
    create_access_token, decode_access_token, decrypt_secret, encrypt_secret, hash_password, hash_recovery_code,
    hash_token, ip_digest, new_recovery_codes, new_refresh_token, new_totp_secret, provisioning_uri,
    verify_password, verify_recovery_code, verify_totp,
)


settings = get_settings()
app = FastAPI(title="小白算盘 API", version="1.1.0", docs_url="/api/docs" if settings.app_env != "production" else None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)

ACCESS_COOKIE = "xbs_access"
REFRESH_COOKIE = "xbs_refresh"
scheduler = BackgroundScheduler(timezone="UTC")


def iso(value):
    return value.isoformat() if value else None


def cookie_options() -> dict:
    return {"httponly": True, "secure": settings.app_env == "production", "samesite": "lax", "path": "/"}


def set_auth_cookies(response: Response, access: str, refresh: str) -> None:
    response.set_cookie(ACCESS_COOKIE, access, max_age=15 * 60, **cookie_options())
    response.set_cookie(REFRESH_COOKIE, refresh, max_age=30 * 24 * 3600, **cookie_options())


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")


def log_event(db: Session, user_id: str | None, event: str, metadata: dict | None = None, severity: str = "INFO") -> None:
    db.add(AuditLog(user_id=user_id, event=event, severity=severity, metadata_json=metadata or {}))


def current_user(
    db: Annotated[Session, Depends(get_db)],
    request: Request,
    xbs_access: str | None = Cookie(default=None),
    authorization: str | None = Header(default=None),
) -> User:
    token = xbs_access
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if not token:
        raise HTTPException(status_code=401, detail="NOT_AUTHENTICATED")
    try:
        payload = decode_access_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="ACCESS_EXPIRED") from exc
    session = db.get(RefreshSession, payload.get("sid"))
    if not session or session.revoked_at or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="SESSION_REVOKED")
    user = db.get(User, payload.get("sub"))
    if not user or user.role != "OWNER":
        raise HTTPException(status_code=403, detail="OWNER_ONLY")
    session.last_seen_at = utcnow()
    db.commit()
    return user


Owner = Annotated[User, Depends(current_user)]
DB = Annotated[Session, Depends(get_db)]


def owned_session(db: Session, user: User, session_id: str, include_deleted: bool = False) -> ClearingSession:
    query = select(ClearingSession).where(ClearingSession.id == session_id, ClearingSession.user_id == user.id)
    if not include_deleted:
        query = query.where(ClearingSession.deleted_at.is_(None))
    session = db.scalar(query)
    if not session:
        raise HTTPException(status_code=404, detail="清算不存在")
    return session


def serialize_item(item: AssetItem) -> dict:
    return {
        "id": item.id, "session_id": item.session_id, "name": item.name, "account_alias": item.account_alias,
        "asset_type": item.asset_type, "category": item.category, "original_currency": item.original_currency,
        "original_value": str(item.original_value), "current_market_value": str(item.current_market_value) if item.current_market_value is not None else None,
        "cost_basis": str(item.cost_basis) if item.cost_basis is not None else None,
        "unrealized_pl": str(item.unrealized_pl) if item.unrealized_pl is not None else None,
        "quantity": str(item.quantity) if item.quantity is not None else None,
        "interest_rate": str(item.interest_rate) if item.interest_rate is not None else None,
        "maturity_date": iso(item.maturity_date), "liquidity_level": item.liquidity_level,
        "is_liability": item.is_liability, "source": item.source, "status": item.status,
        "confidence": str(item.confidence) if item.confidence is not None else None,
        "value_cny": str(item.value_cny) if item.value_cny is not None else None,
        "fx_rate_to_cny": str(item.fx_rate_to_cny) if item.fx_rate_to_cny is not None else None,
        "price_timestamp": iso(item.price_timestamp), "notes": item.notes, "metadata_json": item.metadata_json,
    }


def serialize_session(session: ClearingSession, with_items: bool = False) -> dict:
    payload = {
        "id": session.id, "kind": session.kind, "status": session.status, "revision_number": session.revision_number,
        "supersedes_id": session.supersedes_id, "started_at": iso(session.started_at), "confirmed_at": iso(session.confirmed_at),
        "completeness": str(session.completeness), "totals": session.totals_json, "fx_snapshot": session.fx_snapshot_json,
        "comparison": session.comparison_json, "revision_reason": session.revision_reason,
    }
    if with_items:
        payload["items"] = [serialize_item(item) for item in session.items]
    return payload


def next_schedule_time(value: ScheduleInput, after: datetime | None = None) -> datetime:
    try:
        local_tz = ZoneInfo(value.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=422, detail="无效的 IANA 时区") from exc
    reference = after or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    now = reference.astimezone(local_tz)
    candidate = now.replace(hour=value.hour, minute=value.minute, second=0, microsecond=0)
    if value.frequency == "WEEKLY":
        weekday = value.weekday if value.weekday is not None else 0
        candidate += timedelta(days=(weekday - candidate.weekday()) % 7)
        if candidate <= now:
            candidate += timedelta(days=7)
    elif value.frequency == "CUSTOM":
        if not value.custom_date:
            raise HTTPException(status_code=422, detail="请选择单次清算日期")
        candidate = datetime.combine(value.custom_date, datetime.min.time(), tzinfo=local_tz).replace(hour=value.hour, minute=value.minute)
        if candidate <= now:
            raise HTTPException(status_code=422, detail="自定义清算时间必须晚于当前时间")
    elif value.frequency == "YEARLY":
        if not value.custom_date:
            raise HTTPException(status_code=422, detail="请选择年度清算的月和日")
        month = value.custom_date.month
        day = min(value.custom_date.day, calendar.monthrange(candidate.year, month)[1])
        candidate = candidate.replace(month=month, day=day)
        if candidate <= now:
            year = candidate.year + 1
            candidate = candidate.replace(year=year, day=min(day, calendar.monthrange(year, month)[1]))
    else:
        day = value.day_of_month or 28
        candidate = candidate.replace(day=min(day, calendar.monthrange(candidate.year, candidate.month)[1]))
        months = {"MONTHLY": 1, "QUARTERLY": 3, "SEMIANNUAL": 6}.get(value.frequency, 1)
        if candidate <= now:
            month_index = candidate.year * 12 + candidate.month - 1 + months
            year, month = month_index // 12, month_index % 12 + 1
            candidate = candidate.replace(year=year, month=month, day=min(day, calendar.monthrange(year, month)[1]))
    return candidate.astimezone(timezone.utc)


def schedule_input_from_row(row: ClearingSchedule) -> ScheduleInput:
    return ScheduleInput.model_validate({
        "frequency": row.frequency, "timezone": row.timezone, "hour": row.hour, "minute": row.minute,
        "day_of_month": row.day_of_month, "weekday": row.weekday, "custom_date": row.custom_date,
        "remind_before_days": row.remind_before_days, "repeat_overdue_days": row.repeat_overdue_days,
        "email_enabled": row.email_enabled, "paused": row.paused,
    })


async def send_email(subject: str, body: str, recipient: str) -> None:
    if not settings.smtp_host or not recipient:
        return
    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    await aiosmtplib.send(
        message, hostname=settings.smtp_host, port=settings.smtp_port,
        username=settings.smtp_username or None, password=settings.smtp_password or None,
        local_hostname="localhost",
        start_tls=settings.smtp_port != 465, use_tls=settings.smtp_port == 465,
    )


def process_reminders() -> None:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        schedules = db.scalars(select(ClearingSchedule).where(ClearingSchedule.paused.is_(False))).all()
        for schedule in schedules:
            if not schedule.next_run_at:
                continue
            run_at = schedule.next_run_at.replace(tzinfo=schedule.next_run_at.tzinfo or timezone.utc)
            remind_at = run_at - timedelta(days=schedule.remind_before_days)
            run_key = run_at.strftime("%Y%m%d")
            if now < run_at:
                marker = f"CR:{schedule.id[:8]}:{run_key}:PRE"
            elif schedule.repeat_overdue_days:
                days_overdue = max((now.date() - run_at.date()).days, 0)
                overdue_bucket = days_overdue // schedule.repeat_overdue_days
                marker = f"CR:{schedule.id[:8]}:{run_key}:O{overdue_bucket}"
            else:
                marker = f"CR:{schedule.id[:8]}:{run_key}:DUE"
            exists = db.scalar(select(Notification.id).where(Notification.user_id == schedule.user_id, Notification.kind == marker))
            if remind_at <= now and not exists:
                user = db.get(User, schedule.user_id)
                overdue = now >= run_at
                title = "资产清算已经到期" if overdue else "该做一次资产清算了"
                db.add(Notification(user_id=schedule.user_id, kind=marker, title=title, body=f"计划清算时间：{run_at.isoformat()}。先遮挡敏感信息，再上传截图。"))
                db.commit()
                if schedule.email_enabled and user:
                    recipient = settings.alert_email or (user.email if "@" in user.email else "")
                    try:
                        asyncio.run(send_email(f"小白算盘：{title}", "到时间看看最近的资产变化啦。准备好后，打开小白算盘完成一次清算就好。", recipient))
                    except Exception:
                        log_event(db, user.id, "EMAIL_SEND_FAILED", {"kind": "clearing_reminder"}, "WARNING")
                        db.commit()


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        count = db.scalar(select(func.count(User.id))) or 0
        owner_identifier = (settings.owner_id or settings.owner_email).strip()
        if count == 0 and owner_identifier and settings.owner_password:
            db.add(User(email=owner_identifier.lower(), phone=settings.owner_phone or None, password_hash=hash_password(settings.owner_password), role="OWNER"))
            db.commit()
    if not scheduler.running:
        scheduler.add_job(process_reminders, "interval", minutes=15, id="clearing-reminders", replace_existing=True, max_instances=1)
        scheduler.start()


@app.on_event("shutdown")
def shutdown() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


@app.get("/health")
def health() -> dict:
    key, base_url, workspace = settings.aliyun_credentials()
    return {
        "status": "ok", "version": "1.1.0", "database": engine.dialect.name,
        "aliyun_configured": bool(key and base_url), "aliyun_workspace_configured": bool(workspace),
        "openai_gateway_configured": bool(settings.openai_gateway_url and settings.gateway_shared_secret),
    }


@app.post("/auth/login")
def login(body: LoginRequest, request: Request, response: Response, db: DB) -> dict:
    identifier = body.identifier.strip().lower()
    user = db.scalar(select(User).where(or_(func.lower(User.email) == identifier, User.phone == body.identifier.strip())))
    now = datetime.now(timezone.utc)
    if not user or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= 5:
                user.locked_until = now + timedelta(minutes=15)
        log_event(db, user.id if user else None, "LOGIN_FAILED", {"ip_hash": ip_digest(request.client.host if request.client else "")}, "WARNING")
        db.commit()
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    locked_until = user.locked_until.replace(tzinfo=user.locked_until.tzinfo or timezone.utc) if user.locked_until else None
    if locked_until and locked_until > now:
        raise HTTPException(status_code=423, detail="登录暂时锁定，请稍后再试")
    if user.totp_enabled:
        verified = False
        if body.totp_code and user.totp_secret_encrypted:
            verified = verify_totp(decrypt_secret(user.totp_secret_encrypted), body.totp_code)
        elif body.recovery_code:
            verified, remaining = verify_recovery_code(body.recovery_code, user.recovery_code_hashes or [])
            if verified:
                user.recovery_code_hashes = remaining
        if not verified:
            raise HTTPException(status_code=428, detail="TOTP_REQUIRED")
    user.failed_login_count = 0
    user.locked_until = None
    refresh = new_refresh_token()
    device = RefreshSession(
        user_id=user.id, token_hash=hash_token(refresh), device_name=body.device_name,
        user_agent=request.headers.get("user-agent", ""), ip_hash=ip_digest(request.client.host if request.client else ""),
        expires_at=now + timedelta(days=30),
    )
    db.add(device)
    db.flush()
    access = create_access_token(user.id, device.id)
    log_event(db, user.id, "LOGIN_SUCCEEDED", {"device_id": device.id})
    db.commit()
    set_auth_cookies(response, access, refresh)
    return {"ok": True, "security_setup_required": not user.totp_enabled, "forced_password_change": user.forced_password_change}


@app.post("/auth/refresh")
def refresh(response: Response, db: DB, xbs_refresh: str | None = Cookie(default=None)) -> dict:
    if not xbs_refresh:
        raise HTTPException(status_code=401, detail="REFRESH_REQUIRED")
    session = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == hash_token(xbs_refresh)))
    now = datetime.now(timezone.utc)
    if not session or session.revoked_at or session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc) <= now:
        raise HTTPException(status_code=401, detail="REFRESH_EXPIRED")
    new_refresh = new_refresh_token()
    session.token_hash = hash_token(new_refresh)
    session.last_seen_at = now
    db.commit()
    set_auth_cookies(response, create_access_token(session.user_id, session.id), new_refresh)
    return {"ok": True}


@app.post("/auth/logout")
def logout(response: Response, db: DB, user: Owner, xbs_refresh: str | None = Cookie(default=None)) -> dict:
    if xbs_refresh:
        session = db.scalar(select(RefreshSession).where(RefreshSession.token_hash == hash_token(xbs_refresh), RefreshSession.user_id == user.id))
        if session:
            session.revoked_at = utcnow()
    log_event(db, user.id, "LOGOUT")
    db.commit()
    clear_auth_cookies(response)
    return {"ok": True}


@app.get("/auth/me")
def me(user: Owner, db: DB) -> dict:
    reconcile_funding_allocations(db, user.id, latest_confirmed(db, user.id))
    pending_goals = sync_goal_completion_notifications(db, user.id)
    return {
        "id": user.id, "email": user.email, "phone": user.phone, "role": user.role,
        "totp_enabled": user.totp_enabled, "security_setup_required": not user.totp_enabled,
        "region": user.region, "model_preference": user.model_preference, "timezone": user.timezone,
        "unread_notifications": db.scalar(select(func.count(Notification.id)).where(Notification.user_id == user.id, Notification.read_at.is_(None))) or 0,
        "pending_goal_completions": pending_goals,
    }


@app.post("/auth/totp/setup")
def totp_setup(user: Owner, db: DB) -> dict:
    secret = new_totp_secret()
    user.totp_secret_encrypted = encrypt_secret(secret)
    user.totp_enabled = False
    db.commit()
    return {"secret": secret, "provisioning_uri": provisioning_uri(secret, user.email), "message": "请用验证器扫描或手工输入；验证成功前不会启用。"}


@app.post("/auth/totp/verify")
def totp_verify(body: TotpVerifyRequest, user: Owner, db: DB) -> dict:
    if not user.totp_secret_encrypted or not verify_totp(decrypt_secret(user.totp_secret_encrypted), body.code):
        raise HTTPException(status_code=400, detail="验证码不正确")
    codes = new_recovery_codes()
    user.totp_enabled = True
    user.recovery_code_hashes = [hash_recovery_code(code) for code in codes]
    log_event(db, user.id, "TOTP_ENABLED")
    db.commit()
    return {"enabled": True, "recovery_codes": codes, "warning": "恢复码只显示这一次，请离线保存。"}


@app.get("/auth/devices")
def devices(user: Owner, db: DB) -> list[dict]:
    rows = db.scalars(select(RefreshSession).where(RefreshSession.user_id == user.id).order_by(desc(RefreshSession.last_seen_at))).all()
    return [{"id": row.id, "device_name": row.device_name, "user_agent": row.user_agent, "created_at": iso(row.created_at), "last_seen_at": iso(row.last_seen_at), "expires_at": iso(row.expires_at), "revoked_at": iso(row.revoked_at)} for row in rows]


@app.delete("/auth/devices/{device_id}")
def revoke_device(device_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(RefreshSession).where(RefreshSession.id == device_id, RefreshSession.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="设备会话不存在")
    row.revoked_at = utcnow()
    log_event(db, user.id, "DEVICE_REVOKED", {"device_id": device_id})
    db.commit()
    return {"ok": True}


def copy_items_to_draft(
    db: Session,
    target: ClearingSession,
    source: ClearingSession,
    item_source: str,
) -> int:
    copied = 0
    for item in source.items:
        if item.status not in {"CONFIRMED", "REVISED"}:
            continue
        db.add(AssetItem(
            session_id=target.id,
            name=item.name,
            account_alias=item.account_alias,
            asset_type=item.asset_type,
            category=item.category,
            original_currency=item.original_currency,
            original_value=item.original_value,
            current_market_value=item.current_market_value,
            cost_basis=item.cost_basis,
            unrealized_pl=item.unrealized_pl,
            quantity=item.quantity,
            interest_rate=item.interest_rate,
            maturity_date=item.maturity_date,
            liquidity_level=item.liquidity_level,
            is_liability=item.is_liability,
            source=item_source,
            status="CONFIRMED",
            notes=item.notes,
            metadata_json={
                **(item.metadata_json or {}),
                "carried_from_item": item.id,
                "carried_from_session": source.id,
            },
        ))
        copied += 1
    return copied


@app.post("/sessions")
async def create_session(body: SessionCreate, user: Owner, db: DB) -> dict:
    active = db.scalar(select(ClearingSession).where(ClearingSession.user_id == user.id, ClearingSession.status == "DRAFT", ClearingSession.deleted_at.is_(None)).order_by(desc(ClearingSession.started_at)))
    previous = db.scalar(select(ClearingSession).where(
        ClearingSession.user_id == user.id,
        ClearingSession.status.in_(["CONFIRMED", "REVISED"]),
        ClearingSession.deleted_at.is_(None),
    ).order_by(desc(ClearingSession.confirmed_at)).limit(1))
    # A draft created by an older version may be completely empty. Opening the
    # clearing page must still start from the latest confirmed structure.
    if active:
        if not active.items and previous and previous.id != active.id:
            copied = copy_items_to_draft(db, active, previous, "CARRY_FORWARD")
            log_event(db, user.id, "EMPTY_DRAFT_RESEEDED", {
                "session_id": active.id,
                "source_session_id": previous.id,
                "carried_forward_items": copied,
            })
            db.commit()
            db.refresh(active)
        return serialize_session(active, with_items=True)
    row = ClearingSession(user_id=user.id, kind=body.kind.upper(), status="DRAFT")
    db.add(row)
    db.flush()
    copied = 0
    if previous:
        copied = copy_items_to_draft(db, row, previous, "CARRY_FORWARD")
    log_event(db, user.id, "CLEARING_STARTED", {"kind": row.kind, "carried_forward_items": copied})
    db.commit()
    db.refresh(row)
    return serialize_session(row, with_items=True)


@app.get("/sessions")
def list_sessions(user: Owner, db: DB, status_filter: str | None = None) -> list[dict]:
    query = select(ClearingSession).where(ClearingSession.user_id == user.id, ClearingSession.deleted_at.is_(None))
    if status_filter:
        query = query.where(ClearingSession.status == status_filter.upper())
    rows = db.scalars(query.order_by(desc(ClearingSession.confirmed_at), desc(ClearingSession.started_at))).all()
    return [serialize_session(row) for row in rows]


@app.get("/sessions/{session_id}")
def get_session(session_id: str, user: Owner, db: DB) -> dict:
    return serialize_session(owned_session(db, user, session_id), with_items=True)


@app.post("/sessions/{session_id}/revise")
def revise_session(session_id: str, body: dict, user: Owner, db: DB) -> dict:
    original = owned_session(db, user, session_id)
    if original.status not in {"CONFIRMED", "REVISED"}:
        raise HTTPException(status_code=409, detail="只有已确认清算可修订")
    revision = ClearingSession(
        user_id=user.id, kind=original.kind, status="DRAFT", revision_number=original.revision_number + 1,
        supersedes_id=original.id, revision_reason=str(body.get("reason", "修正已确认数据"))[:1000],
    )
    db.add(revision)
    db.flush()
    for item in original.items:
        if item.status not in {"CONFIRMED", "REVISED"}:
            continue
        db.add(AssetItem(
            session_id=revision.id, name=item.name, account_alias=item.account_alias, asset_type=item.asset_type,
            category=item.category, original_currency=item.original_currency, original_value=item.original_value,
            current_market_value=item.current_market_value, cost_basis=item.cost_basis, unrealized_pl=item.unrealized_pl,
            quantity=item.quantity, interest_rate=item.interest_rate, maturity_date=item.maturity_date,
            liquidity_level=item.liquidity_level, is_liability=item.is_liability, source="MANUAL", status="CONFIRMED",
            notes=item.notes, metadata_json={**(item.metadata_json or {}), "copied_from_item": item.id},
        ))
    log_event(db, user.id, "CLEARING_REVISION_STARTED", {"original_id": original.id, "revision_id": revision.id})
    db.commit()
    db.refresh(revision)
    return serialize_session(revision, with_items=True)


@app.post("/sessions/{session_id}/items")
async def add_item(session_id: str, body: ItemInput, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    if session.status != "DRAFT":
        raise HTTPException(status_code=409, detail="已确认清算不能直接修改，请创建修订")
    values = body.model_dump()
    if body.asset_type == "PHYSICAL_GOLD":
        if body.quantity is None or D(body.quantity) <= 0:
            raise HTTPException(status_code=422, detail="实物黄金请填写大于 0 的克重")
        try:
            quote = await GoldSpotProvider().get_cny_quote(db, user.id)
        except (ProviderError, StaleRateError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        grams = D(body.quantity)
        values.update({
            "category": "GOLD",
            "original_currency": "CNY",
            "original_value": grams * D(quote["cny_per_gram"]),
            "current_market_value": None,
            "is_liability": False,
            "metadata_json": {**body.metadata_json, "gold_quote": quote, "valuation_formula": "grams × live_cny_per_gram"},
        })
    row = AssetItem(session_id=session.id, **values)
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_item(row)


@app.patch("/sessions/{session_id}/items/{item_id}")
async def update_item(session_id: str, item_id: str, body: ItemPatch, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    if session.status != "DRAFT":
        raise HTTPException(status_code=409, detail="已确认清算不能直接修改")
    item = db.scalar(select(AssetItem).where(AssetItem.id == item_id, AssetItem.session_id == session.id))
    if not item:
        raise HTTPException(status_code=404, detail="资产项不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        if isinstance(value, str) and key in {"asset_type", "category", "original_currency", "liquidity_level", "status"}:
            value = value.upper()
        setattr(item, key, value)
    if item.asset_type == "PHYSICAL_GOLD" and ({"quantity", "asset_type"} & body.model_fields_set or not (item.metadata_json or {}).get("gold_quote")):
        if item.quantity is None or D(item.quantity) <= 0:
            raise HTTPException(status_code=422, detail="实物黄金请填写大于 0 的克重")
        try:
            quote = await GoldSpotProvider().get_cny_quote(db, user.id)
        except (ProviderError, StaleRateError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        item.category = "GOLD"
        item.original_currency = "CNY"
        item.original_value = D(item.quantity) * D(quote["cny_per_gram"])
        item.current_market_value = None
        item.is_liability = False
        item.metadata_json = {**(item.metadata_json or {}), "gold_quote": quote, "valuation_formula": "grams × live_cny_per_gram"}
    db.commit()
    db.refresh(item)
    return serialize_item(item)


@app.delete("/sessions/{session_id}/items/{item_id}")
def delete_item(session_id: str, item_id: str, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    if session.status != "DRAFT":
        raise HTTPException(status_code=409, detail="已确认清算不能直接修改")
    item = db.scalar(select(AssetItem).where(AssetItem.id == item_id, AssetItem.session_id == session.id))
    if not item:
        raise HTTPException(status_code=404, detail="资产项不存在")
    db.delete(item)
    db.commit()
    return {"ok": True}


@app.post("/sessions/{session_id}/recognize")
async def recognize_screenshot(
    session_id: str, user: Owner, db: DB,
    file: UploadFile = File(...), privacy_confirmed: bool = Form(...),
) -> dict:
    session = owned_session(db, user, session_id)
    if session.status != "DRAFT":
        raise HTTPException(status_code=409, detail="清算已确认")
    if not privacy_confirmed:
        raise HTTPException(status_code=400, detail="必须确认已在本机遮挡敏感信息")
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="只接受图片")
    image = await file.read((settings.max_upload_mb * 1024 * 1024) + 1)
    if len(image) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"图片不可超过 {settings.max_upload_mb}MB")
    digest = hashlib.sha256(image).hexdigest()
    duplicate = db.scalar(select(UploadedImage).where(UploadedImage.user_id == user.id, UploadedImage.sha256 == digest).order_by(desc(UploadedImage.created_at)))
    record = UploadedImage(
        user_id=user.id, session_id=session.id, sha256=digest, original_filename=(file.filename or "masked-image")[:240],
        size_bytes=len(image), was_client_masked=True,
    )
    db.add(record)
    db.commit()
    try:
        result = await QwenClient().recognize_assets(db, user.id, image, file.content_type)
        created = []
        validation_warnings = list(result.get("warnings", []))
        if duplicate:
            validation_warnings.append("这张图之前也读过一次；本次仍已重新识别，请留意是否有重复项目。")
        for candidate in result.get("items", []):
            try:
                confidence = D(candidate.get("confidence", "0"))
                body = ItemInput.model_validate({
                    **candidate, "source": "SCREENSHOT",
                    "status": "NEEDS_REVIEW" if confidence < Decimal("0.85") else "EXTRACTED",
                    "metadata_json": {"page_type": result.get("page_type"), "image_sha256": digest, "ocr_excerpt": result.get("ocr_text", "")[:2000]},
                })
                row = AssetItem(session_id=session.id, **body.model_dump())
                db.add(row)
                db.flush()
                created.append(serialize_item(row))
            except Exception as exc:
                validation_warnings.append(f"一个候选项因字段无效未写入：{type(exc).__name__}")
        log_event(db, user.id, "SCREENSHOT_RECOGNIZED", {"session_id": session.id, "candidate_count": len(created), "image_sha256": digest})
        db.commit()
        if not created:
            validation_warnings.append("这张图里暂时没有读到可用的资产金额。可以换一张更清楚的截图，或直接手工添加。")
        return {
            "items": created,
            "recognized_count": len(created),
            "status": "RECOGNIZED" if created else "NO_ITEMS",
            "message": f"已经读出 {len(created)} 个项目，放在下方等你看看。" if created else "图片已经看完了，但暂时没找到可用的资产项目。",
            "page_type": result.get("page_type"),
            "warnings": validation_warnings,
            "requires_owner_confirmation": True,
        }
    except ProviderError as exc:
        log_event(db, user.id, "SCREENSHOT_RECOGNITION_FAILED", {"session_id": session.id, "reason": str(exc)}, "WARNING")
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        # The processed image is held in memory only and released immediately; no original or masked file persists.
        record.deletion_status = "DELETED"
        record.deleted_at = utcnow()
        db.commit()


@app.post("/sessions/{session_id}/confirm")
async def confirm_session(session_id: str, body: ConfirmRequest, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    existing = db.scalar(select(ClearingSession).where(ClearingSession.user_id == user.id, ClearingSession.idempotency_key == body.idempotency_key))
    if existing:
        return serialize_session(existing, with_items=True)
    if session.status != "DRAFT":
        raise HTTPException(status_code=409, detail="清算已经确认或不可修改")
    confirmed = [item for item in session.items if item.status == "CONFIRMED"]
    if not confirmed:
        raise HTTPException(status_code=422, detail="至少确认一个项目后，才能完成这次清算")
    physical_gold = [item for item in confirmed if item.asset_type == "PHYSICAL_GOLD"]
    if physical_gold:
        try:
            live_gold = await GoldSpotProvider().get_cny_quote(db, user.id)
        except (ProviderError, StaleRateError) as exc:
            raise HTTPException(status_code=502, detail=f"实物黄金需要实时估值后才能确认：{exc}") from exc
        for item in physical_gold:
            if item.quantity is None or D(item.quantity) <= 0:
                raise HTTPException(status_code=422, detail=f"“{item.name}”还没有填写有效克重")
            item.original_currency = "CNY"
            item.original_value = D(item.quantity) * D(live_gold["cny_per_gram"])
            item.category = "GOLD"
            item.is_liability = False
            item.metadata_json = {**(item.metadata_json or {}), "gold_quote": live_gold, "valuation_formula": "grams × live_cny_per_gram"}
    total_candidates = len([item for item in session.items if item.status != "EXCLUDED"])
    session.completeness = (Decimal(len(confirmed)) / Decimal(total_candidates or 1) * Decimal("100")).quantize(Decimal("0.01"))
    currencies = {item.original_currency for item in confirmed}
    try:
        rates, metadata = await FxProvider().get_rates(db, currencies, accept_stale=body.accept_stale_rates)
    except StaleRateError as exc:
        raise HTTPException(status_code=409, detail={"code": "STALE_RATES", "currencies": exc.currencies, "cached": exc.cached, "message": "汇率不是当前价格。核对后可明确选择继续。"}) from exc
    try:
        totals, calculated = calculate_snapshot(confirmed, rates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    calculated_map = {row["id"]: row for row in calculated}
    now = utcnow()
    for item in confirmed:
        computed = calculated_map[item.id]
        item.value_cny = computed["value_cny"]
        item.fx_rate_to_cny = computed["fx_rate_to_cny"]
        item.price_timestamp = now
    previous = db.scalar(select(ClearingSession).where(
        ClearingSession.user_id == user.id, ClearingSession.status.in_(["CONFIRMED", "REVISED"]),
        ClearingSession.deleted_at.is_(None), ClearingSession.id != session.id,
    ).order_by(desc(ClearingSession.confirmed_at)).limit(1))
    session.totals_json = totals
    session.fx_snapshot_json = metadata
    session.comparison_json = compare_totals(totals, previous.totals_json if previous else None)
    session.status = "REVISED" if session.supersedes_id else "CONFIRMED"
    session.confirmed_at = now
    session.idempotency_key = body.idempotency_key
    if session.supersedes_id:
        original = db.get(ClearingSession, session.supersedes_id)
        if original:
            original.status = "SUPERSEDED"
    schedule = db.scalar(select(ClearingSchedule).where(ClearingSchedule.user_id == user.id))
    if schedule and not schedule.paused:
        if schedule.frequency == "CUSTOM":
            schedule.paused = True
            schedule.next_run_at = None
        else:
            schedule.next_run_at = next_schedule_time(schedule_input_from_row(schedule), after=now + timedelta(minutes=1))
    log_event(db, user.id, "CLEARING_CONFIRMED", {"session_id": session.id, "revision": session.revision_number, "completeness": str(session.completeness)})
    db.commit()
    reconcile_funding_allocations(db, user.id, session)
    sync_goal_completion_notifications(db, user.id)
    db.refresh(session)
    return serialize_session(session, with_items=True)


@app.delete("/sessions/{session_id}")
def remove_session(session_id: str, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    session.deleted_at = utcnow()
    log_event(db, user.id, "CLEARING_DELETED", {"session_id": session.id})
    db.commit()
    return {"ok": True, "recalculation_required": True}


def save_attribution_record(db: Session, user_id: str, session: ClearingSession, payload: dict, answers: list[dict]) -> ClearingAttribution:
    row = db.scalar(select(ClearingAttribution).where(ClearingAttribution.session_id == session.id, ClearingAttribution.user_id == user_id))
    if not row:
        row = ClearingAttribution(user_id=user_id, session_id=session.id)
        db.add(row)
    row.previous_session_id = payload.get("previous_session_id")
    row.breakdown_json = payload
    row.questions_json = payload.get("questions", [])
    row.answers_json = answers[:3]
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


@app.get("/sessions/{session_id}/attribution")
def get_session_attribution(session_id: str, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    if session.status not in {"CONFIRMED", "REVISED"}:
        raise HTTPException(status_code=409, detail="完成这次清算后，才能把变化原因拆开来看。")
    row = db.scalar(select(ClearingAttribution).where(ClearingAttribution.session_id == session.id, ClearingAttribution.user_id == user.id))
    answers = row.answers_json if row else []
    payload = build_attribution(db, session, answers)
    save_attribution_record(db, user.id, session, payload, answers)
    return payload


@app.patch("/sessions/{session_id}/attribution")
def answer_session_attribution(session_id: str, body: AttributionAnswersInput, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    if session.status not in {"CONFIRMED", "REVISED"}:
        raise HTTPException(status_code=409, detail="完成这次清算后，再一起回答变化原因。")
    payload = build_attribution(db, session, body.answers)
    save_attribution_record(db, user.id, session, payload, body.answers)
    log_event(db, user.id, "CLEARING_ATTRIBUTION_ANSWERED", {"session_id": session.id, "answer_count": len(body.answers)})
    db.commit()
    return payload


@app.post("/sessions/{session_id}/attribution/insight")
async def interpret_session_attribution(session_id: str, body: AssistantInput, user: Owner, db: DB) -> dict:
    session = owned_session(db, user, session_id)
    if session.status not in {"CONFIRMED", "REVISED"}:
        raise HTTPException(status_code=409, detail="完成这次清算后，怀特才能复盘变化原因。")
    row = db.scalar(select(ClearingAttribution).where(ClearingAttribution.session_id == session.id, ClearingAttribution.user_id == user.id))
    payload = build_attribution(db, session, row.answers_json if row else [])
    context = {
        "attribution": payload,
        "current_totals": session.totals_json,
        "comparison": session.comparison_json,
        "rules": {
            "breakdown_is_authoritative": True,
            "do_not_call_asset_scale_change_investment_return": True,
            "distinguish_active_saving_market_price_fx_and_liquidity": True,
            "recommend_one_highest_impact_action_first": True,
        },
    }
    prompt = (
        "请把本次净资产变化解释成一份专业但容易读懂的清算复盘。必须准确引用归因金额，说明主动投入、市场价格、"
        "黄金、汇率、负债和未解释项各自贡献，不能把全部增长称为投资收益。特别比较净资产与可用现金是否同向，"
        "指出账面财富与短期支付能力的差别。最后只把一件影响最大、最容易执行的事放在最高优先级，其余路径作为备选。"
    )
    return await dispatch_financial_agent(db, user, prompt, context, context, body.provider, "complex")


def latest_confirmed(db: Session, user_id: str) -> ClearingSession | None:
    return db.scalar(select(ClearingSession).where(
        ClearingSession.user_id == user_id, ClearingSession.status.in_(["CONFIRMED", "REVISED"]),
        ClearingSession.deleted_at.is_(None),
    ).order_by(desc(ClearingSession.confirmed_at)).limit(1))


def goal_completion_prefix(goal: Goal) -> str:
    return f"GC:{goal.id.replace('-', '')[:16]}:"


def goal_completion_kind(goal: Goal) -> str:
    target = format(D(goal.target_cny).quantize(Decimal("0.01")), "f")
    digest = hashlib.sha256(f"{goal.id}:{target}".encode("utf-8")).hexdigest()[:12]
    return f"{goal_completion_prefix(goal)}{digest}"


def goal_completion_state(db: Session, goal: Goal, current: Decimal | None = None) -> dict:
    if current is None:
        current = D(db.scalar(select(func.coalesce(func.sum(GoalFundingAllocation.amount_cny), 0)).where(
            GoalFundingAllocation.user_id == goal.user_id,
            GoalFundingAllocation.goal_id == goal.id,
        )))
    if current < D(goal.target_cny):
        return {"completion_status": "IN_PROGRESS", "completion_confirmed_at": None}
    notice = db.scalar(select(Notification).where(
        Notification.user_id == goal.user_id,
        Notification.kind == goal_completion_kind(goal),
    ))
    return {
        "completion_status": "CONFIRMED" if notice and notice.read_at else "AWAITING_CONFIRMATION",
        "completion_confirmed_at": iso(notice.read_at) if notice else None,
    }


def sync_goal_completion_notifications(db: Session, user_id: str, *, commit: bool = True) -> list[dict]:
    goals = db.scalars(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at)).all()
    pending: list[dict] = []
    changed = False
    for goal in goals:
        current = D(db.scalar(select(func.coalesce(func.sum(GoalFundingAllocation.amount_cny), 0)).where(
            GoalFundingAllocation.user_id == user_id,
            GoalFundingAllocation.goal_id == goal.id,
        )))
        kind = goal_completion_kind(goal)
        notice = db.scalar(select(Notification).where(Notification.user_id == user_id, Notification.kind == kind))
        if current >= D(goal.target_cny):
            title = f"您的{goal.name}理财目标已完成，请前往确认！"
            body = f"已归属 {money(current)} 元，达到目标金额 {money(D(goal.target_cny))} 元。确认后一起庆祝这个里程碑。"
            if not notice:
                notice = Notification(
                    user_id=user_id,
                    kind=kind,
                    title=title,
                    body=body,
                )
                db.add(notice)
                changed = True
            elif not notice.read_at and (notice.title != title or notice.body != body):
                notice.title = title
                notice.body = body
                changed = True
            if not notice.read_at:
                pending.append({"id": goal.id, "name": goal.name})
        elif notice and not notice.read_at:
            db.delete(notice)
            changed = True
    if changed:
        db.flush()
        if commit:
            db.commit()
    return pending


def goal_progress(goal: Goal, latest: ClearingSession | None, db: Session) -> dict:
    current = D(db.scalar(select(func.coalesce(func.sum(GoalFundingAllocation.amount_cny), 0)).where(
        GoalFundingAllocation.user_id == goal.user_id,
        GoalFundingAllocation.goal_id == goal.id,
    )))
    target = D(goal.target_cny)
    gap = max(target - current, Decimal("0"))
    progress = min(current / target * D(100), D(100)) if target else Decimal("0")
    months_left = None
    required_monthly = None
    if goal.due_date:
        today = date.today()
        months_left = max((goal.due_date.year - today.year) * 12 + goal.due_date.month - today.month, 1)
        required_monthly = gap / D(months_left)
    if gap == 0:
        analysis = ["这个目标已经到达啦。接下来可以决定继续巩固，还是给自己安排一个新的方向。"]
    elif not latest:
        analysis = ["目标已经记好了。完成资产清算后，再从资金归属页给它分配专属资金。"]
    elif required_monthly is not None:
        analysis = [f"按目标日期计算，目前还差 {money(gap)} 元，平均每月需要准备约 {money(required_monthly)} 元。"]
    else:
        analysis = [f"目前已经走完 {money(progress)}%，还差 {money(gap)} 元。没有截止日期也没关系，可以按舒服的节奏慢慢推进。"]
    return {
        "current_cny": money(current),
        "progress_pct": money(progress),
        "gap_cny": money(gap),
        "months_left": months_left,
        "required_monthly_cny": money(required_monthly) if required_monthly is not None else None,
        "analysis": analysis,
        "uses_dedicated_funding": True,
    }


def serialize_goal_plan(plan: GoalPlan | None) -> dict | None:
    if not plan:
        return None
    return {
        "id": plan.id,
        "monthly_income_cny": money(D(plan.monthly_income_cny)),
        "monthly_fixed_expenses_cny": money(D(plan.monthly_fixed_expenses_cny)),
        "monthly_safety_buffer_cny": money(D(plan.monthly_safety_buffer_cny)),
        "calculation": plan.calculation_json,
        "guidance": plan.guidance_json,
        "provider": plan.provider,
        "model": plan.model,
        "updated_at": iso(plan.updated_at),
    }


def goal_payload(db: Session, goal: Goal, latest: ClearingSession | None) -> dict:
    plan = db.scalar(select(GoalPlan).where(GoalPlan.goal_id == goal.id, GoalPlan.user_id == goal.user_id))
    progress = goal_progress(goal, latest, db)
    return {
        "id": goal.id,
        "name": goal.name,
        "goal_type": goal.goal_type,
        "target_cny": money(D(goal.target_cny)),
        "due_date": iso(goal.due_date),
        "included_asset_types": goal.included_asset_types or [],
        **progress,
        **goal_completion_state(db, goal, D(progress["current_cny"])),
        "plan": serialize_goal_plan(plan),
    }


def serialize_action_item(item: ActionItem) -> dict:
    return {
        "id": item.id,
        "goal_id": item.goal_id,
        "title": item.title,
        "reason": item.reason,
        "expected_impact": item.expected_impact,
        "risk": item.risk,
        "review_trigger": item.review_trigger,
        "priority": item.priority,
        "status": item.status,
        "source": item.source,
        "due_date": iso(item.due_date),
        "completed_at": iso(item.completed_at),
        "created_at": iso(item.created_at),
        "updated_at": iso(item.updated_at),
    }


def intelligence_overview(db: Session, user_id: str) -> dict:
    latest = latest_confirmed(db, user_id)
    sessions = db.scalars(select(ClearingSession).where(
        ClearingSession.user_id == user_id,
        ClearingSession.status.in_(["CONFIRMED", "REVISED"]),
        ClearingSession.deleted_at.is_(None),
    ).order_by(ClearingSession.confirmed_at)).all()
    goals = db.scalars(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at)).all()
    plan = db.scalar(select(GoalPlan).where(GoalPlan.user_id == user_id).order_by(desc(GoalPlan.updated_at)))
    factors: list[dict] = []
    alerts: list[dict] = []
    score = Decimal("0")
    possible = Decimal("0")
    totals = latest.totals_json if latest else {}

    liquidity_months = None
    if latest and plan and D(plan.monthly_fixed_expenses_cny) > 0:
        liquidity_months = D(totals.get("liquid_assets_cny")) / D(plan.monthly_fixed_expenses_cny)
        factor_score = min(liquidity_months / D(6) * D(30), D(30))
        factors.append({
            "code": "LIQUIDITY",
            "name": "现金缓冲",
            "score": money(factor_score),
            "max_score": "30.00",
            "value": f"{money(liquidity_months)} 个月固定支出",
            "interpretation": "用可立即使用的资产覆盖固定支出的月数，6 个月及以上按满分计。",
        })
        score += factor_score
        possible += D(30)
        if liquidity_months < D(3):
            alerts.append({"level": "HIGH", "code": "LOW_LIQUIDITY", "title": "现金缓冲偏薄", "detail": "可立即使用的资产不足 3 个月固定支出，遇到收入波动时回旋空间会比较小。"})

    if latest and D(totals.get("assets_cny")) > 0:
        assets = D(totals.get("assets_cny"))
        liabilities = D(totals.get("liabilities_cny"))
        debt_ratio = liabilities / assets
        factor_score = max(D(0), D(25) * (D(1) - min(debt_ratio / D("0.8"), D(1))))
        factors.append({
            "code": "DEBT",
            "name": "负债承压",
            "score": money(factor_score),
            "max_score": "25.00",
            "value": f"{money(debt_ratio * D(100))}%",
            "interpretation": "负债占总资产的比例越低，资产价格或收入波动时越有余地。",
        })
        score += factor_score
        possible += D(25)
        if debt_ratio > D("0.5"):
            alerts.append({"level": "HIGH", "code": "DEBT_PRESSURE", "title": "负债占比较高", "detail": "负债已经超过总资产的一半，新增长期承诺前值得先看清还款节奏。"})

        by_type = {key: D(value) for key, value in totals.get("by_type", {}).items() if D(value) > 0}
        if by_type:
            top_type = max(by_type, key=by_type.get)
            top_ratio = by_type[top_type] / assets
            factor_score = max(D(0), D(20) * (D(1) - max(top_ratio - D("0.3"), D(0)) / D("0.7")))
            factors.append({
                "code": "CONCENTRATION",
                "name": "资产分散度",
                "score": money(factor_score),
                "max_score": "20.00",
                "value": f"最高类型 {top_type} · {money(top_ratio * D(100))}%",
                "interpretation": "单一资产类型占比越高，家庭资产越容易被同一种风险同时影响。",
            })
            score += factor_score
            possible += D(20)
            if top_ratio > D("0.5"):
                alerts.append({"level": "MEDIUM", "code": "CONCENTRATION", "title": "资产集中度较高", "detail": f"{top_type} 占总资产 {money(top_ratio * D(100))}%，它会主导整体资产变化。"})

    goal_rows = []
    if goals:
        on_track = 0
        assessable = 0
        for goal in goals:
            progress = goal_progress(goal, latest, db)
            goal_plan = db.scalar(select(GoalPlan).where(GoalPlan.goal_id == goal.id, GoalPlan.user_id == user_id))
            contribution = D((goal_plan.calculation_json or {}).get("suggested_monthly_contribution_cny")) if goal_plan else D(0)
            required = D(progress.get("required_monthly_cny")) if progress.get("required_monthly_cny") else None
            is_on_track = None
            if D(progress["gap_cny"]) == 0:
                is_on_track = True
            elif required is not None:
                assessable += 1
                is_on_track = contribution >= required
                if is_on_track:
                    on_track += 1
                else:
                    alerts.append({"level": "MEDIUM", "code": "GOAL_DRIFT", "title": f"“{goal.name}”的月计划偏离期限", "detail": f"按期每月约需 {money(required)} 元，目前计划为 {money(contribution)} 元。"})
            goal_rows.append({**goal_payload(db, goal, latest), "planned_monthly_cny": money(contribution), "on_track": is_on_track})
        if assessable:
            factor_score = D(15) * D(on_track) / D(assessable)
            factors.append({
                "code": "GOALS",
                "name": "目标可行度",
                "score": money(factor_score),
                "max_score": "15.00",
                "value": f"{on_track}/{assessable} 个有期限目标按计划可达",
                "interpretation": "比较目标期限所需金额和当前保存的月度计划。",
            })
            score += factor_score
            possible += D(15)

    freshness_days = None
    if latest:
        confirmed_date = (latest.confirmed_at or latest.started_at).date()
        freshness_days = max((date.today() - confirmed_date).days, 0)
    continuity = min(D(len(sessions)) / D(4) * D(6), D(6))
    freshness = D(4) if freshness_days is not None and freshness_days <= 45 else D(2) if freshness_days is not None and freshness_days <= 90 else D(0)
    data_score = continuity + freshness
    factors.append({
        "code": "DATA",
        "name": "数据连续性",
        "score": money(data_score),
        "max_score": "10.00",
        "value": f"{len(sessions)} 个清算点" + (f" · 最近 {freshness_days} 天" if freshness_days is not None else ""),
        "interpretation": "连续的真实快照越多，趋势与归因判断越可靠。",
    })
    score += data_score
    possible += D(10)
    if len(sessions) < 2:
        alerts.append({"level": "INFO", "code": "NEED_SECOND_SNAPSHOT", "title": "再完成一次清算就能看方向", "detail": "第二个确认快照会让趋势、变化幅度和偏离判断真正运转起来。"})

    readiness_score = score / possible * D(100) if possible else D(0)
    actions = db.scalars(select(ActionItem).where(ActionItem.user_id == user_id).order_by(ActionItem.status, ActionItem.priority, desc(ActionItem.updated_at))).all()
    return {
        "score": money(readiness_score),
        "score_label": "财务决策准备度",
        "score_explanation": "它衡量当前数据能否支持稳健决策，不代表投资表现，也不是征信评分。",
        "factors": factors,
        "alerts": alerts,
        "data_availability": {
            "has_snapshot": latest is not None,
            "snapshot_count": len(sessions),
            "has_cashflow": plan is not None,
            "goal_count": len(goals),
        },
        "cashflow_source": ({
            "monthly_income_cny": money(D(plan.monthly_income_cny)),
            "monthly_fixed_expenses_cny": money(D(plan.monthly_fixed_expenses_cny)),
            "monthly_safety_buffer_cny": money(D(plan.monthly_safety_buffer_cny)),
            "updated_at": iso(plan.updated_at),
        } if plan else None),
        "liquidity_months": money(liquidity_months) if liquidity_months is not None else None,
        "goals": goal_rows,
        "latest_totals": totals if latest else None,
        "actions": [serialize_action_item(item) for item in actions],
    }


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def build_goal_allocation(db: Session, user_id: str, available: Decimal, strategy: str) -> list[dict]:
    latest = latest_confirmed(db, user_id)
    goals = db.scalars(select(Goal).where(Goal.user_id == user_id).order_by(Goal.created_at)).all()
    rows: list[dict] = []
    for goal in goals:
        progress = goal_progress(goal, latest, db)
        gap = D(progress["gap_cny"])
        if gap <= 0:
            continue
        months_left = progress.get("months_left")
        required = D(progress.get("required_monthly_cny")) if progress.get("required_monthly_cny") else D(0)
        rows.append({
            "goal": goal,
            "gap": gap,
            "months_left": months_left,
            "required": min(required, gap),
            "allocation": D(0),
        })
    if not rows or available <= 0:
        return []

    due_total = sum((row["required"] for row in rows), D(0))
    if due_total > 0:
        scale = min(available / due_total, D(1))
        for row in rows:
            row["allocation"] = row["required"] * scale
    remaining = max(available - sum((row["allocation"] for row in rows), D(0)), D(0))
    strategy = strategy.upper()
    for _ in range(3):
        active = [row for row in rows if row["gap"] > row["allocation"]]
        if not active or remaining <= D("0.01"):
            break
        urgency_values = [D(1) / D(row["months_left"] or 48) for row in active]
        attainability_values = [D(1) / max(row["gap"], D(1)) for row in active]
        urgency_sum = sum(urgency_values, D(0))
        attainability_sum = sum(attainability_values, D(0))
        weights = []
        for index, row in enumerate(active):
            urgency = urgency_values[index] / urgency_sum if urgency_sum else D(0)
            attainability = attainability_values[index] / attainability_sum if attainability_sum else D(0)
            if strategy == "DEADLINE_FIRST":
                weight = urgency
            elif strategy == "SMALLEST_GAP":
                weight = attainability
            else:
                weight = urgency * D("0.65") + attainability * D("0.35")
            weights.append(weight)
        allocated_now = D(0)
        for row, weight in zip(active, weights):
            room = row["gap"] - row["allocation"]
            extra = min(remaining * weight, room)
            row["allocation"] += extra
            allocated_now += extra
        remaining = max(remaining - allocated_now, D(0))

    result = []
    for row in rows:
        contribution = row["allocation"]
        months = int((row["gap"] / contribution).to_integral_value(rounding="ROUND_CEILING")) if contribution > 0 else None
        projected = add_months(date.today(), months) if months is not None else None
        goal: Goal = row["goal"]
        result.append({
            "goal_id": goal.id,
            "goal_name": goal.name,
            "gap_cny": money(row["gap"]),
            "monthly_allocation_cny": money(contribution),
            "required_monthly_cny": money(row["required"]) if row["months_left"] else None,
            "projected_months": months,
            "projected_completion_date": iso(projected),
            "due_date": iso(goal.due_date),
            "on_track": projected <= goal.due_date if projected and goal.due_date else None,
        })
    return result


def stable_asset_key(item: AssetItem) -> str:
    identity = "|".join([
        (item.name or "").strip().lower(),
        (item.account_alias or "").strip().lower(),
        (item.asset_type or "").strip().upper(),
    ])
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def funding_asset_lineage(db: Session, item: AssetItem) -> list[AssetItem]:
    lineage = [item]
    seen = {item.id}
    current = item
    while True:
        metadata = current.metadata_json or {}
        previous_id = metadata.get("carried_from_item") or metadata.get("copied_from_item")
        if not previous_id or str(previous_id) in seen:
            break
        previous = db.get(AssetItem, str(previous_id))
        if not previous:
            break
        lineage.append(previous)
        seen.add(previous.id)
        current = previous
    return lineage


def funding_asset_key(db: Session, item: AssetItem) -> str:
    root = funding_asset_lineage(db, item)[-1]
    return hashlib.sha256(f"funding-asset:{root.id}".encode("utf-8")).hexdigest()


def funding_cents(value) -> Decimal:
    return D(money(D(value)))


def current_funding_assets(db: Session, latest: ClearingSession | None) -> tuple[dict[str, AssetItem], dict[str, str]]:
    assets: dict[str, AssetItem] = {}
    alias_candidates: dict[str, set[str]] = {}
    if not latest:
        return assets, {}
    for item in latest.items:
        if item.status not in {"CONFIRMED", "REVISED"} or item.is_liability:
            continue
        key = funding_asset_key(db, item)
        assets[key] = item
        aliases = {stable_asset_key(member) for member in funding_asset_lineage(db, item)}
        for alias in aliases:
            alias_candidates.setdefault(alias, set()).add(key)
    # Legacy identity keys may collide. Only migrate aliases that identify one
    # current asset unambiguously; the new lineage keys are always unique.
    aliases = {alias: next(iter(keys)) for alias, keys in alias_candidates.items() if len(keys) == 1}
    return assets, aliases


def reconcile_funding_allocations(db: Session, user_id: str, latest: ClearingSession | None) -> list[GoalFundingAllocation]:
    assets, aliases = current_funding_assets(db, latest)
    goals = set(db.scalars(select(Goal.id).where(Goal.user_id == user_id)).all())
    rows = db.scalars(select(GoalFundingAllocation).where(GoalFundingAllocation.user_id == user_id).order_by(GoalFundingAllocation.created_at, GoalFundingAllocation.id)).all()
    previous_count = len(rows)
    normalized: dict[tuple[str, str], Decimal] = {}
    changed = False
    for row in rows:
        current_key = row.asset_key if row.asset_key in assets else aliases.get(row.asset_key)
        if not current_key or row.goal_id not in goals:
            changed = True
            continue
        if current_key != row.asset_key:
            changed = True
        pair = (current_key, row.goal_id)
        normalized[pair] = normalized.get(pair, D(0)) + funding_cents(row.amount_cny)
    remaining_by_asset = {key: funding_cents(item.value_cny) for key, item in assets.items()}
    capped: dict[tuple[str, str], Decimal] = {}
    for (asset_key, goal_id), amount in normalized.items():
        remaining = remaining_by_asset.get(asset_key, D(0))
        accepted = min(amount, remaining)
        if accepted != amount:
            changed = True
        if accepted > 0:
            capped[(asset_key, goal_id)] = accepted
            remaining_by_asset[asset_key] = remaining - accepted
    normalized = capped
    if len(normalized) != len(rows):
        changed = True
    if changed:
        db.execute(delete(GoalFundingAllocation).where(GoalFundingAllocation.user_id == user_id))
        for (asset_key, goal_id), amount in normalized.items():
            if amount > 0:
                db.add(GoalFundingAllocation(user_id=user_id, asset_key=asset_key, goal_id=goal_id, amount_cny=amount))
        db.flush()
        rows = db.scalars(select(GoalFundingAllocation).where(GoalFundingAllocation.user_id == user_id)).all()
        log_event(db, user_id, "FUNDING_ALLOCATIONS_RECONCILED", {"before": previous_count, "after": len(rows)})
        db.commit()
    return rows


def build_attribution(db: Session, session: ClearingSession, answers: list[dict] | None = None) -> dict:
    previous = db.scalar(select(ClearingSession).where(
        ClearingSession.user_id == session.user_id,
        ClearingSession.status.in_(["CONFIRMED", "REVISED"]),
        ClearingSession.deleted_at.is_(None),
        ClearingSession.id != session.id,
        ClearingSession.confirmed_at < session.confirmed_at,
    ).order_by(desc(ClearingSession.confirmed_at)).limit(1)) if session.confirmed_at else None
    if not previous:
        return {
            "available": False,
            "reason": "这是第一份资产快照。下一次清算完成后，就能把变化拆开来看。",
            "session_id": session.id,
            "previous_session_id": None,
            "total_change_cny": "0.00",
            "breakdown": [],
            "questions": [],
            "answers": answers or [],
        }

    total_change = D(session.totals_json.get("net_worth_cny")) - D(previous.totals_json.get("net_worth_cny"))
    components = {
        "NEW_CAPITAL": D(0),
        "STOCK_PRICE": D(0),
        "GOLD_PRICE": D(0),
        "FX": D(0),
        "DEBT_REDUCTION": D(0),
        "VALUATION_METHOD": D(0),
    }
    previous_by_id = {item.id: item for item in previous.items if item.status in {"CONFIRMED", "REVISED"}}
    previous_by_key = {stable_asset_key(item): item for item in previous_by_id.values()}
    matched_previous: set[str] = set()
    changes: list[dict] = []

    for current in [item for item in session.items if item.status in {"CONFIRMED", "REVISED"}]:
        metadata = current.metadata_json or {}
        previous_item = previous_by_id.get(str(metadata.get("carried_from_item", ""))) or previous_by_key.get(stable_asset_key(current))
        current_value = D(current.value_cny)
        if not previous_item:
            changes.append({"name": current.name, "change_cny": money(current_value), "kind": "NEW_OR_UNMATCHED"})
            continue
        matched_previous.add(previous_item.id)
        previous_value = D(previous_item.value_cny)
        item_change = (-current_value + previous_value) if current.is_liability else (current_value - previous_value)
        explained = D(0)
        if current.is_liability and previous_item.is_liability:
            debt_effect = previous_value - current_value
            components["DEBT_REDUCTION"] += debt_effect
            explained += debt_effect
        elif current.asset_type == "PHYSICAL_GOLD" and previous_item.asset_type == "PHYSICAL_GOLD":
            current_grams = D(current.quantity)
            previous_grams = D(previous_item.quantity)
            current_price = D((metadata.get("gold_quote") or {}).get("cny_per_gram"))
            previous_price = D(((previous_item.metadata_json or {}).get("gold_quote") or {}).get("cny_per_gram"))
            if current_price > 0 and previous_price > 0:
                price_effect = min(current_grams, previous_grams) * (current_price - previous_price)
                quantity_effect = (current_grams - previous_grams) * current_price
                components["GOLD_PRICE"] += price_effect
                components["NEW_CAPITAL"] += quantity_effect
                explained += price_effect + quantity_effect
        elif current.asset_type in {"STOCK", "FUND"} and previous_item.asset_type == current.asset_type:
            current_quantity = D(current.quantity)
            previous_quantity = D(previous_item.quantity)
            if current_quantity > 0 and previous_quantity > 0:
                current_unit = current_value / current_quantity
                previous_unit = previous_value / previous_quantity
                price_effect = min(current_quantity, previous_quantity) * (current_unit - previous_unit)
                quantity_effect = (current_quantity - previous_quantity) * current_unit
                components["STOCK_PRICE"] += price_effect
                components["NEW_CAPITAL"] += quantity_effect
                explained += price_effect + quantity_effect
        if not current.is_liability and current.original_currency == previous_item.original_currency and current.original_currency != "CNY":
            common_original = min(D(current.original_value), D(previous_item.original_value))
            fx_effect = common_original * (D(current.fx_rate_to_cny) - D(previous_item.fx_rate_to_cny))
            components["FX"] += fx_effect
            explained += fx_effect
        previous_method = (previous_item.metadata_json or {}).get("valuation_method")
        current_method = metadata.get("valuation_method")
        if previous_method and current_method and previous_method != current_method:
            method_effect = item_change - explained
            components["VALUATION_METHOD"] += method_effect
            explained += method_effect
        changes.append({"name": current.name, "change_cny": money(item_change), "unexplained_cny": money(item_change - explained), "kind": "MATCHED"})

    for previous_item in previous_by_id.values():
        if previous_item.id not in matched_previous:
            effect = D(previous_item.value_cny) if previous_item.is_liability else -D(previous_item.value_cny)
            changes.append({"name": previous_item.name, "change_cny": money(effect), "kind": "REMOVED_OR_UNMATCHED"})

    answered_components: dict[str, Decimal] = {}
    answer_list = (answers or [])[:3]
    answer_choice = next((item.get("value") for item in answer_list if item.get("question_id") == "cause"), None)
    answer_amount = next((D(item.get("value")) for item in answer_list if item.get("question_id") == "amount"), D(0))
    known_total = sum(components.values(), D(0))
    unexplained = total_change - known_total
    if answer_choice and answer_amount > 0 and unexplained != 0:
        signed_amount = min(abs(answer_amount), abs(unexplained)) * (D(1) if unexplained > 0 else D(-1))
        label_map = {
            "LARGE_EXPENSE": "大额消费",
            "UNRECORDED_ACCOUNT": "转入尚未录入的账户",
            "DEBT_PAYMENT": "用于偿还负债",
            "NEW_ASSET": "购置新的资产",
            "GIFT_OR_LOAN": "赠送或借给他人",
            "OTHER": "其他已说明变化",
        }
        answered_components[label_map.get(str(answer_choice), "其他已说明变化")] = signed_amount
        unexplained -= signed_amount

    labels = {
        "NEW_CAPITAL": "新增投入",
        "STOCK_PRICE": "股票 / 基金价格变化",
        "GOLD_PRICE": "黄金价格变化",
        "FX": "汇率变化",
        "DEBT_REDUCTION": "负债减少",
        "VALUATION_METHOD": "估值方式调整",
    }
    breakdown = [
        {"code": code, "label": labels[code], "value_cny": money(value)}
        for code, value in components.items() if abs(value) >= D("0.01")
    ]
    breakdown.extend({"code": "ANSWERED", "label": label, "value_cny": money(value)} for label, value in answered_components.items())
    breakdown.append({"code": "UNEXPLAINED", "label": "尚未解释的变化", "value_cny": money(unexplained)})
    breakdown.sort(key=lambda item: abs(D(item["value_cny"])), reverse=True)
    biggest = max(changes, key=lambda item: abs(D(item.get("unexplained_cny", item.get("change_cny"))))) if changes else None
    questions = []
    if abs(unexplained) >= D("100"):
        direction = "增加" if unexplained > 0 else "减少"
        subject = f"其中“{biggest['name']}”变化最明显。" if biggest else ""
        questions = [
            {
                "id": "cause",
                "type": "choice",
                "question": f"还有 {money(abs(unexplained))} 元{direction}没有找到明确原因。{subject}最接近实际情况的是哪一种？",
                "options": [
                    {"value": "LARGE_EXPENSE", "label": "发生了大额消费"},
                    {"value": "UNRECORDED_ACCOUNT", "label": "转到了尚未录入的账户"},
                    {"value": "DEBT_PAYMENT", "label": "用于偿还负债"},
                    {"value": "NEW_ASSET", "label": "购买了新的资产"},
                    {"value": "GIFT_OR_LOAN", "label": "赠送或借给他人"},
                    {"value": "OTHER", "label": "其他"},
                ],
            },
            {"id": "amount", "type": "amount", "question": "这次大约涉及多少钱？", "suggested_value": money(abs(unexplained))},
            {"id": "remember", "type": "boolean", "question": "以后遇到同类变化时，要把这个答案作为优先提示吗？"},
        ]
    active_total = sum((abs(D(item["value_cny"])) for item in breakdown if item["code"] != "UNEXPLAINED"), D(0))
    main_contributor = next((item for item in breakdown if item["code"] != "UNEXPLAINED"), None)
    liquid_change = D(session.totals_json.get("liquid_assets_cny")) - D(previous.totals_json.get("liquid_assets_cny"))
    narrative = (
        f"本次净资产{'增加' if total_change >= 0 else '减少'} {money(abs(total_change))} 元。"
        + (f"目前已解释的变化中，{main_contributor['label']}影响最大（{money(abs(D(main_contributor['value_cny'])))} 元）。" if main_contributor else "")
        + (f"与此同时，可用现金{'增加' if liquid_change >= 0 else '减少'} {money(abs(liquid_change))} 元，短期支付能力{'有所增强' if liquid_change >= 0 else '需要额外留意'}。")
    )
    return {
        "available": True,
        "session_id": session.id,
        "previous_session_id": previous.id,
        "total_change_cny": money(total_change),
        "liquid_change_cny": money(liquid_change),
        "explained_abs_cny": money(active_total),
        "breakdown": breakdown,
        "questions": questions,
        "answers": answer_list,
        "narrative": narrative,
        "item_changes": changes,
        "calculation_note": "仅把数量、国际金价、汇率、负债余额和估值方式等有明确数据依据的变化自动归因；其余变化保留为未解释项。",
    }


async def dispatch_financial_agent(
    db: Session,
    user: User,
    message: str,
    full_context: dict,
    minimized_context: dict,
    provider: str,
    depth: str,
) -> dict:
    requested = provider.upper()
    preference = user.model_preference.upper()
    wants_openai = requested == "OPENAI" or (requested == "AUTO" and preference == "OPENAI")
    allowed_openai = user.region.upper() in {"KR", "OTHER_SUPPORTED"}
    complex_task = depth.lower() == "complex"
    if wants_openai and not allowed_openai:
        if requested == "OPENAI":
            raise HTTPException(status_code=403, detail="当前地区设置还没有开启 OpenAI。可以在系统设置里切换地区，或先使用自动线路。")
        wants_openai = False
    if wants_openai:
        try:
            result = await OpenAIGatewayClient().analyze(db, user.id, message, minimized_context, complex_task)
            return {
                "provider": "OPENAI",
                "model": settings.openai_complex_model if complex_task else settings.openai_ordinary_model,
                "result": result,
                "context_minimized": True,
            }
        except Exception as exc:
            if not isinstance(exc, ProviderError):
                log_event(db, user.id, "OPENAI_AGENT_UNEXPECTED_ERROR", {"error_type": type(exc).__name__}, "ERROR")
            try:
                fallback = await QwenClient().analyze(db, user.id, message, full_context, complex_task)
                return {
                    "provider": "QWEN",
                    "fallback_from": "OPENAI",
                    "fallback_reason": str(exc),
                    "model": settings.qwen_complex_model if complex_task else settings.qwen_chat_model,
                    "result": fallback,
                }
            except Exception as fallback_exc:
                if not isinstance(fallback_exc, ProviderError):
                    log_event(db, user.id, "QWEN_AGENT_UNEXPECTED_ERROR", {"error_type": type(fallback_exc).__name__}, "ERROR")
                return deterministic_agent_fallback(
                    message,
                    minimized_context,
                    f"OpenAI 与百炼暂时都没有完成分析：{fallback_exc}",
                    fallback_from="OPENAI_AND_QWEN",
                )
    try:
        result = await QwenClient().analyze(db, user.id, message, full_context, complex_task)
        return {
            "provider": "QWEN",
            "model": settings.qwen_complex_model if complex_task else settings.qwen_chat_model,
            "result": result,
        }
    except Exception as exc:
        if not isinstance(exc, ProviderError):
            log_event(db, user.id, "QWEN_AGENT_UNEXPECTED_ERROR", {"error_type": type(exc).__name__}, "ERROR")
        return deterministic_agent_fallback(message, minimized_context, str(exc), fallback_from="QWEN")


def deterministic_agent_fallback(
    message: str,
    context: dict,
    reason: str,
    fallback_from: str,
) -> dict:
    allocation = context.get("deterministic_allocation") or {}
    spending = context.get("deterministic_ruling") or {}
    selected_metric = context.get("selected_metric")
    verified = context.get("verified_series") or {}
    latest_totals = context.get("latest_totals") or {}
    key_numbers: list[dict] = []
    facts: list[str] = []
    analysis: list[str] = []
    recommendations: list[dict] = []
    if spending:
        verdict = spending.get("verdict_label", "已经算好")
        safe = spending.get("safe_to_spend_cny", "0.00")
        simulation = spending.get("simulation") or {}
        battery = spending.get("battery") or {}
        summary = f"结论：{verdict}。这次判断已经按你的真实资产、近期支出、目标占用和现金缓冲完成计算。"
        key_numbers = [
            {"label": "放心花上限", "value": f"{safe} 元", "meaning": "不挤占当前保护资金的本月参考额度"},
            {"label": "买完可用现金", "value": f"{simulation.get('cash_after_cny', '0.00')} 元", "meaning": "完成这笔支出后的流动资产"},
            {"label": "财务电量", "value": f"{battery.get('before_pct', '0')}% → {battery.get('after_pct', '0')}%", "meaning": "必要生活保障的变化"},
        ]
        facts = [
            f"是否需要卖出投资资产：{'需要' if spending.get('needs_investment_sale') else '不需要'}。",
            f"对目标进度的预计影响：{spending.get('goal_delay_days') or 0} 天。",
        ]
        analysis = list(spending.get("regret_warnings") or [])[:4]
        recommendations = [{
            "priority": "HIGH",
            "action": verdict,
            "reason": spending.get("calculation_note", "已先保护必要资金，再计算可用额度。"),
            "expected_impact": f"买完后的状态是“{battery.get('after_label', '已重新计算')}”。",
            "risk": analysis[0] if analysis else "当前没有额外触发后悔预警。",
            "review_trigger": "收入、近期支出、目标或购买预算变化时重新裁决。",
        }]
    elif allocation:
        available = allocation.get("monthly_available_cny", "0.00")
        allocated = allocation.get("monthly_allocated_cny", "0.00")
        unallocated = allocation.get("monthly_unallocated_cny", "0.00")
        summary = f"程序已经完成资金调度：本月可安排 {available} 元，已分配 {allocated} 元，还留有 {unallocated} 元余地。"
        key_numbers = [
            {"label": "本月可安排", "value": f"{available} 元", "meaning": "收入扣除固定支出与机动金后的上限"},
            {"label": "已经安排", "value": f"{allocated} 元", "meaning": "分给全部未完成目标的合计"},
            {"label": "剩余余地", "value": f"{unallocated} 元", "meaning": "没有重复分配的月结余"},
        ]
        facts = [f"调度策略为 {allocation.get('strategy', 'BALANCED')}。", f"期限冲突 {allocation.get('deadline_conflict_count', 0)} 个。"]
        recommendations = [{
            "priority": "HIGH",
            "action": "先按页面列出的月度金额执行一个月",
            "reason": "这些金额由程序按可用结余、目标缺口和期限计算，没有超过本月上限。",
            "expected_impact": "每个目标都有明确资金去向，同时保留未分配余地。",
            "risk": "收入、固定支出或目标期限变化后，原方案会失真。",
            "review_trigger": "下次收入到账、固定支出变化或一个月后重新生成。",
        }]
    elif selected_metric and selected_metric in verified:
        selected = verified[selected_metric]
        curve = selected.get("analysis") or {}
        points = selected.get("points") or []
        change = curve.get("absolute_change", curve.get("total_change", "0.00"))
        summary = f"这条趋势已有 {len(points)} 个确认点，累计变化 {change} 元；它代表资产规模变化，不等同于投资收益。"
        key_numbers = [
            {"label": "确认点", "value": str(len(points)), "meaning": "每一点都来自一次已确认清算"},
            {"label": "累计变化", "value": f"{change} 元", "meaning": "可能同时包含投入、价格、汇率与负债变化"},
            {"label": "最大回撤", "value": str(curve.get("max_drawdown_pct", "—")), "meaning": "历史清算点之间出现过的最大下行幅度"},
        ]
        facts = ["趋势至少包含两个已确认清算点。", "程序计算结果没有把净资产变化当作投资收益。"]
        analysis = [str(item) for item in curve.get("limitations", [])[:3]]
        recommendations = [{
            "priority": "HIGH",
            "action": "先完成页面上的三问清算",
            "reason": "它能把尚未解释的变化归到最可能的真实原因。",
            "expected_impact": "下一次趋势解读会更接近真实投入、消费与市场变化。",
            "risk": "没有流水时仍可能保留少量无法解释的差额。",
            "review_trigger": "回答三问后立即重新解读，或下次清算时复盘。",
        }]
    else:
        net = latest_totals.get("net_worth_cny", "0.00")
        liquid = latest_totals.get("liquid_assets_cny", "0.00")
        summary = "程序已经先把可确认的数字整理好了，你仍然可以继续使用当前页面。"
        key_numbers = [
            {"label": "净资产", "value": f"{net} 元", "meaning": "最近一次已确认清算的资产减负债"},
            {"label": "可用资金", "value": f"{liquid} 元", "meaning": "目前记录为可较快使用的资产"},
        ]
    return {
        "provider": "RULE_ENGINE",
        "model": "deterministic-financial-fallback-v1",
        "fallback_from": fallback_from,
        "fallback_reason": reason,
        "result": {
            "executive_summary": summary,
            "confirmed_facts": facts,
            "key_numbers": key_numbers,
            "analysis": analysis,
            "recommendations": recommendations,
            "alternatives": ["稍后重新连接怀特的深度分析，程序计算结果不会因此改变。"],
            "assumptions": [],
            "limitations": ["智能线路本次没有及时完成，当前文字由确定性规则根据页面数字生成。"],
            "follow_up_questions": [],
            "requires_owner_confirmation": False,
        },
    }


def spending_profile_payload(db: Session, user_id: str) -> dict:
    row = db.scalar(select(SpendingProfile).where(SpendingProfile.user_id == user_id))
    if row:
        return {
            "configured": True,
            "source": "SPENDING_PROFILE",
            "monthly_income_cny": money(D(row.monthly_income_cny)),
            "monthly_essential_expenses_cny": money(D(row.monthly_essential_expenses_cny)),
            "monthly_current_expenses_cny": money(D(row.monthly_current_expenses_cny)),
            "emergency_months": money(D(row.emergency_months)),
        }
    plan = db.scalar(select(GoalPlan).where(GoalPlan.user_id == user_id).order_by(desc(GoalPlan.updated_at)))
    if plan and D(plan.monthly_fixed_expenses_cny) > 0:
        return {
            "configured": True,
            "source": "LATEST_GOAL_PLAN",
            "monthly_income_cny": money(D(plan.monthly_income_cny)),
            "monthly_essential_expenses_cny": money(D(plan.monthly_fixed_expenses_cny)),
            "monthly_current_expenses_cny": money(D(plan.monthly_fixed_expenses_cny)),
            "emergency_months": "6.00",
        }
    return {
        "configured": False,
        "source": "MISSING",
        "monthly_income_cny": "0.00",
        "monthly_essential_expenses_cny": "0.00",
        "monthly_current_expenses_cny": "0.00",
        "emergency_months": "6.00",
    }


def extract_spending_amount(decision: str) -> Decimal | None:
    import re

    normalized = decision.replace(",", "").replace("，", "")
    ten_thousand = re.search(r"(\d+(?:\.\d+)?)\s*万", normalized)
    if ten_thousand:
        return D(ten_thousand.group(1)) * D(10000)
    currency = re.search(r"(?:¥|￥)?\s*(\d+(?:\.\d+)?)\s*(?:元|块|人民币)?", normalized)
    return D(currency.group(1)) if currency else None


def build_spending_snapshot(db: Session, user_id: str, purchase_amount: Decimal = Decimal("0")) -> dict:
    profile = spending_profile_payload(db, user_id)
    latest = latest_confirmed(db, user_id)
    if not latest:
        return {
            "ready": False,
            "reason": "先完成一次资产清算，怀特才知道现在手里有哪些钱。",
            "profile": profile,
        }
    if not profile["configured"]:
        return {
            "ready": False,
            "reason": "再告诉怀特每月收入和生活开销，就能算出真正可以放心花的额度。",
            "profile": profile,
        }
    income = D(profile["monthly_income_cny"])
    essential = D(profile["monthly_essential_expenses_cny"])
    current_spend = max(D(profile["monthly_current_expenses_cny"]), essential)
    emergency_months = D(profile["emergency_months"])
    totals = latest.totals_json or {}
    liquid = D(totals.get("liquid_assets_cny"))
    assets = D(totals.get("assets_cny"))
    net_worth = D(totals.get("net_worth_cny"))
    liabilities = D(totals.get("liabilities_cny"))
    confirmed_items = [item for item in latest.items if item.status in {"CONFIRMED", "REVISED"} and not item.is_liability]
    cash_like = sum((
        D(item.value_cny)
        for item in confirmed_items
        if item.asset_type in {"CASH", "FIXED_DEPOSIT"} and item.liquidity_level in {"HIGH", "MEDIUM"}
    ), D(0))
    allocations = reconcile_funding_allocations(db, user_id, latest)
    allocated_by_asset: dict[str, Decimal] = {}
    for allocation in allocations:
        allocated_by_asset[allocation.asset_key] = allocated_by_asset.get(allocation.asset_key, D(0)) + D(allocation.amount_cny)
    committed_liquid = sum((
        min(D(item.value_cny), allocated_by_asset.get(funding_asset_key(db, item), D(0)))
        for item in confirmed_items
        if item.liquidity_level == "HIGH"
    ), D(0))
    horizon = date.today() + timedelta(days=90)
    obligations = db.scalars(select(FutureObligation).where(
        FutureObligation.user_id == user_id,
        FutureObligation.status == "UPCOMING",
        FutureObligation.due_date <= horizon,
    )).all()
    upcoming_certain = sum((D(row.amount_cny) for row in obligations if row.likelihood == "CERTAIN"), D(0))
    upcoming_probable = sum((D(row.amount_cny) * D("0.7") for row in obligations if row.likelihood != "CERTAIN"), D(0))
    upcoming = upcoming_certain + upcoming_probable
    debt_buffer = min(liabilities, essential) if liabilities > 0 else D(0)
    investment = D(totals.get("investment_assets_cny"))
    by_currency = totals.get("by_currency", {}) or {}
    foreign = sum((D(value) for currency, value in by_currency.items() if currency != "CNY"), D(0))
    investment_pct = investment / assets * D(100) if assets > 0 else D(0)
    foreign_pct = foreign / assets * D(100) if assets > 0 else D(0)
    risk_level = "HIGH" if investment_pct > 60 or foreign_pct > 50 else "MEDIUM" if investment_pct > 35 or foreign_pct > 30 else "LOW"
    monthly_surplus = max(income - current_spend, D(0))
    risk_reserve = monthly_surplus * (D("0.15") if risk_level == "HIGH" else D("0.05") if risk_level == "MEDIUM" else D(0))
    emergency_reserve = essential * emergency_months
    protected_cash = emergency_reserve + upcoming + committed_liquid + debt_buffer + risk_reserve
    free_cash = max(liquid - protected_cash, D(0))
    if income > 0:
        safe_month = min(free_cash, monthly_surplus)
    else:
        safe_month = min(free_cash, essential * D("0.1"))
    reassess_threshold = min(free_cash, safe_month * D("1.4") + essential * D("0.2"))
    amount = max(D(purchase_amount), D(0))
    liquid_after = max(liquid - amount, D(0))
    cash_like_after = max(cash_like - amount, D(0))
    effective_before = max(liquid - upcoming - committed_liquid - debt_buffer, D(0))
    effective_after = max(liquid_after - upcoming - committed_liquid - debt_buffer, D(0))

    def runway(cash: Decimal, monthly: Decimal) -> str | None:
        return money(cash / monthly) if monthly > 0 else None

    def battery(cash: Decimal) -> Decimal:
        target = essential * emergency_months
        return min(max(cash / target * D(100), D(0)), D(100)) if target > 0 else D(0)

    battery_before = battery(effective_before)
    battery_after = battery(effective_after)

    def battery_label(value: Decimal) -> str:
        if value >= 80:
            return "比较安心"
        if value >= 60:
            return "还有余地"
        if value >= 40:
            return "需要留心"
        return "先稳住现金"

    needs_investment_sale = amount > liquid
    invades_emergency = liquid_after < emergency_reserve
    invades_goals = liquid_after < committed_liquid + upcoming
    if amount <= safe_month and battery_after >= 60 and not needs_investment_sale:
        verdict = "DO_IT"
        verdict_label = "放心做"
    elif amount <= max(reassess_threshold, safe_month) and battery_after >= 40 and not needs_investment_sale:
        verdict = "ADJUST"
        verdict_label = "可以做，但要调整"
    else:
        verdict = "WAIT"
        verdict_label = "现在先别做"
    suggested_budget = min(amount, safe_month) if verdict == "DO_IT" else safe_month
    plans = db.scalars(select(GoalPlan).where(GoalPlan.user_id == user_id)).all()
    monthly_goal_contribution = sum((D((plan.calculation_json or {}).get("suggested_monthly_contribution_cny")) for plan in plans), D(0))
    over_safe = max(amount - safe_month, D(0))
    delay_days = int((over_safe / monthly_goal_contribution * D(30)).to_integral_value(rounding="ROUND_CEILING")) if over_safe > 0 and monthly_goal_contribution > 0 else 0 if over_safe == 0 else None
    regrets = []
    if invades_emergency:
        regrets.append("这笔钱会碰到应急资金，遇到收入中断时缓冲会变薄。")
    if invades_goals:
        regrets.append("它可能占用已经留给目标或近期支出的资金。")
    if needs_investment_sale:
        regrets.append("现有可用现金不够，完成决定可能需要卖出股票、基金或黄金。")
    if upcoming > 0 and liquid_after < upcoming + emergency_reserve:
        regrets.append("未来 90 天还有确定或大概率支出，买完后两边可能会抢同一笔钱。")
    if risk_level != "LOW" and battery_after < 60:
        regrets.append("投资或外币占比较高，而买完后现金缓冲偏薄，市场波动时选择会更少。")
    alternatives = []
    if suggested_budget > 0 and suggested_budget < amount:
        alternatives.append(f"把预算降到 {money(suggested_budget)} 元以内，先守住现金缓冲。")
    if monthly_surplus > 0 and amount > safe_month:
        months = int((amount / monthly_surplus).to_integral_value(rounding="ROUND_CEILING"))
        alternatives.append(f"先准备 {months} 个月，每月留出 {money(min(monthly_surplus, amount))} 元，再决定时不用动目标资金。")
        alternatives.append("等下一次收入到账后再做同一笔模拟，看看财务电量是否回到更安心的位置。")
    if amount > 0:
        alternatives.append(f"分两阶段准备：先留出 {money(amount / D(2))} 元，剩余部分下个月再补齐。")
    return {
        "ready": True,
        "snapshot_id": latest.id,
        "profile": profile,
        "safe_to_spend_cny": money(safe_month),
        "reassess_above_cny": money(reassess_threshold),
        "free_cash_after_reserves_cny": money(free_cash),
        "protected_cash_cny": money(protected_cash),
        "protection": {
            "emergency_reserve_cny": money(emergency_reserve),
            "upcoming_90d_cny": money(upcoming),
            "committed_goal_cash_cny": money(committed_liquid),
            "debt_buffer_cny": money(debt_buffer),
            "risk_reserve_cny": money(risk_reserve),
        },
        "risk": {
            "level": risk_level,
            "investment_pct": money(investment_pct),
            "foreign_currency_pct": money(foreign_pct),
        },
        "battery": {
            "before_pct": money(battery_before),
            "after_pct": money(battery_after),
            "before_label": battery_label(battery_before),
            "after_label": battery_label(battery_after),
            "current_lifestyle_months_before": runway(liquid, current_spend),
            "current_lifestyle_months_after": runway(liquid_after, current_spend),
            "essential_only_months_before": runway(liquid, essential),
            "essential_only_months_after": runway(liquid_after, essential),
            "without_selling_investments_months_before": runway(cash_like, essential),
            "without_selling_investments_months_after": runway(cash_like_after, essential),
        },
        "simulation": {
            "amount_cny": money(amount),
            "cash_before_cny": money(liquid),
            "cash_after_cny": money(liquid_after),
            "net_worth_before_cny": money(net_worth),
            "net_worth_after_cny": money(net_worth - amount),
        },
        "verdict": verdict,
        "verdict_label": verdict_label,
        "suggested_max_budget_cny": money(suggested_budget),
        "needs_investment_sale": needs_investment_sale,
        "goal_delay_days": delay_days,
        "regret_warnings": regrets[:4],
        "alternatives": alternatives[:4],
        "calculation_note": "先守住应急资金、未来 90 天支出、已归属目标的现金与负债缓冲，再用本月结余确定放心花额度。",
    }


@app.get("/spending/profile")
def get_spending_profile(user: Owner, db: DB) -> dict:
    return spending_profile_payload(db, user.id)


@app.put("/spending/profile")
def update_spending_profile(body: SpendingProfileInput, user: Owner, db: DB) -> dict:
    if body.monthly_current_expenses_cny < body.monthly_essential_expenses_cny:
        raise HTTPException(status_code=422, detail="维持当前生活的开销不能低于必要生活费，请再核对一下。")
    if body.monthly_income_cny and body.monthly_current_expenses_cny > body.monthly_income_cny * D(5):
        raise HTTPException(status_code=422, detail="当前开销明显高于收入很多，请确认是否多输入了一个零。")
    row = db.scalar(select(SpendingProfile).where(SpendingProfile.user_id == user.id))
    if not row:
        row = SpendingProfile(user_id=user.id)
        db.add(row)
    row.monthly_income_cny = body.monthly_income_cny
    row.monthly_essential_expenses_cny = body.monthly_essential_expenses_cny
    row.monthly_current_expenses_cny = body.monthly_current_expenses_cny
    row.emergency_months = body.emergency_months
    row.updated_at = utcnow()
    log_event(db, user.id, "SPENDING_PROFILE_UPDATED")
    db.commit()
    db.refresh(row)
    return spending_profile_payload(db, user.id)


@app.get("/spending/safe-to-spend")
def safe_to_spend(user: Owner, db: DB) -> dict:
    return build_spending_snapshot(db, user.id)


@app.post("/spending/preview")
def preview_spending(body: SpendingPreviewInput, user: Owner, db: DB) -> dict:
    amount = body.amount_cny or extract_spending_amount(body.decision)
    if not amount or amount <= 0:
        raise HTTPException(status_code=422, detail="告诉我大约要花多少钱就好，例如“15000”或“1.5 万”。")
    return {**build_spending_snapshot(db, user.id, amount), "decision": body.decision, "category": body.category.upper(), "planned_date": iso(body.planned_date)}


@app.post("/spending/ruling")
async def rule_spending(body: SpendingRulingInput, user: Owner, db: DB) -> dict:
    amount = body.amount_cny or extract_spending_amount(body.decision)
    if not amount or amount <= 0:
        raise HTTPException(status_code=422, detail="告诉我大约要花多少钱就好，例如“15000”或“1.5 万”。")
    result = build_spending_snapshot(db, user.id, amount)
    if not result.get("ready"):
        raise HTTPException(status_code=409, detail=result.get("reason"))
    context = {
        "decision": body.decision,
        "amount_cny": money(amount),
        "deterministic_ruling": result,
        "rules": {
            "verdict_cannot_be_changed": True,
            "only_three_allowed_verdicts": ["放心做", "可以做，但要调整", "现在先别做"],
            "do_not_recommend_borrowing_for_consumption": True,
            "give_at_most_three_concrete_alternatives": True,
        },
    }
    prompt = (
        "请复核这次花钱决定。程序已经算好结论、最高预算、财务电量、目标延迟、是否需要卖投资和后悔预警，"
        "不得改变这些数字与结论。只用普通人一眼能懂的语言解释最重要的原因，并把替代方案按最容易执行的顺序排列。"
    )
    agent = await dispatch_financial_agent(db, user, prompt, context, context, body.provider, body.depth)
    row = SpendingDecision(
        user_id=user.id,
        decision_text=body.decision,
        category=body.category.upper(),
        amount_cny=amount,
        planned_date=body.planned_date,
        verdict=result["verdict"],
        result_json=result,
        agent_json=agent["result"],
        provider=agent["provider"],
        model=agent["model"],
    )
    db.add(row)
    log_event(db, user.id, "SPENDING_DECISION_RULED", {"verdict": result["verdict"], "provider": agent["provider"]})
    db.commit()
    db.refresh(row)
    return {"id": row.id, "decision": row.decision_text, "created_at": iso(row.created_at), "result": result, "agent": agent}


@app.get("/spending/decisions")
def list_spending_decisions(user: Owner, db: DB) -> list[dict]:
    rows = db.scalars(select(SpendingDecision).where(SpendingDecision.user_id == user.id).order_by(desc(SpendingDecision.created_at)).limit(20)).all()
    return [{
        "id": row.id,
        "decision": row.decision_text,
        "amount_cny": money(D(row.amount_cny)),
        "verdict": row.verdict,
        "result": row.result_json,
        "provider": row.provider,
        "model": row.model,
        "created_at": iso(row.created_at),
    } for row in rows]


@app.get("/dashboard")
def dashboard(user: Owner, db: DB) -> dict:
    latest = latest_confirmed(db, user.id)
    schedule = db.scalar(select(ClearingSchedule).where(ClearingSchedule.user_id == user.id))
    if not latest:
        goals = [goal_payload(db, goal, None) for goal in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()]
        return {"has_snapshot": False, "next_clearing_at": iso(schedule.next_run_at) if schedule else None, "goals": goals, "risks": [], "trend": {"data_level": "EMPTY", "point_count": 0}, "spending": build_spending_snapshot(db, user.id)}
    confirmed_sessions = db.scalars(select(ClearingSession).where(
        ClearingSession.user_id == user.id, ClearingSession.status.in_(["CONFIRMED", "REVISED"]), ClearingSession.deleted_at.is_(None)
    ).order_by(ClearingSession.confirmed_at)).all()
    points = build_series(confirmed_sessions, "net_worth_cny")
    trend = analyze_series(points)
    goals = [goal_payload(db, goal, latest) for goal in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()]
    totals = latest.totals_json
    assets = D(totals.get("assets_cny"))
    risks = []
    if assets:
        by_type = {key: D(value) for key, value in totals.get("by_type", {}).items()}
        if by_type and max(by_type.values()) / assets > Decimal("0.5"):
            top = max(by_type, key=by_type.get)
            risks.append({"level": "MEDIUM", "code": "CONCENTRATION", "title": "资产较集中", "detail": f"{top} 占总资产超过 50%。"})
        foreign = sum((D(value) for key, value in totals.get("by_currency", {}).items() if key != "CNY"), Decimal("0"))
        if foreign / assets > Decimal("0.3"):
            risks.append({"level": "INFO", "code": "FX_EXPOSURE", "title": "外币敞口较高", "detail": "外币资产超过总资产 30%，汇率变化会明显影响人民币净值。"})
    if D(totals.get("liquid_assets_cny")) < D(totals.get("liabilities_cny")):
        risks.append({"level": "HIGH", "code": "LIQUIDITY", "title": "流动资金低于负债", "detail": "可立即使用资金低于当前负债余额，请核对还款节奏。"})
    return {
        "has_snapshot": True, "snapshot": serialize_session(latest, with_items=True), "totals": totals,
        "next_clearing_at": iso(schedule.next_run_at) if schedule else None,
        "goals": goals, "risks": risks, "trend": trend, "spending": build_spending_snapshot(db, user.id),
        "data_freshness": {"confirmed_at": iso(latest.confirmed_at), "fx_snapshot": latest.fx_snapshot_json, "completeness": str(latest.completeness)},
    }


@app.get("/trend")
def trend(user: Owner, db: DB, metric: str = "net_worth_cny", granularity: str = "month") -> dict:
    allowed_metrics = {"assets_cny", "net_worth_cny", "liquid_assets_cny", "investment_assets_cny"}
    if metric not in allowed_metrics:
        raise HTTPException(status_code=422, detail="不支持的趋势指标")
    if granularity not in {"clearing", "day", "week", "month", "quarter", "year"}:
        raise HTTPException(status_code=422, detail="不支持的聚合粒度")
    sessions = db.scalars(select(ClearingSession).where(
        ClearingSession.user_id == user.id, ClearingSession.status.in_(["CONFIRMED", "REVISED"]), ClearingSession.deleted_at.is_(None)
    ).order_by(ClearingSession.confirmed_at)).all()
    points = build_series(sessions, metric)
    annotations = db.scalars(select(ChartAnnotation).where(ChartAnnotation.user_id == user.id).order_by(ChartAnnotation.event_at)).all()
    return {
        "metric": metric, "granularity": granularity, "points": points,
        "candles": [] if granularity == "clearing" else aggregate_ohlc(points, granularity),
        "analysis": analyze_series(points),
        "annotations": [{"id": item.id, "event_at": iso(item.event_at), "event_type": item.event_type, "label": item.label, "notes": item.notes} for item in annotations],
        "disclaimer": "这条线展示的是每次清算时的资产规模。它能帮你看方向，但和证券账户里的投资收益率不是同一个指标。",
    }


@app.post("/trend/insight")
async def trend_insight(body: TrendInsightInput, user: Owner, db: DB) -> dict:
    allowed_metrics = {"assets_cny", "net_worth_cny", "liquid_assets_cny", "investment_assets_cny"}
    if body.metric not in allowed_metrics:
        raise HTTPException(status_code=422, detail="这个趋势指标暂时还不能解读")
    sessions = db.scalars(select(ClearingSession).where(
        ClearingSession.user_id == user.id,
        ClearingSession.status.in_(["CONFIRMED", "REVISED"]),
        ClearingSession.deleted_at.is_(None),
    ).order_by(ClearingSession.confirmed_at)).all()
    if len(sessions) < 2:
        raise HTTPException(status_code=409, detail="再完成一次清算，怀特就能把两个真实快照放在一起解读了。")
    metric_series = {
        metric: {"points": build_series(sessions, metric), "analysis": analyze_series(build_series(sessions, metric))}
        for metric in allowed_metrics
    }
    annotations = db.scalars(select(ChartAnnotation).where(
        ChartAnnotation.user_id == user.id
    ).order_by(ChartAnnotation.event_at)).all()
    latest = sessions[-1]
    attribution_row = db.scalar(select(ClearingAttribution).where(ClearingAttribution.session_id == latest.id, ClearingAttribution.user_id == user.id))
    latest_attribution = build_attribution(db, latest, attribution_row.answers_json if attribution_row else [])
    goals = [goal_payload(db, goal, latest) for goal in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()]
    full_context = {
        "selected_metric": body.metric,
        "verified_series": metric_series,
        "latest_snapshot": snapshot_payload(latest),
        "goals": goals,
        "chart_annotations": [
            {"event_at": iso(item.event_at), "event_type": item.event_type, "label": item.label, "notes": item.notes}
            for item in annotations
        ],
        "latest_change_attribution": latest_attribution,
        "rules": {
            "two_points_are_enough_for_direction": True,
            "asset_scale_change_is_not_investment_return": True,
            "do_not_invent_transactions_or_causes": True,
            "deterministic_metrics_are_authoritative": True,
        },
    }
    minimized = {
        "selected_metric": body.metric,
        "verified_series": metric_series,
        "latest_totals": latest.totals_json,
        "latest_comparison": latest.comparison_json,
        "goals": goals,
        "chart_annotations": full_context["chart_annotations"],
        "latest_change_attribution": latest_attribution,
        "rules": full_context["rules"],
    }
    prompt = (
        "请对这段已经确认的个人资产趋势做一次资深顾问级复盘。先给出一句明确结论，再说明方向、变化幅度、"
        "最大回撤、流动性与投资资产之间的关系，以及目标是否受到影响。结合事件标记做归因，但没有证据时至少列出"
        "两种合理解释并明确不能下结论的部分。不要把资产规模变化叫作收益率。最后给出按优先级排序的核对动作、"
        "调整动作和清晰的复盘触发条件；只有两个清算点时也要给出有用的方向性分析，不得以样本少为由拒绝。"
    )
    agent = await dispatch_financial_agent(db, user, prompt, full_context, minimized, body.provider, body.depth)
    log_event(db, user.id, "TREND_AGENT_INTERPRETED", {"metric": body.metric, "points": len(sessions), "provider": agent["provider"]})
    db.commit()
    return {**agent, "metric": body.metric, "point_count": len(sessions), "deterministic_analysis": metric_series[body.metric]["analysis"]}


@app.post("/trend/annotations")
def add_annotation(body: AnnotationInput, user: Owner, db: DB) -> dict:
    row = ChartAnnotation(user_id=user.id, **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, **body.model_dump(mode="json")}


@app.delete("/trend/annotations/{annotation_id}")
def delete_annotation(annotation_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(ChartAnnotation).where(ChartAnnotation.id == annotation_id, ChartAnnotation.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="事件标记不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.post("/scenario")
def scenario(body: ScenarioInput, user: Owner, db: DB) -> dict:
    latest = latest_confirmed(db, user.id)
    if not latest:
        raise HTTPException(status_code=409, detail="请先完成一次清算")
    return run_scenario(latest.items, latest.totals_json, {k.upper(): v for k, v in body.asset_type_shocks.items()}, {k.upper(): v for k, v in body.currency_shocks.items()}, body.liability_change_pct)


@app.post("/goals")
def create_goal_record(body: GoalInput, user: Owner, db: DB) -> dict:
    row = Goal(user_id=user.id, name=body.name, goal_type=body.goal_type.upper(), target_cny=body.target_cny, due_date=body.due_date, included_asset_types=[item.upper() for item in body.included_asset_types])
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "goal_type": row.goal_type, "target_cny": str(row.target_cny), "due_date": iso(row.due_date), "included_asset_types": row.included_asset_types}


@app.get("/goals")
def list_goals(user: Owner, db: DB) -> list[dict]:
    sync_goal_completion_notifications(db, user.id)
    latest = latest_confirmed(db, user.id)
    return [goal_payload(db, row, latest) for row in db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at)).all()]


@app.get("/goals/{goal_id}")
def get_goal_record(goal_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这个目标")
    sync_goal_completion_notifications(db, user.id)
    return goal_payload(db, row, latest_confirmed(db, user.id))


@app.patch("/goals/{goal_id}")
def update_goal_record(goal_id: str, body: GoalUpdate, user: Owner, db: DB) -> dict:
    row = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这个目标")
    previous_kind = goal_completion_kind(row)
    row.name = body.name.strip()
    row.goal_type = body.goal_type.upper()
    row.target_cny = body.target_cny
    row.due_date = body.due_date
    row.included_asset_types = [item.upper() for item in body.included_asset_types] if row.goal_type == "SPECIFIC" else []
    if previous_kind != goal_completion_kind(row):
        db.execute(delete(Notification).where(
            Notification.user_id == user.id,
            Notification.kind == previous_kind,
            Notification.read_at.is_(None),
        ))
    db.flush()
    sync_goal_completion_notifications(db, user.id, commit=False)
    log_event(db, user.id, "GOAL_UPDATED", {"goal_id": row.id})
    db.commit()
    db.refresh(row)
    return goal_payload(db, row, latest_confirmed(db, user.id))


@app.post("/goals/{goal_id}/completion/confirm")
def confirm_goal_completion(goal_id: str, user: Owner, db: DB) -> dict:
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if not goal:
        raise HTTPException(status_code=404, detail="没有找到这个目标")
    progress = goal_progress(goal, latest_confirmed(db, user.id), db)
    if D(progress["current_cny"]) < D(goal.target_cny):
        raise HTTPException(status_code=409, detail="这个目标当前还没有达到目标金额，请刷新后再确认。")
    kind = goal_completion_kind(goal)
    notice = db.scalar(select(Notification).where(Notification.user_id == user.id, Notification.kind == kind))
    if not notice:
        notice = Notification(
            user_id=user.id,
            kind=kind,
            title=f"您的{goal.name}理财目标已完成，请前往确认！",
            body=f"已归属 {progress['current_cny']} 元，达到目标金额 {money(D(goal.target_cny))} 元。",
        )
        db.add(notice)
    if not notice.read_at:
        notice.read_at = utcnow()
        log_event(db, user.id, "GOAL_COMPLETION_CONFIRMED", {"goal_id": goal.id, "target_cny": money(D(goal.target_cny))})
    db.commit()
    return goal_payload(db, goal, latest_confirmed(db, user.id))


@app.post("/goals/{goal_id}/plan")
async def generate_goal_plan(goal_id: str, body: GoalPlanInput, user: Owner, db: DB) -> dict:
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if not goal:
        raise HTTPException(status_code=404, detail="没有找到这个目标")
    if body.monthly_fixed_expenses_cny + body.monthly_safety_buffer_cny >= body.monthly_income_cny:
        raise HTTPException(status_code=422, detail="固定支出和机动金已经达到或超过收入，先调整一下金额，我再帮你安排更稳妥的计划。")
    latest = latest_confirmed(db, user.id)
    progress = goal_progress(goal, latest, db)
    income = D(body.monthly_income_cny)
    fixed = D(body.monthly_fixed_expenses_cny)
    buffer = D(body.monthly_safety_buffer_cny)
    available = max(income - fixed - buffer, Decimal("0"))
    gap = D(progress["gap_cny"])
    required = D(progress.get("required_monthly_cny")) if progress.get("required_monthly_cny") else None
    suggested = min(available, required if required is not None else available * D("0.6"), gap)
    if gap == 0:
        suggested = Decimal("0")
    estimated_months = int((gap / suggested).to_integral_value(rounding="ROUND_CEILING")) if suggested > 0 else None
    calculation = {
        "monthly_surplus_cny": money(income - fixed),
        "monthly_available_after_buffer_cny": money(available),
        "suggested_monthly_contribution_cny": money(suggested),
        "required_monthly_for_due_date_cny": money(required) if required is not None else None,
        "estimated_months": estimated_months,
        "gap_cny": money(gap),
        "calculation_note": "建议金额不会超过扣除固定支出与机动金后的月度可用额。没有目标日期时，先用可用额的 60% 做一个舒服的起点。",
    }
    goal_context = {
        "data_availability": {"has_confirmed_snapshot": latest is not None},
        "goal": {**goal_payload(db, goal, latest), "plan": None},
        "monthly_budget": {
            "income_cny": money(income),
            "fixed_expenses_cny": money(fixed),
            "safety_buffer_cny": money(buffer),
        },
        "calculated_plan": calculation,
        "latest_snapshot": snapshot_payload(latest) if latest else None,
        "rules": {
            "calculated_amounts_are_authoritative": True,
            "do_not_promise_returns": True,
            "plan_must_fit_monthly_available_amount": True,
        },
    }
    minimized = {
        "data_availability": goal_context["data_availability"],
        "goal": {key: value for key, value in goal_context["goal"].items() if key != "plan"},
        "monthly_budget": goal_context["monthly_budget"],
        "calculated_plan": calculation,
        "latest_totals": latest.totals_json if latest else None,
        "rules": goal_context["rules"],
    }
    prompt = (
        "请以资深个人财务顾问的标准，为这个目标制定一份现实、可执行、可复盘的月度计划。"
        "直接使用上下文中已经算好的金额并核对计划是否在月度可用额内，不要重算或改变权威金额。"
        "先判断期限可行性与现金流压力，再给出转入日期、资金顺序、缓冲安排和里程碑；如果按期所需金额超过可用额，"
        "必须明确指出缺口，并给出延长期限、降低目标金额、增加结余三条路径的取舍。"
        "说明收入下降、固定支出上升、应急事件或资产价格波动分别触发怎样的调整。"
        "每条建议都要有优先级、预期影响、风险和可量化的复盘触发条件，避免空泛的‘坚持储蓄’。"
    )
    agent = await dispatch_financial_agent(db, user, prompt, goal_context, minimized, body.provider, body.depth)
    plan = db.scalar(select(GoalPlan).where(GoalPlan.goal_id == goal.id, GoalPlan.user_id == user.id))
    if not plan:
        plan = GoalPlan(goal_id=goal.id, user_id=user.id, provider=agent["provider"], model=agent["model"])
        db.add(plan)
    plan.monthly_income_cny = income
    plan.monthly_fixed_expenses_cny = fixed
    plan.monthly_safety_buffer_cny = buffer
    plan.calculation_json = calculation
    plan.guidance_json = agent["result"]
    plan.provider = agent["provider"]
    plan.model = agent["model"]
    plan.updated_at = utcnow()
    log_event(db, user.id, "GOAL_PLAN_GENERATED", {"goal_id": goal.id, "provider": agent["provider"], "model": agent["model"]})
    db.commit()
    db.refresh(plan)
    return {"goal": goal_payload(db, goal, latest), "plan": serialize_goal_plan(plan), "fallback_from": agent.get("fallback_from")}


@app.patch("/goals/{goal_id}/plan")
def update_goal_plan(goal_id: str, body: GoalPlanUpdate, user: Owner, db: DB) -> dict:
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if not goal:
        raise HTTPException(status_code=404, detail="没有找到这个目标")
    plan = db.scalar(select(GoalPlan).where(GoalPlan.goal_id == goal.id, GoalPlan.user_id == user.id))
    if not plan:
        raise HTTPException(status_code=404, detail="这个目标还没有智能计划，可以先请怀特生成一份。")
    income = D(body.monthly_income_cny)
    fixed = D(body.monthly_fixed_expenses_cny)
    buffer = D(body.monthly_safety_buffer_cny)
    available = income - fixed - buffer
    if available < 0:
        raise HTTPException(status_code=422, detail="固定支出和机动金超过了收入，先把金额调到能长期坚持的范围吧。")
    contribution = D(body.suggested_monthly_contribution_cny)
    if contribution > available:
        raise HTTPException(status_code=422, detail=f"每月投入不能超过扣除支出和机动金后的 {money(available)} 元。")
    latest = latest_confirmed(db, user.id)
    progress = goal_progress(goal, latest, db)
    gap = D(progress["gap_cny"])
    required = D(progress.get("required_monthly_cny")) if progress.get("required_monthly_cny") else None
    estimated_months = int((gap / contribution).to_integral_value(rounding="ROUND_CEILING")) if contribution > 0 and gap > 0 else 0 if gap == 0 else None
    plan.monthly_income_cny = income
    plan.monthly_fixed_expenses_cny = fixed
    plan.monthly_safety_buffer_cny = buffer
    plan.calculation_json = {
        **(plan.calculation_json or {}),
        "monthly_surplus_cny": money(income - fixed),
        "monthly_available_after_buffer_cny": money(available),
        "suggested_monthly_contribution_cny": money(contribution),
        "required_monthly_for_due_date_cny": money(required) if required is not None else None,
        "estimated_months": estimated_months,
        "gap_cny": money(gap),
        "manually_adjusted": True,
        "calculation_note": "这份计划已经按你的想法调整；每月投入仍不超过扣除固定支出与机动金后的可用额。",
    }
    plan.guidance_json = normalize_agent_output(body.guidance)
    plan.updated_at = utcnow()
    log_event(db, user.id, "GOAL_PLAN_UPDATED", {"goal_id": goal.id, "monthly_contribution_cny": money(contribution)})
    db.commit()
    db.refresh(plan)
    return {"goal": goal_payload(db, goal, latest), "plan": serialize_goal_plan(plan)}


@app.delete("/goals/{goal_id}")
def delete_goal_record(goal_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="目标不存在")
    db.execute(delete(GoalPlan).where(GoalPlan.goal_id == row.id, GoalPlan.user_id == user.id))
    db.execute(delete(GoalFundingAllocation).where(GoalFundingAllocation.goal_id == row.id, GoalFundingAllocation.user_id == user.id))
    db.execute(update(ActionItem).where(ActionItem.goal_id == row.id, ActionItem.user_id == user.id).values(goal_id=None))
    db.execute(update(FutureObligation).where(FutureObligation.goal_id == row.id, FutureObligation.user_id == user.id).values(goal_id=None))
    db.execute(delete(Notification).where(
        Notification.user_id == user.id,
        Notification.kind.like(f"{goal_completion_prefix(row)}%"),
    ))
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.get("/intelligence/overview")
def get_intelligence_overview(user: Owner, db: DB) -> dict:
    return intelligence_overview(db, user.id)


def serialize_obligation(row: FutureObligation) -> dict:
    return {
        "id": row.id,
        "goal_id": row.goal_id,
        "title": row.title,
        "category": row.category,
        "amount_cny": money(D(row.amount_cny)),
        "due_date": iso(row.due_date),
        "likelihood": row.likelihood,
        "status": row.status,
        "notes": row.notes,
    }


@app.get("/funding/map")
def get_funding_map(user: Owner, db: DB) -> dict:
    latest = latest_confirmed(db, user.id)
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at)).all()
    allocations = reconcile_funding_allocations(db, user.id, latest)
    sync_goal_completion_notifications(db, user.id)
    allocation_by_asset: dict[str, Decimal] = {}
    allocation_by_goal: dict[str, Decimal] = {}
    for row in allocations:
        allocation_by_asset[row.asset_key] = allocation_by_asset.get(row.asset_key, D(0)) + D(row.amount_cny)
        allocation_by_goal[row.goal_id] = allocation_by_goal.get(row.goal_id, D(0)) + D(row.amount_cny)
    assets = []
    if latest:
        for item in latest.items:
            if item.status not in {"CONFIRMED", "REVISED"} or item.is_liability:
                continue
            key = funding_asset_key(db, item)
            value = funding_cents(item.value_cny)
            committed = funding_cents(allocation_by_asset.get(key, D(0)))
            assets.append({
                "asset_key": key,
                "name": item.name,
                "account_alias": item.account_alias,
                "asset_type": item.asset_type,
                "value_cny": money(value),
                "committed_cny": money(committed),
                "free_cny": money(max(value - committed, D(0))),
            })
    obligations = db.scalars(select(FutureObligation).where(
        FutureObligation.user_id == user.id,
        FutureObligation.status == "UPCOMING",
    ).order_by(FutureObligation.due_date)).all()
    standalone_obligations = sum((D(row.amount_cny) for row in obligations if not row.goal_id), D(0))
    committed = sum((funding_cents(value) for value in allocation_by_asset.values()), D(0))
    net_worth = funding_cents(latest.totals_json.get("net_worth_cny")) if latest else D(0)
    categories: dict[str, dict] = {}
    for asset in assets:
        group = categories.setdefault(asset["asset_type"], {
            "asset_type": asset["asset_type"], "asset_count": 0,
            "value_cny": D(0), "committed_cny": D(0), "free_cny": D(0),
        })
        group["asset_count"] += 1
        group["value_cny"] += D(asset["value_cny"])
        group["committed_cny"] += D(asset["committed_cny"])
        group["free_cny"] += D(asset["free_cny"])
    return {
        "has_snapshot": latest is not None,
        "snapshot_id": latest.id if latest else None,
        "net_worth_cny": money(net_worth),
        "committed_to_goals_cny": money(committed),
        "standalone_obligations_cny": money(standalone_obligations),
        "free_net_worth_cny": money(net_worth - committed - standalone_obligations),
        "assets": assets,
        "asset_categories": [{**group, "value_cny": money(group["value_cny"]), "committed_cny": money(group["committed_cny"]), "free_cny": money(group["free_cny"])} for group in categories.values()],
        "goals": [
            {
                "id": goal.id,
                "name": goal.name,
                "target_cny": money(D(goal.target_cny)),
                "allocated_cny": money(allocation_by_goal.get(goal.id, D(0))),
                "due_date": iso(goal.due_date),
                **goal_completion_state(db, goal, allocation_by_goal.get(goal.id, D(0))),
            }
            for goal in goals
        ],
        "allocations": [
            {"id": row.id, "asset_key": row.asset_key, "goal_id": row.goal_id, "amount_cny": money(D(row.amount_cny))}
            for row in allocations
        ],
        "obligations": [serialize_obligation(row) for row in obligations],
        "rule": "一元一归属：同一资产中已经分配给目标的金额，不能再次覆盖另一个目标。",
    }


@app.put("/funding/allocations")
def replace_funding_allocations(body: FundingAllocationInput, user: Owner, db: DB) -> dict:
    latest = latest_confirmed(db, user.id)
    if not latest:
        raise HTTPException(status_code=409, detail="完成一次资产清算后，才能给真实资金安排归属。")
    if body.snapshot_id and body.snapshot_id != latest.id:
        raise HTTPException(status_code=409, detail="资产清算刚刚更新了，页面会载入最新资产后再请你确认归属。")
    assets, legacy_aliases = current_funding_assets(db, latest)
    asset_values = {key: funding_cents(item.value_cny) for key, item in assets.items()}
    goals = {goal.id: goal for goal in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()}
    by_asset: dict[str, Decimal] = {}
    normalized: dict[tuple[str, str], Decimal] = {}
    for item in body.allocations:
        asset_key = item.asset_key if item.asset_key in asset_values else legacy_aliases.get(item.asset_key)
        if not asset_key:
            raise HTTPException(status_code=409, detail="这项资产来自较早的清算记录，页面会载入最新资产。请重新确认一次归属。")
        if item.goal_id not in goals:
            raise HTTPException(status_code=409, detail="选中的理财目标已经变化，页面会载入最新目标。请重新确认一次归属。")
        amount = funding_cents(item.amount_cny)
        pair = (asset_key, item.goal_id)
        normalized[pair] = normalized.get(pair, D(0)) + amount
        by_asset[asset_key] = by_asset.get(asset_key, D(0)) + amount
    for key, amount in by_asset.items():
        if amount > asset_values[key]:
            asset = assets[key]
            raise HTTPException(status_code=422, detail=f"“{asset.name}”最多可归属 {money(asset_values[key])} 元，当前合计为 {money(amount)} 元。请减少超出的部分。")
    db.execute(delete(GoalFundingAllocation).where(GoalFundingAllocation.user_id == user.id))
    for (asset_key, goal_id), amount in normalized.items():
        if amount <= 0:
            continue
        db.add(GoalFundingAllocation(
            user_id=user.id,
            goal_id=goal_id,
            asset_key=asset_key,
            amount_cny=amount,
        ))
    db.flush()
    sync_goal_completion_notifications(db, user.id, commit=False)
    log_event(db, user.id, "GOAL_FUNDING_REPLACED", {"allocation_count": len(normalized), "snapshot_id": latest.id})
    db.commit()
    return get_funding_map(user, db)


@app.post("/funding/obligations")
def create_obligation(body: FutureObligationInput, user: Owner, db: DB) -> dict:
    if body.goal_id and not db.scalar(select(Goal).where(Goal.id == body.goal_id, Goal.user_id == user.id)):
        raise HTTPException(status_code=404, detail="关联的目标不存在")
    row = FutureObligation(
        user_id=user.id,
        goal_id=body.goal_id,
        title=body.title.strip(),
        category=body.category.upper(),
        amount_cny=body.amount_cny,
        due_date=body.due_date,
        likelihood=body.likelihood.upper(),
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return serialize_obligation(row)


@app.patch("/funding/obligations/{obligation_id}")
def update_obligation(obligation_id: str, body: FutureObligationUpdate, user: Owner, db: DB) -> dict:
    row = db.scalar(select(FutureObligation).where(FutureObligation.id == obligation_id, FutureObligation.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这笔未来支出")
    if body.goal_id and not db.scalar(select(Goal).where(Goal.id == body.goal_id, Goal.user_id == user.id)):
        raise HTTPException(status_code=404, detail="关联的目标不存在")
    for key, value in body.model_dump().items():
        if key in {"category", "likelihood", "status"} and isinstance(value, str):
            value = value.upper()
        setattr(row, key, value)
    row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return serialize_obligation(row)


@app.delete("/funding/obligations/{obligation_id}")
def delete_obligation(obligation_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(FutureObligation).where(FutureObligation.id == obligation_id, FutureObligation.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这笔未来支出")
    db.delete(row)
    db.commit()
    return {"ok": True}


DEFAULT_CONSTITUTION_RULES = [
    ("EMERGENCY_MONTHS_MIN", "应急资金不得低于必要生活费的指定月数", {"months": 6}),
    ("SINGLE_STOCK_MAX_PCT", "单只股票不得超过净资产的指定比例", {"max_pct": 10}),
    ("HIGH_RISK_MAX_PCT", "高波动资产不得超过净资产的指定比例", {"max_pct": 30}),
    ("NO_BORROW_INVEST", "任何情况下不借钱投资", {}),
    ("RESTRICTED_NOT_LIQUID", "受限资产不得被视为日常可用资金", {}),
    ("FX_RANGE", "外币资产比例保持在设定区间", {"min_pct": 20, "max_pct": 40}),
    ("LARGE_SPEND_SIMULATION", "超过指定金额的非必要支出先模拟影响", {"amount_cny": 20000}),
]


def ensure_constitution(db: Session, user_id: str) -> list[FinancialRule]:
    rows = db.scalars(
        select(FinancialRule)
        .where(FinancialRule.user_id == user_id)
        .order_by(desc(FinancialRule.updated_at), desc(FinancialRule.created_at))
    ).all()
    # Older installations may have received the defaults twice when two pages opened
    # at the same instant. Keep the most recently edited copy so owner changes win.
    by_type: dict[str, FinancialRule] = {}
    changed = False
    for row in rows:
        if row.rule_type in by_type:
            db.delete(row)
            changed = True
        else:
            by_type[row.rule_type] = row
    for rule_type, title, parameters in DEFAULT_CONSTITUTION_RULES:
        if rule_type not in by_type:
            row = FinancialRule(
                user_id=user_id,
                rule_type=rule_type,
                title=title,
                parameters_json=parameters,
                enabled=True,
            )
            db.add(row)
            by_type[rule_type] = row
            changed = True
    if changed:
        db.commit()
    order = {rule_type: index for index, (rule_type, _, _) in enumerate(DEFAULT_CONSTITUTION_RULES)}
    return sorted(by_type.values(), key=lambda row: order.get(row.rule_type, len(order)))


def constitution_evaluation(db: Session, user_id: str) -> dict:
    rules = ensure_constitution(db, user_id)
    latest = latest_confirmed(db, user_id)
    latest_plan = db.scalar(select(GoalPlan).where(GoalPlan.user_id == user_id).order_by(desc(GoalPlan.updated_at)))
    totals = latest.totals_json if latest else {}
    net_worth = D(totals.get("net_worth_cny"))
    assets = D(totals.get("assets_cny"))
    items = [item for item in latest.items if item.status in {"CONFIRMED", "REVISED"} and not item.is_liability] if latest else []
    results = []
    for rule in rules:
        params = rule.parameters_json or {}
        status_value = "UNVERIFIABLE"
        measured = "还缺少足够数据"
        detail = "这条规则已经保存，数据齐全后会自动检查。"
        verification: dict = {}
        if not rule.enabled:
            status_value, measured, detail = "DISABLED", "已暂停", "这条规则当前不参与检查。"
        elif rule.rule_type == "EMERGENCY_MONTHS_MIN":
            target = D(params.get("months", 6))
            if latest and latest_plan and D(latest_plan.monthly_fixed_expenses_cny) > 0:
                current = D(totals.get("liquid_assets_cny")) / D(latest_plan.monthly_fixed_expenses_cny)
                status_value = "PASS" if current >= target else "WARNING" if current >= target * D("0.8") else "VIOLATION"
                measured = f"{money(current)} 个月 / 规则 {money(target)} 个月"
                detail = "按可立即使用资产 ÷ 每月固定支出计算。"
                verification = {"metric": "liquidity_months", "operator": ">=", "target": money(target), "current": money(current)}
        elif rule.rule_type == "SINGLE_STOCK_MAX_PCT":
            target = D(params.get("max_pct", 10))
            if latest and net_worth > 0:
                stocks = [(item.name, D(item.value_cny) / net_worth * D(100)) for item in items if item.asset_type == "STOCK"]
                name, current = max(stocks, key=lambda pair: pair[1]) if stocks else ("没有单只股票", D(0))
                status_value = "PASS" if current <= target else "WARNING" if current <= target * D("1.1") else "VIOLATION"
                measured = f"{name} {money(current)}% / 上限 {money(target)}%"
                detail = "按单只股票当前人民币价值 ÷ 净资产计算；上涨也可能让比例越线。"
                verification = {"metric": "single_stock_max_pct", "operator": "<=", "target": money(target), "current": money(current)}
        elif rule.rule_type == "HIGH_RISK_MAX_PCT":
            target = D(params.get("max_pct", 30))
            if latest and net_worth > 0:
                current = sum((D(item.value_cny) for item in items if item.asset_type in {"STOCK", "FUND", "CRYPTO"}), D(0)) / net_worth * D(100)
                status_value = "PASS" if current <= target else "WARNING" if current <= target * D("1.1") else "VIOLATION"
                measured = f"{money(current)}% / 上限 {money(target)}%"
                detail = "当前把股票、基金与加密资产计入高波动资产。"
                verification = {"metric": "high_risk_pct", "operator": "<=", "target": money(target), "current": money(current)}
        elif rule.rule_type == "NO_BORROW_INVEST":
            if latest and D(totals.get("liabilities_cny")) == 0:
                status_value, measured, detail = "PASS", "当前没有记录负债", "在已确认资产数据范围内没有发现借款。"
            elif latest:
                status_value, measured, detail = "UNVERIFIABLE", f"记录负债 {money(D(totals.get('liabilities_cny')))} 元", "仅凭资产快照无法判断负债是否用于投资，需要你确认用途。"
        elif rule.rule_type == "RESTRICTED_NOT_LIQUID":
            if latest:
                status_value, measured, detail = "PASS", f"受限资产 {money(D(totals.get('restricted_assets_cny')))} 元", "系统计算可用现金时已经自动排除受限资产。"
        elif rule.rule_type == "FX_RANGE":
            minimum, maximum = D(params.get("min_pct", 20)), D(params.get("max_pct", 40))
            if latest and assets > 0:
                foreign = sum((D(value) for currency, value in totals.get("by_currency", {}).items() if currency != "CNY"), D(0))
                current = foreign / assets * D(100)
                status_value = "PASS" if minimum <= current <= maximum else "WARNING" if minimum * D("0.8") <= current <= maximum * D("1.1") else "VIOLATION"
                measured = f"{money(current)}% / 区间 {money(minimum)}%–{money(maximum)}%"
                detail = "按外币资产人民币价值 ÷ 总资产计算。"
                verification = {"metric": "fx_pct", "operator": "between", "minimum": money(minimum), "maximum": money(maximum), "current": money(current)}
        elif rule.rule_type == "LARGE_SPEND_SIMULATION":
            status_value = "PASS"
            measured = f"门槛 {money(D(params.get('amount_cny', 20000)))} 元"
            detail = "这是一条决策流程规则；达到门槛时，可先在怀特理财顾问的压力测试中查看影响。"
        results.append({
            "id": rule.id,
            "rule_type": rule.rule_type,
            "title": rule.title,
            "parameters": params,
            "enabled": rule.enabled,
            "status": status_value,
            "measured": measured,
            "detail": detail,
            "verification": verification,
        })
    counts = {status_name: len([item for item in results if item["status"] == status_name]) for status_name in ["PASS", "WARNING", "VIOLATION", "UNVERIFIABLE", "DISABLED"]}
    return {"rules": results, "counts": counts, "snapshot_id": latest.id if latest else None, "checked_at": iso(utcnow())}


def focus_verification_passed(verification: dict, evaluation: dict) -> bool:
    metric = verification.get("metric")
    candidates = [item.get("verification", {}) for item in evaluation["rules"]]
    current_match = next((item for item in candidates if item.get("metric") == metric), None)
    if not current_match:
        return False
    current = D(current_match.get("current"))
    operator = verification.get("operator")
    if operator == ">=":
        return current >= D(verification.get("target"))
    if operator == "<=":
        return current <= D(verification.get("target"))
    if operator == "between":
        return D(verification.get("minimum")) <= current <= D(verification.get("maximum"))
    return False


@app.get("/constitution")
def get_constitution(user: Owner, db: DB) -> dict:
    evaluation = constitution_evaluation(db, user.id)
    focus_rows = db.scalars(select(FocusTask).where(FocusTask.user_id == user.id, FocusTask.status == "ACTIVE").order_by(desc(FocusTask.created_at))).all()
    active_focus = None
    for focus in focus_rows:
        action = db.scalar(select(ActionItem).where(ActionItem.id == focus.action_id, ActionItem.user_id == user.id))
        if not action:
            continue
        focus.checked_at = utcnow()
        if focus_verification_passed(focus.verification_json or {}, evaluation):
            focus.status = "COMPLETED"
            action.status = "DONE"
            action.completed_at = utcnow()
        elif not active_focus:
            active_focus = {"id": focus.id, "verification": focus.verification_json, "action": serialize_action_item(action)}
    db.commit()
    return {**evaluation, "active_focus": active_focus}


@app.put("/constitution")
def replace_constitution(body: ConstitutionInput, user: Owner, db: DB) -> dict:
    db.execute(delete(FinancialRule).where(FinancialRule.user_id == user.id))
    for item in body.rules:
        db.add(FinancialRule(
            user_id=user.id,
            rule_type=item.rule_type.upper(),
            title=item.title.strip(),
            parameters_json=item.parameters,
            enabled=item.enabled,
        ))
    log_event(db, user.id, "FINANCIAL_CONSTITUTION_UPDATED", {"rule_count": len(body.rules)})
    db.commit()
    return constitution_evaluation(db, user.id)


@app.post("/constitution/focus")
async def generate_constitution_focus(body: AssistantInput, user: Owner, db: DB) -> dict:
    evaluation = constitution_evaluation(db, user.id)
    candidates = [item for item in evaluation["rules"] if item["enabled"] and item["status"] in {"VIOLATION", "WARNING"}]
    if not candidates:
        overview = intelligence_overview(db, user.id)
        issue = overview["alerts"][0] if overview["alerts"] else {"title": "保持本月计划", "detail": "当前没有触发明显警戒线。"}
        verification = {}
    else:
        issue = candidates[0]
        verification = issue.get("verification", {})
    context = {"constitution_evaluation": evaluation, "single_focus_issue": issue, "rules": {"return_exactly_one_recommendation": True}}
    prompt = (
        "请只选择一件本期最值得做、影响最大且最容易执行的事。不要列出第二项任务。解释它为什么优先、完成后的具体影响、"
        "可能遇到的阻力，以及下次清算如何验证是否完成。建议要尊重用户自己的规则，不直接命令交易证券。"
    )
    agent = await dispatch_financial_agent(db, user, prompt, context, context, body.provider, "complex")
    recommendations = agent["result"].get("recommendations", [])
    recommendation = recommendations[0] if recommendations else {
        "priority": "HIGH", "action": issue.get("title", "复盘当前计划"), "reason": issue.get("detail", ""),
        "expected_impact": "让下一次决策更有依据", "risk": "执行前请核对实际现金流", "review_trigger": "下次资产清算时复盘",
    }
    return {"recommendation": recommendation, "verification": verification, "issue": issue, "provider": agent["provider"], "model": agent["model"]}


@app.post("/constitution/focus/accept")
def accept_constitution_focus(body: FocusAcceptInput, user: Owner, db: DB) -> dict:
    item = body.recommendation
    action = ActionItem(
        user_id=user.id,
        title=str(item.get("action", "本期重点行动"))[:240],
        reason=str(item.get("reason", "")),
        expected_impact=str(item.get("expected_impact", "")),
        risk=str(item.get("risk", "")),
        review_trigger=str(item.get("review_trigger", "下次资产清算时复盘")),
        priority="HIGH",
        status="TODO",
        source="CONSTITUTION_FOCUS",
    )
    db.add(action)
    db.flush()
    focus = FocusTask(
        user_id=user.id,
        action_id=action.id,
        source_session_id=(latest_confirmed(db, user.id).id if latest_confirmed(db, user.id) else None),
        verification_json=body.verification,
    )
    db.add(focus)
    db.commit()
    db.refresh(action)
    return {"action": serialize_action_item(action), "focus_id": focus.id}


@app.post("/intelligence/allocate")
async def allocate_goals(body: AllocationInput, user: Owner, db: DB) -> dict:
    income = D(body.monthly_income_cny)
    fixed = D(body.monthly_fixed_expenses_cny)
    buffer = D(body.monthly_safety_buffer_cny)
    available = income - fixed - buffer
    if available <= 0:
        raise HTTPException(status_code=422, detail="扣除固定支出和机动金后还没有可分配结余，先把现金流调到有余地的状态。")
    strategy = body.strategy.upper()
    if strategy not in {"BALANCED", "DEADLINE_FIRST", "SMALLEST_GAP"}:
        raise HTTPException(status_code=422, detail="这个分配策略暂时不支持")
    allocation = build_goal_allocation(db, user.id, available, strategy)
    if not allocation:
        raise HTTPException(status_code=409, detail="目前没有需要分配资金的未完成目标，先写下一个目标吧。")
    allocated = sum((D(item["monthly_allocation_cny"]) for item in allocation), D(0))
    conflicts = [item for item in allocation if item["on_track"] is False]
    overview = intelligence_overview(db, user.id)
    deterministic = {
        "monthly_income_cny": money(income),
        "monthly_fixed_expenses_cny": money(fixed),
        "monthly_safety_buffer_cny": money(buffer),
        "monthly_available_cny": money(available),
        "monthly_allocated_cny": money(allocated),
        "monthly_unallocated_cny": money(max(available - allocated, D(0))),
        "strategy": strategy,
        "allocations": allocation,
        "deadline_conflict_count": len(conflicts),
    }
    context = {
        "financial_twin": overview,
        "deterministic_allocation": deterministic,
        "rules": {
            "allocation_total_must_not_exceed_available": True,
            "deterministic_amounts_are_authoritative": True,
            "surface_goal_conflicts": True,
            "do_not_assume_investment_returns": True,
        },
    }
    minimized = {
        "score": overview["score"],
        "factors": overview["factors"],
        "alerts": overview["alerts"],
        "latest_totals": overview["latest_totals"],
        "deterministic_allocation": deterministic,
        "rules": context["rules"],
    }
    prompt = (
        "请复核这份由程序计算出的多目标资金调度方案。不能改写任何分配金额。先判断它是否覆盖了最紧迫的期限、"
        "是否存在目标冲突和现金流过紧，再说明为什么按这个顺序分配。对不能按期完成的目标，给出调整期限、目标金额、"
        "月结余三种路径的具体取舍。最后输出本月执行顺序、复盘日期和收入或支出变化时的触发阈值。"
    )
    agent = await dispatch_financial_agent(db, user, prompt, context, minimized, body.provider, body.depth)
    log_event(db, user.id, "MULTI_GOAL_ALLOCATION_GENERATED", {"strategy": strategy, "goals": len(allocation), "provider": agent["provider"]})
    db.commit()
    return {"plan": deterministic, "agent": agent, "overview": overview}


@app.get("/intelligence/actions")
def list_action_items(user: Owner, db: DB) -> list[dict]:
    rows = db.scalars(select(ActionItem).where(ActionItem.user_id == user.id).order_by(ActionItem.status, ActionItem.priority, desc(ActionItem.updated_at))).all()
    return [serialize_action_item(row) for row in rows]


@app.post("/intelligence/actions")
def create_action_item(body: ActionItemInput, user: Owner, db: DB) -> dict:
    priority = body.priority.upper()
    if priority not in {"HIGH", "MEDIUM", "LOW"}:
        raise HTTPException(status_code=422, detail="行动优先级只支持高、中、低")
    if body.goal_id and not db.scalar(select(Goal).where(Goal.id == body.goal_id, Goal.user_id == user.id)):
        raise HTTPException(status_code=404, detail="关联的目标不存在")
    row = ActionItem(
        user_id=user.id,
        goal_id=body.goal_id,
        title=body.title.strip(),
        reason=body.reason,
        expected_impact=body.expected_impact,
        risk=body.risk,
        review_trigger=body.review_trigger,
        priority=priority,
        status="TODO",
        source=body.source.upper(),
        due_date=body.due_date,
    )
    db.add(row)
    log_event(db, user.id, "FINANCIAL_ACTION_CREATED", {"title": row.title, "source": row.source})
    db.commit()
    db.refresh(row)
    return serialize_action_item(row)


@app.patch("/intelligence/actions/{action_id}")
def update_action_item(action_id: str, body: ActionItemUpdate, user: Owner, db: DB) -> dict:
    row = db.scalar(select(ActionItem).where(ActionItem.id == action_id, ActionItem.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这条行动")
    changes = body.model_dump(exclude_unset=True)
    if "priority" in changes and changes["priority"] is not None:
        changes["priority"] = changes["priority"].upper()
        if changes["priority"] not in {"HIGH", "MEDIUM", "LOW"}:
            raise HTTPException(status_code=422, detail="行动优先级只支持高、中、低")
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].upper()
        if changes["status"] not in {"TODO", "DOING", "DONE", "SNOOZED"}:
            raise HTTPException(status_code=422, detail="这个行动状态暂时不支持")
    if changes.get("goal_id") and not db.scalar(select(Goal).where(Goal.id == changes["goal_id"], Goal.user_id == user.id)):
        raise HTTPException(status_code=404, detail="关联的目标不存在")
    for key, value in changes.items():
        setattr(row, key, value)
    if changes.get("status") == "DONE":
        row.completed_at = utcnow()
    elif "status" in changes:
        row.completed_at = None
    row.updated_at = utcnow()
    log_event(db, user.id, "FINANCIAL_ACTION_UPDATED", {"action_id": row.id, "status": row.status})
    db.commit()
    db.refresh(row)
    return serialize_action_item(row)


@app.delete("/intelligence/actions/{action_id}")
def delete_action_item(action_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(ActionItem).where(ActionItem.id == action_id, ActionItem.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这条行动")
    db.delete(row)
    log_event(db, user.id, "FINANCIAL_ACTION_DELETED", {"action_id": action_id})
    db.commit()
    return {"ok": True}


def product_suitability(db: Session, user_id: str, amount: Decimal | None, extraction: dict) -> dict:
    latest = latest_confirmed(db, user_id)
    plan = db.scalar(select(GoalPlan).where(GoalPlan.user_id == user_id).order_by(desc(GoalPlan.updated_at)))
    liquid = D(latest.totals_json.get("liquid_assets_cny")) if latest else None
    fixed = D(plan.monthly_fixed_expenses_cny) if plan else None
    before_months = liquid / fixed if liquid is not None and fixed and fixed > 0 else None
    after_liquid = max(liquid - amount, D(0)) if liquid is not None and amount is not None else None
    after_months = after_liquid / fixed if after_liquid is not None and fixed and fixed > 0 else None
    flags = []
    if extraction.get("principal_guaranteed", {}).get("value") != "YES":
        flags.append("页面没有形成明确的保本承诺，不能把产品名称或宣传语当作本金保证。")
    if extraction.get("return_type") in {"FLOATING", "HISTORICAL_DISPLAY", "UNCLEAR"}:
        flags.append("页面展示的收益不是可直接当作未来固定到账金额的数字。")
    if after_months is not None and after_months < D(3):
        flags.append(f"按投入 {money(amount or D(0))} 元的情景，可用现金续航会降到约 {money(after_months)} 个月。")
    elif before_months is not None and after_months is not None:
        flags.append(f"按这笔投入测算，现金续航会从约 {money(before_months)} 个月变为 {money(after_months)} 个月。")
    return {
        "intended_amount_cny": money(amount) if amount is not None else None,
        "liquid_assets_before_cny": money(liquid) if liquid is not None else None,
        "liquid_assets_after_cny": money(after_liquid) if after_liquid is not None else None,
        "runway_before_months": money(before_months) if before_months is not None else None,
        "runway_after_months": money(after_months) if after_months is not None else None,
        "flags": flags,
        "calculation_note": "流动性情景保守地把计划投入金额视为暂时不可用于日常支出；实际赎回能力以产品条款为准。",
    }


def render_scanned_pdf_preview(content: bytes, max_pages: int = 6) -> bytes:
    import fitz
    from PIL import Image

    document = fitz.open(stream=content, filetype="pdf")
    pages = []
    for index in range(min(document.page_count, max_pages)):
        pixmap = document.load_page(index).get_pixmap(matrix=fitz.Matrix(1.35, 1.35), alpha=False)
        pages.append(Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB"))
    if not pages:
        raise ValueError("PDF has no pages")
    width = max(image.width for image in pages)
    height = sum(image.height for image in pages) + 24 * (len(pages) - 1)
    canvas = Image.new("RGB", (width, height), "white")
    offset = 0
    for image in pages:
        canvas.paste(image, ((width - image.width) // 2, offset))
        offset += image.height + 24
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


@app.post("/xray")
async def create_product_xray(
    user: Owner,
    db: DB,
    file: UploadFile = File(...),
    intended_amount_cny: str | None = Form(default=None),
) -> dict:
    content_type = (file.content_type or "").lower()
    if content_type not in {"application/pdf", "image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(status_code=415, detail="请上传 PDF、PNG、JPG 或 WebP 文件。")
    content = await file.read((settings.max_upload_mb * 1024 * 1024) + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件不可超过 {settings.max_upload_mb}MB")
    amount = D(intended_amount_cny) if intended_amount_cny not in {None, ""} else None
    if amount is not None and amount <= 0:
        raise HTTPException(status_code=422, detail="计划投入金额需要大于 0")
    page_count = None
    model_content: bytes | None = content
    model_content_type = content_type
    extracted_text = ""
    if content_type == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(content))
            if reader.is_encrypted:
                raise HTTPException(status_code=422, detail="这个 PDF 有密码保护，请先解锁后再上传。")
            page_count = len(reader.pages)
            if page_count > 30:
                raise HTTPException(status_code=422, detail="PDF 最多支持 30 页，可以只保留产品说明和费用条款后再上传。")
            extracted_text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
            if len(extracted_text.strip()) >= 120:
                model_content = None
            else:
                model_content = render_scanned_pdf_preview(content)
                model_content_type = "image/jpeg"
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=422, detail="PDF 没有成功打开，请确认文件完整后再试。") from exc
    try:
        extraction = await QwenClient().xray_product(db, user.id, model_content, model_content_type, extracted_text)
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    suitability = product_suitability(db, user.id, amount, extraction)
    row = ProductXray(
        user_id=user.id,
        original_filename=(file.filename or "product")[:240],
        content_type=content_type,
        sha256=hashlib.sha256(content).hexdigest(),
        page_count=page_count,
        intended_amount_cny=amount,
        extraction_json=extraction,
        suitability_json=suitability,
        provider="QWEN",
        model=settings.qwen_vision_model if model_content is not None else settings.qwen_complex_model,
    )
    db.add(row)
    log_event(db, user.id, "PRODUCT_XRAY_CREATED", {"content_type": content_type, "page_count": page_count})
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "filename": row.original_filename,
        "content_type": row.content_type,
        "page_count": row.page_count,
        "extraction": extraction,
        "suitability": suitability,
        "provider": row.provider,
        "model": row.model,
        "created_at": iso(row.created_at),
        "original_file_stored": False,
    }


@app.get("/xray")
def list_product_xrays(user: Owner, db: DB) -> list[dict]:
    rows = db.scalars(select(ProductXray).where(ProductXray.user_id == user.id).order_by(desc(ProductXray.created_at))).all()
    return [{
        "id": row.id,
        "filename": row.original_filename,
        "content_type": row.content_type,
        "page_count": row.page_count,
        "extraction": row.extraction_json,
        "suitability": row.suitability_json,
        "provider": row.provider,
        "model": row.model,
        "created_at": iso(row.created_at),
        "original_file_stored": False,
    } for row in rows]


@app.delete("/xray/{xray_id}")
def delete_product_xray(xray_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(ProductXray).where(ProductXray.id == xray_id, ProductXray.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="没有找到这份产品 X 光")
    db.delete(row)
    db.commit()
    return {"ok": True}


@app.get("/gold/spot")
async def get_live_gold_spot(user: Owner, db: DB) -> dict:
    try:
        return await GoldSpotProvider().get_cny_quote(db, user.id)
    except (ProviderError, StaleRateError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/gold/quotes")
def add_gold_quote(body: GoldQuoteInput, user: Owner, db: DB) -> dict:
    row = GoldQuote(user_id=user.id, method=body.method.upper(), price_per_gram_cny=body.price_per_gram_cny, source=body.source, quoted_at=body.quoted_at, brand=body.brand, city=body.city, notes=body.notes)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "method": row.method, "price_per_gram_cny": str(row.price_per_gram_cny), "source": row.source, "quoted_at": iso(row.quoted_at), "brand": row.brand, "city": row.city}


@app.get("/gold/quotes")
def list_gold_quotes(user: Owner, db: DB) -> list[dict]:
    rows = db.scalars(select(GoldQuote).where(GoldQuote.user_id == user.id).order_by(desc(GoldQuote.quoted_at))).all()
    return [{"id": row.id, "method": row.method, "price_per_gram_cny": str(row.price_per_gram_cny), "source": row.source, "quoted_at": iso(row.quoted_at), "brand": row.brand, "city": row.city, "notes": row.notes} for row in rows]


@app.post("/gold/estimate")
def estimate_gold(body: GoldEstimateInput, user: Owner, db: DB) -> dict:
    quote = db.scalar(select(GoldQuote).where(GoldQuote.id == body.quote_id, GoldQuote.user_id == user.id))
    if not quote:
        raise HTTPException(status_code=404, detail="黄金报价不存在")
    if quote.method == "STORE_BUYBACK":
        value = body.weight_grams * D(quote.price_per_gram_cny) - body.explicit_fees_cny
        formula = "净重量 × 门店回收单价 - 明确费用；不重复乘纯度"
    else:
        value = body.weight_grams * body.purity * D(quote.price_per_gram_cny) - body.explicit_fees_cny
        formula = "重量 × 纯度 × 每克参考价 - 明确费用"
    return {"value_cny": money(value), "method": quote.method, "quote_time": iso(quote.quoted_at), "source": quote.source, "formula": formula, "reference_only": quote.method == "STORE_BUYBACK"}


@app.post("/assistant")
async def assistant(body: AssistantInput, user: Owner, db: DB) -> dict:
    latest = latest_confirmed(db, user.id)
    sessions = db.scalars(select(ClearingSession).where(ClearingSession.user_id == user.id, ClearingSession.status.in_(["CONFIRMED", "REVISED"]), ClearingSession.deleted_at.is_(None)).order_by(ClearingSession.confirmed_at)).all()
    trend_points = build_series(sessions, "net_worth_cny")
    trend_data = {"points": trend_points, "analysis": analyze_series(trend_points)}
    goals_data = [goal_payload(db, goal, latest) for goal in db.scalars(select(Goal).where(Goal.user_id == user.id)).all()]
    draft = db.scalar(select(ClearingSession).where(ClearingSession.user_id == user.id, ClearingSession.status == "DRAFT", ClearingSession.deleted_at.is_(None)).order_by(desc(ClearingSession.started_at)))
    draft_items = [serialize_item(item) for item in draft.items] if draft else []
    schedule = db.scalar(select(ClearingSchedule).where(ClearingSchedule.user_id == user.id))
    quotes = db.scalars(select(GoldQuote).where(GoldQuote.user_id == user.id).order_by(desc(GoldQuote.quoted_at)).limit(10)).all()
    annotations = db.scalars(select(ChartAnnotation).where(ChartAnnotation.user_id == user.id).order_by(desc(ChartAnnotation.event_at)).limit(20)).all()
    action_items = db.scalars(select(ActionItem).where(ActionItem.user_id == user.id).order_by(desc(ActionItem.updated_at)).limit(30)).all()
    funding_data = get_funding_map(user, db)
    constitution_data = constitution_evaluation(db, user.id)
    recent_xrays = db.scalars(
        select(ProductXray)
        .where(ProductXray.user_id == user.id)
        .order_by(desc(ProductXray.created_at))
        .limit(5)
    ).all()
    xray_context = [
        {
            "filename": row.original_filename,
            "created_at": iso(row.created_at),
            "intended_amount_cny": money(D(row.intended_amount_cny)) if row.intended_amount_cny is not None else None,
            "extraction": row.extraction_json,
            "suitability": row.suitability_json,
        }
        for row in recent_xrays
    ]
    spending_data = build_spending_snapshot(db, user.id)
    recent_spending_decisions = db.scalars(
        select(SpendingDecision)
        .where(SpendingDecision.user_id == user.id)
        .order_by(desc(SpendingDecision.created_at))
        .limit(10)
    ).all()
    spending_context = {
        "current": spending_data,
        "recent_decisions": [
            {
                "decision": row.decision_text,
                "amount_cny": money(D(row.amount_cny)),
                "verdict": row.verdict,
                "result": row.result_json,
                "created_at": iso(row.created_at),
            }
            for row in recent_spending_decisions
        ],
    }
    full_context = {
        "data_availability": {
            "has_confirmed_snapshot": latest is not None,
            "confirmed_snapshot_count": len(sessions),
            "has_draft_clearing": draft is not None,
            "draft_item_count": len(draft_items),
            "goal_count": len(goals_data),
        },
        "latest_confirmed_snapshot": snapshot_payload(latest) if latest else None,
        "current_clearing": {
            "session_id": draft.id,
            "started_at": iso(draft.started_at),
            "items": draft_items,
        } if draft else None,
        "trend": trend_data,
        "goals": goals_data,
        "clearing_schedule": ({column.name: iso(getattr(schedule, column.name)) if isinstance(getattr(schedule, column.name), (datetime, date)) else getattr(schedule, column.name) for column in schedule.__table__.columns if column.name not in {"id", "user_id"}} if schedule else None),
        "gold_quotes": [{"method": row.method, "price_per_gram_cny": str(row.price_per_gram_cny), "source": row.source, "quoted_at": iso(row.quoted_at), "brand": row.brand, "city": row.city} for row in quotes],
        "chart_annotations": [{"event_at": iso(row.event_at), "event_type": row.event_type, "label": row.label, "notes": row.notes} for row in annotations],
        "financial_actions": [serialize_action_item(row) for row in action_items],
        "funding_and_free_net_worth": funding_data,
        "financial_constitution": constitution_data,
        "recent_product_xrays": xray_context,
        "safe_spending_and_financial_battery": spending_context,
        "preferences": {"region": user.region, "timezone": user.timezone, "model_preference": user.model_preference},
        "rules": {
            "general_finance_questions_are_always_allowed": True,
            "missing_personal_data_must_not_block_general_answers": True,
            "asset_curve_is_not_investment_return": True,
            "no_transaction_ledger": True,
            "deterministic_totals_are_authoritative": True,
        },
    }
    minimized = {
        "data_availability": full_context["data_availability"],
        "snapshot_time": iso(latest.confirmed_at) if latest else None,
        "completeness": str(latest.completeness) if latest else None,
        "totals": latest.totals_json if latest else None,
        "comparison": latest.comparison_json if latest else None,
        "draft_items": [{"name": item["name"], "asset_type": item["asset_type"], "currency": item["original_currency"], "value": item["original_value"], "status": item["status"]} for item in draft_items],
        "trend": trend_data,
        "goals": goals_data,
        "clearing_schedule": full_context["clearing_schedule"],
        "gold_quotes": full_context["gold_quotes"],
        "financial_actions": full_context["financial_actions"],
        "funding_and_free_net_worth": {
            "net_worth_cny": funding_data["net_worth_cny"],
            "committed_to_goals_cny": funding_data["committed_to_goals_cny"],
            "standalone_obligations_cny": funding_data["standalone_obligations_cny"],
            "free_net_worth_cny": funding_data["free_net_worth_cny"],
            "goal_allocations": funding_data["goals"],
            "future_obligations": funding_data["obligations"],
        },
        "financial_constitution": constitution_data,
        "recent_product_xrays": xray_context,
        "safe_spending_and_financial_battery": spending_context,
        "preferences": full_context["preferences"],
        "rules": full_context["rules"],
    }
    return await dispatch_financial_agent(db, user, body.message, full_context, minimized, body.provider, body.depth)


@app.get("/settings")
async def get_owner_settings(user: Owner, db: DB) -> dict:
    schedule = db.scalar(select(ClearingSchedule).where(ClearingSchedule.user_id == user.id))
    key, base_url, workspace = settings.aliyun_credentials()
    gateway_configured = False
    gateway_reachable = False
    gateway_upstream_available = None
    gateway_error_code = None
    gateway_checked_at = None
    if settings.openai_gateway_url and settings.gateway_shared_secret:
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                gateway_response = await client.get(f"{settings.openai_gateway_url.rstrip('/')}/health")
            gateway_reachable = gateway_response.is_success
            gateway_health = gateway_response.json()
            gateway_configured = gateway_reachable and bool(gateway_health.get("openai_configured"))
            upstream = gateway_health.get("last_upstream") or {}
            gateway_upstream_available = upstream.get("available")
            gateway_error_code = upstream.get("error_code")
            gateway_checked_at = upstream.get("checked_at")
        except (httpx.HTTPError, ValueError):
            pass
    return {
        "region": user.region, "model_preference": user.model_preference, "timezone": user.timezone,
        "providers": {
            "qwen": {"configured": bool(key and base_url), "workspace_configured": bool(workspace), "ocr_model": settings.qwen_ocr_model, "vision_model": settings.qwen_vision_model, "chat_model": settings.qwen_chat_model},
            "openai": {"configured": gateway_configured, "gateway_reachable": gateway_reachable, "upstream_available": gateway_upstream_available, "error_code": gateway_error_code, "checked_at": gateway_checked_at, "ordinary_model": settings.openai_ordinary_model, "complex_model": settings.openai_complex_model, "region_allowed": user.region in {"KR", "OTHER_SUPPORTED"}},
            "fx": {"provider": "Frankfurter / ECB reference rates", "max_age_hours": settings.fx_max_age_hours},
            "gold": {"mode": "LIVE_INTERNATIONAL_SPOT", "message": "实时读取国际 XAU/USD 现货金价，并按 ECB 参考汇率折算成人民币每克；清算确认时会再次刷新。"},
        },
        "schedule": ({column.name: iso(getattr(schedule, column.name)) if isinstance(getattr(schedule, column.name), (datetime, date)) else getattr(schedule, column.name) for column in schedule.__table__.columns} if schedule else None),
    }


@app.put("/settings")
def update_owner_settings(body: SettingsInput, user: Owner, db: DB) -> dict:
    region = body.region.upper()
    if region not in {"CN", "KR", "OTHER_SUPPORTED", "UNKNOWN"}:
        raise HTTPException(status_code=422, detail="不支持的地区设置")
    preference = body.model_preference.upper()
    if preference not in {"AUTO", "QWEN", "OPENAI"}:
        raise HTTPException(status_code=422, detail="不支持的模型偏好")
    if preference == "OPENAI" and region not in {"KR", "OTHER_SUPPORTED"}:
        raise HTTPException(status_code=422, detail="OpenAI 只能在官方支持地区启用")
    user.region = region
    user.model_preference = preference
    user.timezone = body.timezone
    log_event(db, user.id, "OWNER_SETTINGS_UPDATED", {"region": region, "model_preference": preference, "timezone": body.timezone})
    db.commit()
    return {"ok": True}


@app.put("/schedule")
def update_schedule(body: ScheduleInput, user: Owner, db: DB) -> dict:
    row = db.scalar(select(ClearingSchedule).where(ClearingSchedule.user_id == user.id))
    if not row:
        row = ClearingSchedule(user_id=user.id)
        db.add(row)
    for key, value in body.model_dump().items():
        setattr(row, key, value.upper() if key == "frequency" else value)
    row.next_run_at = next_schedule_time(body)
    user.timezone = body.timezone
    log_event(db, user.id, "CLEARING_SCHEDULE_UPDATED", {"frequency": row.frequency, "next_run_at": iso(row.next_run_at)})
    db.commit()
    return {"id": row.id, "next_run_at": iso(row.next_run_at), **body.model_dump(mode="json")}


@app.get("/notifications")
def notifications(user: Owner, db: DB) -> list[dict]:
    sync_goal_completion_notifications(db, user.id)
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id)).all()
    goal_by_kind = {goal_completion_kind(goal): goal.id for goal in goals}
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(100)).all()
    return [{"id": row.id, "kind": row.kind, "title": row.title, "body": row.body, "goal_id": goal_by_kind.get(row.kind), "read_at": iso(row.read_at), "created_at": iso(row.created_at)} for row in rows]


@app.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str, user: Owner, db: DB) -> dict:
    row = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="通知不存在")
    row.read_at = utcnow()
    db.commit()
    return {"ok": True}


@app.get("/sessions/{session_id}/export/{format_name}")
def export_session(session_id: str, format_name: str, user: Owner, db: DB):
    session = owned_session(db, user, session_id)
    if session.status not in {"CONFIRMED", "REVISED", "SUPERSEDED"}:
        raise HTTPException(status_code=409, detail="只有已确认清算可以导出")
    format_name = format_name.lower()
    if format_name == "json":
        data, media, suffix = as_json_bytes(session), "application/json", "json"
    elif format_name == "csv":
        data, media, suffix = as_csv_bytes(session), "text/csv; charset=utf-8", "csv"
    elif format_name == "pdf":
        data, media, suffix = as_pdf_bytes(session), "application/pdf", "pdf"
    else:
        raise HTTPException(status_code=404, detail="导出格式仅支持 CSV、JSON、PDF")
    log_event(db, user.id, "DATA_EXPORTED", {"session_id": session.id, "format": format_name})
    db.commit()
    filename = f"xiaobai-clearing-{session.id[:8]}.{suffix}"
    return StreamingResponse(iter([data]), media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@app.post("/backups")
def create_backup(user: Owner, db: DB) -> dict:
    record = create_encrypted_backup(db, user.id)
    log_event(db, user.id, "BACKUP_CREATED", {"backup_id": record.id, "sha256": record.sha256})
    db.commit()
    return {"id": record.id, "file_name": record.file_name, "sha256": record.sha256, "size_bytes": record.size_bytes, "created_at": iso(record.created_at), "encrypted": True}


@app.get("/backups")
def list_backups(user: Owner, db: DB) -> list[dict]:
    rows = db.scalars(select(BackupRecord).where(BackupRecord.user_id == user.id).order_by(desc(BackupRecord.created_at))).all()
    return [{"id": row.id, "file_name": row.file_name, "sha256": row.sha256, "size_bytes": row.size_bytes, "status": row.status, "created_at": iso(row.created_at)} for row in rows]


@app.get("/backups/{backup_id}/download")
def download_backup(backup_id: str, user: Owner, db: DB):
    row = db.scalar(select(BackupRecord).where(BackupRecord.id == backup_id, BackupRecord.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="备份不存在")
    path = backup_path(row)
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
        row.status = "CORRUPT_OR_MISSING"
        log_event(db, user.id, "BACKUP_INTEGRITY_FAILED", {"backup_id": row.id}, "HIGH")
        db.commit()
        raise HTTPException(status_code=500, detail="备份完整性校验失败")
    log_event(db, user.id, "BACKUP_DOWNLOADED", {"backup_id": row.id})
    db.commit()
    return StreamingResponse(path.open("rb"), media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{row.file_name}"', "Cache-Control": "no-store"})


@app.post("/backups/{backup_id}/restore")
def restore_backup(backup_id: str, body: ReauthRequest, user: Owner, db: DB) -> dict:
    verify_reauth(user, body)
    row = db.scalar(select(BackupRecord).where(BackupRecord.id == backup_id, BackupRecord.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="备份不存在")
    try:
        result = restore_encrypted_backup(db, row, user.id)
    except ValueError as exc:
        row.status = "CORRUPT_OR_MISSING"
        log_event(db, user.id, "BACKUP_RESTORE_FAILED", {"backup_id": row.id, "reason": str(exc)}, "HIGH")
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    log_event(db, user.id, "BACKUP_RESTORED", {"backup_id": row.id, "restored": result["restored"]}, "HIGH")
    db.commit()
    return {"ok": True, **result}


@app.get("/audit")
def audit_logs(user: Owner, db: DB, limit: int = 100) -> list[dict]:
    limit = min(max(limit, 1), 500)
    rows = db.scalars(select(AuditLog).where(AuditLog.user_id == user.id).order_by(desc(AuditLog.created_at)).limit(limit)).all()
    return [{"id": row.id, "event": row.event, "severity": row.severity, "metadata": row.metadata_json, "created_at": iso(row.created_at)} for row in rows]


@app.get("/images/deletion-status")
def image_deletion_status(user: Owner, db: DB) -> dict:
    rows = db.scalars(select(UploadedImage).where(UploadedImage.user_id == user.id).order_by(desc(UploadedImage.created_at)).limit(100)).all()
    pending = [row for row in rows if row.deletion_status not in {"DELETED", "DUPLICATE_SKIPPED"}]
    return {
        "all_recent_deleted": not pending,
        "records": [{"id": row.id, "session_id": row.session_id, "filename": row.original_filename, "size_bytes": row.size_bytes, "client_masked": row.was_client_masked, "status": row.deletion_status, "created_at": iso(row.created_at), "deleted_at": iso(row.deleted_at)} for row in rows],
    }


def verify_reauth(user: User, body: ReauthRequest) -> None:
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="密码不正确")
    if user.totp_enabled:
        if not body.totp_code or not user.totp_secret_encrypted or not verify_totp(decrypt_secret(user.totp_secret_encrypted), body.totp_code):
            raise HTTPException(status_code=401, detail="需要正确的动态验证码")


@app.post("/data/purge")
def purge_all_data(body: ReauthRequest, user: Owner, db: DB) -> dict:
    verify_reauth(user, body)
    for model in (
        SpendingDecision, SpendingProfile, ProductXray, FocusTask, FinancialRule,
        FutureObligation, GoalFundingAllocation, ActionItem, GoalPlan, ClearingAttribution,
    ):
        db.execute(delete(model).where(model.user_id == user.id))
    session_ids = list(db.scalars(select(ClearingSession.id).where(ClearingSession.user_id == user.id)).all())
    if session_ids:
        db.execute(delete(UploadedImage).where(UploadedImage.session_id.in_(session_ids)))
        db.execute(delete(AssetItem).where(AssetItem.session_id.in_(session_ids)))
        db.execute(delete(ClearingSession).where(ClearingSession.id.in_(session_ids)))
    db.execute(delete(Goal).where(Goal.user_id == user.id))
    db.execute(delete(GoldQuote).where(GoldQuote.user_id == user.id))
    db.execute(delete(ChartAnnotation).where(ChartAnnotation.user_id == user.id))
    db.execute(delete(ClearingSchedule).where(ClearingSchedule.user_id == user.id))
    db.execute(delete(Notification).where(Notification.user_id == user.id))
    for record in db.scalars(select(BackupRecord).where(BackupRecord.user_id == user.id)).all():
        path = backup_path(record)
        if path.exists():
            path.unlink()
        db.delete(record)
    log_event(db, user.id, "ALL_FINANCIAL_DATA_PURGED", {"completed_at": utcnow().isoformat()}, "HIGH")
    db.commit()
    return {"ok": True, "message": "财务数据、短期图片记录和本地加密备份已清除；安全审计日志保留。"}
