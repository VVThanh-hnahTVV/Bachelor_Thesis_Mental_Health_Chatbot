from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

CONVERSATIONS = "conversations"
MESSAGES = "messages"
ACTIVITY_COMPLETIONS = "activity_completions"
WELLNESS_ACTIVITIES = "wellness_activities"
ACTIVITY_RATINGS = "activity_ratings"


SUPPORT_MODES = ("ai", "awaiting_support", "human", "closed")
MESSAGE_VISIBILITY_ALL = "all"
MESSAGE_VISIBILITY_SUPPORT_ONLY = "support_only"


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[MESSAGES].create_index([("conversation_id", 1), ("created_at", 1)])
    await db[CONVERSATIONS].create_index([("session_id", 1)], unique=True)
    await db[CONVERSATIONS].create_index([("user_id", 1), ("updated_at", -1)])
    await db[CONVERSATIONS].create_index([("support_mode", 1), ("handoff_requested_at", -1)])
    await db[ACTIVITY_COMPLETIONS].create_index([("session_id", 1), ("created_at", -1)])
    await db[ACTIVITY_COMPLETIONS].create_index([("linked_message_id", 1)])
    await db[WELLNESS_ACTIVITIES].create_index([("id", 1)], unique=True)
    await db[WELLNESS_ACTIVITIES].create_index([("active", 1), ("scope", 1)])
    await db[ACTIVITY_RATINGS].create_index([("session_id", 1), ("created_at", -1)])
    await db[ACTIVITY_RATINGS].create_index(
        [("completion_id", 1), ("session_id", 1)], unique=True
    )


async def create_conversation(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    title: str | None = None,
    chat_mode: str = "medical",
    user_id: ObjectId | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "session_id": session_id,
        "title": title or "New chat",
        "chat_mode": chat_mode,
        "support_mode": "ai",
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
    """Read rolling session summary persisted on the conversations document."""
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
            },
            "$unset": {
                "human_session_summary": "",
                "human_session_summary_updated_at": "",
            },
        },
    )


