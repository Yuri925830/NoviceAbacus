import io
from datetime import datetime, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import ClearingSession, SpendingDecision, SpendingProfile, User
from app.security import decrypt_secret, hash_password


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.add(User(email="owner@test.local", password_hash=hash_password("Correct-Horse-Battery-99"), role="OWNER"))
        db.commit()
    with TestClient(app) as value:
        yield value


def login(client: TestClient):
    response = client.post("/auth/login", json={"identifier": "owner@test.local", "password": "Correct-Horse-Battery-99", "device_name": "pytest"})
    assert response.status_code == 200, response.text
    return response


def test_owner_auth_totp_and_complete_clearing_flow(client: TestClient):
    login(client)
    me = client.get("/auth/me")
    assert me.status_code == 200
    assert me.json()["security_setup_required"] is True

    setup = client.post("/auth/totp/setup")
    assert setup.status_code == 200
    totp_secret = setup.json()["secret"]
    code = pyotp.TOTP(totp_secret).now()
    verified = client.post("/auth/totp/verify", json={"code": code})
    assert verified.status_code == 200
    assert len(verified.json()["recovery_codes"]) == 8

    created = client.post("/sessions", json={"kind": "AD_HOC"})
    assert created.status_code == 200
    session_id = created.json()["id"]
    stock = client.post(f"/sessions/{session_id}/items", json={
        "name": "A股账户", "asset_type": "STOCK", "category": "INVESTMENT", "original_currency": "CNY",
        "original_value": "12000", "current_market_value": "12000", "cost_basis": "10000", "unrealized_pl": "2000",
        "liquidity_level": "MEDIUM", "is_liability": False, "source": "MANUAL", "status": "CONFIRMED",
    })
    assert stock.status_code == 200, stock.text
    liability = client.post(f"/sessions/{session_id}/items", json={
        "name": "信用卡", "asset_type": "LIABILITY", "category": "LIABILITY", "original_currency": "CNY",
        "original_value": "2000", "liquidity_level": "LOW", "is_liability": True, "source": "MANUAL", "status": "CONFIRMED",
    })
    assert liability.status_code == 200

    confirmed = client.post(f"/sessions/{session_id}/confirm", json={"accept_stale_rates": False, "idempotency_key": "pytest-confirm-0001"})
    assert confirmed.status_code == 200, confirmed.text
    payload = confirmed.json()
    assert payload["totals"]["assets_cny"] == "12000.00"
    assert payload["totals"]["liabilities_cny"] == "2000.00"
    assert payload["totals"]["net_worth_cny"] == "10000.00"

    repeated = client.post(f"/sessions/{session_id}/confirm", json={"accept_stale_rates": False, "idempotency_key": "pytest-confirm-0001"})
    assert repeated.status_code == 200
    assert repeated.json()["id"] == session_id

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["has_snapshot"] is True
    trend = client.get("/trend?metric=net_worth_cny&granularity=month")
    assert trend.status_code == 200
    assert trend.json()["analysis"]["data_level"] == "BASELINE"

    csv_export = client.get(f"/sessions/{session_id}/export/csv")
    assert csv_export.status_code == 200
    assert "A股账户" in csv_export.content.decode("utf-8-sig")

    backup = client.post("/backups")
    assert backup.status_code == 200, backup.text
    backup_id = backup.json()["id"]
    deleted = client.delete(f"/sessions/{session_id}")
    assert deleted.status_code == 200
    assert client.get("/dashboard").json()["has_snapshot"] is False

    restored = client.post(f"/backups/{backup_id}/restore", json={
        "password": "Correct-Horse-Battery-99",
        "totp_code": pyotp.TOTP(totp_secret).now(),
    })
    assert restored.status_code == 200, restored.text
    assert restored.json()["restored"]["clearing_sessions"] == 1
    assert client.get("/dashboard").json()["has_snapshot"] is True


