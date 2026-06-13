"""Localized handoff copy."""

from __future__ import annotations

HANDOFF_CONSENT_NOTICE: dict[str, str] = {
    "vi": (
        "Khi bạn kết nối với chuyên gia, họ có thể đọc **tóm tắt** và **toàn bộ lịch sử chat** "
        "của cuộc trò chuyện này để hỗ trợ bạn tốt hơn.\n\n"
        "Bạn có thể **đồng ý và kết nối ngay**, hoặc **mở một phiên trò chuyện mới** "
        "rồi kết nối với chuyên gia ở đó. Nếu chưa sẵn sàng, cứ tiếp tục trò chuyện với tôi bình thường."
    ),
    "en": (
        "If you connect with a specialist, they can read the **summary** and **full chat history** "
        "of this conversation to support you better.\n\n"
        "You can **agree and connect now**, or **start a new chat session** "
        "and connect with a specialist there. If you're not ready, keep chatting with me as usual."
    ),
}

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


def handoff_consent_notice(language: str) -> str:
    lang = (language or "en").split("-", 1)[0].lower()
    return HANDOFF_CONSENT_NOTICE.get(lang, HANDOFF_CONSENT_NOTICE["en"])


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


OFF_TOPIC_SCOPE_NOTICE: dict[str, str] = {
    "vi": (
        "Mình là **Helios**, trợ lý hỗ trợ **thông tin và tư vấn về sức khỏe tâm thần** — "
        "cảm xúc, căng thẳng, tri thức y khoa liên quan, và gợi ý wellness nhẹ nhàng.\n\n"
        "Câu hỏi của bạn nằm **ngoài phạm vi** mình hỗ trợ. "
        "Bạn có muốn chia sẻ điều gì đang bận tâm, hoặc hỏi về chủ đề sức khỏe tâm thần / y tế không?"
    ),
    "en": (
        "I'm **Helios**, focused on **mental health information and supportive guidance** — "
        "emotions, stress, related medical topics, and gentle wellness suggestions.\n\n"
        "Your question is **outside what I can help with here**. "
        "Would you like to share what's on your mind, or ask about mental health / medical topics?"
    ),
}


def off_topic_scope_notice(language: str) -> str:
    lang = (language or "vi").split("-", 1)[0].lower()
    return OFF_TOPIC_SCOPE_NOTICE.get(lang, OFF_TOPIC_SCOPE_NOTICE["vi"])
