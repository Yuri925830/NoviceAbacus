from __future__ import annotations

import csv
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", "/app")).resolve()
load_dotenv(PROJECT_ROOT / ".env.local")
load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    app_env: str = "development"
    app_base_url: str = "http://localhost:3000"
    database_url: str = "sqlite:///./data/xiaobai.db"
    jwt_signing_key: str = "development-only-change-me-please-32-chars"
    data_encryption_key: str = ""
    owner_id: str = ""
    owner_email: str = ""
    owner_password: str = ""
    owner_phone: str = ""

    aliyun_credentials_csv: str = ""
    dashscope_api_key: str = ""
    dashscope_base_url: str = ""
    aliyun_workspace_id: str = ""
    qwen_ocr_model: str = "qwen3.5-ocr"
    qwen_vision_model: str = "qwen3-vl-plus"
    qwen_chat_model: str = "qwen3.7-plus"
    qwen_complex_model: str = "qwen3.7-max"

    openai_gateway_url: str = ""
    gateway_shared_secret: str = ""
    openai_ordinary_model: str = "gpt-5.6-terra"
    openai_complex_model: str = "gpt-5.6-sol"

    fx_provider_url: str = "https://api.frankfurter.app"
    fx_max_age_hours: int = 96

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    alert_email: str = ""

    model_daily_request_limit: int = 120
    model_daily_cost_limit: float = 20.0
    max_upload_mb: int = 20
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])

    @property
    def data_dir(self) -> Path:
        path = PROJECT_ROOT / "data"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def aliyun_credentials(self) -> tuple[str, str, str]:
        key = self.dashscope_api_key
        base_url = self.dashscope_base_url
        workspace_id = self.aliyun_workspace_id
        csv_path = Path(self.aliyun_credentials_csv) if self.aliyun_credentials_csv else None
        if csv_path and csv_path.exists():
            with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                headers = reader.fieldnames or []
                if len(headers) >= 2:
                    value_column = headers[1]
                    values = {row.get("id", "").strip(): row.get(value_column, "").strip() for row in reader}
                    key = key or values.get("apiKey", "")
                    base_url = base_url or values.get("openAiCompatible", "") or values.get("apiHost", "")
                    workspace_id = workspace_id or values.get("workspaceId", "")
        if base_url:
            base_url = base_url.rstrip("/")
            if not base_url.endswith("/v1") and "compatible-mode" in base_url:
                base_url += "/v1"
        elif workspace_id:
            base_url = f"https://{workspace_id}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        return key, base_url, workspace_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
