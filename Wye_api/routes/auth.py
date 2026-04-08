from fastapi import APIRouter
from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"

auth_router = APIRouter(tags=["Authentication"])

@auth_router.get("/")
async def root():
    return {"message": "Welcome to the Authentication API"}

@auth_router.post("/login")
async def login(request: LoginRequest):
    return {"message": "Login successful"}