from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings


_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        s = get_settings()
        _client = AsyncIOMotorClient(s.mongo_uri)
    return _client


async def close_mongo_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
