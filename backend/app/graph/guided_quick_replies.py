"""Rule-based fallback quick replies — always pad to exactly 3 options."""
from __future__ import annotations

from typing import Any

_TEMPLATES_VI: dict[str, list[dict[str, str]]] = {
    "reflective_listening": [
        {"id": "rl1", "label": "Kể thêm", "message": "Tôi muốn kể thêm về chuyện này"},
        {"id": "rl2", "label": "Tủi hờn", "message": "Tôi cảm thấy tủi hờn và nặng lòng"},
        {"id": "rl3", "label": "Không biết nói gì", "message": "Tôi không biết nói gì nhưng vẫn muốn ở đây"},
    ],
    "relationship": [
        {"id": "rs1", "label": "Về người đó", "message": "Tôi muốn nói thêm về người mình thích"},
        {"id": "rs2", "label": "Đau lòng", "message": "Tôi đau lòng vì không được đáp lại"},
        {"id": "rs3", "label": "Cần lắng nghe", "message": "Tôi chỉ cần được lắng nghe thôi"},
    ],
    "stabilization": [
        {"id": "st1", "label": "Đã thử bài tập", "message": "Tôi đã thử bài tập rồi"},
        {"id": "st2", "label": "Chưa làm được", "message": "Tôi chưa làm được bài tập đó"},
        {"id": "st3", "label": "Cần nói thêm", "message": "Tôi cần nói thêm về cảm giác của mình"},
    ],
    "post_stabilization": [
        {"id": "ps1", "label": "Hơi đỡ", "message": "Tôi thấy hơi đỡ một chút rồi"},
        {"id": "ps2", "label": "Vẫn nặng", "message": "Tôi vẫn thấy nặng nhưng muốn nói tiếp"},
        {"id": "ps3", "label": "Chưa ổn", "message": "Tôi chưa ổn, cần hỗ trợ khác"},
    ],
    "CBT": [
        {"id": "cbt1", "label": "Không đủ tốt", "message": "Tôi nghĩ mình không đủ tốt"},
        {"id": "cbt2", "label": "Họ không thích", "message": "Có lẽ họ không thích mình"},
        {"id": "cbt3", "label": "Nhìn khác đi", "message": "Tôi muốn thử nhìn chuyện này theo cách khác"},
    ],
    "default": [
        {"id": "d1", "label": "Nói thêm", "message": "Tôi muốn nói thêm một chút"},
        {"id": "d2", "label": "Cảm thấy nặng", "message": "Tôi vẫn cảm thấy nặng nề"},
        {"id": "d3", "label": "Cần hỗ trợ", "message": "Tôi cần được hỗ trợ thêm"},
    ],
}

_TEMPLATES_EN: dict[str, list[dict[str, str]]] = {
    "reflective_listening": [
        {"id": "rl1", "label": "Share more", "message": "I'd like to share more about this"},
        {"id": "rl2", "label": "Feeling heavy", "message": "I feel heavy and sad right now"},
        {"id": "rl3", "label": "Hard to talk", "message": "I don't know what to say but I want to stay here"},
    ],
    "relationship": [
        {"id": "rs1", "label": "About them", "message": "I want to talk more about the person I like"},
        {"id": "rs2", "label": "It hurts", "message": "It hurts that my feelings aren't returned"},
        {"id": "rs3", "label": "Just listen", "message": "I just need someone to listen"},
    ],
    "stabilization": [
        {"id": "st1", "label": "Tried it", "message": "I tried the exercise"},
        {"id": "st2", "label": "Couldn't yet", "message": "I couldn't do it yet"},
        {"id": "st3", "label": "Need to talk", "message": "I need to talk more about how I feel"},
    ],
    "post_stabilization": [
        {"id": "ps1", "label": "A bit better", "message": "I feel a little better now"},
        {"id": "ps2", "label": "Still heavy", "message": "It's still heavy but I want to keep talking"},
        {"id": "ps3", "label": "Not okay", "message": "I'm not okay yet and need different support"},
    ],
    "CBT": [
        {"id": "cbt1", "label": "Not good enough", "message": "I think I'm not good enough"},
        {"id": "cbt2", "label": "They don't like me", "message": "Maybe they don't like me"},
        {"id": "cbt3", "label": "Another view", "message": "I want to try seeing this differently"},
    ],
    "default": [
        {"id": "d1", "label": "Say more", "message": "I want to say a bit more"},
        {"id": "d2", "label": "Still heavy", "message": "I still feel really heavy"},
        {"id": "d3", "label": "Need support", "message": "I need more support"},
    ],
}


def _template_key(strategy: str | None, emotion: str, intent: str) -> str:
    s = strategy or ""
    if s in ("post_stabilization",):
        return "post_stabilization"
    if s == "stabilization":
        return "stabilization"
    if s == "CBT":
        return "CBT"
    if intent == "relationship_stress" or emotion in ("lonely", "grief", "sadness"):
        return "relationship"
    if s == "reflective_listening":
        return "reflective_listening"
    return "default"


def guided_quick_replies(
    *,
    lang: str,
    strategy: str | None,
    emotion: str,
    intent: str,
) -> list[dict[str, str]]:
    templates = _TEMPLATES_EN if lang == "en" else _TEMPLATES_VI
    key = _template_key(strategy, emotion, intent)
    return [dict(item) for item in templates.get(key, templates["default"])]


def ensure_three_quick_replies(
    options: list[dict[str, str]],
    *,
    lang: str,
    strategy: str | None,
    emotion: str,
    intent: str,
) -> list[dict[str, str]]:
    """Return exactly 3 quick-reply dicts with id, label, message."""
    out: list[dict[str, str]] = []
    seen_messages: set[str] = set()
    for item in options:
        msg = str(item.get("message", "")).strip()
        if not msg or msg in seen_messages:
            continue
        seen_messages.add(msg)
        out.append({
            "id": str(item.get("id", f"q{len(out)}")),
            "label": str(item.get("label", msg))[:28],
            "message": msg,
        })
        if len(out) >= 3:
            return out[:3]

    fallback = guided_quick_replies(
        lang=lang, strategy=strategy, emotion=emotion, intent=intent
    )
    for item in fallback:
        msg = item["message"]
        if msg in seen_messages:
            continue
        seen_messages.add(msg)
        out.append(dict(item))
        if len(out) >= 3:
            break
    return out[:3]
