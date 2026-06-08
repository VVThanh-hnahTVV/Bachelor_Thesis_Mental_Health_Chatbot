from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

CONVERSATIONS = "conversations"
MESSAGES = "messages"
MOOD_ENTRIES = "mood_entries"
ACTIVITY_COMPLETIONS = "activity_completions"
USER_PROFILES = "user_profiles"
MESSAGE_FEEDBACK = "message_feedback"
SCREENING_RESPONSES = "screening_responses"
KNOWLEDGE_CHUNKS = "knowledge_chunks"


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[MESSAGES].create_index([("conversation_id", 1), ("created_at", 1)])
    await db[MOOD_ENTRIES].create_index([("session_id", 1), ("created_at", -1)])
    await db[CONVERSATIONS].create_index([("session_id", 1)], unique=True)
    await db[CONVERSATIONS].create_index([("user_id", 1), ("updated_at", -1)])
    await db[ACTIVITY_COMPLETIONS].create_index([("session_id", 1), ("created_at", -1)])
    await db[ACTIVITY_COMPLETIONS].create_index([("linked_message_id", 1)])
    await db[USER_PROFILES].create_index([("session_id", 1)], unique=True)
    await db[MESSAGE_FEEDBACK].create_index(
        [("assistant_message_id", 1), ("session_id", 1)], unique=True
    )
    await db[SCREENING_RESPONSES].create_index([("session_id", 1), ("created_at", -1)])
    await db[KNOWLEDGE_CHUNKS].create_index([("id", 1)], unique=True)
    await db[KNOWLEDGE_CHUNKS].create_index([("topic", 1)])


async def create_conversation(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    title: str | None = None,
    chat_mode: str = "psychologist",
    user_id: ObjectId | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "session_id": session_id,
        "title": title or "New chat",
        "chat_mode": chat_mode,
        "created_at": now,
        "updated_at": now,
    }
    if user_id is not None:
        doc["user_id"] = user_id
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


async def list_conversations_for_user(
    db: AsyncIOMotorDatabase,
    *,
    user_id: ObjectId,
    limit: int = 50,
) -> list[dict[str, Any]]:
    from app.auth.repository import SESSION_LINKS

    linked_ids: list[str] = []
    async for link in db[SESSION_LINKS].find({"user_id": user_id}, {"session_id": 1}):
        sid = link.get("session_id")
        if isinstance(sid, str) and sid:
            linked_ids.append(sid)

    clauses: list[dict[str, Any]] = [{"user_id": user_id}]
    if linked_ids:
        clauses.append({"session_id": {"$in": linked_ids}})

    query: dict[str, Any] = clauses[0] if len(clauses) == 1 else {"$or": clauses}
    cursor = (
        db[CONVERSATIONS]
        .find(query)
        .sort("updated_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def list_conversations_by_session_ids(
    db: AsyncIOMotorDatabase,
    *,
    session_ids: list[str],
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not session_ids:
        return []
    cursor = (
        db[CONVERSATIONS]
        .find({"session_id": {"$in": session_ids}})
        .sort("updated_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def update_conversation_title(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
    title: str,
) -> None:
    await db[CONVERSATIONS].update_one(
        {"_id": conversation_id},
        {"$set": {"title": title, "updated_at": datetime.now(UTC)}},
    )


async def get_conversation_summary(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> str:
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        return ""
    summary = conv.get("summary")
    return str(summary).strip() if summary else ""


async def update_conversation_summary(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
    summary: str,
) -> None:
    now = datetime.now(UTC)
    await db[CONVERSATIONS].update_one(
        {"_id": conversation_id},
        {
            "$set": {
                "summary": summary,
                "summary_updated_at": now,
                "updated_at": now,
            }
        },
    )


async def delete_conversation_by_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> bool:
    """Remove conversation, messages, and session-scoped chat data. Returns False if not found."""
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        return False
    cid = conv.get("_id")
    if isinstance(cid, ObjectId):
        await db[MESSAGES].delete_many({"conversation_id": cid})
        await db[ACTIVITY_COMPLETIONS].delete_many(
            {"$or": [{"session_id": session_id}, {"conversation_id": cid}]}
        )
    else:
        await db[ACTIVITY_COMPLETIONS].delete_many({"session_id": session_id})
    await db[MESSAGE_FEEDBACK].delete_many({"session_id": session_id})
    await db[USER_PROFILES].delete_one({"session_id": session_id})
    await db[CONVERSATIONS].delete_one({"session_id": session_id})
    return True


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


async def count_user_messages(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
) -> int:
    return await db[MESSAGES].count_documents(
        {"conversation_id": conversation_id, "role": "user"}
    )


async def save_message_feedback(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    assistant_message_id: str,
    value: str,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "session_id": session_id,
        "assistant_message_id": assistant_message_id,
        "value": value,
        "created_at": now,
    }
    await db[MESSAGE_FEEDBACK].update_one(
        {"session_id": session_id, "assistant_message_id": assistant_message_id},
        {"$set": doc},
        upsert=True,
    )
    return doc


async def get_message_feedback(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    assistant_message_id: str,
) -> dict[str, Any] | None:
    return await db[MESSAGE_FEEDBACK].find_one(
        {"session_id": session_id, "assistant_message_id": assistant_message_id}
    )


async def save_screening_response(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    instrument: str,
    answers: list[int],
    score: int,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "session_id": session_id,
        "instrument": instrument,
        "answers": answers,
        "score": score,
        "created_at": now,
    }
    res = await db[SCREENING_RESPONSES].insert_one(doc)
    doc["_id"] = res.inserted_id
    return doc


async def latest_screening(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    instrument: str | None = None,
) -> dict[str, Any] | None:
    query: dict[str, Any] = {"session_id": session_id}
    if instrument:
        query["instrument"] = instrument
    return await db[SCREENING_RESPONSES].find_one(query, sort=[("created_at", -1)])


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


# ---------------------------------------------------------------------------
# Knowledge chunks — optional Mongo-backed vector RAG
# ---------------------------------------------------------------------------

async def upsert_knowledge_chunk(
    db: AsyncIOMotorDatabase,
    *,
    chunk_id: str,
    text: str,
    topic: str = "",
    embedding: list[float] | None = None,
    source: str = "chunks.json",
) -> None:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "id": chunk_id,
        "text": text,
        "topic": topic,
        "source": source,
        "updated_at": now,
    }
    if embedding is not None:
        doc["embedding"] = embedding
    await db[KNOWLEDGE_CHUNKS].update_one(
        {"id": chunk_id},
        {
            "$set": doc,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def list_knowledge_chunks(
    db: AsyncIOMotorDatabase,
    *,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    cursor = db[KNOWLEDGE_CHUNKS].find({}).limit(limit)
    return [doc async for doc in cursor]
