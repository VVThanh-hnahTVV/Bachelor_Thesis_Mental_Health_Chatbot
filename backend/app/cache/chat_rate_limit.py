from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger("uvicorn.error")

_VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class RateLimitStatus(NamedTuple):
    allowed: bool
    used: int
    limit: int
    remaining: int
    resets_at: datetime


def _now_vn() -> datetime:
    return datetime.now(_VN_TZ)


def _today_key_vn(now: datetime | None = None) -> str:
    return (now or _now_vn()).strftime("%Y-%m-%d")


def _next_midnight_vn(now: datetime | None = None) -> datetime:
    now = now or _now_vn()
    tomorrow = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return tomorrow


def _seconds_until_midnight_vn(now: datetime | None = None) -> int:
    now = now or _now_vn()
    return max(1, int((_next_midnight_vn(now) - now).total_seconds()))


def _user_key(user_id: str, day: str) -> str:
    return f"chat:daily:user:{user_id}:{day}"


def _ip_key(ip: str, day: str) -> str:
    return f"chat:daily:ip:{ip}:{day}"


def _status_when_skipped(limit: int) -> RateLimitStatus:
    return RateLimitStatus(
        allowed=True,
        used=0,
        limit=limit,
        remaining=limit,
        resets_at=_next_midnight_vn(),
    )


async def check_and_consume(
    redis: aioredis.Redis | None,
    *,
    user_id: str | None,
    ip: str | None,
) -> RateLimitStatus:
    """Atomically increment the applicable daily counters (user + ip).

    Counters reset at midnight Vietnam time via per-key TTL. If any applicable
    counter would exceed its limit, all increments performed in this call are
    rolled back so a rejected request does not consume a slot.

    Fail-open: when Redis is unavailable or errors, the request is allowed.
    """
    s = get_settings()
    user_limit = s.user_daily_chat_limit
    ip_limit = s.ip_daily_chat_limit
    fallback_limit = user_limit if user_id else ip_limit

    if redis is None:
        return _status_when_skipped(fallback_limit)

    now = _now_vn()
    day = _today_key_vn(now)
    ttl = _seconds_until_midnight_vn(now)
    resets_at = _next_midnight_vn(now)

    # (redis_key, limit) pairs for every dimension that applies to this request.
    dimensions: list[tuple[str, int]] = []
    if user_id:
        dimensions.append((_user_key(user_id, day), user_limit))
    if ip:
        dimensions.append((_ip_key(ip, day), ip_limit))

    if not dimensions:
        return _status_when_skipped(fallback_limit)

    try:
        pipe = redis.pipeline()
        for key, _ in dimensions:
            pipe.incr(key)
        for key, _ in dimensions:
            pipe.ttl(key)
        results = await pipe.execute()

        n = len(dimensions)
        counts = [int(v) for v in results[:n]]
        ttls = [int(v) for v in results[n:]]

        # Ensure every key expires at the next VN midnight.
        expire_pipe = redis.pipeline()
        needs_expire = False
        for (key, _), key_ttl in zip(dimensions, ttls):
            if key_ttl == -1:
                expire_pipe.expire(key, ttl)
                needs_expire = True
        if needs_expire:
            await expire_pipe.execute()

        # Report the most constrained dimension (highest used/limit ratio).
        used, limit = max(
            ((count, lim) for count, (_, lim) in zip(counts, dimensions)),
            key=lambda cl: cl[0] / cl[1] if cl[1] else 0,
        )
        exceeded = any(
            count > lim for count, (_, lim) in zip(counts, dimensions)
        )

        if exceeded:
            rollback = redis.pipeline()
            for key, _ in dimensions:
                rollback.decr(key)
            await rollback.execute()
            return RateLimitStatus(
                allowed=False,
                used=min(used, limit),
                limit=limit,
                remaining=0,
                resets_at=resets_at,
            )

        return RateLimitStatus(
            allowed=True,
            used=used,
            limit=limit,
            remaining=max(0, limit - used),
            resets_at=resets_at,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat rate limit check failed (fail-open): %s", exc)
        return _status_when_skipped(fallback_limit)


async def peek_quota(
    redis: aioredis.Redis | None,
    *,
    user_id: str | None,
    ip: str | None,
) -> RateLimitStatus:
    """Read current usage without consuming a slot (for quota display)."""
    s = get_settings()
    user_limit = s.user_daily_chat_limit
    ip_limit = s.ip_daily_chat_limit
    fallback_limit = user_limit if user_id else ip_limit

    if redis is None:
        return _status_when_skipped(fallback_limit)

    now = _now_vn()
    day = _today_key_vn(now)
    resets_at = _next_midnight_vn(now)

    dimensions: list[tuple[str, int]] = []
    if user_id:
        dimensions.append((_user_key(user_id, day), user_limit))
    if ip:
        dimensions.append((_ip_key(ip, day), ip_limit))

    if not dimensions:
        return _status_when_skipped(fallback_limit)

    try:
        pipe = redis.pipeline()
        for key, _ in dimensions:
            pipe.get(key)
        raw = await pipe.execute()
        counts = [int(v) if v is not None else 0 for v in raw]

        used, limit = max(
            ((count, lim) for count, (_, lim) in zip(counts, dimensions)),
            key=lambda cl: cl[0] / cl[1] if cl[1] else 0,
        )
        return RateLimitStatus(
            allowed=used < limit,
            used=min(used, limit),
            limit=limit,
            remaining=max(0, limit - used),
            resets_at=resets_at,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat quota peek failed (fail-open): %s", exc)
        return _status_when_skipped(fallback_limit)
