"""Node 7 / background task: memory_update — extract and persist long-term user profile."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import ProviderName
from app.llm.factory import get_chat_model, invoke_with_fallback

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are extracting structured information from a single therapy chat turn.
Return ONLY valid JSON with these optional fields (omit fields with no new info):

{
  "new_stressors": ["<stressor>", ...],
  "coping_pref": "<preference or null>",
  "tone_pref": "gentle" | "direct" | "informative" | null
}

Rules:
- new_stressors: concrete recurring stressors mentioned ("thi cử", "áp lực công việc", "chia tay")
- coping_pref: if user expressed preference for a coping style ("tôi thích viết nhật ký", "nghe nhạc giúp tôi")
- tone_pref: inferred preferred tone; null if unclear
- If nothing new to extract, return {}
"""


async def run_memory_update(
    db: Any,
    session_id: str,
    user_input: str,
    assistant_reply: str,
    provider: ProviderName,
) -> None:
    """Fire-and-forget: extract insights from current turn and upsert user profile."""
    if db is None or not session_id:
        return
    try:
        llm = get_chat_model(provider)
        content = f"User: {user_input}\nAssistant: {assistant_reply}"
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=content)],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        m = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
        if not m:
            return
        data: dict[str, Any] = json.loads(m.group())
        if not data:
            return

        updates: dict[str, Any] = {}
        if data.get("new_stressors"):
            updates["recurring_stressors"] = data["new_stressors"]
        if data.get("coping_pref"):
            updates["coping_preferences"] = [data["coping_pref"]]
        if data.get("tone_pref"):
            updates["preferred_tone"] = data["tone_pref"]

        if updates:
            from app.db.repository import upsert_user_profile
            await upsert_user_profile(db, session_id, updates)
    except Exception as exc:
        logger.warning("memory_update failed (non-critical): %s", exc)
