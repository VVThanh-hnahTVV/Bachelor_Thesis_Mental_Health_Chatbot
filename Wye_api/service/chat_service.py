from __future__ import annotations

from datetime import UTC, datetime

from bson import ObjectId
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from motor.motor_asyncio import AsyncIOMotorDatabase

from config import get_llm_registry
from db.setup_collections import CONVERSATIONS_COLLECTION, MESSAGES_COLLECTION


def pick_chat_models():
    registry = get_llm_registry()
    return [model for model in (registry.gemini, registry.openai, registry.groq) if model is not None]


CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are Wye, a supportive mental wellness assistant. "
            "Keep answers empathetic, short, and practical. "
            "Do not provide medical diagnosis.",
        ),
        ("human", "{user_input}"),
    ]
)
OUTPUT_PARSER = StrOutputParser()


async def generate_assistant_reply(user_content: str) -> str:
    models = pick_chat_models()
    if not models:
        return "Mình chưa thể phản hồi lúc này vì backend chưa được cấu hình API key cho LLM."

    last_error: Exception | None = None
    for model in models:
        try:
            chain = CHAT_PROMPT | model | OUTPUT_PARSER
            reply = (await chain.ainvoke({"user_input": user_content})).strip()
            if reply:
                return reply
        except Exception as exc:
            last_error = exc
            print(f"[chat_service] LLM call failed on {type(model).__name__}: {exc}")
            continue

    if last_error is not None:
        return "Mình chưa thể trả lời do nhà cung cấp AI đang lỗi thanh toán hoặc tạm thời không khả dụng."
    return "Mình đang ở đây với bạn. Bạn có thể chia sẻ thêm để mình hỗ trợ tốt hơn."


async def persist_user_message_and_reply(
    db: AsyncIOMotorDatabase,
    *,
    conversation_id: ObjectId,
    user_id: ObjectId,
    content: str,
) -> tuple[dict, dict]:
    conversations = db[CONVERSATIONS_COLLECTION]
    messages = db[MESSAGES_COLLECTION]

    now = datetime.now(UTC)
    user_doc = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "role": "user",
        "content": content,
        "created_at": now,
    }
    user_insert = await messages.insert_one(user_doc)
    user_doc["_id"] = user_insert.inserted_id
    await conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"updated_at": now, "last_message_preview": content[:500]}},
    )

    assistant_content = await generate_assistant_reply(content)
    assistant_now = datetime.now(UTC)
    assistant_doc = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "role": "assistant",
        "content": assistant_content,
        "created_at": assistant_now,
    }
    assistant_insert = await messages.insert_one(assistant_doc)
    assistant_doc["_id"] = assistant_insert.inserted_id
    await conversations.update_one(
        {"_id": conversation_id, "user_id": user_id},
        {"$set": {"updated_at": assistant_now, "last_message_preview": assistant_content[:500]}},
    )

    return user_doc, assistant_doc
