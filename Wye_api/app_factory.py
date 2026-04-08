from routes.auth import auth_router
from fastapi import FastAPI

def create_app() -> FastAPI:
    app = FastAPI(
        title = 'Wye Mental Health API',
        description = 'API for the Wye Mental Health app',
        version = '0.1.0',
        docs_url = '/docs',
        redoc_url = '/redoc',
        openapi_url = '/openapi.json',
    )

    app.include_router(auth_router)

    return app
