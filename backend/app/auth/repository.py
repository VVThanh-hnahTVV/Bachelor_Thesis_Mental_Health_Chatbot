from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repository import (
    ACTIVITY_COMPLETIONS,
    CONVERSATIONS,
    create_conversation,
    get_conversation_by_session,
)

USERS = "users"
SESSION_LINKS = "session_links"


async def ensure_auth_indexes(db: AsyncIOMotorDatabase) -> None:
    await db[USERS].create_index([("email", 1)], unique=True)
    await db[USERS].create_index(
        [("password_reset_token_hash", 1)],
        sparse=True,
        name="password_reset_token_hash_sparse",
    )
    await db[SESSION_LINKS].create_index([("session_id", 1)], unique=True)
    await db[SESSION_LINKS].create_index([("user_id", 1)])


async def get_user_by_email(db: AsyncIOMotorDatabase, email: str) -> dict[str, Any] | None:
    return await db[USERS].find_one({"email": email.lower().strip()})


async def get_user_by_id(db: AsyncIOMotorDatabase, user_id: ObjectId) -> dict[str, Any] | None:
    return await db[USERS].find_one({"_id": user_id})


async def get_session_link_by_session_id(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> dict[str, Any] | None:
    return await db[SESSION_LINKS].find_one({"session_id": session_id})


async def is_session_owned_by_user(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
    user_id: ObjectId,
) -> bool:
    doc = await get_session_link_by_session_id(db, session_id)
    if not doc:
        return False
    owner = doc.get("user_id")
    return isinstance(owner, ObjectId) and owner == user_id


async def create_user(
    db: AsyncIOMotorDatabase,
    *,
    email: str,
    name: str,
    password_hash: str,
    role: str = "user",
) -> dict[str, Any]:
    now = datetime.now(UTC)
    doc = {
        "email": email.lower().strip(),
        "name": name.strip(),
        "password_hash": password_hash,
        "role": role if role in ("user", "admin", "support") else "user",
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
        "role": str(doc.get("role") or "user"),
    }


def admin_user_public(doc: dict[str, Any]) -> dict[str, Any]:
    created = doc.get("created_at")
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "name": doc["name"],
        "role": str(doc.get("role") or "user"),
        "created_at": created.isoformat() if hasattr(created, "isoformat") else None,
    }


