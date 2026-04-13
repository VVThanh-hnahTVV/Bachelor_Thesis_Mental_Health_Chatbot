"""Ensure MongoDB collections and indexes exist at application startup."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

USERS_COLLECTION = "users"

# Optional auth fields: omit from document until set. Never store plaintext passwords — use ``password_hash``.
USERS_JSON_SCHEMA: dict = {
    "bsonType": "object",
    "required": [
        "device_id",
        "created_at",
        "last_active",
        "platform",
        "locale",
        "settings",
    ],
    "properties": {
        "_id": {"bsonType": "objectId"},
        "device_id": {"bsonType": "string", "minLength": 1},
        "created_at": {"bsonType": "date"},
        "last_active": {"bsonType": "date"},
        "platform": {"enum": ["ios", "android", "web"]},
        "locale": {
            "bsonType": "string",
            "pattern": "^[a-z]{2}(-[A-Z]{2})?$",
        },
        "settings": {
            "bsonType": "object",
            "required": ["reminder_enabled", "notification_time"],
            "properties": {
                "reminder_enabled": {"bsonType": "bool"},
                "notification_time": {
                    "bsonType": "string",
                    "pattern": "^([01]\\d|2[0-3]):[0-5]\\d$",
                },
            },
            "additionalProperties": False,
        },
        "email": {
            "bsonType": "string",
            "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$",
        },
        "password_hash": {"bsonType": "string", "minLength": 1},
        "access_token": {"bsonType": ["string", "null"]},
        "refresh_token": {"bsonType": ["string", "null"]},
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

    coll = db[USERS_COLLECTION]
    await coll.create_index("device_id", unique=True)
    await coll.create_index(
        "email",
        unique=True,
        sparse=True,
        name="users_email_unique_sparse",
    )
    await coll.create_index([("last_active", -1)])
