"""Wysa-style gradual crisis escalation with intent-aware branching.

Stage machine:
  NONE → (crisis detected) → CONCERN
  CONCERN → need_more_help       → HUMAN_ESCALATION
  CONCERN → just_overwhelmed     → OVERWHELM
  CONCERN → misunderstood        → SAFETY_WATCH
  CONCERN → someone_else         → SOMEONE_ELSE
  HUMAN_ESCALATION → show_emergency / help_message_someone → stays
  HUMAN_ESCALATION → i_am_safe_now → NONE
  OVERWHELM → activity chip      → OVERWHELM_DOING
  OVERWHELM_DOING → done_activity → OVERWHELM_CHECK
  OVERWHELM_CHECK → feel_better_yes → RECOVERY
  OVERWHELM_CHECK → feel_better_no  → OVERWHELM_NOT_BETTER
  OVERWHELM_NOT_BETTER → not_better_need_help → HUMAN_ESCALATION
  OVERWHELM_NOT_BETTER → try_another          → OVERWHELM
  OVERWHELM_NOT_BETTER → not_better_back_to_chat → NONE
  RECOVERY → back_to_conversation / end_for_now → NONE
  SAFETY_WATCH → sw_back_to_chat / explain_more → NONE
  SOMEONE_ELSE → triage chip       → SOMEONE_ELSE_FOLLOWUP
  SOMEONE_ELSE → back_to_chat      → NONE
  SOMEONE_ELSE_FOLLOWUP → back_to_chat → NONE
  CONFIRM (legacy) → confirm_self_harm / talk_to_someone → SOS
  SOS → feel_safer / return_chat → NONE
"""
from __future__ import annotations

import json
from enum import Enum
from typing import TypedDict

from redis.asyncio import Redis

from app.graph.safety_engine import SafetyResult, crisis_reply_for_language

TTL_SEC = 7200

CRISIS_CHIP_PREFIX = "__crisis_id__:"
# Legacy / mistyped prefixes still accepted when parsing
_CRISIS_CHIP_PREFIX_ALIASES = (CRISIS_CHIP_PREFIX, "crisis_id:", "__crisis_id:")


class CrisisStage(str, Enum):
    NONE = "none"
    CONCERN = "concern"
    CONFIRM = "confirm"           # legacy — kept for backward compat
    SOS = "sos"
    # Intent-branching paths
    HUMAN_ESCALATION = "human_escalation"         # "Yes, I need more help"
    OVERWHELM = "overwhelm"                       # activity choice
    OVERWHELM_DOING = "overwhelm_doing"           # during chosen activity
    OVERWHELM_CHECK = "overwhelm_check"           # "do you feel better?"
    OVERWHELM_NOT_BETTER = "overwhelm_not_better" # "not really" options
    SAFETY_WATCH = "safety_watch"                 # after misunderstood
    SOMEONE_ELSE = "someone_else"                 # triage: how bad?
    SOMEONE_ELSE_FOLLOWUP = "someone_else_followup"  # after triage
    RECOVERY = "recovery"                         # "yes, I feel better"


class CrisisChoice(TypedDict):
    id: str
    label: str


class CrisisEscalationState(TypedDict, total=False):
    crisis_stage: str
    high_risk_turns: int
    user_acknowledged_risk: bool
    last_chip_id: str | None


# ---------------------------------------------------------------------------
# Chip → LLM strategy mapping
# ---------------------------------------------------------------------------

CHIP_STRATEGY: dict[str, str] = {
    # Legacy / SOS
    "crisis:share_more": "crisis_listen",
    "crisis:breathing_light": "crisis_grounding",
    "crisis:ack_safety_concern": "crisis_safety_check",
    "crisis:confirm_self_harm": "crisis_safety_check",
    "crisis:deny_self_harm": "crisis_reassure",
    "crisis:talk_to_someone": "crisis_connect",
    "crisis:breathing": "crisis_grounding",
    "crisis:ocean": "crisis_grounding",
    "crisis:hotline": "crisis_resources",
    "crisis:feel_safer": "crisis_reassure",
    "crisis:return_chat": "crisis_reassure",
    # Triage chips
    "crisis:need_more_help": "crisis_safety_check",
    "crisis:just_overwhelmed": "crisis_grounding",
    "crisis:misunderstood": "crisis_reassure",
    "crisis:someone_else": "crisis_listen",
    # Human-escalation
    "crisis:show_emergency": "crisis_resources",
    "crisis:help_message_someone": "crisis_connect",
    "crisis:i_am_safe_now": "crisis_reassure",
    # Overwhelm activity choice
    "crisis:slow_breathing": "crisis_grounding",
    "crisis:calming_music": "crisis_grounding",
    "crisis:grounding_exercise": "crisis_grounding",
    # During / after activity
    "crisis:done_activity": "crisis_grounding",
    "crisis:feel_better_yes": "crisis_reassure",
    "crisis:feel_better_no": "crisis_safety_check",
    # Not-better options
    "crisis:not_better_need_help": "crisis_safety_check",
    "crisis:try_another": "crisis_grounding",
    "crisis:not_better_back_to_chat": "crisis_reassure",
    # Recovery
    "crisis:back_to_conversation": "crisis_reassure",
    "crisis:end_for_now": "crisis_reassure",
    # Safety-watch
    "crisis:sw_back_to_chat": "crisis_reassure",
    "crisis:explain_more": "crisis_listen",
    # Someone-else triage
    "crisis:they_in_danger": "crisis_resources",
    "crisis:they_safe_struggling": "crisis_listen",
    "crisis:they_not_sure": "crisis_listen",
    "crisis:back_to_chat": "crisis_reassure",
}

