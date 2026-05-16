from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

CONVERSATIONS = "conversations"
MESSAGES = "messages"
MOOD_ENTRIES = "mood_entries"
ACTIVITY_COMPLETIONS = "activity_completions"
USER_PROFILES = "user_profiles"


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[MESSAGES].create_index([("conversation_id", 1), ("created_at", 1)])
    await db[MOOD_ENTRIES].create_index([("session_id", 1), ("created_at", -1)])
    await db[CONVERSATIONS].create_index([("session_id", 1)], unique=True)
    await db[ACTIVITY_COMPLETIONS].create_index([("session_id", 1), ("created_at", -1)])
    await db[ACTIVITY_COMPLETIONS].create_index([("linked_message_id", 1)])
    await db[USER_PROFILES].create_index([("session_id", 1)], unique=True)


async def create_conversation(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    title: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "session_id": session_id,
        "title": title or "New chat",
        "created_at": now,
        "updated_at": now,
    }
    res = await db[CONVERSATIONS].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def get_conversation_by_session(db: AsyncIOMotorDatabase, session_id: str) -> dict[str, Any] | None:
    return await db[CONVERSATIONS].find_one({"session_id": session_id})


async def list_conversations(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    cursor = (
        db[CONVERSATIONS]
        .find({"session_id": session_id})
        .sort("updated_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def touch_conversation(db: AsyncIOMotorDatabase, conversation_oid: ObjectId) -> None:
    await db[CONVERSATIONS].update_one(
        {"_id": conversation_oid},
        {"$set": {"updated_at": datetime.now(UTC)}},
    )


async def append_message(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "created_at": now,
    }
    if metadata:
        doc["metadata"] = metadata
    res = await db[MESSAGES].insert_one(doc)
    doc["_id"] = res.inserted_id
    await touch_conversation(db, conversation_id)
    return doc


async def recent_messages(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
    limit: int = 20,
) -> list[dict[str, Any]]:
    cursor = (
        db[MESSAGES]
        .find({"conversation_id": conversation_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = [doc async for doc in cursor]
    rows.reverse()
    return rows


async def list_messages_chronological(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
    limit: int = 100,
) -> list[dict[str, Any]]:
    cursor = (
        db[MESSAGES]
        .find({"conversation_id": conversation_id})
        .sort("created_at", 1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def add_activity_completion(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    conversation_id: ObjectId,
    activity_id: str,
    linked_message_id: ObjectId | None = None,
    duration_sec: int | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "activity_id": activity_id,
        "created_at": now,
    }
    if linked_message_id is not None:
        doc["linked_message_id"] = linked_message_id
    if duration_sec is not None:
        doc["duration_sec"] = duration_sec
    res = await db[ACTIVITY_COMPLETIONS].insert_one(doc)
    doc["_id"] = res.inserted_id
    await touch_conversation(db, conversation_id)
    return doc


async def list_activity_completions(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    cursor = (
        db[ACTIVITY_COMPLETIONS]
        .find({"session_id": session_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def add_mood_entry(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    score: int,
    note: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "session_id": session_id,
        "score": score,
        "note": note,
        "created_at": now,
    }
    res = await db[MOOD_ENTRIES].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def list_mood_entries(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    limit: int = 60,
) -> list[dict[str, Any]]:
    cursor = (
        db[MOOD_ENTRIES]
        .find({"session_id": session_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = [doc async for doc in cursor]
    rows.reverse()
    return rows


# ---------------------------------------------------------------------------
# User profiles — long-term memory across sessions
# ---------------------------------------------------------------------------

async def get_user_profile(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> dict[str, Any] | None:
    return await db[USER_PROFILES].find_one({"session_id": session_id})


async def upsert_user_profile(
    db: AsyncIOMotorDatabase,
    session_id: str,
    updates: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    await db[USER_PROFILES].update_one(
        {"session_id": session_id},
        {
            "$set": {**updates, "updated_at": now},
            "$setOnInsert": {"session_id": session_id, "created_at": now},
        },
        upsert=True,
    )


async def get_mood_trend(
    db: AsyncIOMotorDatabase,
    session_id: str,
    limit: int = 5,
) -> str:
    """Derive mood trend from recent entries: 'improving', 'declining', or 'stable'."""
    cursor = (
        db[MOOD_ENTRIES]
        .find({"session_id": session_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    rows = [doc async for doc in cursor]
    if len(rows) < 2:
        return "stable"
    scores = [int(r["score"]) for r in reversed(rows)]
    delta = scores[-1] - scores[0]
    if delta >= 1:
        return "improving"
    if delta <= -1:
        return "declining"
    return "stable"