def _admin_summary(doc: dict[str, Any]) -> str | None:
    summary = doc.get("summary")
    legacy_human = doc.get("human_session_summary")
    s = str(summary).strip() if summary else ""
    h = str(legacy_human).strip() if legacy_human else ""
    if s and h and h not in s:
        return f"{s}\n\n---\n\n{h}"
    merged = s or h
    return merged or None


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
    include_support_only: bool = True,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"conversation_id": conversation_id}
    if not include_support_only:
        query["$or"] = [
            {"metadata.visibility": {"$exists": False}},
            {"metadata.visibility": MESSAGE_VISIBILITY_ALL},
            {"metadata": {"$exists": False}},
        ]
    cursor = (
        db[MESSAGES]
        .find(query)
        .sort("created_at", 1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def list_messages_for_user(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return await list_messages_chronological(
        db,
        conversation_id=conversation_id,
        limit=limit,
        include_support_only=False,
    )


async def get_latest_handoff_brief(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
) -> str | None:
    cursor = (
        db[MESSAGES]
        .find(
            {
                "conversation_id": conversation_id,
                "metadata.message_type": "handoff_brief",
            }
        )
        .sort("created_at", -1)
        .limit(1)
    )
    rows = [doc async for doc in cursor]
    if not rows:
        return None
    content = rows[0].get("content")
    return str(content) if content else None


async def try_claim_human_support(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
    admin_id: ObjectId,
    support_name: str,
    now: datetime,
    handoff_requested_at: datetime | None = None,
) -> bool:
    """Atomically assign human support if session is still ai/awaiting_support."""
    extra: dict[str, Any] = {
        "support_mode": "human",
        "assigned_support_id": admin_id,
        "assigned_support_name": support_name,
        "updated_at": now,
    }
    result = await db[CONVERSATIONS].update_one(
        {
            "_id": conversation_id,
            "support_mode": {"$in": ["ai", "awaiting_support"]},
        },
        {"$set": extra},
    )
    if result.modified_count == 0:
        return False

    await db[CONVERSATIONS].update_one(
        {"_id": conversation_id, "human_session_started_at": {"$exists": False}},
        {"$set": {"human_session_started_at": now}},
    )
    if handoff_requested_at is not None:
        await db[CONVERSATIONS].update_one(
            {"_id": conversation_id, "handoff_requested_at": {"$exists": False}},
            {"$set": {"handoff_requested_at": handoff_requested_at}},
        )
    return True


async def list_messages_since(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
    since: datetime,
    roles: list[str] | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {
        "conversation_id": conversation_id,
        "created_at": {"$gte": since},
    }
    if roles:
        query["role"] = {"$in": roles}
    cursor = db[MESSAGES].find(query).sort("created_at", 1)
    return [doc async for doc in cursor]


def get_support_mode(conv: dict[str, Any] | None) -> str:
    if not conv:
        return "ai"
    mode = str(conv.get("support_mode") or "ai")
    return mode if mode in SUPPORT_MODES else "ai"


async def update_conversation_support_mode(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
    support_mode: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    if support_mode not in SUPPORT_MODES:
        raise ValueError(f"Invalid support_mode: {support_mode}")
    now = datetime.now(UTC)
    payload: dict[str, Any] = {"support_mode": support_mode, "updated_at": now}
    if extra:
        payload.update(extra)
    await db[CONVERSATIONS].update_one(
        {"_id": conversation_id},
        {"$set": payload},
    )


async def update_human_session_summary(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
    summary: str,
) -> None:
    """Deprecated: use update_conversation_summary for unified summaries."""
    await update_conversation_summary(db, conversation_id, summary)


async def list_conversations_support_queue(
    db: AsyncIOMotorDatabase,
    *,
    assigned_support_id: ObjectId | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = [{"support_mode": "awaiting_support"}]
    if assigned_support_id is not None:
        clauses.append(
            {
                "support_mode": "human",
                "assigned_support_id": assigned_support_id,
            }
        )
    query = {"$or": clauses} if len(clauses) > 1 else clauses[0]
    cursor = (
        db[CONVERSATIONS]
        .find(query)
        .sort("handoff_requested_at", -1)
        .limit(limit)
    )
    return [doc async for doc in cursor]


async def update_message_metadata(
    db: AsyncIOMotorDatabase,
    message_id: ObjectId,
    metadata_patch: dict[str, Any],
) -> dict[str, Any] | None:
    """Merge metadata_patch into an existing message (top-level keys)."""
    doc = await db[MESSAGES].find_one({"_id": message_id})
    if not doc:
        return None
    meta = doc.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    merged = {**meta, **metadata_patch}
    await db[MESSAGES].update_one(
        {"_id": message_id},
        {"$set": {"metadata": merged}},
    )
    doc["metadata"] = merged
    return doc


async def add_activity_completion(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    conversation_id: ObjectId,
    activity_id: str,
    linked_message_id: ObjectId | None = None,
    duration_sec: int | None = None,
    chat_mode: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "session_id": session_id,
        "conversation_id": conversation_id,
        "activity_id": activity_id,
        "created_at": now,
    }
    if chat_mode:
        doc["chat_mode"] = chat_mode
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


async def count_user_messages(
    db: AsyncIOMotorDatabase,
    conversation_id: ObjectId,
) -> int:
    return await db[MESSAGES].count_documents(
        {"conversation_id": conversation_id, "role": "user"}
    )


# ---------------------------------------------------------------------------
# Wellness activities catalog (Helios + shared)
# ---------------------------------------------------------------------------


def _localized(doc: dict[str, Any], field: str, lang: str) -> str:
    raw = doc.get(field) or {}
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return str(raw.get(lang) or raw.get("vi") or raw.get("en") or "")
    return ""


def activity_to_api(doc: dict[str, Any], *, lang: str = "vi") -> dict[str, Any]:
    """Public API shape for an activity."""
    benefits = doc.get("benefits") if lang == "vi" else doc.get("benefits_en") or doc.get("benefits")
    video_source_raw = doc.get("video_source")
    video_source: dict[str, Any] | None = None
    if isinstance(video_source_raw, dict):
        attribution_raw = video_source_raw.get("attribution")
        if isinstance(attribution_raw, dict):
            attribution = str(
                attribution_raw.get(lang) or attribution_raw.get("en") or ""
            ).strip()
        else:
            attribution = str(attribution_raw or "").strip()
        video_source = {
            "name": str(video_source_raw.get("name") or "").strip(),
            "url": video_source_raw.get("url"),
            "attribution": attribution or None,
        }
        if not (video_source.get("name") or video_source.get("attribution")):
            video_source = None

    return {
        "id": str(doc.get("id", "")),
        "title": _localized(doc, "title", lang),
        "description": _localized(doc, "description", lang),
        "content_type": str(doc.get("content_type") or "interactive"),
        "activity_type": str(doc.get("activity_type") or "exercise"),
        "ui_component": str(doc.get("ui_component") or doc.get("id", "")),
        "video_url": doc.get("video_url"),
        "youtube_id": doc.get("youtube_id"),
        "video_source": video_source,
        "duration_min": int(doc.get("duration_min") or 5),
        "avg_rating": float(doc.get("avg_rating") or 0),
        "rating_count": int(doc.get("rating_count") or 0),
        "benefits": list(benefits) if isinstance(benefits, list) else [],
        "tags": list(doc.get("tags") or []),
    }


async def upsert_wellness_activity(
    db: AsyncIOMotorDatabase,
    doc: dict[str, Any],
) -> None:
    now = datetime.now(UTC)
    activity_id = str(doc["id"])
    await db[WELLNESS_ACTIVITIES].update_one(
        {"id": activity_id},
        {
            "$set": {**doc, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )


async def list_wellness_activities(
    db: AsyncIOMotorDatabase,
    *,
    scope: str | None = None,
    active_only: bool = True,
    implemented_only: bool = False,
    limit: int = 100,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if active_only:
        query["active"] = True
    if implemented_only:
        query["implemented"] = True
    if scope:
        query["scope"] = scope
    cursor = db[WELLNESS_ACTIVITIES].find(query).sort("id", 1).limit(limit)
    return [doc async for doc in cursor]


async def get_wellness_activity_by_id(
    db: AsyncIOMotorDatabase,
    activity_id: str,
) -> dict[str, Any] | None:
    return await db[WELLNESS_ACTIVITIES].find_one({"id": activity_id})


def wellness_activity_admin_dict(doc: dict[str, Any]) -> dict[str, Any]:
    """Serialize a wellness activity document for admin API responses."""
    created = doc.get("created_at")
    updated = doc.get("updated_at")
    title = doc.get("title") or {}
    description = doc.get("description") or {}
    if not isinstance(title, dict):
        title = {"vi": str(title), "en": str(title)}
    if not isinstance(description, dict):
        description = {"vi": str(description), "en": str(description)}

    return {
        "id": str(doc.get("id", "")),
        "scope": list(doc.get("scope") or []),
        "content_type": str(doc.get("content_type") or "interactive"),
        "activity_type": str(doc.get("activity_type") or "exercise"),
        "ui_component": str(doc.get("ui_component") or doc.get("id", "")),
        "title": {
            "vi": str(title.get("vi") or ""),
            "en": str(title.get("en") or ""),
        },
        "description": {
            "vi": str(description.get("vi") or ""),
            "en": str(description.get("en") or ""),
        },
        "benefits": list(doc.get("benefits") or []),
        "benefits_en": list(doc.get("benefits_en") or []),
        "tags": list(doc.get("tags") or []),
        "duration_min": int(doc.get("duration_min") or 5),
        "avg_rating": float(doc.get("avg_rating") or 0),
        "rating_count": int(doc.get("rating_count") or 0),
        "active": bool(doc.get("active", True)),
        "implemented": bool(doc.get("implemented", False)),
        "video_url": doc.get("video_url"),
        "youtube_id": doc.get("youtube_id"),
        "video_source": doc.get("video_source"),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else None,
        "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else None,
    }


async def count_wellness_activities(
    db: AsyncIOMotorDatabase,
    *,
    active_only: bool = False,
    implemented_only: bool = False,
) -> int:
    query: dict[str, Any] = {}
    if active_only:
        query["active"] = True
    if implemented_only:
        query["implemented"] = True
    return await db[WELLNESS_ACTIVITIES].count_documents(query)


async def is_valid_activity_id(db: AsyncIOMotorDatabase, activity_id: str) -> bool:
    doc = await get_wellness_activity_by_id(db, activity_id)
    if doc and doc.get("active") and doc.get("implemented"):
        return True
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    return any(
        str(d.get("id")) == activity_id and d.get("active") and d.get("implemented")
        for d in DEFAULT_WELLNESS_ACTIVITIES
    )


async def save_activity_rating(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    activity_id: str,
    completion_id: ObjectId,
    rating: int,
    chat_mode: str = "medical",
    user_id: ObjectId | None = None,
) -> dict[str, Any]:
    if rating < 1 or rating > 5:
        raise ValueError("rating must be 1-5")
    now = datetime.now(UTC)
    doc: dict[str, Any] = {
        "session_id": session_id,
        "activity_id": activity_id,
        "completion_id": completion_id,
        "rating": rating,
        "chat_mode": chat_mode,
        "created_at": now,
    }
    if user_id is not None:
        doc["user_id"] = user_id
    await db[ACTIVITY_RATINGS].update_one(
        {"completion_id": completion_id, "session_id": session_id},
        {"$set": doc},
        upsert=True,
    )
    await update_activity_rating_stats(db, activity_id=activity_id, new_rating=rating)
    return doc


async def update_activity_rating_stats(
    db: AsyncIOMotorDatabase,
    *,
    activity_id: str,
    new_rating: int,
) -> None:
    """Incremental mean update for avg_rating."""
    activity = await get_wellness_activity_by_id(db, activity_id)
    if not activity:
        return
    count = int(activity.get("rating_count") or 0)
    avg = float(activity.get("avg_rating") or 0)
    # If re-rating same completion, skip duplicate increment (upsert overwrites rating doc)
    existing_count = count
    new_count = existing_count + 1
    new_avg = ((avg * existing_count) + new_rating) / new_count if new_count else float(new_rating)
    await db[WELLNESS_ACTIVITIES].update_one(
        {"id": activity_id},
        {"$set": {"avg_rating": round(new_avg, 2), "rating_count": new_count}},
    )


async def get_activity_completion_by_id(
    db: AsyncIOMotorDatabase,
    completion_id: ObjectId,
) -> dict[str, Any] | None:
    return await db[ACTIVITY_COMPLETIONS].find_one({"_id": completion_id})


def _day_bounds(day: datetime) -> tuple[datetime, datetime]:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _conversations_user_resolve_stages() -> list[dict[str, Any]]:
    from app.auth.repository import SESSION_LINKS

    return [
        {
            "$lookup": {
                "from": SESSION_LINKS,
                "localField": "session_id",
                "foreignField": "session_id",
                "as": "_session_link",
            }
        },
        {
            "$addFields": {
                "resolved_user_id": {
                    "$ifNull": [
                        "$user_id",
                        {"$arrayElemAt": ["$_session_link.user_id", 0]},
                    ]
                }
            }
        },
    ]


def _conversations_admin_lookup_stages() -> list[dict[str, Any]]:
    from app.auth.repository import USERS

    return [
        *_conversations_user_resolve_stages(),
        {
            "$lookup": {
                "from": MESSAGES,
                "let": {"cid": "$_id"},
                "pipeline": [
                    {
                        "$match": {
                            "$expr": {"$eq": ["$conversation_id", "$$cid"]}
                        }
                    },
                    {"$count": "count"},
                ],
                "as": "_msg_stats",
            }
        },
        {
            "$addFields": {
                "message_count": {
                    "$ifNull": [{"$arrayElemAt": ["$_msg_stats.count", 0]}, 0]
                }
            }
        },
        {
            "$lookup": {
                "from": USERS,
                "localField": "resolved_user_id",
                "foreignField": "_id",
                "as": "_user_doc",
            }
        },
    ]


def _conversations_admin_match_stage(
    *,
    search: str | None = None,
    owner: str | None = None,
) -> dict[str, Any] | None:
    clauses: list[dict[str, Any]] = []

    if search:
        term = search.strip()
        if term:
            regex = {"$regex": term, "$options": "i"}
            clauses.append(
                {
                    "$or": [
                        {"title": regex},
                        {"summary": regex},
                        {"session_id": regex},
                    ]
                }
            )

    if owner == "guest":
        clauses.append({"resolved_user_id": None})
    elif owner == "registered":
        clauses.append({"resolved_user_id": {"$ne": None}})

    if not clauses:
        return None
    if len(clauses) == 1:
        return {"$match": clauses[0]}
    return {"$match": {"$and": clauses}}


def conversation_admin_dict(doc: dict[str, Any]) -> dict[str, Any]:
    user_payload: dict[str, str] | None = None
    user_rows = doc.get("_user_doc") or []
    if isinstance(user_rows, list) and user_rows:
        user_doc = user_rows[0]
        if isinstance(user_doc, dict):
            user_payload = {
                "id": str(user_doc.get("_id", "")),
                "name": str(user_doc.get("name") or ""),
                "email": str(user_doc.get("email") or ""),
            }

    return {
        "session_id": str(doc.get("session_id") or ""),
        "conversation_id": str(doc.get("_id") or ""),
        "title": str(doc.get("title") or "Cuộc trò chuyện mới"),
        "chat_mode": str(doc.get("chat_mode") or "medical"),
        "support_mode": str(doc.get("support_mode") or "ai"),
        "summary": _admin_summary(doc),
        "summary_updated_at": _iso_datetime(doc.get("summary_updated_at")),
        "human_session_summary": None,
        "human_session_summary_updated_at": None,
        "handoff_requested_at": _iso_datetime(doc.get("handoff_requested_at")),
        "assigned_support_id": (
            str(doc["assigned_support_id"])
            if isinstance(doc.get("assigned_support_id"), ObjectId)
            else None
        ),
        "assigned_support_name": doc.get("assigned_support_name") or None,
        "human_session_started_at": _iso_datetime(doc.get("human_session_started_at")),
        "human_session_ended_at": _iso_datetime(doc.get("human_session_ended_at")),
        "created_at": _iso_datetime(doc.get("created_at")),
        "updated_at": _iso_datetime(doc.get("updated_at")),
        "message_count": int(doc.get("message_count") or 0),
        "user": user_payload,
    }


async def count_conversations_admin(
    db: AsyncIOMotorDatabase,
    *,
    search: str | None = None,
    owner: str | None = None,
) -> int:
    pipeline: list[dict[str, Any]] = [
        *_conversations_admin_lookup_stages(),
    ]
    match_stage = _conversations_admin_match_stage(search=search, owner=owner)
    if match_stage:
        pipeline.append(match_stage)
    pipeline.append({"$count": "total"})

    rows = await db[CONVERSATIONS].aggregate(pipeline).to_list(1)
    if not rows:
        return 0
    return int(rows[0].get("total") or 0)


async def list_conversations_admin(
    db: AsyncIOMotorDatabase,
    *,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    owner: str | None = None,
) -> list[dict[str, Any]]:
    pipeline: list[dict[str, Any]] = [
        *_conversations_admin_lookup_stages(),
    ]
    match_stage = _conversations_admin_match_stage(search=search, owner=owner)
    if match_stage:
        pipeline.append(match_stage)
    pipeline.extend(
        [
            {"$sort": {"updated_at": -1}},
            {"$skip": max(0, skip)},
            {"$limit": max(1, limit)},
        ]
    )

    rows = await db[CONVERSATIONS].aggregate(pipeline).to_list(limit)
    return [conversation_admin_dict(row) for row in rows]


async def get_conversation_admin_stats(
    db: AsyncIOMotorDatabase,
    *,
    days: int = 7,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    today_start, _ = _day_bounds(now)

    total_conversations = await db[CONVERSATIONS].count_documents({})
    total_messages = await db[MESSAGES].count_documents({})
    conversations_today = await db[CONVERSATIONS].count_documents(
        {"created_at": {"$gte": today_start}}
    )
    messages_today = await db[MESSAGES].count_documents(
        {"created_at": {"$gte": today_start}}
    )
    with_summary = await db[CONVERSATIONS].count_documents(
        {"summary": {"$exists": True, "$nin": [None, ""]}}
    )

    registered_rows = await db[CONVERSATIONS].aggregate(
        [
            *_conversations_user_resolve_stages(),
            {"$match": {"resolved_user_id": {"$ne": None}}},
            {"$count": "total"},
        ]
    ).to_list(1)
    registered_sessions = int(registered_rows[0].get("total") or 0) if registered_rows else 0
    guest_sessions = max(0, total_conversations - registered_sessions)

    unique_user_rows = await db[CONVERSATIONS].aggregate(
        [
            *_conversations_user_resolve_stages(),
            {"$match": {"resolved_user_id": {"$ne": None}}},
            {"$group": {"_id": "$resolved_user_id"}},
            {"$count": "total"},
        ]
    ).to_list(1)
    unique_users_with_sessions = (
        int(unique_user_rows[0].get("total") or 0) if unique_user_rows else 0
    )

    avg_messages = (
        round(total_messages / total_conversations, 1) if total_conversations else 0.0
    )

    clamped_days = max(1, min(days, 30))
    messages_by_day: list[dict[str, Any]] = []
    for offset in range(clamped_days - 1, -1, -1):
        day_start, day_end = _day_bounds(today_start - timedelta(days=offset))
        msg_count = await db[MESSAGES].count_documents(
            {"created_at": {"$gte": day_start, "$lt": day_end}}
        )
        session_count = await db[CONVERSATIONS].count_documents(
            {"updated_at": {"$gte": day_start, "$lt": day_end}}
        )
        new_sessions = await db[CONVERSATIONS].count_documents(
            {"created_at": {"$gte": day_start, "$lt": day_end}}
        )
        messages_by_day.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "label": day_start.strftime("%d/%m"),
                "messages": msg_count,
                "active_sessions": session_count,
                "new_sessions": new_sessions,
            }
        )

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "conversations_today": conversations_today,
        "messages_today": messages_today,
        "registered_sessions": registered_sessions,
        "guest_sessions": guest_sessions,
        "unique_users_with_sessions": unique_users_with_sessions,
        "with_summary": with_summary,
        "avg_messages_per_conversation": avg_messages,
        "messages_by_day": messages_by_day,
        "updated_at": now.isoformat(),
    }


async def get_admin_overview_stats(
    db: AsyncIOMotorDatabase,
    *,
    days: int = 7,
) -> dict[str, Any]:
    from app.auth.repository import USERS, get_user_by_id

    now = datetime.now(UTC)
    today_start, _ = _day_bounds(now)

    total_users = await db[USERS].count_documents({})
    total_conversations = await db[CONVERSATIONS].count_documents({})
    total_messages = await db[MESSAGES].count_documents({})

    messages_today = await db[MESSAGES].count_documents(
        {"created_at": {"$gte": today_start}}
    )
    conversations_today = await db[CONVERSATIONS].count_documents(
        {"created_at": {"$gte": today_start}}
    )

    month_start = today_start.replace(day=1)
    prev_month_end = month_start
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    users_this_month = await db[USERS].count_documents(
        {"created_at": {"$gte": month_start}}
    )
    users_prev_month = await db[USERS].count_documents(
        {"created_at": {"$gte": prev_month_start, "$lt": prev_month_end}}
    )
    user_growth_pct: float | None = None
    if users_prev_month > 0:
        user_growth_pct = round(
            ((users_this_month - users_prev_month) / users_prev_month) * 100, 1
        )

    messages_by_day: list[dict[str, Any]] = []
    clamped_days = max(1, min(days, 30))
    for offset in range(clamped_days - 1, -1, -1):
        day_start, day_end = _day_bounds(today_start - timedelta(days=offset))
        msg_count = await db[MESSAGES].count_documents(
            {"created_at": {"$gte": day_start, "$lt": day_end}}
        )
        session_count = await db[CONVERSATIONS].count_documents(
            {"updated_at": {"$gte": day_start, "$lt": day_end}}
        )
        messages_by_day.append(
            {
                "date": day_start.strftime("%Y-%m-%d"),
                "label": day_start.strftime("%d/%m"),
                "messages": msg_count,
                "active_sessions": session_count,
            }
        )

    completions_today = await db[ACTIVITY_COMPLETIONS].count_documents(
        {"created_at": {"$gte": today_start}}
    )
    total_completions = await db[ACTIVITY_COMPLETIONS].count_documents({})

    rating_rows = await db[WELLNESS_ACTIVITIES].aggregate(
        [
            {
                "$group": {
                    "_id": None,
                    "avg_rating": {"$avg": "$avg_rating"},
                    "total_ratings": {"$sum": "$rating_count"},
                }
            }
        ]
    ).to_list(1)
    avg_wellness_rating: float | None = None
    total_wellness_ratings = 0
    if rating_rows:
        avg_wellness_rating = rating_rows[0].get("avg_rating")
        total_wellness_ratings = int(rating_rows[0].get("total_ratings") or 0)
        if avg_wellness_rating is not None:
            avg_wellness_rating = round(float(avg_wellness_rating), 1)

    recent_conversations: list[dict[str, Any]] = []
    cursor = db[CONVERSATIONS].find({}).sort("updated_at", -1).limit(5)
    async for conv in cursor:
        user_label = "Khách"
        user_id = conv.get("user_id")
        if isinstance(user_id, ObjectId):
            user_doc = await get_user_by_id(db, user_id)
            if user_doc:
                user_label = str(user_doc.get("name") or user_doc.get("email") or "User")

        updated = conv.get("updated_at")
        recent_conversations.append(
            {
                "session_id": str(conv.get("session_id") or ""),
                "title": str(conv.get("title") or "Cuộc trò chuyện mới"),
                "user_label": user_label,
                "updated_at": updated.isoformat() if hasattr(updated, "isoformat") else None,
            }
        )

    return {
        "total_users": total_users,
        "users_this_month": users_this_month,
        "user_growth_pct": user_growth_pct,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "messages_today": messages_today,
        "conversations_today": conversations_today,
        "messages_by_day": messages_by_day,
        "wellness_completions_today": completions_today,
        "wellness_completions_total": total_completions,
        "avg_wellness_rating": avg_wellness_rating,
        "total_wellness_ratings": total_wellness_ratings,
        "recent_conversations": recent_conversations,
        "updated_at": now.isoformat(),
    }
