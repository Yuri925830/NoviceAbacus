import io
from datetime import datetime, timezone

import pyotp
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.database import Base, SessionLocal, engine
from app.main import app, stable_asset_key
from app.models import AssetItem, ClearingSession, GoalFundingAllocation, SpendingDecision, SpendingProfile, User
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
    persisted = client.get("/auth/me")
    assert persisted.json()["totp_enabled"] is True
    assert persisted.json()["security_setup_required"] is False
    duplicate_setup = client.post("/auth/totp/setup")
    assert duplicate_setup.status_code == 409
    assert client.get("/auth/me").json()["totp_enabled"] is True

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
    assert dashboard.json()["snapshot"]["items"][0]["name"] == "A股账户"
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


def test_integer_profile_values_and_action_ledger_are_accepted(client: TestClient):
    login(client)
    profile = client.put("/spending/profile", json={
        "monthly_income_cny": 1,
        "monthly_essential_expenses_cny": 0,
        "monthly_current_expenses_cny": 0,
        "emergency_months": 6,
    })
    assert profile.status_code == 200, profile.text
    assert profile.json()["monthly_income_cny"] == "1.00"
    assert profile.json()["monthly_essential_expenses_cny"] == "0.00"
    assert profile.json()["monthly_current_expenses_cny"] == "0.00"

    action = client.post("/intelligence/actions", json={
        "title": "建立应急储备",
        "reason": "先守住生活底线",
        "expected_impact": "提高现金缓冲",
        "risk": "需要控制非必要支出",
        "review_trigger": "下次清算时复盘",
        "priority": "HIGH",
        "source": "DECISION_STUDIO",
    })
    assert action.status_code == 200, action.text
    assert action.json()["title"] == "建立应急储备"
    assert client.get("/intelligence/actions").json()[0]["source"] == "DECISION_STUDIO"

    for frequency in ("CUSTOM", "YEARLY"):
        missing_date = client.put("/schedule", json={"frequency": frequency, "hour": 20, "minute": 0})
        assert missing_date.status_code == 422, missing_date.text
        assert "日期" in missing_date.json()["detail"] or "月和日" in missing_date.json()["detail"]


