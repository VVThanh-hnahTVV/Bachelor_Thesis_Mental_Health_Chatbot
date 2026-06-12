"""Localized handoff copy."""

from __future__ import annotations

AWAITING_SUPPORT_ACK: dict[str, str] = {
    "vi": (
        "Tôi hiểu bạn muốn được hỗ trợ từ chuyên viên. "
        "Tôi đã chuyển yêu cầu — một chuyên viên sẽ tham gia sớm. "
        "Trong lúc chờ, bạn có thể tiếp tục mô tả tình huống."
    ),
    "en": (
        "I understand you'd like support from a counselor. "
        "I've forwarded your request — a specialist will join soon. "
        "While you wait, you can continue describing your situation."
    ),
}

SUPPORT_JOINED_NOTICE: dict[str, str] = {
    "vi": "{name} đã tham gia cuộc trò chuyện.",
    "en": "{name} has joined the conversation.",
}

SUPPORT_LEFT_NOTICE: dict[str, str] = {
    "vi": "Phiên hỗ trợ đã kết thúc. Bạn có thể tiếp tục trò chuyện với Helios nếu cần.",
    "en": "The support session has ended. You can continue chatting with Helios if needed.",
}

CLOSED_SESSION_NOTICE: dict[str, str] = {
    "vi": "Phiên trò chuyện này đã được đóng.",
    "en": "This conversation session has been closed.",
}

HUMAN_MODE_HTTP_HINT: dict[str, str] = {
    "vi": "Bạn đang trò chuyện với chuyên viên. Vui lòng gửi tin nhắn qua kết nối trực tiếp.",
    "en": "You are chatting with a counselor. Please send messages through the live connection.",
}


def handoff_ack(language: str) -> str:
    lang = (language or "en").split("-", 1)[0].lower()
    return AWAITING_SUPPORT_ACK.get(lang, AWAITING_SUPPORT_ACK["en"])


def support_joined_notice(name: str, language: str = "vi") -> str:
    lang = (language or "vi").split("-", 1)[0].lower()
    template = SUPPORT_JOINED_NOTICE.get(lang, SUPPORT_JOINED_NOTICE["en"])
    return template.format(name=name)


def support_left_notice(language: str = "vi") -> str:
    lang = (language or "vi").split("-", 1)[0].lower()
    return SUPPORT_LEFT_NOTICE.get(lang, SUPPORT_LEFT_NOTICE["en"])
