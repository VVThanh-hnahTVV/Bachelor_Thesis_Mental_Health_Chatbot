import pytest
from bson import ObjectId
from fastapi import HTTPException

from app.auth.dependencies import require_admin


@pytest.mark.asyncio
async def test_require_admin_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await require_admin(user={"_id": ObjectId(), "role": "user"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_admin_allows_admin():
    user = {"_id": ObjectId(), "role": "admin"}
    result = await require_admin(user=user)
    assert result["role"] == "admin"