def test_funding_keys_precision_categories_and_stale_snapshot_are_safe(client: TestClient):
    login(client)
    first = client.post("/sessions", json={"kind": "AD_HOC"}).json()
    for name, asset_type, value in [
        ("零钱", "CASH", "26948.749"),
        ("同名账户", "CASH", "10"),
        ("同名账户", "CASH", "20"),
        ("指数基金", "FUND", "300"),
    ]:
        created = client.post(f"/sessions/{first['id']}/items", json={
            "name": name, "asset_type": asset_type, "category": asset_type,
            "original_currency": "CNY", "original_value": value,
            "liquidity_level": "HIGH", "is_liability": False,
            "source": "MANUAL", "status": "CONFIRMED",
        })
        assert created.status_code == 200, created.text
    confirmed = client.post(f"/sessions/{first['id']}/confirm", json={
        "accept_stale_rates": False, "idempotency_key": "funding-edge-confirm-0001",
    })
    assert confirmed.status_code == 200, confirmed.text
    goal = client.post("/goals", json={
        "name": "完整边界测试", "goal_type": "NET_WORTH", "target_cny": "50000",
        "included_asset_types": [],
    }).json()

    funding = client.get("/funding/map")
    assert funding.status_code == 200, funding.text
    payload = funding.json()
    assert [(row["asset_type"], row["asset_count"]) for row in payload["asset_categories"]] == [("CASH", 3), ("FUND", 1)]
    assert len({row["asset_key"] for row in payload["assets"]}) == 4
    precise = next(row for row in payload["assets"] if row["name"] == "零钱")
    assert precise["value_cny"] == "26948.75"

    full = client.put("/funding/allocations", json={
        "snapshot_id": payload["snapshot_id"],
        "allocations": [{"asset_key": precise["asset_key"], "goal_id": goal["id"], "amount_cny": "26948.75"}],
    })
    assert full.status_code == 200, full.text
    assert full.json()["allocations"][0]["amount_cny"] == "26948.75"
    repeated = client.put("/funding/allocations", json={
        "snapshot_id": payload["snapshot_id"],
        "allocations": [{"asset_key": precise["asset_key"], "goal_id": goal["id"], "amount_cny": 26948.75}],
    })
    assert repeated.status_code == 200, repeated.text

    with SessionLocal() as db:
        latest_item = db.query(AssetItem).filter(AssetItem.name == "零钱").one()
        legacy_key = stable_asset_key(latest_item)
        db.query(GoalFundingAllocation).delete()
        db.add(GoalFundingAllocation(user_id=latest_item.session.user_id, goal_id=goal["id"], asset_key=legacy_key, amount_cny="100"))
        db.add(GoalFundingAllocation(user_id=latest_item.session.user_id, goal_id=goal["id"], asset_key="f" * 64, amount_cny="50"))
        db.commit()
    reconciled = client.get("/funding/map")
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["allocations"] == [{
        "id": reconciled.json()["allocations"][0]["id"],
        "asset_key": precise["asset_key"], "goal_id": goal["id"], "amount_cny": "100.00",
    }]

    second = client.post("/sessions", json={"kind": "AD_HOC"}).json()
    carried = next(row for row in second["items"] if row["name"] == "零钱")
    renamed = client.patch(f"/sessions/{second['id']}/items/{carried['id']}", json={"name": "零钱（改名）"})
    assert renamed.status_code == 200, renamed.text
    second_confirmed = client.post(f"/sessions/{second['id']}/confirm", json={
        "accept_stale_rates": False, "idempotency_key": "funding-edge-confirm-0002",
    })
    assert second_confirmed.status_code == 200, second_confirmed.text
    after_carry = client.get("/funding/map").json()
    renamed_asset = next(row for row in after_carry["assets"] if row["name"] == "零钱（改名）")
    assert renamed_asset["asset_key"] == precise["asset_key"]
    assert renamed_asset["committed_cny"] == "100.00"

    stale = client.put("/funding/allocations", json={
        "snapshot_id": payload["snapshot_id"],
        "allocations": [{"asset_key": precise["asset_key"], "goal_id": goal["id"], "amount_cny": "1"}],
    })
    assert stale.status_code == 409
    assert "资产清算刚刚更新" in stale.json()["detail"]


