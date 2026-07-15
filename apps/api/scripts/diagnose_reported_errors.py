"""Reproduce the two authenticated Agent requests reported by the owner.

The script prints only endpoint status and a short non-secret response excerpt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from sqlalchemy import desc, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal
from app.models import RefreshSession, User
from app.security import create_access_token


def main() -> None:
    print("diagnostic_start", flush=True)
    with SessionLocal() as db:
        print("database_open", flush=True)
        user = db.scalar(select(User).order_by(User.created_at))
        if not user:
            raise RuntimeError("owner is missing")
        session = db.scalar(
            select(RefreshSession)
            .where(
                RefreshSession.user_id == user.id,
                RefreshSession.revoked_at.is_(None),
            )
            .order_by(desc(RefreshSession.last_seen_at))
        )
        if not session:
            raise RuntimeError("active trusted device is missing")
        token = create_access_token(user.id, session.id)
        print("token_ready", flush=True)

    with httpx.Client(
        base_url="http://127.0.0.1:8000",
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    ) as client:
        requests = [
            (
                "trend",
                "/trend/insight",
                {
                    "metric": "net_worth_cny",
                    "provider": "openai",
                    "depth": "complex",
                },
            ),
            (
                "allocation",
                "/intelligence/allocate",
                {
                    "monthly_income_cny": "10000",
                    "monthly_fixed_expenses_cny": "2000",
                    "monthly_safety_buffer_cny": "0",
                    "strategy": "BALANCED",
                    "provider": "openai",
                    "depth": "complex",
                },
            ),
        ]
        for label, endpoint, body in requests:
            print(label, "request_start", flush=True)
            response = client.post(endpoint, json=body)
            print(label, response.status_code, response.text[:1200], flush=True)


if __name__ == "__main__":
    main()
