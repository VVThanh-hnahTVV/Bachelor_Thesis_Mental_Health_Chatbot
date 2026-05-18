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

OPTIONS_VI = [
    "Không hề",
    "Vài ngày",
    "Hơn một nửa số ngày",
    "Gần như mỗi ngày",
]

DISCLAIMER_VI = (
    "Đây chỉ là khảo sát sàng lọc ngắn, không thay cho đánh giá lâm sàng. "
    "Nếu bạn lo lắng về sức khỏe tâm lý, hãy trao đổi với chuyên gia y tế."
)


def score_phq(answers: list[int]) -> int:
    return sum(max(0, min(3, int(a))) for a in answers)


def interpret_phq2(score: int) -> str:
    if score >= 3:
        return "Kết quả gợi ý nên theo dõi thêm hoặc trao đổi với chuyên gia."
    return "Điểm sàng lọc thấp — tiếp tục chăm sóc bản thân và theo dõi cảm xúc."


def get_questions(instrument: str) -> list[str]:
    if instrument == "phq4":
        return list(PHQ4_QUESTIONS_VI)
    return list(PHQ2_QUESTIONS_VI)
