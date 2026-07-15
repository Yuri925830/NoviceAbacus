from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.financial import aggregate_ohlc, analyze_series, calculate_snapshot, run_scenario
from app.main import next_schedule_time
from app.schemas import ScheduleInput


def item(**values):
    defaults = dict(
        id="item", name="item", asset_type="CASH", original_currency="CNY",
        original_value=Decimal("0"), current_market_value=None, unrealized_pl=None,
        liquidity_level="HIGH", is_liability=False, status="CONFIRMED", value_cny=None,
    )
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_snapshot_uses_market_value_without_double_counting_profit():
    rows = [
        item(id="stock", name="stock", asset_type="STOCK", original_value=Decimal("12000"), current_market_value=Decimal("12000"), unrealized_pl=Decimal("2000"), liquidity_level="MEDIUM"),
        item(id="pension", name="pension", asset_type="PENSION", original_value=Decimal("86000"), liquidity_level="RESTRICTED"),
        item(id="krw", name="krw", original_currency="KRW", original_value=Decimal("5000000")),
        item(id="loan", name="loan", asset_type="LIABILITY", original_value=Decimal("82000"), is_liability=True, liquidity_level="LOW"),
    ]
    totals, calculated = calculate_snapshot(rows, {"CNY": Decimal("1"), "KRW": Decimal("0.00508")})
    assert totals["assets_cny"] == "123400.00"
    assert totals["liabilities_cny"] == "82000.00"
    assert totals["net_worth_cny"] == "41400.00"
    assert totals["liquid_assets_cny"] == "25400.00"
    assert totals["restricted_assets_cny"] == "86000.00"
    assert next(row for row in calculated if row["id"] == "stock")["value_cny"] == Decimal("12000.00000000")


def test_ohlc_uses_real_confirmed_points_and_marks_single_point():
    points = [
        {"session_id": "a", "time": "2026-07-01T09:00:00+00:00", "value": "100.00"},
        {"session_id": "b", "time": "2026-07-10T09:00:00+00:00", "value": "120.00"},
        {"session_id": "c", "time": "2026-08-03T09:00:00+00:00", "value": "110.00"},
    ]
    candles = aggregate_ohlc(points, "month")
    assert candles[0] | {"session_ids": []} == {
        "bucket": "2026-07", "open": "100.00", "high": "120.00", "low": "100.00", "close": "120.00",
        "change": "20.00", "sample_count": 2, "single_point": False, "session_ids": [],
    }
    assert candles[1]["single_point"] is True
    assert candles[1]["open"] == candles[1]["high"] == candles[1]["low"] == candles[1]["close"] == "110.00"


def test_trend_analysis_respects_data_threshold():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    points = [{"session_id": str(i), "time": (start + timedelta(days=i * 7)).isoformat(), "value": str(100 + i * 3), "completeness": "100"} for i in range(8)]
    analysis = analyze_series(points)
    assert analysis["data_level"] == "FULL"
    assert analysis["point_count"] == 8
    assert analysis["max_drawdown_pct"] == "0.00"


def test_two_clearing_points_are_enough_for_a_full_trend():
    points = [
        {"session_id": "a", "time": "2026-07-01T09:00:00+00:00", "value": "100.00", "completeness": "100"},
        {"session_id": "b", "time": "2026-07-02T09:00:00+00:00", "value": "110.00", "completeness": "100"},
    ]
    analysis = analyze_series(points)
    assert analysis["data_level"] == "FULL"
    assert analysis["point_count"] == 2
    assert not any("8 个清算点" in item for item in analysis["limitations"])


def test_scenario_is_deterministic_and_labels_assumptions():
    rows = [
        item(id="stock", asset_type="STOCK", original_currency="CNY", value_cny=Decimal("100000")),
        item(id="cash", asset_type="CASH", original_currency="KRW", value_cny=Decimal("50000")),
    ]
    result = run_scenario(rows, {"net_worth_cny": "130000", "liabilities_cny": "20000"}, {"STOCK": Decimal("-20")}, {"KRW": Decimal("-10")}, Decimal("0"))
    assert result["scenario_net_worth_cny"] == "105000.00"
    assert result["change_cny"] == "-25000.00"
    assert "不是未来收益预测" in result["warning"]


def test_monthly_schedule_uses_local_timezone_and_real_month_end():
    schedule = ScheduleInput(frequency="MONTHLY", timezone="Asia/Seoul", hour=20, minute=0, day_of_month=31)
    first = next_schedule_time(schedule, after=datetime(2026, 1, 30, 12, tzinfo=timezone.utc))
    assert first == datetime(2026, 1, 31, 11, tzinfo=timezone.utc)
    february = next_schedule_time(schedule, after=datetime(2026, 1, 31, 12, tzinfo=timezone.utc))
    assert february == datetime(2026, 2, 28, 11, tzinfo=timezone.utc)
