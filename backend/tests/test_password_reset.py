from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.auth.password_reset import generate_reset_token, hash_token, reset_expires_at
from app.auth.security import hash_password, verify_password


def test_generate_reset_token_unique():
    plain1, hash1 = generate_reset_token()
    plain2, hash2 = generate_reset_token()
    assert plain1 != plain2
    assert hash1 == hash_token(plain1)
    assert hash1 != hash2


def test_reset_expires_at_in_future():
    expires = reset_expires_at(minutes=60)
    assert expires > datetime.now(UTC)


@pytest.mark.asyncio
async def test_forgot_password_always_returns_success_message(monkeypatch):
    from app.api.auth_routes import forgot_password, ForgotPasswordBody

    class FakeRequest:
        class App:
            class State:
                db = object()

            state = State()

        app = App()

    async def fake_get_user(_db, _email):
        return None

    monkeypatch.setattr("app.api.auth_routes.get_user_by_email", fake_get_user)

    result = await forgot_password(
        ForgotPasswordBody(email="missing@example.com"),
        FakeRequest(),
    )
    assert "tài khoản" in result.message.lower()


@pytest.mark.asyncio
async def test_reset_password_rejects_invalid_token(monkeypatch):
    from fastapi import HTTPException

    from app.api.auth_routes import reset_password, ResetPasswordBody

    class FakeRequest:
        class App:
            class State:
                db = object()

            state = State()

        app = App()

    async def fake_get_user(_db, _token_hash):
        return None

    monkeypatch.setattr(
        "app.api.auth_routes.get_user_by_reset_token_hash",
        fake_get_user,
    )

    with pytest.raises(HTTPException) as exc:
        await reset_password(
            ResetPasswordBody(token="invalid-token-value", password="newpass12"),
            FakeRequest(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_updates_hash(monkeypatch):
    from app.api.auth_routes import reset_password, ResetPasswordBody

    user_id = ObjectId()
    stored: dict = {"password_hash": hash_password("old-password")}

    class FakeRequest:
        class App:
            class State:
                db = object()

            state = State()

        app = App()

    async def fake_get_user(_db, _token_hash):
        return {"_id": user_id, "email": "u@example.com", **stored}

    async def fake_update(_db, *, user_id, password_hash):
        stored["password_hash"] = password_hash

    monkeypatch.setattr(
        "app.api.auth_routes.get_user_by_reset_token_hash",
        fake_get_user,
    )
    monkeypatch.setattr("app.api.auth_routes.update_user_password", fake_update)

    result = await reset_password(
        ResetPasswordBody(token="a" * 32, password="newpass12"),
        FakeRequest(),
    )
    assert result.message == "Đặt lại mật khẩu thành công."
    assert verify_password("newpass12", stored["password_hash"])
    assert not verify_password("old-password", stored["password_hash"])
