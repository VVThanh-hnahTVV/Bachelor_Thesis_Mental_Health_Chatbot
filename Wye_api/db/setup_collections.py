"""Ensure MongoDB collections and indexes exist at application startup."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

USERS_COLLECTION = "users"
CONVERSATIONS_COLLECTION = "conversations"
MESSAGES_COLLECTION = "messages"

USERS_JSON_SCHEMA: dict = {
    "bsonType": "object",
    "required": [
        "name",
        "email",
        "password_hash",
        "created_at",
        "updated_at",
    ],
    "properties": {
        "_id": {"bsonType": "objectId"},
        "name": {"bsonType": "string", "minLength": 1},
        "email": {
            "bsonType": "string",
            "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
        },
        "password_hash": {"bsonType": "string", "minLength": 1},
        "created_at": {"bsonType": "date"},
        "updated_at": {"bsonType": "date"},
        "last_login_at": {"bsonType": ["date", "null"]},
    },
    "additionalProperties": False,
}

CONVERSATIONS_JSON_SCHEMA: dict = {
    "bsonType": "object",
    "required": ["user_id", "title", "created_at", "updated_at"],
    "properties": {
        "_id": {"bsonType": "objectId"},
        "user_id": {"bsonType": "objectId"},
        "title": {"bsonType": "string", "minLength": 1, "maxLength": 120},
        "created_at": {"bsonType": "date"},
        "updated_at": {"bsonType": "date"},
        "last_message_preview": {"bsonType": ["string", "null"], "maxLength": 500},
    },
    "additionalProperties": False,
}

MESSAGES_JSON_SCHEMA: dict = {
    "bsonType": "object",
    "required": ["conversation_id", "user_id", "role", "content", "created_at"],
    "properties": {
        "_id": {"bsonType": "objectId"},
        "conversation_id": {"bsonType": "objectId"},
        "user_id": {"bsonType": "objectId"},
        "role": {"enum": ["user", "assistant"]},
        "content": {"bsonType": "string", "minLength": 1, "maxLength": 4000},
        "created_at": {"bsonType": "date"},
    },
    "additionalProperties": False,
}


async def ensure_users_collection(db: AsyncIOMotorDatabase) -> None:
    """Create ``users`` with JSON Schema validation if missing; always ensure indexes."""
    names = await db.list_collection_names()
    if USERS_COLLECTION not in names:
        await db.create_collection(
            USERS_COLLECTION,
            validator={"$jsonSchema": USERS_JSON_SCHEMA},
            validationLevel="strict",
            validationAction="error",
        )
    else:
        await db.command(
            {
                "collMod": USERS_COLLECTION,
                "validator": {"$jsonSchema": USERS_JSON_SCHEMA},
                "validationLevel": "strict",
                "validationAction": "error",
            }
        )

    coll = db[USERS_COLLECTION]
    index_info = await coll.index_information()
    for index_name in ("users_email_unique_sparse", "device_id_1", "last_active_-1"):
        if index_name in index_info:
            await coll.drop_index(index_name)

    await coll.create_index(
        "email",
        unique=True,
        name="users_email_unique",
    )


async def ensure_conversations_collection(db: AsyncIOMotorDatabase) -> None:
    """Create ``conversations`` with JSON Schema validation if missing; always ensure indexes."""
    names = await db.list_collection_names()
    if CONVERSATIONS_COLLECTION not in names:
        await db.create_collection(
            CONVERSATIONS_COLLECTION,
            validator={"$jsonSchema": CONVERSATIONS_JSON_SCHEMA},
            validationLevel="strict",
            validationAction="error",
        )
    else:
        await db.command(
            {
                "collMod": CONVERSATIONS_COLLECTION,
                "validator": {"$jsonSchema": CONVERSATIONS_JSON_SCHEMA},
                "validationLevel": "strict",
                "validationAction": "error",
            }
        )

    coll = db[CONVERSATIONS_COLLECTION]
    await coll.create_index([("user_id", 1), ("updated_at", -1)], name="conversations_user_updated_idx")


async def ensure_messages_collection(db: AsyncIOMotorDatabase) -> None:
    """Create ``messages`` with JSON Schema validation if missing; always ensure indexes."""
    names = await db.list_collection_names()
    if MESSAGES_COLLECTION not in names:
        await db.create_collection(
            MESSAGES_COLLECTION,
            validator={"$jsonSchema": MESSAGES_JSON_SCHEMA},
            validationLevel="strict",
            validationAction="error",
        )
    else:
        await db.command(
            {
                "collMod": MESSAGES_COLLECTION,
                "validator": {"$jsonSchema": MESSAGES_JSON_SCHEMA},
                "validationLevel": "strict",
                "validationAction": "error",
            }
        )

    coll = db[MESSAGES_COLLECTION]
    await coll.create_index(
        [("conversation_id", 1), ("created_at", 1)],
        name="messages_conversation_created_idx",
    )
    await coll.create_index([("user_id", 1), ("created_at", -1)], name="messages_user_created_idx")
