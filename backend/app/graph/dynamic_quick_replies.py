"""Contextual follow-up chips — LLM decides when to offer them and what they say."""
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
Generate exactly 3 tap-to-send reply chips so the user can respond to Luna's last message.

ALWAYS set offer_chips: true and provide exactly 3 options unless the user message is crisis-adjacent.

Rules:
- Labels: max 22 characters; match conversation language (Vietnamese or English).
- message: first-person sentence the user would send (not a duplicate of the label).
- Options must fit Luna's last message — answer her question or continue the emotional thread.
- For grounding/stabilization: offer chips like "I tried it", "Not yet", "I need to talk more".
- For reflective listening: offer chips that open the story (feelings, relationship, need to be heard).
- Do NOT suggest breathing apps, generic menus, or unrelated topics.

JSON only:
{"offer_chips": true, "options": [{"id": "1", "label": "...", "message": "..."}, ...]}
"""


def _parse_llm_response(raw: str) -> tuple[bool, list[dict[str, str]]]:
    text = raw.strip()
    if "```" in text:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
        if m:
            text = m.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return False, []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return False, []

    offer = bool(data.get("offer_chips", False))
    opts = data.get("options") or data.get("quick_replies") or []
    if not offer or not isinstance(opts, list):
        return False, []

    out: list[dict[str, str]] = []
    for i, item in enumerate(opts[:3]):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()[:28]
        message = str(item.get("message", label)).strip()
        if not label:
            continue
        out.append({"id": str(item.get("id", f"llm{i}")), "label": label, "message": message})

    if not out:
        return False, []
    return True, out


async def generate_follow_up_quick_replies(
    *,
    user_input: str,
    assistant_reply: str,
    lang: str,
    provider: ProviderName,
    intent: str = "",
    emotion: str | None = None,
    therapy_strategy: str | None = None,
) -> list[dict[str, str]]:
    """Return contextual chips when the LLM judges them helpful, else []."""
    reply = assistant_reply.strip()
    if len(reply) < 12:
        return []

    human = (
        f"language: {lang}\n"
        f"user_last_message: {user_input}\n"
        f"luna_last_message: {assistant_reply}\n"
        f"intent: {intent or 'unknown'}\n"
        f"emotion: {emotion or 'unknown'}\n"
        f"therapy_strategy: {therapy_strategy or 'unknown'}\n"
    )
    try:
        llm = get_chat_model(provider)
        msg = await invoke_with_fallback(
            llm,
            [SystemMessage(content=_SYSTEM), HumanMessage(content=human)],
            primary=provider,
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        offer, options = _parse_llm_response(raw)
        if offer and options:
            return options[:3]
    except Exception as exc:
        logger.warning("dynamic quick replies LLM failed: %s", exc)

    return []
