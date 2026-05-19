from bson import ObjectId
from fastapi import HTTPException
import pytest

from app.auth.dependencies import ensure_session_ownership


@pytest.mark.asyncio
async def test_ensure_session_ownership_forbidden_when_not_linked(monkeypatch):
    async def fake_get_session_link(_db, _session_id):
        return None

    monkeypatch.setattr(
        "app.auth.dependencies.get_session_link_by_session_id",
        fake_get_session_link,
    )

    with pytest.raises(HTTPException) as exc:
        await ensure_session_ownership(
            db=object(),
            session_id="session-12345678",
            user_id=ObjectId(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_ensure_session_ownership_forbidden_when_owner_mismatch(monkeypatch):
    async def fake_get_session_link(_db, _session_id):
        return {"user_id": ObjectId()}

    monkeypatch.setattr(
        "app.auth.dependencies.get_session_link_by_session_id",
        fake_get_session_link,
    )

    with pytest.raises(HTTPException) as exc:
        await ensure_session_ownership(
            db=object(),
            session_id="session-12345678",
            user_id=ObjectId(),
        )
    assert exc.value.status_code == 403
