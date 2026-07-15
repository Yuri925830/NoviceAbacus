"""Live smoke check for configured providers without printing credentials or financial values."""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pyotp
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings
from app.database import SessionLocal
from app.main import app
from app.models import User
from app.security import decrypt_secret


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        user = db.scalar(select(User).order_by(User.created_at))
        if not user:
            raise RuntimeError("owner is missing")
        totp_code = pyotp.TOTP(decrypt_secret(user.totp_secret_encrypted)).now() if user.totp_enabled and user.totp_secret_encrypted else None

    with TestClient(app) as client:
        login = client.post("/auth/login", json={
            "identifier": settings.owner_id or user.email,
            "password": settings.owner_password,
            "totp_code": totp_code,
            "device_name": "integration-smoke",
        })
        login.raise_for_status()

        gold = client.get("/gold/spot")
        if not gold.is_success:
            print("gold_spot_error", gold.status_code, gold.json().get("detail"))
        gold.raise_for_status()
        gold_payload = gold.json()
        print("gold_spot", gold_payload["status"], gold_payload["symbol"], bool(gold_payload.get("quoted_at")))

        assistant = client.post("/assistant", json={
            "message": "请用专业顾问标准，分析当前财务数据里最需要先核对的一件事，并说明关键数字、取舍和复盘触发条件。",
            "provider": "openai",
            "depth": "complex",
        })
        assistant.raise_for_status()
        answer = assistant.json()
        result = answer["result"]
        print("assistant", answer["provider"], bool(result.get("executive_summary")), len(result.get("key_numbers", [])), len(result.get("recommendations", [])))

        trend = client.get("/trend?metric=net_worth_cny&granularity=clearing")
        trend.raise_for_status()
        if len(trend.json().get("points", [])) >= 2:
            insight = client.post("/trend/insight", json={"metric": "net_worth_cny", "provider": "openai", "depth": "complex"})
            insight.raise_for_status()
            print("trend_insight", insight.json()["provider"], bool(insight.json()["result"].get("executive_summary")))
        else:
            print("trend_insight", "SKIPPED_NEEDS_TWO_POINTS")

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer)
        pdf.drawString(72, 760, "Bank wealth product: displayed historical annualized return 3.8%.")
        pdf.drawString(72, 740, "Principal is not guaranteed. Closed for 180 days. Early redemption is not allowed.")
        pdf.drawString(72, 720, "Risk rating R2. Management fee 0.30% per year. Underlying assets are bonds and deposits.")
        pdf.save()
        xray = client.post("/xray", data={"intended_amount_cny": "50000"}, files={"file": ("integration-product.pdf", buffer.getvalue(), "application/pdf")})
        xray.raise_for_status()
        xray_payload = xray.json()
        print("product_xray", xray_payload["provider"], bool(xray_payload["extraction"].get("plain_language_summary")), xray_payload["original_file_stored"])
        client.delete(f"/xray/{xray_payload['id']}").raise_for_status()


if __name__ == "__main__":
    main()