def _users_filter_query(
    *,
    search: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if role in ("user", "admin", "support"):
        query["role"] = role
    if search and search.strip():
        term = search.strip()
        query["$or"] = [
            {"email": {"$regex": term, "$options": "i"}},
            {"name": {"$regex": term, "$options": "i"}},
        ]
    return query


async def count_users(
    db: AsyncIOMotorDatabase,
    *,
    search: str | None = None,
    role: str | None = None,
) -> int:
    return await db[USERS].count_documents(_users_filter_query(search=search, role=role))


async def count_admins(db: AsyncIOMotorDatabase) -> int:
    return await db[USERS].count_documents({"role": "admin"})


async def list_users(
    db: AsyncIOMotorDatabase,
    *,
    skip: int = 0,
    limit: int = 20,
    search: str | None = None,
    role: str | None = None,
) -> list[dict[str, Any]]:
    query = _users_filter_query(search=search, role=role)
    cursor = (
        db[USERS]
        .find(query, {"password_hash": 0, "password_reset_token_hash": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    return [admin_user_public(doc) async for doc in cursor]


async def update_user_by_id(
    db: AsyncIOMotorDatabase,
    user_id: ObjectId,
    *,
    name: str | None = None,
    role: str | None = None,
    password_hash: str | None = None,
) -> dict[str, Any] | None:
    updates: dict[str, Any] = {"updated_at": datetime.now(UTC)}
    if name is not None:
        updates["name"] = name.strip()
    if role is not None:
        if role not in ("user", "admin", "support"):
            raise ValueError("role must be user, admin, or support")
        updates["role"] = role
    if password_hash is not None:
        updates["password_hash"] = password_hash

    if len(updates) == 1:
        doc = await get_user_by_id(db, user_id)
        return admin_user_public(doc) if doc else None

    result = await db[USERS].update_one({"_id": user_id}, {"$set": updates})
    if result.matched_count == 0:
        return None
    doc = await get_user_by_id(db, user_id)
    return admin_user_public(doc) if doc else None


async def delete_user_by_id(db: AsyncIOMotorDatabase, user_id: ObjectId) -> bool:
    result = await db[USERS].delete_one({"_id": user_id})
    if result.deleted_count == 0:
        return False
    await db[SESSION_LINKS].delete_many({"user_id": user_id})
    return True


async def set_user_role(
    db: AsyncIOMotorDatabase,
    *,
    email: str,
    role: str,
) -> dict[str, Any] | None:
    if role not in ("user", "admin", "support"):
        raise ValueError("role must be user, admin, or support")
    await db[USERS].update_one(
        {"email": email.lower().strip()},
        {"$set": {"role": role, "updated_at": datetime.now(UTC)}},
    )
    return await get_user_by_email(db, email)


async def delete_session_link(
    db: AsyncIOMotorDatabase,
    *,
    session_id: str,
) -> None:
    await db[SESSION_LINKS].delete_one({"session_id": session_id})


async def set_password_reset_token(
    db: AsyncIOMotorDatabase,
    *,
    user_id: ObjectId,
    token_hash: str,
    expires_at: datetime,
) -> None:
    await db[USERS].update_one(
        {"_id": user_id},
        {
            "$set": {
                "password_reset_token_hash": token_hash,
                "password_reset_expires_at": expires_at,
                "updated_at": datetime.now(UTC),
            }
        },
    )


async def get_user_by_reset_token_hash(
    db: AsyncIOMotorDatabase,
    token_hash: str,
) -> dict[str, Any] | None:
    now = datetime.now(UTC)
    return await db[USERS].find_one(
        {
            "password_reset_token_hash": token_hash,
            "password_reset_expires_at": {"$gt": now},
        }
    )


async def update_user_password(
    db: AsyncIOMotorDatabase,
    *,
    user_id: ObjectId,
    password_hash: str,
) -> None:
    await db[USERS].update_one(
        {"_id": user_id},
        {
            "$set": {
                "password_hash": password_hash,
                "updated_at": datetime.now(UTC),
            },
            "$unset": {
                "password_reset_token_hash": "",
                "password_reset_expires_at": "",
            },
        },
    )


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
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        await create_conversation(db, session_id=session_id, user_id=user_id)
    else:
        await db[CONVERSATIONS].update_one(
            {"session_id": session_id},
            {"$set": {"user_id": user_id}},
        )

    user_ref = user_id
    await db[ACTIVITY_COMPLETIONS].update_many(
        {"session_id": session_id},
        {"$set": {"user_id": user_ref}},
    )


async def resolve_user_id_for_session(
    db: AsyncIOMotorDatabase,
    session_id: str,
) -> ObjectId | None:
    """Resolve user_id from session_links first, then conversations.user_id."""
    link = await get_session_link_by_session_id(db, session_id)
    if link:
        linked = link.get("user_id")
        if isinstance(linked, ObjectId):
            return linked
    conv = await get_conversation_by_session(db, session_id)
    if conv:
        owner = conv.get("user_id")
        if isinstance(owner, ObjectId):
            return owner
    return None


async def get_user_long_term_memory(
    db: AsyncIOMotorDatabase,
    user_id: ObjectId,
) -> str:
    doc = await get_user_by_id(db, user_id)
    if not doc:
        return ""
    memory = doc.get("long_term_memory")
    return str(memory).strip() if memory else ""


async def update_user_long_term_memory(
    db: AsyncIOMotorDatabase,
    user_id: ObjectId,
    memory: str,
) -> None:
    now = datetime.now(UTC)
    await db[USERS].update_one(
        {"_id": user_id},
        {
            "$set": {
                "long_term_memory": memory,
                "long_term_memory_updated_at": now,
                "updated_at": now,
            }
        },
    )
