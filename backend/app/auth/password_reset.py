from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta


def generate_reset_token() -> tuple[str, str]:
    """Return (plain_token, token_hash) for storage."""
    plain = secrets.token_urlsafe(32)
    token_hash = hash_token(plain)
    return plain, token_hash


def hash_token(plain_token: str) -> str:
    return hashlib.sha256(plain_token.encode("utf-8")).hexdigest()


def reset_expires_at(*, minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes)
