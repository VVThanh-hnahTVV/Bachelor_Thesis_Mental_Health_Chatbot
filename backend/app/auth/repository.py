from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repository import (
    ACTIVITY_COMPLETIONS,
    CONVERSATIONS,
    MOOD_ENTRIES,
)

USERS = "users"
SESSION_LINKS = "session_links"


async def ensure_auth_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[USERS].create_index([("email", 1)], unique=True)
    await db[SESSION_LINKS].create_index([("session_id", 1)], unique=True)
    await db[SESSION_LINKS].create_index([("user_id", 1)])


async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> dict[str, Any] | None:
    return await db[USERS].find_one({"email": email.lower().strip()})


async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: ObjectId) -> dict[str, Any] | None:
    return await db[USERS].find_one({"_id": user_id})


async def create_user(
    db: AsyncIOMotorDatabase,
    *,
    email: str,
    name: str,
    password_hash: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "email": email.lower().strip(),
        "name": name.strip(),
        "password_hash": password_hash,
        "created_at": now,
        "updated_at": now,
    }
    res = await db[USERS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


def user_public(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "_id": str(doc["_id"]),
        "email": doc["email"],
        "name": doc["name"],
    }


async def link_session_to_user(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    user_id: ObjectId,
) -> None:
    now = datetime.now(UTC)
    await db[SESSION_LINKS].update_one(
        {"session_id": session_id},
        {"$set": {"user_id": user_id, "linked_at": now}},
        upsert=True,
    )
    user_ref = user_id
    for coll in (CONVERSATIONS, MOOD_ENTRIES, ACTIVITY_COMPLETIONS):
        await db[coll].update_many(
            {"session_id": session_id},
            {"$set": {"user_id": user_ref}},
        )
