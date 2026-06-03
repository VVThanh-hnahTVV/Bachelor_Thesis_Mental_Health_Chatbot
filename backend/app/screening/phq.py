"""PHQ-2 / PHQ-4 scoring (screening only — not diagnostic)."""
from __future__ import annotations

PHQ2_QUESTIONS_VI = [
    "Trong 2 tuần qua, bạn có ít hứng thú hoặc vui khi làm việc không?",
    "Trong 2 tuần qua, bạn có cảm thấy buồn, chán nản hoặc tuyệt vọng không?",
]

PHQ4_QUESTIONS_VI = PHQ2_QUESTIONS_VI + [
    "Trong 2 tuần qua, bạn có khó ngủ, ngủ không yên hoặc ngủ quá nhiều không?",
    "Trong 2 tuần qua, bạn có cảm thấy mệt hoặc thiếu năng lượng không?",
]

PHQ2_QUESTIONS_EN = [
    "Over the last 2 weeks, have you had little interest or pleasure in doing things?",
    "Over the last 2 weeks, have you felt down, depressed, or hopeless?",
]

PHQ4_QUESTIONS_EN = PHQ2_QUESTIONS_EN + [
    "Over the last 2 weeks, have you had trouble sleeping or slept too much?",
    "Over the last 2 weeks, have you felt tired or had little energy?",
]

OPTIONS_VI = [
    "Không hề",
    "Vài ngày",
    "Hơn một nửa số ngày",
    "Gần như mỗi ngày",
]

OPTIONS_EN = [
    "Not at all",
    "Several days",
    "More than half the days",
    "Nearly every day",
]

DISCLAIMER_VI = (
    "Đây chỉ là khảo sát sàng lọc ngắn, không thay cho đánh giá lâm sàng. "
    "Nếu bạn lo lắng về sức khỏe tâm lý, hãy trao đổi với chuyên gia y tế."
)

DISCLAIMER_EN = (
    "This is a brief screening survey, not a clinical diagnosis. "
    "If you are concerned about your mental health, please speak with a healthcare professional."
)


def score_phq(answers: list[int]) -> int:
    return sum(max(0, min(3, int(a))) for a in answers)


def interpret_phq2(score: int, lang: str = "en") -> str:
    if lang == "vi":
        if score >= 3:
            return "Kết quả gợi ý nên theo dõi thêm hoặc trao đổi với chuyên gia."
        return "Điểm sàng lọc thấp — tiếp tục chăm sóc bản thân và theo dõi cảm xúc."
    if score >= 3:
        return "Your score suggests follow-up or a conversation with a professional may help."
    return "Low screening score — keep caring for yourself and monitoring how you feel."


def get_questions(instrument: str, lang: str = "en") -> list[str]:
    use_vi = lang == "vi"
    if instrument == "phq4":
        return list(PHQ4_QUESTIONS_VI if use_vi else PHQ4_QUESTIONS_EN)
    return list(PHQ2_QUESTIONS_VI if use_vi else PHQ2_QUESTIONS_EN)


def get_options(lang: str = "en") -> list[str]:
    return list(OPTIONS_VI if lang == "vi" else OPTIONS_EN)


def get_disclaimer(lang: str = "en") -> str:
    return DISCLAIMER_VI if lang == "vi" else DISCLAIMER_EN
