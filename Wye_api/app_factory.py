from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_mongo_client, get_settings
from db.setup_collections import ensure_users_collection
from routes.auth import auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = get_mongo_client()
    s = get_settings()
    try:
        await client.admin.command("ping")
        db = client[s.mongo_db_name]
        await ensure_users_collection(db)
        print("Connected to MongoDB", s.mongo_db_name)
        app.state.mongo_client = client
        app.state.db = db
        yield
    finally:
        print("Closing MongoDB connection")
        client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Wye Mental Health API",
        description="API for the Wye Mental Health app",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)

    return app
