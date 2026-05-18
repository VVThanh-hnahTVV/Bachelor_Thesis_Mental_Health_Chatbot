"""UI metadata helpers: quick replies, micro-feedback eligibility."""
from __future__ import annotations

from typing import Any

from app.graph.nodes.response_generator import detect_language, is_meta_conversation

_QUICK_REPLIES_VI = [
    {"id": "listen", "label": "Lắng nghe", "message": "Tôi muốn được lắng nghe"},
    {"id": "breathe", "label": "Bài tập thở", "message": "Tôi muốn thử bài tập thở"},
    {"id": "learn", "label": "Tìm hiểu chủ đề", "message": "Tôi muốn tìm hiểu về sức khỏe tâm lý"},
]

_QUICK_REPLIES_EN = [
    {"id": "listen", "label": "Just listen", "message": "I'd like to be heard"},
    {"id": "breathe", "label": "Breathing exercise", "message": "I'd like to try a breathing exercise"},
    {"id": "learn", "label": "Learn more", "message": "I'd like to learn about mental wellness"},
]

_META_REPLY_VI = (
    "Chào bạn! Mình là Luna — người bạn đồng hành về sức khỏe tâm lý. "
    "Bạn muốn làm gì hôm nay?"
)

_META_REPLY_EN = (
    "Hi! I'm Luna — your mental wellness companion. "
    "What would you like to do today?"
)


def is_casual_or_meta(intent: str, user_input: str) -> bool:
    return intent == "casual" or is_meta_conversation(user_input)


_LEARN_PATTERNS = (
    "tìm hiểu",
    "tìm hieu",
    "learn about",
    "mental wellness",
    "sức khỏe tâm lý",
    "suc khoe tam ly",
    "muốn biết thêm",
    "want to learn",
)

_BREATHE_PATTERNS = (
    "bài tập thở",
    "hít thở",
    "breathing",
    "thử bài tập thở",
    "try a breathing",
)


def is_learn_exploration(user_input: str) -> bool:
    """User chose education path, not a tool session."""
    t = user_input.lower().strip()
    if any(p in t for p in _BREATHE_PATTERNS):
        return False
    return any(p in t for p in _LEARN_PATTERNS)


def is_breathe_request(user_input: str) -> bool:
    t = user_input.lower().strip()
    return any(p in t for p in _BREATHE_PATTERNS)


def is_substantive_reply(reply: str, *, min_chars: int = 140) -> bool:
    """Enough real content to ask 'did this help?' or show activity CTAs."""
    text = reply.strip()
    if len(text) < min_chars:
        return False
    # Clarifying-only: asks which topic without teaching yet
    low = text.lower()
    clarify_markers = (
        "chủ đề nào",
        "chủ đề cụ thể",
        "which topic",
        "what topic",
        "bạn đang quan tâm",
        "bạn muốn tìm hiểu",
        "mình sẽ chia sẻ",
    )
    if len(text) < 200 and any(m in low for m in clarify_markers):
        return False
    return True


def should_skip_wellness_suggestions(
    *,
    user_input: str,
    intent: str,
    therapy_strategy: str | None,
    reply: str,
) -> bool:
    if is_casual_or_meta(intent, user_input) or is_learn_exploration(user_input):
        return True
    if therapy_strategy == "psychoeducation" and not is_substantive_reply(reply, min_chars=120):
        return True
    return False


def should_skip_quick_replies(
    *,
    user_input: str,
    intent: str,
    therapy_strategy: str | None,
    objection_detected: bool,
    chat_blocked: bool,
    message_type: str,
) -> bool:
    """Skip chip generation when tap-to-send options would feel out of place."""
    if chat_blocked or message_type != "normal":
        return True
    if is_casual_or_meta(intent, user_input) or objection_detected:
        return True
    if therapy_strategy in ("stabilization",):
        return True
    return False


def get_quick_replies(lang: str) -> list[dict[str, str]]:
    return list(_QUICK_REPLIES_EN if lang == "en" else _QUICK_REPLIES_VI)


def get_meta_reply(lang: str) -> str:
    return _META_REPLY_EN if lang == "en" else _META_REPLY_VI


def should_show_micro_feedback(
    *,
    message_type: str,
    intent: str,
    user_input: str,
    therapy_strategy: str | None,
    reply: str,
    objection_detected: bool,
    chat_blocked: bool,
) -> bool:
    if chat_blocked or message_type != "normal":
        return False
    if is_casual_or_meta(intent, user_input) or objection_detected:
        return False
    if therapy_strategy == "stabilization":
        return False
    if is_learn_exploration(user_input):
        return False
    if not is_substantive_reply(reply, min_chars=140):
        return False
    return True
