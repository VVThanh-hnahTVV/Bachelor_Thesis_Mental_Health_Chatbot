import pytest

from app.cache.session_memory import (
    get_personalization_context,
    set_personalization_context,
)


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.expire_calls: list[tuple[str, int]] = []

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))


@pytest.mark.asyncio
async def test_personalization_context_roundtrip():
    redis = FakeRedis()
    payload = {"mood_trend": "stable", "user_display_name": "Viet"}
    await set_personalization_context(redis, "session-12345678", payload)
    out = await get_personalization_context(redis, "session-12345678")
    assert out == payload