def test_assistant_answers_without_a_clearing_and_goal_plan_is_saved(client: TestClient, monkeypatch):
    login(client)
    captured_contexts = []

    async def fake_analyze(self, db, user_id, prompt, context, complex_task=False):
        captured_contexts.append(context)
        return {
            "confirmed_facts": [],
            "analysis": ["应急金通常可以从几个月必要支出开始准备。"],
            "recommendations": [
                {"action": "先存下第一个月", "reason": "小步更容易坚持", "risk": "仍要保留日常周转金"}
            ],
            "limitations": [],
            "requires_owner_confirmation": False,
        }

    monkeypatch.setattr("app.main.QwenClient.analyze", fake_analyze)
    response = client.post("/assistant", json={"message": "没有资产数据时，我该怎么准备应急金？", "provider": "qwen"})
    assert response.status_code == 200, response.text
    assert response.json()["result"]["analysis"]
    assert captured_contexts[-1]["data_availability"]["has_confirmed_snapshot"] is False

    created = client.post("/goals", json={
        "name": "安心应急金",
        "goal_type": "LIQUID_CASH",
        "target_cny": "60000",
        "included_asset_types": [],
    })
    assert created.status_code == 200
    goal_id = created.json()["id"]
    planned = client.post(f"/goals/{goal_id}/plan", json={
        "monthly_income_cny": "12000",
        "monthly_fixed_expenses_cny": "5000",
        "monthly_safety_buffer_cny": "2000",
        "provider": "qwen",
        "depth": "complex",
    })
    assert planned.status_code == 200, planned.text
    assert planned.json()["plan"]["calculation"]["suggested_monthly_contribution_cny"] == "3000.00"
    loaded = client.get(f"/goals/{goal_id}")
    assert loaded.status_code == 200
    assert loaded.json()["plan"]["guidance"]["recommendations"]

    edited_goal = client.patch(f"/goals/{goal_id}", json={
        "name": "更安心的应急金", "goal_type": "LIQUID_CASH", "target_cny": "72000",
        "due_date": "2028-12-31", "included_asset_types": [],
    })
    assert edited_goal.status_code == 200, edited_goal.text
    assert edited_goal.json()["target_cny"] == "72000.00"
    plan = loaded.json()["plan"]
    edited_plan = client.patch(f"/goals/{goal_id}/plan", json={
        "monthly_income_cny": "12000", "monthly_fixed_expenses_cny": "5000",
        "monthly_safety_buffer_cny": "2000", "suggested_monthly_contribution_cny": "2800",
        "guidance": plan["guidance"],
    })
    assert edited_plan.status_code == 200, edited_plan.text
    assert edited_plan.json()["plan"]["calculation"]["suggested_monthly_contribution_cny"] == "2800.00"


def test_second_clearing_carries_assets_and_attribution_answers_are_editable(client: TestClient):
    login(client)
    first = client.post("/sessions", json={"kind": "AD_HOC"}).json()
    item = client.post(f"/sessions/{first['id']}/items", json={
        "name": "生活存款", "asset_type": "CASH", "category": "CASH", "original_currency": "CNY",
        "original_value": "100000", "liquidity_level": "HIGH", "is_liability": False,
        "source": "MANUAL", "status": "CONFIRMED",
    })
    assert item.status_code == 200
    confirmed = client.post(f"/sessions/{first['id']}/confirm", json={"accept_stale_rates": False, "idempotency_key": "carry-first-0001"})
    assert confirmed.status_code == 200, confirmed.text

    second = client.post("/sessions", json={"kind": "AD_HOC"})
    assert second.status_code == 200
    carried = second.json()["items"]
    assert len(carried) == 1
    assert carried[0]["source"] == "CARRY_FORWARD"
    updated = client.patch(f"/sessions/{second.json()['id']}/items/{carried[0]['id']}", json={"original_value": "88000"})
    assert updated.status_code == 200
    confirmed_second = client.post(f"/sessions/{second.json()['id']}/confirm", json={"accept_stale_rates": False, "idempotency_key": "carry-second-0002"})
    assert confirmed_second.status_code == 200, confirmed_second.text
    attribution = client.get(f"/sessions/{second.json()['id']}/attribution")
    assert attribution.status_code == 200, attribution.text
    assert attribution.json()["available"] is True
    assert attribution.json()["total_change_cny"] == "-12000.00"
    answered = client.patch(f"/sessions/{second.json()['id']}/attribution", json={"answers": [
        {"question_id": "cause", "value": "LARGE_EXPENSE"},
        {"question_id": "amount", "value": "12000"},
        {"question_id": "remember", "value": True},
    ]})
    assert answered.status_code == 200
    assert any(row["label"] == "大额消费" for row in answered.json()["breakdown"])


