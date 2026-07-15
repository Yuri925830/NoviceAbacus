from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PROJECT_ROOT / ".env")


def main() -> None:
    secret = os.environ["GATEWAY_SHARED_SECRET"]
    response = httpx.post(
        "http://127.0.0.1:8100/v1/analyze",
        headers={"Authorization": f"Bearer {secret}"},
        json={
            "message": "请用一句话向理财小白解释：为什么净资产等于总资产减去总负债？",
            "context": {
                "currency": "CNY",
                "confirmed_totals": {
                    "assets": "120000.00",
                    "liabilities": "20000.00",
                    "net_worth": "100000.00",
                },
                "data_scope": "synthetic connectivity check; no personal data",
            },
            "depth": "ordinary",
        },
        timeout=180,
    )
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "gateway request failed")
        except ValueError:
            detail = "gateway returned a non-JSON error"
        print(
            json.dumps(
                {
                    "ok": False,
                    "gateway_status": response.status_code,
                    "detail": detail,
                },
                ensure_ascii=False,
            )
        )
        raise SystemExit(1)
    payload = response.json()
    result = payload.get("result", {})
    print(
        json.dumps(
            {
                "ok": True,
                "model": payload.get("model"),
                "request_id_present": bool(payload.get("request_id")),
                "store": payload.get("store"),
                "structured": all(
                    field in result
                    for field in (
                        "confirmed_facts",
                        "analysis",
                        "recommendations",
                        "limitations",
                        "requires_owner_confirmation",
                    )
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
