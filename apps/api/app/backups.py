from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, select
from sqlalchemy.sql.sqltypes import Date as SADate, DateTime as SADateTime, Numeric
from sqlalchemy.orm import Session

from .config import get_settings
from .models import (
    ActionItem, AssetItem, AuditLog, BackupRecord, ChartAnnotation, ClearingAttribution,
    ClearingSchedule, ClearingSession, FinancialRule, FocusTask, FutureObligation, Goal,
    GoalFundingAllocation, GoalPlan, GoldQuote, Notification, ProductXray, SpendingDecision,
    SpendingProfile, UploadedImage, User,
)
from .security import _fernet


settings = get_settings()


def encode(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def model_dict(instance) -> dict:
    return {column.name: encode(getattr(instance, column.name)) for column in instance.__table__.columns}


def create_encrypted_backup(db: Session, user_id: str) -> BackupRecord:
    user = db.get(User, user_id)
    if not user:
        raise ValueError("账号不存在")
    payload = {
        "format": "xiaobai-owner-backup-v3",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "owner_settings": {"region": user.region, "model_preference": user.model_preference, "timezone": user.timezone},
        "clearing_sessions": [model_dict(item) for item in db.scalars(select(ClearingSession).where(ClearingSession.user_id == user_id)).all()],
        "asset_items": [model_dict(item) for item in db.scalars(select(AssetItem).join(ClearingSession).where(ClearingSession.user_id == user_id)).all()],
        "goals": [model_dict(item) for item in db.scalars(select(Goal).where(Goal.user_id == user_id)).all()],
        "goal_plans": [model_dict(item) for item in db.scalars(select(GoalPlan).where(GoalPlan.user_id == user_id)).all()],
        "action_items": [model_dict(item) for item in db.scalars(select(ActionItem).where(ActionItem.user_id == user_id)).all()],
        "clearing_attributions": [model_dict(item) for item in db.scalars(select(ClearingAttribution).where(ClearingAttribution.user_id == user_id)).all()],
        "funding_allocations": [model_dict(item) for item in db.scalars(select(GoalFundingAllocation).where(GoalFundingAllocation.user_id == user_id)).all()],
        "future_obligations": [model_dict(item) for item in db.scalars(select(FutureObligation).where(FutureObligation.user_id == user_id)).all()],
        "financial_rules": [model_dict(item) for item in db.scalars(select(FinancialRule).where(FinancialRule.user_id == user_id)).all()],
        "focus_tasks": [model_dict(item) for item in db.scalars(select(FocusTask).where(FocusTask.user_id == user_id)).all()],
        "product_xrays": [model_dict(item) for item in db.scalars(select(ProductXray).where(ProductXray.user_id == user_id)).all()],
        "spending_profiles": [model_dict(item) for item in db.scalars(select(SpendingProfile).where(SpendingProfile.user_id == user_id)).all()],
        "spending_decisions": [model_dict(item) for item in db.scalars(select(SpendingDecision).where(SpendingDecision.user_id == user_id)).all()],
        "gold_quotes": [model_dict(item) for item in db.scalars(select(GoldQuote).where(GoldQuote.user_id == user_id)).all()],
        "annotations": [model_dict(item) for item in db.scalars(select(ChartAnnotation).where(ChartAnnotation.user_id == user_id)).all()],
        "schedule": [model_dict(item) for item in db.scalars(select(ClearingSchedule).where(ClearingSchedule.user_id == user_id)).all()],
        "notifications": [model_dict(item) for item in db.scalars(select(Notification).where(Notification.user_id == user_id)).all()],
        "image_deletion_audit": [model_dict(item) for item in db.scalars(select(UploadedImage).where(UploadedImage.user_id == user_id)).all()],
        "audit_logs": [model_dict(item) for item in db.scalars(select(AuditLog).where(AuditLog.user_id == user_id)).all()],
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encrypted = _fernet().encrypt(raw)
    folder = settings.data_dir / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"xiaobai-backup-{stamp}.xbs"
    path = folder / filename
    path.write_bytes(encrypted)
    record = BackupRecord(user_id=user_id, file_name=filename, sha256=hashlib.sha256(encrypted).hexdigest(), size_bytes=len(encrypted))
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def backup_path(record: BackupRecord) -> Path:
    path = (settings.data_dir / "backups" / record.file_name).resolve()
    allowed = (settings.data_dir / "backups").resolve()
    if allowed not in path.parents:
        raise ValueError("非法备份路径")
    return path


def _decode_row(model, row: dict, enforced: dict | None = None) -> dict:
    enforced = enforced or {}
    values: dict = {}
    for column in model.__table__.columns:
        if column.name in enforced:
            values[column.name] = enforced[column.name]
            continue
        if column.name not in row:
            continue
        value = row[column.name]
        if value is not None and isinstance(column.type, SADateTime):
            value = datetime.fromisoformat(value)
        elif value is not None and isinstance(column.type, SADate):
            value = date.fromisoformat(value)
        elif value is not None and isinstance(column.type, Numeric):
            value = Decimal(str(value))
        values[column.name] = value
    return values


def _add_rows(db: Session, model, rows: list[dict], enforced: dict | None = None, skip_existing: bool = False) -> int:
    restored = 0
    for row in rows:
        values = _decode_row(model, row, enforced)
        primary_key = values.get("id")
        if skip_existing and primary_key and db.get(model, primary_key):
            continue
        db.add(model(**values))
        restored += 1
    db.flush()
    return restored


def restore_encrypted_backup(db: Session, record: BackupRecord, user_id: str) -> dict:
    path = backup_path(record)
    if not path.exists():
        raise ValueError("备份文件不存在")
    encrypted = path.read_bytes()
    if hashlib.sha256(encrypted).hexdigest() != record.sha256:
        raise ValueError("备份完整性校验失败")
    try:
        payload = json.loads(_fernet().decrypt(encrypted).decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("备份无法解密或内容已损坏") from exc
    if payload.get("format") not in {"xiaobai-owner-backup-v1", "xiaobai-owner-backup-v2", "xiaobai-owner-backup-v3"}:
        raise ValueError("不支持的备份格式")

    sessions = payload.get("clearing_sessions", [])
    items = payload.get("asset_items", [])
    session_ids = {row.get("id") for row in sessions if row.get("id")}
    if any(row.get("session_id") not in session_ids for row in items):
        raise ValueError("备份中的资产与清算关系无效")

    try:
        current_session_ids = list(db.scalars(select(ClearingSession.id).where(ClearingSession.user_id == user_id)).all())
        for model in (
            SpendingDecision, SpendingProfile, ProductXray, FocusTask, FinancialRule,
            FutureObligation, GoalFundingAllocation, ActionItem, GoalPlan, ClearingAttribution,
        ):
            db.execute(delete(model).where(model.user_id == user_id))
        if current_session_ids:
            db.execute(delete(UploadedImage).where(UploadedImage.session_id.in_(current_session_ids)))
            db.execute(delete(AssetItem).where(AssetItem.session_id.in_(current_session_ids)))
            db.execute(delete(ClearingSession).where(ClearingSession.id.in_(current_session_ids)))
        for model in (Goal, GoldQuote, ChartAnnotation, ClearingSchedule, Notification):
            db.execute(delete(model).where(model.user_id == user_id))

        counts = {
            "clearing_sessions": _add_rows(db, ClearingSession, sessions, {"user_id": user_id}),
            "asset_items": _add_rows(db, AssetItem, items),
            "goals": _add_rows(db, Goal, payload.get("goals", []), {"user_id": user_id}),
            "goal_plans": _add_rows(db, GoalPlan, payload.get("goal_plans", []), {"user_id": user_id}),
            "action_items": _add_rows(db, ActionItem, payload.get("action_items", []), {"user_id": user_id}),
            "clearing_attributions": _add_rows(db, ClearingAttribution, payload.get("clearing_attributions", []), {"user_id": user_id}),
            "funding_allocations": _add_rows(db, GoalFundingAllocation, payload.get("funding_allocations", []), {"user_id": user_id}),
            "future_obligations": _add_rows(db, FutureObligation, payload.get("future_obligations", []), {"user_id": user_id}),
            "financial_rules": _add_rows(db, FinancialRule, payload.get("financial_rules", []), {"user_id": user_id}),
            "focus_tasks": _add_rows(db, FocusTask, payload.get("focus_tasks", []), {"user_id": user_id}),
            "product_xrays": _add_rows(db, ProductXray, payload.get("product_xrays", []), {"user_id": user_id}),
            "spending_profiles": _add_rows(db, SpendingProfile, payload.get("spending_profiles", []), {"user_id": user_id}),
            "spending_decisions": _add_rows(db, SpendingDecision, payload.get("spending_decisions", []), {"user_id": user_id}),
            "gold_quotes": _add_rows(db, GoldQuote, payload.get("gold_quotes", []), {"user_id": user_id}),
            "annotations": _add_rows(db, ChartAnnotation, payload.get("annotations", []), {"user_id": user_id}),
            "schedule": _add_rows(db, ClearingSchedule, payload.get("schedule", []), {"user_id": user_id}),
            "notifications": _add_rows(db, Notification, payload.get("notifications", []), {"user_id": user_id}),
            "image_deletion_audit": _add_rows(db, UploadedImage, payload.get("image_deletion_audit", []), {"user_id": user_id}),
            "audit_logs_merged": _add_rows(db, AuditLog, payload.get("audit_logs", []), {"user_id": user_id}, skip_existing=True),
        }
        owner = db.get(User, user_id)
        owner_settings = payload.get("owner_settings", {})
        if owner and owner_settings:
            owner.region = str(owner_settings.get("region", owner.region))[:20]
            owner.model_preference = str(owner_settings.get("model_preference", owner.model_preference))[:20]
            owner.timezone = str(owner_settings.get("timezone", owner.timezone))[:80]
        db.commit()
        return {"format": payload["format"], "created_at": payload.get("created_at"), "restored": counts}
    except Exception:
        db.rollback()
        raise