def test_funding_incrementally_uses_only_unallocated_balance_across_goals(client: TestClient):
    login(client)
    session = client.post("/sessions", json={"kind": "AD_HOC"}).json()
    for name, asset_type, value in [
        ("股票资产", "STOCK", "10000"),
        ("三年定期", "FIXED_DEPOSIT", "30000"),
    ]:
        created = client.post(f"/sessions/{session['id']}/items", json={
            "name": name, "asset_type": asset_type, "category": asset_type,
            "original_currency": "CNY", "original_value": value,
            "liquidity_level": "HIGH", "is_liability": False,
            "source": "MANUAL", "status": "CONFIRMED",
        })
        assert created.status_code == 200, created.text
    confirmed = client.post(f"/sessions/{session['id']}/confirm", json={
        "accept_stale_rates": False, "idempotency_key": "funding-incremental-confirm-0001",
    })
    assert confirmed.status_code == 200, confirmed.text
    phone = client.post("/goals", json={
        "name": "买手机", "goal_type": "NET_WORTH", "target_cny": "10000", "included_asset_types": [],
    }).json()
    travel = client.post("/goals", json={
        "name": "旅行", "goal_type": "NET_WORTH", "target_cny": "50000", "included_asset_types": [],
    }).json()
    funding = client.get("/funding/map").json()
    stock = next(asset for asset in funding["assets"] if asset["name"] == "股票资产")
    deposit = next(asset for asset in funding["assets"] if asset["name"] == "三年定期")

    phone_saved = client.put("/funding/allocations", json={
        "snapshot_id": funding["snapshot_id"],
        "allocations": [{"asset_key": stock["asset_key"], "goal_id": phone["id"], "amount_cny": "3000"}],
    })
    assert phone_saved.status_code == 200, phone_saved.text
    phone_map = phone_saved.json()
    assert next(asset for asset in phone_map["assets"] if asset["name"] == "股票资产")["free_cny"] == "7000.00"
    assert next(asset for asset in phone_map["assets"] if asset["name"] == "三年定期")["free_cny"] == "30000.00"
    assert next(goal for goal in phone_map["goals"] if goal["id"] == phone["id"])["allocated_cny"] == "3000.00"

    travel_saved = client.put("/funding/allocations", json={
        "snapshot_id": funding["snapshot_id"],
        "allocations": [
            {"asset_key": stock["asset_key"], "goal_id": phone["id"], "amount_cny": "3000"},
            {"asset_key": stock["asset_key"], "goal_id": travel["id"], "amount_cny": "7000"},
            {"asset_key": deposit["asset_key"], "goal_id": travel["id"], "amount_cny": "30000"},
        ],
    })
    assert travel_saved.status_code == 200, travel_saved.text
    travel_map = travel_saved.json()
    assert next(goal for goal in travel_map["goals"] if goal["id"] == phone["id"])["allocated_cny"] == "3000.00"
    assert next(goal for goal in travel_map["goals"] if goal["id"] == travel["id"])["allocated_cny"] == "37000.00"
    assert all(asset["free_cny"] == "0.00" for asset in travel_map["assets"])


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

    goal = client.post("/goals", json={"name": "买车", "goal_type": "NET_WORTH", "target_cny": "5000", "included_asset_types": []}).json()
    funding = client.get("/funding/map")
    key = funding.json()["assets"][0]["asset_key"]
    rejected = client.put("/funding/allocations", json={"allocations": [{"asset_key": key, "goal_id": goal["id"], "amount_cny": "10000"}]})
    assert rejected.status_code == 422
    saved = client.put("/funding/allocations", json={"allocations": [{"asset_key": key, "goal_id": goal["id"], "amount_cny": "9000"}]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["free_net_worth_cny"] == "0.00"
    assert saved.json()["goals"][0]["completion_status"] == "AWAITING_CONFIRMATION"
    completed_goal = client.get("/goals").json()[0]
    assert completed_goal["completion_status"] == "AWAITING_CONFIRMATION"
    assert client.get("/auth/me").json()["pending_goal_completions"] == [{"id": goal["id"], "name": "买车"}]
    notices = client.get("/notifications").json()
    assert notices[0]["title"] == "您的买车理财目标已完成，请前往确认！"
    assert notices[0]["goal_id"] == goal["id"]

    confirmed_goal = client.post(f"/goals/{goal['id']}/completion/confirm")
    assert confirmed_goal.status_code == 200, confirmed_goal.text
    assert confirmed_goal.json()["completion_status"] == "CONFIRMED"
    assert confirmed_goal.json()["completion_confirmed_at"] is not None
    assert client.get("/auth/me").json()["pending_goal_completions"] == []

    upgraded_goal = client.patch(f"/goals/{goal['id']}", json={
        "name": "买车升级版", "goal_type": "NET_WORTH", "target_cny": 12000,
        "due_date": None, "included_asset_types": [],
    })
    assert upgraded_goal.status_code == 200, upgraded_goal.text
    assert upgraded_goal.json()["completion_status"] == "IN_PROGRESS"
    assert upgraded_goal.json()["gap_cny"] == "3000.00"
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
    deleted_goal = client.delete(f"/goals/{goal['id']}")
    assert deleted_goal.status_code == 200, deleted_goal.text
    assert client.get("/goals").json() == []
    assert client.get("/funding/map").json()["free_net_worth_cny"] == "9000.00"