# Chips that count as de-escalation (do NOT bump high_risk_turns)
_DEESCALATION_CHIP_IDS = frozenset({
    "crisis:share_more",
    "crisis:breathing_light",
    "crisis:deny_self_harm",
    "crisis:feel_safer",
    "crisis:return_chat",
    "crisis:just_overwhelmed",
    "crisis:misunderstood",
    "crisis:slow_breathing",
    "crisis:calming_music",
    "crisis:grounding_exercise",
    "crisis:done_activity",
    "crisis:feel_better_yes",
    "crisis:back_to_conversation",
    "crisis:end_for_now",
    "crisis:i_am_safe_now",
    "crisis:someone_else",
    "crisis:they_in_danger",
    "crisis:they_safe_struggling",
    "crisis:they_not_sure",
    "crisis:back_to_chat",
    "crisis:sw_back_to_chat",
    "crisis:explain_more",
    "crisis:not_better_back_to_chat",
    "crisis:try_another",
    "crisis:show_emergency",
    "crisis:help_message_someone",
})


# ---------------------------------------------------------------------------
# Chip definitions (VI / EN)
# ---------------------------------------------------------------------------

_CHIPS: dict[CrisisStage, dict[str, list[CrisisChoice]]] = {
    CrisisStage.CONCERN: {
        "vi": [
            {"id": "crisis:need_more_help",   "label": "Có, tôi cần thêm giúp đỡ"},
            {"id": "crisis:just_overwhelmed", "label": "Không, tôi chỉ đang quá tải"},
            {"id": "crisis:misunderstood",    "label": "Bạn hiểu sai rồi"},
            {"id": "crisis:someone_else",     "label": "Đây là về người khác"},
        ],
        "en": [
            {"id": "crisis:need_more_help",   "label": "Yes, I need more help"},
            {"id": "crisis:just_overwhelmed", "label": "No, just feeling overwhelmed"},
            {"id": "crisis:misunderstood",    "label": "You misunderstood"},
            {"id": "crisis:someone_else",     "label": "It's someone else"},
        ],
    },
    CrisisStage.CONFIRM: {  # legacy
        "vi": [
            {"id": "crisis:confirm_self_harm", "label": "Có, mình đang nghĩ tự làm hại"},
            {"id": "crisis:deny_self_harm",    "label": "Không, chỉ buồn thôi"},
            {"id": "crisis:talk_to_someone",   "label": "Mình muốn nói với người thân"},
        ],
        "en": [
            {"id": "crisis:confirm_self_harm", "label": "Yes, I'm thinking of hurting myself"},
            {"id": "crisis:deny_self_harm",    "label": "No, I'm just very sad"},
            {"id": "crisis:talk_to_someone",   "label": "I want to talk to someone I trust"},
        ],
    },
    CrisisStage.SOS: {
        "vi": [
            {"id": "crisis:breathing",    "label": "Tôi muốn thử bài tập hít thở"},
            {"id": "crisis:ocean",        "label": "Cho tôi nghe âm sóng thư giãn"},
            {"id": "crisis:hotline",      "label": "Tôi muốn xem số điện thoại hỗ trợ"},
            {"id": "crisis:feel_safer",   "label": "Tôi cảm thấy đỡ hơn một chút rồi"},
            {"id": "crisis:return_chat",  "label": "Quay lại trò chuyện bình thường"},
        ],
        "en": [
            {"id": "crisis:breathing",    "label": "I want to try a breathing exercise"},
            {"id": "crisis:ocean",        "label": "Play calming ocean sounds"},
            {"id": "crisis:hotline",      "label": "Show me support numbers"},
            {"id": "crisis:feel_safer",   "label": "I feel a little safer now"},
            {"id": "crisis:return_chat",  "label": "Return to normal conversation"},
        ],
    },
    CrisisStage.HUMAN_ESCALATION: {
        "vi": [
            {"id": "crisis:show_emergency",       "label": "Xem số liên hệ khẩn cấp"},
            {"id": "crisis:help_message_someone", "label": "Giúp tôi nhắn tin cho người thân"},
            {"id": "crisis:i_am_safe_now",        "label": "Tôi đang an toàn rồi"},
        ],
        "en": [
            {"id": "crisis:show_emergency",       "label": "Show emergency contacts"},
            {"id": "crisis:help_message_someone", "label": "Help me message someone I trust"},
            {"id": "crisis:i_am_safe_now",        "label": "I am safe now"},
        ],
    },
    CrisisStage.OVERWHELM: {
        "vi": [
            {"id": "crisis:slow_breathing",    "label": "Hít thở chậm"},
            {"id": "crisis:calming_music",     "label": "Nhạc thư giãn"},
            {"id": "crisis:grounding_exercise","label": "Bài tập hiện diện"},
        ],
        "en": [
            {"id": "crisis:slow_breathing",    "label": "Slow breathing"},
            {"id": "crisis:calming_music",     "label": "Calming music"},
            {"id": "crisis:grounding_exercise","label": "Grounding exercise"},
        ],
    },
    CrisisStage.OVERWHELM_DOING: {
        "vi": [
            {"id": "crisis:done_activity", "label": "Tôi đã làm xong"},
        ],
        "en": [
            {"id": "crisis:done_activity", "label": "Done, check how I feel"},
        ],
    },
    CrisisStage.OVERWHELM_CHECK: {
        "vi": [
            {"id": "crisis:feel_better_yes", "label": "Có, tôi cảm thấy đỡ hơn"},
            {"id": "crisis:feel_better_no",  "label": "Chưa, vẫn còn nặng nề"},
        ],
        "en": [
            {"id": "crisis:feel_better_yes", "label": "Yes, I feel better"},
            {"id": "crisis:feel_better_no",  "label": "Not really"},
        ],
    },
    CrisisStage.OVERWHELM_NOT_BETTER: {
        "vi": [
            {"id": "crisis:not_better_need_help",    "label": "Có, tôi cần thêm hỗ trợ"},
            {"id": "crisis:try_another",             "label": "Thử hoạt động khác"},
            {"id": "crisis:not_better_back_to_chat", "label": "Quay lại trò chuyện"},
        ],
        "en": [
            {"id": "crisis:not_better_need_help",    "label": "Yes, I need more help"},
            {"id": "crisis:try_another",             "label": "Try another calming exercise"},
            {"id": "crisis:not_better_back_to_chat", "label": "Back to conversation"},
        ],
    },
    CrisisStage.SAFETY_WATCH: {
        "vi": [
            {"id": "crisis:sw_back_to_chat", "label": "Quay lại trò chuyện"},
            {"id": "crisis:explain_more",    "label": "Cho tôi giải thích thêm"},
        ],
        "en": [
            {"id": "crisis:sw_back_to_chat", "label": "Back to conversation"},
            {"id": "crisis:explain_more",    "label": "Let me explain what I meant"},
        ],
    },
    CrisisStage.SOMEONE_ELSE: {
        "vi": [
            {"id": "crisis:they_in_danger",      "label": "Họ có thể đang gặp nguy hiểm"},
            {"id": "crisis:they_safe_struggling", "label": "Họ ổn nhưng đang khó khăn"},
            {"id": "crisis:they_not_sure",       "label": "Tôi không chắc"},
            {"id": "crisis:back_to_chat",        "label": "Quay lại trò chuyện"},
        ],
        "en": [
            {"id": "crisis:they_in_danger",      "label": "They might be in danger now"},
            {"id": "crisis:they_safe_struggling", "label": "They are safe but struggling"},
            {"id": "crisis:they_not_sure",       "label": "I'm not sure"},
            {"id": "crisis:back_to_chat",        "label": "Back to our conversation"},
        ],
    },
    CrisisStage.SOMEONE_ELSE_FOLLOWUP: {
        "vi": [
            {"id": "crisis:back_to_chat", "label": "Tôi hiểu, cảm ơn bạn"},
        ],
        "en": [
            {"id": "crisis:back_to_chat", "label": "Understood, thank you"},
        ],
    },
    CrisisStage.RECOVERY: {
        "vi": [
            {"id": "crisis:back_to_conversation", "label": "Quay lại trò chuyện"},
            {"id": "crisis:end_for_now",          "label": "Kết thúc phiên hôm nay"},
        ],
        "en": [
            {"id": "crisis:back_to_conversation", "label": "Back to conversation"},
            {"id": "crisis:end_for_now",          "label": "End for now"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Reply strings (VI / EN)
# ---------------------------------------------------------------------------

_CONFIRM_REPLY_VI = (
    "Cảm ơn bạn đã chia sẻ thêm. Mình muốn chắc chắn mình hiểu đúng — "
    "điều này giúp mình đồng hành an toàn hơn với bạn.\n\n"
    "Bạn có đang nghĩ đến việc tự làm hại bản thân ngay lúc này không?"
)
_CONFIRM_REPLY_EN = (
    "Thank you for sharing more. I want to make sure I understand you correctly — "
    "that helps me support you more safely.\n\n"
    "Are you having thoughts of hurting yourself right now?"
)

_HUMAN_ESCALATION_REPLY_VI = (
    "Tôi thực sự xin lỗi vì bạn đang trải qua điều này. "
    "Cuộc sống của bạn có ý nghĩa, dù lúc này có thể bạn không cảm nhận được điều đó.\n\n"
    "Mình chỉ là một AI và không phải người phù hợp nhất để giúp trong tình huống này. "
    "Hãy liên hệ với người bạn tin tưởng ngay bây giờ, hoặc gọi đến đường dây hỗ trợ khẩn cấp.\n\n"
    "Bạn có thể ở gần một người khác hoặc rời khỏi những thứ có thể gây hại không?"
)
_HUMAN_ESCALATION_REPLY_EN = (
    "I'm really sorry you're going through this. "
    "Your life matters, even if it doesn't feel that way right now.\n\n"
    "I'm only a bot, so I'm not the best person to help in an emergency. "
    "Please contact someone you trust now, or reach emergency support in your area.\n\n"
    "Can you stay near another person or move away from anything you could use to hurt yourself?"
)

_HUMAN_ESCALATION_EMERGENCY_REPLY_VI = (
    "**Các số hỗ trợ khẩn cấp:**\n"
    "- 📞 **1800 599 920** — Sức khỏe tâm thần (miễn phí, 24/7)\n"
    "- 🆘 **115** — Cấp cứu\n\n"
    "Hãy gọi ngay bây giờ — bạn xứng đáng được nhận sự hỗ trợ."
)
_HUMAN_ESCALATION_EMERGENCY_REPLY_EN = (
    "**Emergency support:**\n"
    "- 🇺🇸/🇨🇦 **988** — Suicide & Crisis Lifeline (call or text, 24/7)\n"
    "- 🌍 **findahelpline.com** — Find a crisis line near you\n"
    "- 🆘 **Emergency services** — Call your local emergency number if in immediate danger\n\n"
    "Please call now — you deserve support."
)

_HUMAN_ESCALATION_MESSAGE_REPLY_VI = (
    "Đây là gợi ý tin nhắn bạn có thể gửi cho người thân:\n\n"
    "\"Mình đang trải qua giai đoạn rất khó khăn và cần được nói chuyện với ai đó. "
    "Bạn có thể ở đây với mình không?\"\n\n"
    "Bạn có thể chỉnh sửa theo cách bạn muốn. "
    "Điều quan trọng nhất là liên hệ với họ ngay bây giờ."
)
_HUMAN_ESCALATION_MESSAGE_REPLY_EN = (
    "Here's a message you could send to someone you trust:\n\n"
    "\"I'm going through a really hard time and need to talk to someone. "
    "Can you be here for me?\"\n\n"
    "Feel free to change it to your own words. "
    "The most important thing is to reach out to them now."
)

_OVERWHELM_REPLY_VI = (
    "Mình hiểu cảm giác đó. Bạn không cần phải giải thích thêm gì cả.\n\n"
    "Hãy dành một khoảnh khắc nhỏ cho bản thân. Bạn muốn thử hoạt động nào?"
)
_OVERWHELM_REPLY_EN = (
    "I hear you — it's okay to feel overwhelmed without needing to explain why.\n\n"
    "Let's take a small moment for yourself. Which would you like to try?"
)

_OVERWHELM_DOING_BREATHING_VI = (
    "Rất tốt. Hãy hít thở cùng mình:\n\n"
    "*Hít vào… 1… 2… 3… 4…*\n"
    "*Giữ hơi… 1… 2… 3… 4…*\n"
    "*Thở ra… 1… 2… 3… 4…*\n\n"
    "Lặp lại 3–4 lần theo nhịp của bạn. Nhấn khi xong."
)
_OVERWHELM_DOING_BREATHING_EN = (
    "Great. Follow along:\n\n"
    "*Breathe in… 1… 2… 3… 4…*\n"
    "*Hold… 1… 2… 3… 4…*\n"
    "*Breathe out… 1… 2… 3… 4…*\n\n"
    "Repeat 3–4 times at your own pace. Tap when you're done."
)

_OVERWHELM_DOING_MUSIC_VI = (
    "Mình đang mở nhạc thư giãn cho bạn. "
    "Nhắm mắt lại nếu có thể và chỉ cần để tâm trí nghỉ ngơi.\n\n"
    "Nhấn khi bạn cảm thấy đã sẵn sàng."
)
_OVERWHELM_DOING_MUSIC_EN = (
    "I'm opening some calming sounds for you now. "
    "Close your eyes if you can, and just let yourself breathe.\n\n"
    "Tap when you're ready."
)

_OVERWHELM_DOING_GROUNDING_VI = (
    "Hãy thử bài tập hiện diện 5-4-3-2-1:\n\n"
    "Nhìn xung quanh và xác định:\n"
    "- **5 thứ** bạn có thể nhìn thấy\n"
    "- **4 thứ** bạn có thể chạm vào\n"
    "- **3 âm thanh** bạn có thể nghe\n"
    "- **2 thứ** bạn có thể ngửi\n"
    "- **1 thứ** bạn có thể nếm\n\n"
    "Hãy làm chậm rãi. Nhấn khi xong."
)
_OVERWHELM_DOING_GROUNDING_EN = (
    "Let's try a 5-4-3-2-1 grounding exercise:\n\n"
    "Look around and notice:\n"
    "- **5 things** you can see\n"
    "- **4 things** you can touch\n"
    "- **3 things** you can hear\n"
    "- **2 things** you can smell\n"
    "- **1 thing** you can taste\n\n"
    "Take your time. Tap when you're done."
)

_OVERWHELM_CHECK_REPLY_VI = (
    "Bạn cảm thấy thế nào bây giờ?\n\n"
    "Có đỡ hơn một chút không?"
)
_OVERWHELM_CHECK_REPLY_EN = (
    "How are you feeling now?\n\n"
    "Are you feeling a little better?"
)

_OVERWHELM_NOT_BETTER_REPLY_VI = (
    "Mình xin lỗi khi nghe điều đó. Cảm giác nặng nề đó không dễ chút nào.\n\n"
    "Bạn muốn làm gì tiếp theo?"
)
_OVERWHELM_NOT_BETTER_REPLY_EN = (
    "I'm sorry it still feels heavy. That weight you're carrying is real.\n\n"
    "Would you like more support?"
)

_SAFETY_WATCH_REPLY_VI = (
    "Cảm ơn bạn đã nói rõ. Mình có thể đã hiểu không đúng ý bạn.\n\n"
    "Bạn muốn nói thêm không, hay chúng ta tiếp tục trò chuyện như bình thường?"
)
_SAFETY_WATCH_REPLY_EN = (
    "Thanks for clarifying — I may have misunderstood what you meant.\n\n"
    "Would you like to say more, or shall we continue our conversation?"
)

_SOMEONE_ELSE_REPLY_VI = (
    "Bạn thật sự quan tâm đến họ — điều đó rất đáng trân trọng.\n\n"
    "Để mình hỗ trợ bạn tốt hơn, bạn có thể cho mình biết thêm không?\n\n"
    "Họ đang ở trong tình huống như thế nào?"
)
_SOMEONE_ELSE_REPLY_EN = (
    "It speaks to how much you care for them — that matters deeply.\n\n"
    "To help you better, can you tell me a bit more?\n\n"
    "What's their situation right now?"
)

_SOMEONE_ELSE_DANGER_REPLY_VI = (
    "Đây là tình huống khẩn cấp — hãy hành động ngay bây giờ.\n\n"
    "**Nếu họ đang trong nguy hiểm:**\n"
    "1. Gọi **115** hoặc số cấp cứu địa phương ngay\n"
    "2. Nếu có thể, hãy ở bên họ hoặc giữ họ nói chuyện qua điện thoại\n"
    "3. Đừng để họ một mình\n\n"
    "Bạn đang làm điều đúng đắn khi tìm kiếm sự giúp đỡ cho họ."
)
_SOMEONE_ELSE_DANGER_REPLY_EN = (
    "This is an emergency — please act now.\n\n"
    "**If they are in immediate danger:**\n"
    "1. Call **emergency services** or **988** right now\n"
    "2. If possible, stay with them or keep them on the phone\n"
    "3. Don't leave them alone\n\n"
    "You are doing the right thing by reaching out."
)

_SOMEONE_ELSE_STRUGGLING_REPLY_VI = (
    "Thật tốt khi biết họ đang an toàn. Bạn đang làm rất tốt khi quan tâm đến họ.\n\n"
    "**Một vài điều bạn có thể làm:**\n"
    "1. **Lắng nghe không phán xét** — Để họ nói ra mà không cố giải quyết ngay.\n"
    "2. **Hỏi thẳng** — \"Bạn có đang nghĩ đến việc tự làm hại không?\" — câu hỏi này không làm tình hình tệ hơn.\n"
    "3. **Khuyến khích tìm hỗ trợ** — Cùng gọi **1800 599 920** với họ.\n\n"
    "Bạn không đơn độc trong việc này."
)
_SOMEONE_ELSE_STRUGGLING_REPLY_EN = (
    "I'm glad they're safe. You're doing a kind and caring thing by looking out for them.\n\n"
    "**Some things you can do:**\n"
    "1. **Listen without judgment** — Let them speak without trying to fix things right away.\n"
    "2. **Ask directly** — \"Are you thinking about hurting yourself?\" — asking does not make things worse.\n"
    "3. **Encourage professional support** — Offer to call **988** together, or help them find a counselor.\n\n"
    "You don't have to do this alone either."
)

_SOMEONE_ELSE_NOTSURE_REPLY_VI = (
    "Không sao — bạn không cần phải chắc chắn. Điều quan trọng là bạn đang chú ý đến họ.\n\n"
    "**Nếu bạn lo lắng:**\n"
    "- Hỏi thẳng họ: \"Bạn có ổn không? Mình lo cho bạn.\"\n"
    "- Nếu bạn thấy dấu hiệu nguy hiểm, gọi **115** ngay\n"
    "- Đường dây hỗ trợ: **1800 599 920** (miễn phí, 24/7)\n\n"
    "Bạn đang làm điều đúng khi hỏi thêm."
)
_SOMEONE_ELSE_NOTSURE_REPLY_EN = (
    "That's okay — you don't need to be certain. What matters is that you're paying attention.\n\n"
    "**If you're worried:**\n"
    "- Ask them directly: \"Are you okay? I'm concerned about you.\"\n"
    "- If you see signs of immediate danger, call emergency services now\n"
    "- Crisis line: **988** (US/Canada, 24/7) or **findahelpline.com**\n\n"
    "You're doing the right thing by asking."
)

_RECOVERY_REPLY_VI = (
    "Mình rất vui khi nghe điều đó. "
    "Bạn đã làm rất tốt khi dừng lại và tự chăm sóc bản thân — điều đó không dễ chút nào.\n\n"
    "Cảm ơn bạn đã ở lại cùng mình."
)
_RECOVERY_REPLY_EN = (
    "I'm really glad to hear that. "
    "Taking a moment to care for yourself takes real courage — well done.\n\n"
    "Thank you for staying with me."
)


# ---------------------------------------------------------------------------
# Key / helpers
# ---------------------------------------------------------------------------

def _key(session_id: str) -> str:
    return f"crisis_escalation:{session_id}"


def should_block_free_text(stage: CrisisStage) -> bool:
    return stage != CrisisStage.NONE


def chips_for_stage(stage: CrisisStage, lang: str) -> list[CrisisChoice]:
    if stage == CrisisStage.NONE:
        return []
    bucket = _CHIPS.get(stage, {})
    return list(bucket.get(lang, bucket.get("vi", [])))


def confirm_reply_for_language(lang: str) -> str:
    return _CONFIRM_REPLY_EN if lang == "en" else _CONFIRM_REPLY_VI


def crisis_choices_to_api(chips: list[CrisisChoice]) -> list[dict[str, str]]:
    return [{"id": c["id"], "label": c["label"]} for c in chips]


def chip_message_for_send(chip_id: str, lang: str) -> str:
    """Message body sent when user taps a chip (includes machine-readable id)."""
    for stage_chips in _CHIPS.values():
        for choices in stage_chips.values():
            for c in choices:
                if c["id"] == chip_id:
                    return f"{CRISIS_CHIP_PREFIX}{chip_id}"
    return chip_id


def chip_label_for_id(chip_id: str | None, lang: str) -> str | None:
    if not chip_id:
        return None
    for stage_chips in _CHIPS.values():
        bucket = stage_chips.get(lang, stage_chips.get("vi", []))
        for c in bucket:
            if c["id"] == chip_id:
                return c["label"]
        for choices in stage_chips.values():
            for c in choices:
                if c["id"] == chip_id:
                    return c["label"]
    return None


def user_message_for_storage(user_message: str, lang: str) -> str:
    """Persist human-readable text; keep chip id only for in-flight API routing."""
    chip_id = parse_crisis_chip_id(user_message)
    if chip_id:
        label = chip_label_for_id(chip_id, lang)
        if label:
            return label
    return user_message


def parse_crisis_chip_id(user_message: str) -> str | None:
    text = user_message.strip()
    for prefix in _CRISIS_CHIP_PREFIX_ALIASES:
        if text.startswith(prefix):
            return text[len(prefix):].strip()
    low = text.lower()
    for stage_chips in _CHIPS.values():
        for choices in stage_chips.values():
            for c in choices:
                if c["label"].lower() == low or c["id"] in low:
                    return c["id"]
    return None


def _default_state() -> CrisisEscalationState:
    return {
        "crisis_stage": CrisisStage.NONE.value,
        "high_risk_turns": 0,
        "user_acknowledged_risk": False,
        "last_chip_id": None,
    }


def strategy_for_chip(chip_id: str | None) -> str | None:
    if not chip_id:
        return None
    return CHIP_STRATEGY.get(chip_id)


# ---------------------------------------------------------------------------
# Safety result overrides for chip taps
# ---------------------------------------------------------------------------

def safety_result_for_chip(chip_id: str | None) -> SafetyResult | None:
    """Chip taps are guided steps — avoid re-firing high-risk on benign labels."""
    from app.graph.safety_engine import _make_result

    if not chip_id:
        return None
    if chip_id in _DEESCALATION_CHIP_IDS:
        return _make_result(
            risk_level="medium",
            confidence=0.85,
            triggers=["crisis_chip_deescalation"],
            emergency_mode=False,
            suggested_stage="concern",
        )
    if chip_id in ("crisis:ack_safety_concern", "crisis:need_more_help"):
        return _make_result(
            risk_level="high",
            confidence=0.9,
            triggers=["crisis_chip_safety_check"],
            emergency_mode=False,
            suggested_stage="concern",
        )
    if chip_id in (
        "crisis:confirm_self_harm",
        "crisis:talk_to_someone",
        "crisis:not_better_need_help",
    ):
        return _make_result(
            risk_level="high",
            confidence=0.95,
            triggers=["crisis_chip_escalate"],
            emergency_mode=True,
            suggested_stage="sos",
        )
    return None


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------

async def get_crisis_escalation(
    redis: "Redis | None", session_id: str
) -> CrisisEscalationState:
    if redis is None:
        return _default_state()
    raw = await redis.get(_key(session_id))
    if not raw:
        return _default_state()
    try:
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        if not isinstance(data, dict):
            return _default_state()
        stage = str(data.get("crisis_stage", CrisisStage.NONE.value))
        if stage not in {s.value for s in CrisisStage}:
            stage = CrisisStage.NONE.value
        return {
            "crisis_stage": stage,
            "high_risk_turns": int(data.get("high_risk_turns") or 0),
            "user_acknowledged_risk": bool(data.get("user_acknowledged_risk")),
            "last_chip_id": data.get("last_chip_id"),
        }
    except (json.JSONDecodeError, TypeError, ValueError):
        return _default_state()


async def set_crisis_escalation(
    redis: "Redis | None",
    session_id: str,
    state: CrisisEscalationState,
) -> None:
    if redis is None:
        return
    await redis.set(_key(session_id), json.dumps(state), ex=TTL_SEC)


# ---------------------------------------------------------------------------
# Stage machine
# ---------------------------------------------------------------------------

def _stage_from_value(value: str) -> CrisisStage:
    try:
        return CrisisStage(value)
    except ValueError:
        return CrisisStage.NONE


# All stages that are purely chip-driven (free text keeps current stage)
_CHIP_DRIVEN_STAGES = frozenset({
    CrisisStage.HUMAN_ESCALATION,
    CrisisStage.OVERWHELM,
    CrisisStage.OVERWHELM_DOING,
    CrisisStage.OVERWHELM_CHECK,
    CrisisStage.OVERWHELM_NOT_BETTER,
    CrisisStage.SAFETY_WATCH,
    CrisisStage.SOMEONE_ELSE,
    CrisisStage.SOMEONE_ELSE_FOLLOWUP,
    CrisisStage.RECOVERY,
})


def _chip_transition(chip_id: str | None, current: CrisisStage) -> CrisisStage | None:
    """Return explicit next stage from chip, or None if chip does not drive stage."""
    if not chip_id:
        return None
    # Legacy / SOS chips (backward compat)
    if chip_id == "crisis:ack_safety_concern":
        return CrisisStage.CONFIRM
    if chip_id in ("crisis:confirm_self_harm", "crisis:talk_to_someone"):
        return CrisisStage.SOS
    if chip_id == "crisis:deny_self_harm":
        return CrisisStage.CONCERN
    if chip_id in ("crisis:feel_safer", "crisis:return_chat"):
        return CrisisStage.NONE
    if chip_id in ("crisis:share_more", "crisis:breathing_light"):
        return current
    if chip_id in ("crisis:breathing", "crisis:ocean", "crisis:hotline"):
        return CrisisStage.SOS
    # Concern triage
    if chip_id == "crisis:need_more_help":
        return CrisisStage.HUMAN_ESCALATION
    if chip_id == "crisis:just_overwhelmed":
        return CrisisStage.OVERWHELM
    if chip_id == "crisis:misunderstood":
        return CrisisStage.SAFETY_WATCH
    if chip_id == "crisis:someone_else":
        return CrisisStage.SOMEONE_ELSE
    # Human escalation: emergency/message stay; safe → NONE
    if chip_id in ("crisis:show_emergency", "crisis:help_message_someone"):
        return CrisisStage.HUMAN_ESCALATION
    if chip_id == "crisis:i_am_safe_now":
        return CrisisStage.NONE
    # Overwhelm activity choice → doing
    if chip_id in ("crisis:slow_breathing", "crisis:calming_music", "crisis:grounding_exercise"):
        return CrisisStage.OVERWHELM_DOING
    # During activity → check
    if chip_id == "crisis:done_activity":
        return CrisisStage.OVERWHELM_CHECK
    # Check → recovery or not-better
    if chip_id == "crisis:feel_better_yes":
        return CrisisStage.RECOVERY
    if chip_id == "crisis:feel_better_no":
        return CrisisStage.OVERWHELM_NOT_BETTER
    # Not-better options
    if chip_id == "crisis:not_better_need_help":
        return CrisisStage.HUMAN_ESCALATION
    if chip_id == "crisis:try_another":
        return CrisisStage.OVERWHELM
    if chip_id == "crisis:not_better_back_to_chat":
        return CrisisStage.NONE
    # Recovery
    if chip_id in ("crisis:back_to_conversation", "crisis:end_for_now"):
        return CrisisStage.NONE
    # Safety-watch
    if chip_id in ("crisis:sw_back_to_chat", "crisis:explain_more"):
        return CrisisStage.NONE
    # Someone-else triage → followup
    if chip_id in ("crisis:they_in_danger", "crisis:they_safe_struggling", "crisis:they_not_sure"):
        return CrisisStage.SOMEONE_ELSE_FOLLOWUP
    if chip_id == "crisis:back_to_chat":
        return CrisisStage.NONE
    return None


def resolve_crisis_stage(
    *,
    escalation: CrisisEscalationState,
    safety: SafetyResult,
    user_message: str,
) -> CrisisStage:
    """Compute target stage for this turn before persisting."""
    current = _stage_from_value(str(escalation.get("crisis_stage") or "none"))
    chip_id = parse_crisis_chip_id(user_message)
    chip_next = _chip_transition(chip_id, current)

    if safety.get("emergency_mode"):
        return CrisisStage.SOS

    suggested = str(safety.get("suggested_stage") or "none")
    try:
        suggested_stage = CrisisStage(suggested)
    except ValueError:
        suggested_stage = CrisisStage.NONE

    if chip_next is not None:
        if chip_next == current and current != CrisisStage.NONE:
            return current
        return chip_next

    if current == CrisisStage.SOS:
        if safety.get("risk_level") == "low":
            return CrisisStage.CONCERN
        return CrisisStage.SOS

    if current == CrisisStage.CONFIRM:
        if suggested_stage == CrisisStage.SOS:
            return CrisisStage.SOS
        return CrisisStage.CONFIRM

    if current in _CHIP_DRIVEN_STAGES:
        return current

    if current == CrisisStage.CONCERN:
        if chip_id in ("crisis:share_more", "crisis:breathing_light"):
            return CrisisStage.CONCERN
        high_turns = int(escalation.get("high_risk_turns") or 0)
        if (
            chip_id is None
            and safety.get("risk_level") == "high"
            and high_turns >= 2
        ):
            return CrisisStage.CONFIRM
        return CrisisStage.CONCERN

    # current == NONE
    if suggested_stage in (CrisisStage.CONCERN, CrisisStage.CONFIRM, CrisisStage.SOS):
        return suggested_stage
    if safety.get("risk_level") == "high":
        return CrisisStage.CONCERN
    return CrisisStage.NONE


async def advance_crisis_escalation(
    redis: "Redis | None",
    session_id: str,
    *,
    safety: SafetyResult,
    user_message: str,
) -> tuple[CrisisStage, CrisisEscalationState]:
    """Resolve stage, update counters, persist, return (stage, state)."""
    escalation = await get_crisis_escalation(redis, session_id)
    stage = resolve_crisis_stage(
        escalation=escalation,
        safety=safety,
        user_message=user_message,
    )

    chip_id = parse_crisis_chip_id(user_message)
    if chip_id:
        escalation["last_chip_id"] = chip_id
    if safety.get("risk_level") == "high" and chip_id not in _DEESCALATION_CHIP_IDS:
        escalation["high_risk_turns"] = int(escalation.get("high_risk_turns") or 0) + 1
    if chip_id == "crisis:confirm_self_harm":
        escalation["user_acknowledged_risk"] = True
    if chip_id == "crisis:deny_self_harm":
        escalation["user_acknowledged_risk"] = False
    if stage == CrisisStage.NONE:
        escalation["high_risk_turns"] = 0
        escalation["user_acknowledged_risk"] = False
        escalation["last_chip_id"] = None

    escalation["crisis_stage"] = stage.value
    await set_crisis_escalation(redis, session_id, escalation)
    return stage, escalation


# ---------------------------------------------------------------------------
# Public reply functions used by routes.py
# ---------------------------------------------------------------------------

def sos_reply_and_chips(lang: str) -> tuple[str, list[CrisisChoice]]:
    reply, _legacy = crisis_reply_for_language(lang)
    chips = chips_for_stage(CrisisStage.SOS, lang)
    return reply, chips


def human_escalation_reply_for_language(lang: str, chip_id: str | None = None) -> str:
    if chip_id == "crisis:show_emergency":
        return _HUMAN_ESCALATION_EMERGENCY_REPLY_EN if lang == "en" else _HUMAN_ESCALATION_EMERGENCY_REPLY_VI
    if chip_id == "crisis:help_message_someone":
        return _HUMAN_ESCALATION_MESSAGE_REPLY_EN if lang == "en" else _HUMAN_ESCALATION_MESSAGE_REPLY_VI
    return _HUMAN_ESCALATION_REPLY_EN if lang == "en" else _HUMAN_ESCALATION_REPLY_VI


def overwhelm_reply_for_language(lang: str) -> str:
    return _OVERWHELM_REPLY_EN if lang == "en" else _OVERWHELM_REPLY_VI


def overwhelm_doing_reply_for_language(lang: str, chip_id: str | None = None) -> str:
    if chip_id == "crisis:calming_music":
        return _OVERWHELM_DOING_MUSIC_EN if lang == "en" else _OVERWHELM_DOING_MUSIC_VI
    if chip_id == "crisis:grounding_exercise":
        return _OVERWHELM_DOING_GROUNDING_EN if lang == "en" else _OVERWHELM_DOING_GROUNDING_VI
    return _OVERWHELM_DOING_BREATHING_EN if lang == "en" else _OVERWHELM_DOING_BREATHING_VI


def overwhelm_check_reply_for_language(lang: str) -> str:
    return _OVERWHELM_CHECK_REPLY_EN if lang == "en" else _OVERWHELM_CHECK_REPLY_VI


def overwhelm_not_better_reply_for_language(lang: str) -> str:
    return _OVERWHELM_NOT_BETTER_REPLY_EN if lang == "en" else _OVERWHELM_NOT_BETTER_REPLY_VI


def safety_watch_reply_for_language(lang: str) -> str:
    return _SAFETY_WATCH_REPLY_EN if lang == "en" else _SAFETY_WATCH_REPLY_VI


def someone_else_reply_for_language(lang: str, chip_id: str | None = None) -> str:
    if chip_id == "crisis:they_in_danger":
        return _SOMEONE_ELSE_DANGER_REPLY_EN if lang == "en" else _SOMEONE_ELSE_DANGER_REPLY_VI
    if chip_id == "crisis:they_safe_struggling":
        return _SOMEONE_ELSE_STRUGGLING_REPLY_EN if lang == "en" else _SOMEONE_ELSE_STRUGGLING_REPLY_VI
    if chip_id == "crisis:they_not_sure":
        return _SOMEONE_ELSE_NOTSURE_REPLY_EN if lang == "en" else _SOMEONE_ELSE_NOTSURE_REPLY_VI
    return _SOMEONE_ELSE_REPLY_EN if lang == "en" else _SOMEONE_ELSE_REPLY_VI


def recovery_reply_for_language(lang: str) -> str:
    return _RECOVERY_REPLY_EN if lang == "en" else _RECOVERY_REPLY_VI


def pre_gather_force_strategy(
    escalation: CrisisEscalationState,
    user_message: str,
) -> str | None:
    """Pick LLM role for this crisis turn (chip path or first concern)."""
    from app.graph.safety_engine import _keyword_risk

    chip_id = parse_crisis_chip_id(user_message)
    if chip_id:
        return strategy_for_chip(chip_id)

    current = _stage_from_value(str(escalation.get("crisis_stage") or "none"))
    if current not in (CrisisStage.NONE,):
        return "crisis_concern"
    kw = _keyword_risk(user_message)
    if kw and str(kw.get("suggested_stage")) in ("concern", "confirm", "sos"):
        return "crisis_concern"
    return None
