from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from passlib.context import CryptContext

from config import get_settings

# Use PBKDF2 as default to avoid bcrypt 72-byte limitation for long/unicode passwords.
# Keep bcrypt in the context for backward compatibility with existing hashes.
pwd_context = CryptContext(schemes=["pbkdf2_sha256", "bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def _build_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    settings = get_settings()
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires = timedelta(minutes=settings.access_token_expire_minutes)
    return _build_token(subject=subject, expires_delta=expires, token_type="access")


def create_refresh_token(subject: str) -> str:
    settings = get_settings()
    expires = timedelta(days=settings.refresh_token_expire_days)
    return _build_token(subject=subject, expires_delta=expires, token_type="refresh")
