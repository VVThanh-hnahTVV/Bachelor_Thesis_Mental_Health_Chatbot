from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth_routes import router as auth_router
from app.api.routes import router as api_router
from app.auth.repository import ensure_auth_indexes
from app.cache.redis_client import close_redis_client, get_redis_client
from app.config import get_settings
from app.db.client import close_mongo_client, get_mongo_client
from app.db.repository import ensure_indexes


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()

    # MongoDB
    client = get_mongo_client()
    await client.admin.command("ping")
    db = client[s.mongo_db_name]
    await ensure_indexes(db)
    await ensure_auth_indexes(db)
    app.state.mongo_client = client
    app.state.db = db

    # Redis
    redis = get_redis_client()
    await redis.ping()
    app.state.redis = redis

    yield

    await close_mongo_client()
    await close_redis_client()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Mental Health Chat API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(api_router)
    app.include_router(auth_router)
    return app


app = create_app()
