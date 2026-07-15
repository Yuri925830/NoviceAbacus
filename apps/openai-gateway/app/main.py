from __future__ import annotations

import hmac
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/app")).resolve()
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(title="小白算盘 OpenAI 海外微网关", docs_url=None, redoc_url=None)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SHARED_SECRET = os.getenv("GATEWAY_SHARED_SECRET", "")
ORDINARY_MODEL = os.getenv("OPENAI_ORDINARY_MODEL", "gpt-5.6-terra")
COMPLEX_MODEL = os.getenv("OPENAI_COMPLEX_MODEL", "gpt-5.6-sol")
LAST_UPSTREAM: dict[str, Any] = {
    "available": None,
    "error_type": None,
    "error_code": None,
    "checked_at": None,
}


class AnalyzeRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    context: dict[str, Any]
    depth: str = "ordinary"


OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "executive_summary": {"type": "string"},
        "confirmed_facts": {"type": "array", "items": {"type": "string"}},
        "key_numbers": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "value": {"type": "string"},
                    "meaning": {"type": "string"},
                },
                "required": ["label", "value", "meaning"],
            },
        },
        "analysis": {"type": "array", "items": {"type": "string"}},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "expected_impact": {"type": "string"},
                    "risk": {"type": "string"},
                    "review_trigger": {"type": "string"},
                },
                "required": ["priority", "action", "reason", "expected_impact", "risk", "review_trigger"],
            },
        },
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
        "requires_owner_confirmation": {"type": "boolean"},
    },
    "required": [
        "executive_summary",
        "confirmed_facts",
        "key_numbers",
        "analysis",
        "recommendations",
        "alternatives",
        "assumptions",
        "limitations",
        "follow_up_questions",
        "requires_owner_confirmation",
    ],
}


SYSTEM = """你是小白算盘的“怀特理财顾问”，是一位严谨、温暖、善于把复杂问题讲清楚的资深个人财务顾问。先直接回答问题并给出核心结论，再展开依据。严格区分已确认事实、程序计算、合理推断和未知信息；程序算出的金额与指标以输入 JSON 为准。检查现金流、目标期限、建议金额和多目标资金冲突是否自洽。不确定归因时至少说明两种合理解释，不把资产规模变化称作投资收益或消费。建议必须给出优先级、理由、预期影响、风险和复盘触发条件，并提供可选路径与取舍。缺少信息时仍先给出最佳努力的回答，最后最多提出三个真正会改变判断的追问。语气自然亲切，但不要空泛、说教或机械重复免责声明。可以回答任何理财知识问题，个人数据为空不得拒绝。不得承诺收益、不得给出具体证券的确定买卖指令，不得索取姓名、账号、密码、API Key 或验证码。"""


def require_auth(authorization: str | None) -> None:
    if not SHARED_SECRET:
        raise HTTPException(status_code=503, detail="gateway not configured")
    supplied = authorization[7:] if authorization and authorization.lower().startswith("bearer ") else ""
    if not hmac.compare_digest(supplied, SHARED_SECRET):
        raise HTTPException(status_code=401, detail="unauthorized")


def extract_output_text(payload: dict) -> str:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text":
                return content.get("text", "")
    raise ValueError("missing output_text")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "openai_configured": bool(OPENAI_API_KEY),
        "stores_financial_data": False,
        "last_upstream": LAST_UPSTREAM,
    }


@app.post("/v1/analyze")
async def analyze(body: AnalyzeRequest, authorization: str | None = Header(default=None)) -> dict:
    require_auth(authorization)
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI key not configured")

    encoded_context = json.dumps(body.context, ensure_ascii=False, separators=(",", ":"))
    if len(encoded_context.encode("utf-8")) > 256_000:
        raise HTTPException(status_code=413, detail="minimized context exceeds gateway limit")

    model = COMPLEX_MODEL if body.depth == "complex" else ORDINARY_MODEL
    payload = {
        "model": model,
        "instructions": SYSTEM,
        "input": (
            "经过程序校验的脱敏财务上下文 JSON：\n"
            + encoded_context
            + "\n\n用户的问题："
            + body.message
        ),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "financial_analysis",
                "strict": True,
                "schema": OUTPUT_SCHEMA,
            }
        },
        "reasoning": {"effort": "medium" if body.depth == "complex" else "low"},
        "max_output_tokens": 10000 if body.depth == "complex" else 6000,
        "store": False,
    }
    try:
        async with httpx.AsyncClient(timeout=80) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        LAST_UPSTREAM.update({
            "available": False,
            "error_type": "timeout",
            "error_code": "upstream_timeout",
            "checked_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=504, detail="OpenAI upstream timed out") from exc
    except httpx.RequestError as exc:
        LAST_UPSTREAM.update({
            "available": False,
            "error_type": "network_error",
            "error_code": type(exc).__name__,
            "checked_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail="OpenAI upstream connection failed") from exc

    if response.status_code >= 400:
        request_id = response.headers.get("x-request-id", "")
        try:
            upstream_error = response.json().get("error", {})
        except ValueError:
            upstream_error = {}
        error_type = upstream_error.get("type", "unknown")
        error_code = upstream_error.get("code", "unknown")
        LAST_UPSTREAM.update(
            {
                "available": False,
                "error_type": error_type,
                "error_code": error_code,
                "checked_at": datetime.now(UTC).isoformat(),
            }
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "OpenAI request failed "
                f"({response.status_code}, type={error_type}, code={error_code}, request_id={request_id})"
            ),
        )

    data = response.json()
    if data.get("status") != "completed":
        reason = (data.get("incomplete_details") or {}).get("reason") or data.get("status") or "unknown"
        LAST_UPSTREAM.update({
            "available": False,
            "error_type": "incomplete_response",
            "error_code": str(reason),
            "checked_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail=f"OpenAI response incomplete ({reason})")
    try:
        result = json.loads(extract_output_text(data))
    except (ValueError, json.JSONDecodeError) as exc:
        LAST_UPSTREAM.update({
            "available": False,
            "error_type": "invalid_structured_output",
            "error_code": "missing_or_invalid_output_text",
            "checked_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail="OpenAI returned invalid structured output") from exc

    LAST_UPSTREAM.update(
        {
            "available": True,
            "error_type": None,
            "error_code": None,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    )

    return {
        "model": model,
        "request_id": data.get("id"),
        "result": result,
        "store": False,
    }
