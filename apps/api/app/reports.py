from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def json_default(value):
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(type(value).__name__)


def snapshot_payload(session) -> dict:
    return {
        "session_id": session.id,
        "clearing_time": session.confirmed_at.isoformat() if session.confirmed_at else None,
        "status": session.status,
        "revision_number": session.revision_number,
        "completeness": str(session.completeness),
        "totals": session.totals_json,
        "market_snapshot": session.fx_snapshot_json,
        "comparison": session.comparison_json,
        "items": [{
            "id": item.id, "name": item.name, "account_alias": item.account_alias, "asset_type": item.asset_type,
            "original_currency": item.original_currency, "original_value": str(item.original_value),
            "value_cny": str(item.value_cny) if item.value_cny is not None else None,
            "fx_rate_to_cny": str(item.fx_rate_to_cny) if item.fx_rate_to_cny is not None else None,
            "liquidity_level": item.liquidity_level, "is_liability": item.is_liability,
            "source": item.source, "status": item.status,
        } for item in session.items if item.status in {"CONFIRMED", "REVISED"}],
    }


def as_json_bytes(session) -> bytes:
    return json.dumps(snapshot_payload(session), ensure_ascii=False, indent=2, default=json_default).encode("utf-8")


def as_csv_bytes(session) -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=["id", "name", "account_alias", "asset_type", "currency", "original_value", "fx_rate_to_cny", "value_cny", "liquidity", "is_liability", "source"])
    writer.writeheader()
    for item in session.items:
        if item.status not in {"CONFIRMED", "REVISED"}:
            continue
        writer.writerow({
            "id": item.id, "name": item.name, "account_alias": item.account_alias or "", "asset_type": item.asset_type,
            "currency": item.original_currency, "original_value": item.original_value,
            "fx_rate_to_cny": item.fx_rate_to_cny, "value_cny": item.value_cny,
            "liquidity": item.liquidity_level, "is_liability": item.is_liability, "source": item.source,
        })
    return ("\ufeff" + text.getvalue()).encode("utf-8")


def as_pdf_bytes(session) -> bytes:
    buffer = io.BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm, title="小白算盘清算报告")
    styles = getSampleStyleSheet()
    title = ParagraphStyle("CNTitle", parent=styles["Title"], fontName="STSong-Light", fontSize=20, leading=26, textColor=colors.HexColor("#3C176E"), spaceAfter=12)
    heading = ParagraphStyle("CNHeading", parent=styles["Heading2"], fontName="STSong-Light", fontSize=13, leading=18, textColor=colors.HexColor("#5D2D91"), spaceBefore=12, spaceAfter=7)
    body = ParagraphStyle("CNBody", parent=styles["BodyText"], fontName="STSong-Light", fontSize=9.5, leading=15, alignment=TA_LEFT)
    story = [Paragraph("小白算盘 · 个人资产清算报告", title), Paragraph(f"清算时间：{session.confirmed_at.isoformat() if session.confirmed_at else '-'}　修订版本：{session.revision_number}", body), Spacer(1, 8)]
    totals = session.totals_json
    summary_data = [["指标", "人民币金额"], ["总资产", totals.get("assets_cny", "0.00")], ["总负债", totals.get("liabilities_cny", "0.00")], ["净资产", totals.get("net_worth_cny", "0.00")], ["可立即使用资金", totals.get("liquid_assets_cny", "0.00")], ["受限资产", totals.get("restricted_assets_cny", "0.00")]]
    table = Table(summary_data, colWidths=[70 * mm, 70 * mm])
    table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEE7F8")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3C176E")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8CCE8")), ("ALIGN", (1, 1), (1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    story += [Paragraph("资产概览", heading), table, Paragraph("资产明细", heading)]
    item_data = [["名称", "类型", "原币", "原币金额", "人民币价值"]]
    for item in session.items:
        if item.status in {"CONFIRMED", "REVISED"}:
            item_data.append([item.name, item.asset_type, item.original_currency, str(item.original_value), str(item.value_cny or "")])
    item_table = Table(item_data, repeatRows=1, colWidths=[44 * mm, 27 * mm, 18 * mm, 34 * mm, 34 * mm])
    item_table.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "STSong-Light"), ("FONTSIZE", (0, 0), (-1, -1), 8), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEE7F8")), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#DDD4E9")), ("ALIGN", (2, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [item_table, Paragraph("说明与限制", heading), Paragraph("本报告基于你已经确认的清算时点数据。资产 K 线展示资产规模变化，与证券投资收益曲线不是同一个指标；没有记录原因的变化，也不会被自动归为消费或收益。", body)]
    doc.build(story)
    return buffer.getvalue()
