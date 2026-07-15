from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, getcontext
from math import sqrt
from typing import Any, Iterable


getcontext().prec = 40
ZERO = Decimal("0")
MONEY = Decimal("0.01")
INVESTMENT_TYPES = {"STOCK", "FUND", "GOLD", "PHYSICAL_GOLD", "BOND", "CRYPTO"}


def D(value: Any) -> Decimal:
    if value is None or value == "":
        return ZERO
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return str(value.quantize(MONEY, rounding=ROUND_HALF_UP))


def raw_item_value(item: Any) -> Decimal:
    # Current market value already includes unrealized P/L. Never add P/L twice.
    if item.asset_type in {"STOCK", "FUND", "BOND"} and item.current_market_value is not None:
        return D(item.current_market_value)
    # Fixed-deposit future interest is not an owned asset until credited.
    return D(item.original_value)


def calculate_snapshot(items: Iterable[Any], rates_to_cny: dict[str, Decimal]) -> tuple[dict, list[dict]]:
    totals = defaultdict(lambda: ZERO)
    by_type = defaultdict(lambda: ZERO)
    by_currency = defaultdict(lambda: ZERO)
    calculated: list[dict] = []

    for item in items:
        if item.status not in {"CONFIRMED", "REVISED"}:
            continue
        currency = item.original_currency.upper()
        if currency not in rates_to_cny:
            raise ValueError(f"缺少 {currency}/CNY 汇率")
        original = raw_item_value(item)
        rate = D(rates_to_cny[currency])
        value_cny = (original * rate).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        if value_cny < ZERO:
            raise ValueError(f"{item.name} 金额不可为负；负债请使用负债标记和正余额")

        if item.is_liability:
            totals["liabilities"] += value_cny
        else:
            totals["assets"] += value_cny
            by_type[item.asset_type] += value_cny
            by_currency[currency] += value_cny
            if item.liquidity_level == "HIGH":
                totals["liquid_assets"] += value_cny
            if item.liquidity_level == "RESTRICTED":
                totals["restricted_assets"] += value_cny
            if item.asset_type in INVESTMENT_TYPES:
                totals["investment_assets"] += value_cny

        calculated.append({
            "id": item.id,
            "value_cny": value_cny,
            "fx_rate_to_cny": rate,
            "original_value_used": original,
        })

    totals["net_worth"] = totals["assets"] - totals["liabilities"]
    denominator = totals["assets"] or Decimal("1")
    result = {
        "assets_cny": money(totals["assets"]),
        "liabilities_cny": money(totals["liabilities"]),
        "net_worth_cny": money(totals["net_worth"]),
        "liquid_assets_cny": money(totals["liquid_assets"]),
        "restricted_assets_cny": money(totals["restricted_assets"]),
        "investment_assets_cny": money(totals["investment_assets"]),
        "by_type": {key: money(value) for key, value in sorted(by_type.items())},
        "by_currency": {key: money(value) for key, value in sorted(by_currency.items())},
        "type_percentages": {key: money(value * Decimal("100") / denominator) for key, value in sorted(by_type.items())},
        "currency_percentages": {key: money(value * Decimal("100") / denominator) for key, value in sorted(by_currency.items())},
    }
    return result, calculated


def compare_totals(current: dict, previous: dict | None) -> dict:
    if not previous:
        return {"is_baseline": True, "net_worth_change_cny": "0.00", "assets_change_cny": "0.00"}
    net_change = D(current.get("net_worth_cny")) - D(previous.get("net_worth_cny"))
    asset_change = D(current.get("assets_cny")) - D(previous.get("assets_cny"))
    return {
        "is_baseline": False,
        "net_worth_change_cny": money(net_change),
        "assets_change_cny": money(asset_change),
        "unexplained_change_cny": money(net_change),
        "explanation_limit": "V1.1 不含流水；未解释变化不能自动归为消费或投资收益。",
    }


def _bucket_key(moment: datetime, granularity: str) -> str:
    local = moment
    if granularity == "day":
        return local.strftime("%Y-%m-%d")
    if granularity == "week":
        year, week, _ = local.isocalendar()
        return f"{year}-W{week:02d}"
    if granularity == "month":
        return local.strftime("%Y-%m")
    if granularity == "quarter":
        return f"{local.year}-Q{((local.month - 1) // 3) + 1}"
    if granularity == "year":
        return str(local.year)
    return local.isoformat()


def build_series(sessions: Iterable[Any], metric: str = "net_worth_cny") -> list[dict]:
    points = []
    for session in sorted(sessions, key=lambda item: item.confirmed_at or item.started_at):
        if session.status not in {"CONFIRMED", "REVISED"} or not session.confirmed_at:
            continue
        if metric not in session.totals_json:
            continue
        points.append({
            "session_id": session.id,
            "time": session.confirmed_at.isoformat(),
            "value": money(D(session.totals_json[metric])),
            "completeness": str(session.completeness),
            "low_completeness": D(session.completeness) < Decimal("80"),
        })
    return points


