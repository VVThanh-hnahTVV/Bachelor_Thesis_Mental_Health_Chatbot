from __future__ import annotations

from fastapi import Request

from schemas.users import AuthResponse, LoginRequest, RefreshTokenRequest, RefreshTokenResponse, RegisterRequest
from service.auth_service import login_user, refresh_access_token, register_user


async def register_controller(request: Request, payload: RegisterRequest) -> AuthResponse:
    return await register_user(request.app.state.db, payload)


async def login_controller(request: Request, payload: LoginRequest) -> AuthResponse:
    return await login_user(request.app.state.db, payload)


async def refresh_controller(request: Request, payload: RefreshTokenRequest) -> RefreshTokenResponse:
    return await refresh_access_token(request.app.state.db, payload.refresh_token)