def test_empty_legacy_draft_is_reseeded_edits_accept_decimals_and_ai_never_returns_500(client: TestClient, monkeypatch):
    login(client)
    first = client.post("/sessions", json={"kind": "AD_HOC"}).json()
    added = client.post(f"/sessions/{first['id']}/items", json={
        "name": "日常存款", "asset_type": "CASH", "category": "CASH", "original_currency": "CNY",
        "original_value": "100000", "liquidity_level": "HIGH", "is_liability": False,
        "source": "MANUAL", "status": "CONFIRMED",
    })
    assert added.status_code == 200, added.text
    confirmed = client.post(f"/sessions/{first['id']}/confirm", json={"accept_stale_rates": False, "idempotency_key": "legacy-first-0001"})
    assert confirmed.status_code == 200, confirmed.text

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == "owner@test.local").one()
        empty = ClearingSession(user_id=user.id, kind="AD_HOC", status="DRAFT")
        db.add(empty)
        db.commit()
        empty_id = empty.id

    reopened = client.post("/sessions", json={"kind": "AD_HOC"})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["id"] == empty_id
    assert len(reopened.json()["items"]) == 1
    carried = reopened.json()["items"][0]
    assert carried["source"] == "CARRY_FORWARD"

    edited = client.patch(f"/sessions/{empty_id}/items/{carried['id']}", json={
        "original_value": "90,000.50",
        "quantity": "",
        "liquidity_level": "HIGH",
    })
    assert edited.status_code == 200, edited.text
    assert edited.json()["original_value"] == "90000.50000000"
    assert edited.json()["quantity"] is None
    confirmed_second = client.post(f"/sessions/{empty_id}/confirm", json={"accept_stale_rates": False, "idempotency_key": "legacy-second-0002"})
    assert confirmed_second.status_code == 200, confirmed_second.text

    goal = client.post("/goals", json={
        "name": "明年旅行", "goal_type": "LIQUID_CASH", "target_cny": "30000", "included_asset_types": [],
    })
    assert goal.status_code == 200, goal.text

    async def broken_agent(*args, **kwargs):
        raise RuntimeError("simulated upstream connection reset")

    monkeypatch.setattr("app.main.OpenAIGatewayClient.analyze", broken_agent)
    monkeypatch.setattr("app.main.QwenClient.analyze", broken_agent)
    trend = client.post("/trend/insight", json={"metric": "net_worth_cny", "provider": "auto", "depth": "complex"})
    assert trend.status_code == 200, trend.text
    assert trend.json()["provider"] == "RULE_ENGINE"
    allocation = client.post("/intelligence/allocate", json={
        "monthly_income_cny": "12000", "monthly_fixed_expenses_cny": "5000",
        "monthly_safety_buffer_cny": "2000", "strategy": "BALANCED", "provider": "auto", "depth": "complex",
    })
    assert allocation.status_code == 200, allocation.text
    assert allocation.json()["agent"]["provider"] == "RULE_ENGINE"

    profile = client.put("/spending/profile", json={
        "monthly_income_cny": "12000", "monthly_essential_expenses_cny": "4000",
        "monthly_current_expenses_cny": "6000", "emergency_months": "6",
    })
    assert profile.status_code == 200, profile.text
    safe = client.get("/spending/safe-to-spend")
    assert safe.status_code == 200, safe.text
    assert safe.json()["ready"] is True
    assert safe.json()["safe_to_spend_cny"] == "6000.00"
    preview = client.post("/spending/preview", json={
        "decision": "买一台新电脑", "amount_cny": "5,000.50", "category": "ELECTRONICS",
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["simulation"]["amount_cny"] == "5000.50"
    assert preview.json()["verdict"] in {"DO_IT", "ADJUST", "WAIT"}
    ruling = client.post("/spending/ruling", json={
        "decision": "买一台新电脑", "amount_cny": "5000.50", "category": "ELECTRONICS",
        "provider": "auto", "depth": "complex",
    })
    assert ruling.status_code == 200, ruling.text
    assert ruling.json()["agent"]["provider"] == "RULE_ENGINE"
    assert ruling.json()["result"]["verdict_label"] in {"放心做", "可以做，但要调整", "现在先别做"}
    backup = client.post("/backups")
    assert backup.status_code == 200, backup.text
    with SessionLocal() as db:
        db.query(SpendingDecision).delete()
        db.query(SpendingProfile).delete()
        db.commit()
    restored = client.post(f"/backups/{backup.json()['id']}/restore", json={"password": "Correct-Horse-Battery-99"})
    assert restored.status_code == 200, restored.text
    assert restored.json()["format"] == "xiaobai-owner-backup-v3"
    assert restored.json()["restored"]["spending_profiles"] == 1
    assert restored.json()["restored"]["spending_decisions"] == 1
    assert client.get("/spending/profile").json()["configured"] is True
    assert len(client.get("/spending/decisions").json()) == 1


def test_live_physical_gold_funding_guard_constitution_and_product_xray(client: TestClient, monkeypatch):
    login(client)

    async def fake_gold(self, db, user_id):
        return {
            "quote_id": "quote-test", "symbol": "XAU/USD", "usd_per_troy_ounce": "4000",
            "usd_cny": "7.2", "cny_per_gram": "900.0000", "quoted_at": datetime.now(timezone.utc).isoformat(),
            "fetched_at": datetime.now(timezone.utc).isoformat(), "source": "pytest live source", "status": "CURRENT",
            "fx": {"rate": "7.2"}, "note": "test",
        }

    monkeypatch.setattr("app.main.GoldSpotProvider.get_cny_quote", fake_gold)
    session = client.post("/sessions", json={"kind": "AD_HOC"}).json()
    gold = client.post(f"/sessions/{session['id']}/items", json={
        "name": "投资金条", "asset_type": "PHYSICAL_GOLD", "category": "GOLD", "original_currency": "CNY",
        "original_value": "0", "quantity": "10", "liquidity_level": "MEDIUM", "is_liability": False,
        "source": "MANUAL", "status": "CONFIRMED",
    })
    assert gold.status_code == 200, gold.text
    assert gold.json()["original_value"] == "9000.00000000"
    confirmed = client.post(f"/sessions/{session['id']}/confirm", json={"accept_stale_rates": False, "idempotency_key": "gold-confirm-0001"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["totals"]["assets_cny"] == "9000.00"

    goal = client.post("/goals", json={"name": "买车", "goal_type": "NET_WORTH", "target_cny": "10000", "included_asset_types": []}).json()
    funding = client.get("/funding/map")
    key = funding.json()["assets"][0]["asset_key"]
    rejected = client.put("/funding/allocations", json={"allocations": [{"asset_key": key, "goal_id": goal["id"], "amount_cny": "10000"}]})
    assert rejected.status_code == 422
    saved = client.put("/funding/allocations", json={"allocations": [{"asset_key": key, "goal_id": goal["id"], "amount_cny": "8000"}]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["free_net_worth_cny"] == "1000.00"
    constitution = client.get("/constitution")
    assert constitution.status_code == 200
    assert len(constitution.json()["rules"]) == 7

    async def fake_xray(self, db, user_id, content, content_type, extracted_text=""):
        return {
            "product_name": "稳健六个月", "product_type": "银行理财", "issuer": "测试银行",
            "principal_guaranteed": {"value": "NO", "evidence": "不保证本金"}, "return_type": "HISTORICAL_DISPLAY",
            "displayed_return": {"value": "3.8%", "meaning": "历史年化展示", "is_guaranteed": False},
            "closure_period": "180天", "minimum_holding_period": "180天", "early_redemption": {"allowed": "NO", "loss_or_condition": "封闭期内不可赎回"},
            "fees": [], "risk_level": "R2", "underlying_assets": ["债券"], "worst_case": "可能亏损本金",
            "liquidity_features": ["封闭180天"], "plain_language_summary": ["3.8%不是保证收益"], "red_flags": ["不保本"],
            "evidence": [], "unknown_fields": [], "scope": "仅做条款解释",
        }

    monkeypatch.setattr("app.main.QwenClient.xray_product", fake_xray)
    output = io.BytesIO()
    pdf = canvas.Canvas(output)
    pdf.drawString(72, 760, "Product terms: historical annualized 3.8%, not principal guaranteed, locked 180 days.")
    pdf.save()
    xray = client.post("/xray", data={"intended_amount_cny": "5000"}, files={"file": ("terms.pdf", output.getvalue(), "application/pdf")})
    assert xray.status_code == 200, xray.text
    assert xray.json()["original_file_stored"] is False
    assert xray.json()["extraction"]["principal_guaranteed"]["value"] == "NO"
