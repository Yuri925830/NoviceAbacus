from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import pyotp
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from .config import get_settings


settings = get_settings()
password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(password: str) -> str:
    if len(password) < 6:
        raise ValueError("密码至少需要 6 个字符")
    return password_hasher.hash(password)


def verify_password(password: str, encoded: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except VerifyMismatchError:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    if settings.data_encryption_key:
        raw = settings.data_encryption_key.encode("utf-8")
    else:
        raw = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_signing_key.encode("utf-8")).digest())
    return Fernet(raw)


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def create_access_token(user_id: str, session_id: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "sid": session_id, "role": "OWNER", "iat": now, "exp": now + timedelta(minutes=15)},
        settings.jwt_signing_key,
        algorithm="HS256",
    )


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_signing_key, algorithms=["HS256"])


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_totp_secret() -> str:
    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code.replace(" ", ""), valid_window=1)


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="小白算盘")


def new_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(3).upper()}-{secrets.token_hex(3).upper()}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hash_token(code.replace("-", "").upper())


def verify_recovery_code(code: str, hashes: list[str]) -> tuple[bool, list[str]]:
    target = hash_recovery_code(code)
    if target not in hashes:
        return False, hashes
    return True, [item for item in hashes if item != target]


def ip_digest(ip: str) -> str:
    return hashlib.sha256((ip + settings.jwt_signing_key[:16]).encode("utf-8")).hexdigest()
