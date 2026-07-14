"""Idle-session checkpoint — fold quiet sessions into episodic memory.

Event-driven finalization (new-session start, handoff leave) misses users who
chat once and never come back: their session would never reach long-term
memory. This sweeper periodically finds conversations with no new messages
for ``session_idle_finalize_minutes`` and finalizes them.

The session itself stays open: short-term context (rolling summary + recent
turns) is untouched, so a user resuming hours later continues seamlessly.
``finalize_session_memory`` is idempotent — if new turns arrive after the
checkpoint, the next boundary simply overwrites the episodic record with a
fuller summary.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_LOCK_KEY = "helios:idle-finalize:lock"


async def _acquire_sweep_lock(redis: Any, ttl_seconds: int) -> bool:
    """One sweep per interval across replicas (best-effort ``SET NX EX``)."""
    if redis is None:
        return True
    try:
        return bool(await redis.set(_LOCK_KEY, "1", nx=True, ex=ttl_seconds))
    except Exception as exc:  # noqa: BLE001 — a Redis blip must not stop sweeps
        logger.warning("idle-finalize lock unavailable, sweeping anyway: %s", exc)
        return True


async def sweep_idle_sessions(db: Any, redis: Any) -> int:
    """Finalize sessions idle past the configured window. Returns #finalized."""
    from app.conversation.episodic_memory import finalize_session_memory
    from app.db.repository import (
        list_idle_conversations_for_memory,
        mark_conversation_idle_checked,
    )

    settings = get_settings()
    idle_before = datetime.now(UTC) - timedelta(
        minutes=settings.session_idle_finalize_minutes
    )
    candidates = await list_idle_conversations_for_memory(db, idle_before=idle_before)
    finalized = 0
    for conv in candidates:
        session_id = str(conv.get("session_id") or "")
        cid = conv.get("_id")
        if not session_id or cid is None:
            continue
        try:
            if await finalize_session_memory(
                db, redis, session_id=session_id, reason="idle_timeout"
            ):
                finalized += 1
        except Exception as exc:  # noqa: BLE001 — leave unmarked, retried next sweep
            logger.warning("idle finalize failed for session=%s: %s", session_id, exc)
            continue
        # Mark also when finalize declined (anonymous, too short, nothing new)
        # so unchanged conversations are not rescanned every cycle; a new
        # message moves updated_at past the mark and re-qualifies the session.
        await mark_conversation_idle_checked(db, cid)
    if candidates:
        logger.info(
            "idle-finalize sweep: candidates=%d finalized=%d",
            len(candidates),
            finalized,
        )
    return finalized


def start_idle_finalize_loop(db: Any, redis: Any) -> asyncio.Task | None:
    """Spawn the background sweep loop; None when the feature is disabled."""
    settings = get_settings()
    if not settings.enable_episodic_memory or settings.session_idle_finalize_minutes <= 0:
        return None
    interval = settings.session_idle_sweep_interval_seconds
    lock_ttl = max(30, interval - 10)

    async def _loop() -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                if await _acquire_sweep_lock(redis, ttl_seconds=lock_ttl):
                    await sweep_idle_sessions(db, redis)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("idle-finalize sweep failed (non-critical): %s", exc)

    logger.info(
        "idle-finalize loop started: idle=%dmin interval=%ds",
        settings.session_idle_finalize_minutes,
        interval,
    )
    return asyncio.create_task(_loop())