def aggregate_ohlc(points: list[dict], granularity: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for point in points:
        groups[_bucket_key(datetime.fromisoformat(point["time"]), granularity)].append(point)
    candles = []
    for bucket, bucket_points in sorted(groups.items()):
        values = [D(point["value"]) for point in bucket_points]
        candles.append({
            "bucket": bucket,
            "open": money(values[0]),
            "high": money(max(values)),
            "low": money(min(values)),
            "close": money(values[-1]),
            "change": money(values[-1] - values[0]),
            "sample_count": len(values),
            "single_point": len(values) == 1,
            "session_ids": [point["session_id"] for point in bucket_points],
        })
    return candles


def analyze_series(points: list[dict]) -> dict:
    values = [D(point["value"]) for point in points]
    count = len(values)
    if not values:
        return {"data_level": "EMPTY", "point_count": 0, "limitations": ["还没有已确认清算点。"]}
    peak = values[0]
    max_drawdown = ZERO
    pct_changes: list[Decimal] = []
    rising = falling = max_rising = max_falling = 0
    for previous, current in zip(values, values[1:]):
        peak = max(peak, current)
        if peak > ZERO:
            max_drawdown = max(max_drawdown, (peak - current) / peak)
        if previous != ZERO:
            pct_changes.append((current - previous) / previous)
        if current > previous:
            rising += 1
            falling = 0
        elif current < previous:
            falling += 1
            rising = 0
        else:
            rising = falling = 0
        max_rising = max(max_rising, rising)
        max_falling = max(max_falling, falling)
    if count >= 2:
        xs = [Decimal(index) for index in range(count)]
        x_bar = sum(xs) / D(count)
        y_bar = sum(values) / D(count)
        denominator = sum((x - x_bar) ** 2 for x in xs)
        slope = sum((x - x_bar) * (y - y_bar) for x, y in zip(xs, values)) / denominator if denominator else ZERO
    else:
        slope = ZERO
    volatility = ZERO
    if len(pct_changes) >= 2:
        mean = sum(pct_changes) / D(len(pct_changes))
        variance = sum((item - mean) ** 2 for item in pct_changes) / D(len(pct_changes) - 1)
        volatility = D(sqrt(float(variance)))
    first_time = datetime.fromisoformat(points[0]["time"])
    last_time = datetime.fromisoformat(points[-1]["time"])
    span_days = max((last_time - first_time).days, 0)
    level = "BASELINE" if count == 1 else "FULL"
    limitations = []
    if count == 1:
        limitations.append("这是第一枚坐标；再完成一次清算，就能一起看看变化方向了。")
    limitations.append("这条线记录的是每次清算时的资产规模，和证券账户里的投资收益率不是一回事。")
    return {
        "data_level": level,
        "point_count": count,
        "span_days": span_days,
        "total_change_cny": money(values[-1] - values[0]),
        "change_rate_pct": money((values[-1] - values[0]) / values[0] * D(100)) if values[0] else None,
        "slope_per_clearing_cny": money(slope),
        "max_drawdown_pct": money(max_drawdown * D(100)),
        "volatility_pct": money(volatility * D(100)) if pct_changes else None,
        "max_consecutive_rises": max_rising,
        "max_consecutive_falls": max_falling,
        "moving_average_3": money(sum(values[-3:]) / D(min(3, count))),
        "limitations": limitations,
    }


def run_scenario(items: Iterable[Any], totals: dict, asset_type_shocks: dict[str, Decimal], currency_shocks: dict[str, Decimal], liability_change_pct: Decimal) -> dict:
    changed_assets = ZERO
    contributions: list[dict] = []
    for item in items:
        if item.status not in {"CONFIRMED", "REVISED"} or item.is_liability:
            continue
        base = D(item.value_cny)
        asset_shock = D(asset_type_shocks.get(item.asset_type, ZERO)) / D(100)
        fx_shock = D(currency_shocks.get(item.original_currency, ZERO)) / D(100)
        shocked = base * (D(1) + asset_shock) * (D(1) + fx_shock)
        changed_assets += shocked
        if asset_shock or fx_shock:
            contributions.append({"item_id": item.id, "asset_type": item.asset_type, "currency": item.original_currency, "change_cny": money(shocked - base)})
    liabilities = D(totals.get("liabilities_cny")) * (D(1) + D(liability_change_pct) / D(100))
    net = changed_assets - liabilities
    base_net = D(totals.get("net_worth_cny"))
    return {
        "base_net_worth_cny": money(base_net),
        "scenario_net_worth_cny": money(net),
        "change_cny": money(net - base_net),
        "change_pct": money((net - base_net) / base_net * D(100)) if base_net else None,
        "contributions": contributions,
        "assumptions": {"asset_type_shocks_pct": {k: str(v) for k, v in asset_type_shocks.items()}, "currency_shocks_pct": {k: str(v) for k, v in currency_shocks.items()}, "liability_change_pct": str(liability_change_pct)},
        "warning": "这是带假设的压力测试，不是未来收益预测。",
    }
