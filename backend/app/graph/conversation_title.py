"""Generate a short conversation title from the user's first message."""
from __future__ import annotations

import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.graph.nodes.response_generator import detect_language
from app.llm.factory import default_provider, get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM = """\
Write a very short chat session title (3–8 words) based on the user's first message.
- Match the message language (Vietnamese or English).
- Capture the main topic or feeling; no quotes, no punctuation at the end.
- Do not mention Luna, Helios, AI, or therapy.
- Output only the title text, nothing else.
"""


def _sanitize_title(raw: str, *, max_len: int = 48) -> str:
    text = raw.strip().strip("\"'`")
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


async def generate_conversation_title(
    user_message: str,
    *,
    provider: ProviderName | None = None,
) -> str:
    msg = user_message.strip()
    if not msg:
        return "New conversation"

    lang = detect_language(msg, [])
    fallback = msg if len(msg) <= 40 else f"{msg[:39].rstrip()}…"

    try:
        llm = get_chat_model(provider or default_provider())
        response = await invoke_with_fallback(
            llm,
            [
                SystemMessage(content=_SYSTEM),
                HumanMessage(
                    content=(
                        f"Language hint: {'Vietnamese' if lang == 'vi' else 'English'}\n"
                        f"First user message:\n{msg}"
                    )
                ),
            ],
            primary=provider or default_provider(),
        )
        text = response.content if isinstance(response.content, str) else str(response.content)
        title = _sanitize_title(text)
        return title or fallback
    except Exception as exc:
        logger.warning("conversation title generation failed: %s", exc)
        return fallback
