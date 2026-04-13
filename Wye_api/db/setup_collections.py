"""Ensure MongoDB collections and indexes exist at application startup."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase

USERS_COLLECTION = "users"

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
