from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pprint import pprint

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin_routes import router as admin_router
from app.api.auth_routes import router as auth_router
from app.api.routes import router as api_router
from app.api.ws_routes import router as ws_router
from app.auth.repository import ensure_auth_indexes
from app.cache.redis_client import close_redis_client, get_redis_client
from app.config import get_settings
from app.rag.embeddings import resolve_embedding_model, resolve_embedding_provider
from app.db.client import close_mongo_client, get_mongo_client
from app.db.repository import ensure_indexes
from app.llm.factory import build_provider_chain, default_provider
from app.medical.config import log_qdrant_startup


logger = logging.getLogger("uvicorn.error")


def _active_model_for_provider(primary: str, settings) -> str:
    if primary == "local":
        return settings.local_model
    if primary == "modal":
        return settings.modal_model
    if primary == "groq":
        return settings.groq_model
    if primary == "gemini":
        return settings.gemini_model
    return settings.openai_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    pprint(f"s: {s}")
    primary = default_provider()
    print(f"primary: {primary}")
    provider_chain = build_provider_chain(primary)
    print(f"provider_chain: {provider_chain}")
    active_model = _active_model_for_provider(primary, s)
    emb_provider = resolve_embedding_provider()
    emb_model = resolve_embedding_model(emb_provider)
    logger.info(
        "LLM config: primary=%s active_model=%s fallback_chain=%s completion_model=%s "
        "embedding_provider=%s embedding_model=%s",
        primary,
        active_model,
        ",".join(provider_chain),
        s.completion_model,
        emb_provider,
        emb_model,
    )
    log_qdrant_startup()

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
        title="Helios — Tra cứu & tư vấn sức khỏe tâm thần",
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
    app.include_router(admin_router)
    app.include_router(ws_router)

    return app


app = create_app()
