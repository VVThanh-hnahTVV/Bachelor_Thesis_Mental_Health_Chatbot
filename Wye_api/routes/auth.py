from __future__ import annotations

from fastapi import APIRouter, Request, status

from controller.auth_controller import login_controller, refresh_controller, register_controller
from schemas.users import AuthResponse, LoginRequest, RefreshTokenRequest, RefreshTokenResponse, RegisterRequest

auth_router = APIRouter(tags=["Authentication"])

@auth_router.get("/")
async def root():
    return {"message": "Welcome to the Authentication API"}


@auth_router.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(request: Request, payload: RegisterRequest) -> AuthResponse:
    return await register_controller(request, payload)


@auth_router.post("/auth/login", response_model=AuthResponse)
async def login(request: Request, payload: LoginRequest) -> AuthResponse:
    return await login_controller(request, payload)


@auth_router.post("/auth/refresh", response_model=RefreshTokenResponse)
async def refresh_access_token(request: Request, payload: RefreshTokenRequest) -> RefreshTokenResponse:
    return await refresh_controller(request, payload)