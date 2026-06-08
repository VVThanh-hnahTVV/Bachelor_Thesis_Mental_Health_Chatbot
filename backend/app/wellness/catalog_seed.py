"""Default Helios wellness activity catalog (v1)."""

from __future__ import annotations

from typing import Any


def _youtube_video(
    youtube_id: str,
    *,
    source_name: str,
    source_url: str,
    license_note: str,
    attribution_vi: str,
    attribution_en: str,
) -> dict[str, Any]:
    """Build video_url + youtube_id + video_source for catalog entries."""
    return {
        "youtube_id": youtube_id,
        "video_url": f"https://www.youtube.com/watch?v={youtube_id}",
        "video_source": {
            "name": source_name,
            "url": source_url,
            "license": license_note,
            "attribution": {
                "vi": attribution_vi,
                "en": attribution_en,
            },
        },
    }

DEFAULT_WELLNESS_ACTIVITIES: list[dict[str, Any]] = [
    {
        "id": "breathing_box",
        "scope": ["helios"],
        "content_type": "interactive",
        "activity_type": "exercise",
        "ui_component": "breathing_box",
        "title": {"vi": "Hít thở hộp (4-4-4-4)", "en": "Box breathing (4-4-4-4)"},
        "description": {
            "vi": "Nhịp thở đều trong app — hữu ích khi căng thẳng hoặc muốn tập trung vào hơi thở.",
            "en": "Steady breathing rhythm in the app — helpful when stressed or grounding is needed.",
        },
        "benefits": ["giảm lo âu", "grounding", "giảm căng thẳng", "ổn định nhịp thở"],
        "benefits_en": ["reduce anxiety", "grounding", "stress relief", "steady breathing"],
        "tags": ["anxiety", "stress", "breathing", "grounding"],
        "duration_min": 5,
        "avg_rating": 4.2,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "ocean_sound",
        "scope": ["helios"],
        "content_type": "interactive",
        "activity_type": "audio",
        "ui_component": "ocean_sound",
        "title": {"vi": "Âm sóng nhẹ", "en": "Calming ocean sounds"},
        "description": {
            "vi": "Âm nền dạng sóng biển — phù hợp khi cần thư giãn, dễ ngủ hoặc giảm kích thích.",
            "en": "Gentle wave ambience — good for relaxation, sleep wind-down, or reducing stimulation.",
        },
        "benefits": ["thư giãn", "giảm lo âu", "dễ ngủ", "âm nền thư giãn"],
        "benefits_en": ["relaxation", "reduce anxiety", "sleep support", "calming ambient audio"],
        "tags": ["audio", "radio", "ambient", "sleep", "relaxation"],
        "duration_min": 8,
        "avg_rating": 4.3,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "mindful_forest",
        "scope": ["helios"],
        "content_type": "interactive",
        "activity_type": "audio",
        "ui_component": "mindful_forest",
        "title": {"vi": "Rừng thiền định", "en": "Mindful forest"},
        "description": {
            "vi": "Âm thanh rừng (chim, gió, lá) kèm hướng dẫn thiền ngắn trong app.",
            "en": "Forest sounds (birds, wind, leaves) with a short guided mindfulness session.",
        },
        "benefits": ["mindfulness", "thiền định", "giảm stress", "thư giãn"],
        "benefits_en": ["mindfulness", "meditation", "stress relief", "relaxation"],
        "tags": ["mindfulness", "meditation", "forest", "audio", "stress"],
        "duration_min": 5,
        "avg_rating": 4.1,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "zen_garden",
        "scope": ["helios"],
        "content_type": "interactive",
        "activity_type": "exercise",
        "ui_component": "zen_garden",
        "title": {"vi": "Vườn Zen", "en": "Zen garden"},
        "description": {
            "vi": "Sắp xếp đá, hoa, cây trên cát — hoạt động mindfulness tương tác nhẹ nhàng.",
            "en": "Arrange rocks, flowers, and trees on sand — a gentle interactive mindfulness activity.",
        },
        "benefits": ["mindfulness", "giảm căng thẳng", "tập trung", "thư giãn"],
        "benefits_en": ["mindfulness", "stress relief", "focus", "relaxation"],
        "tags": ["mindfulness", "focus", "stress", "interactive"],
        "duration_min": 10,
        "avg_rating": 4.0,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "body_scan_video",
        "scope": ["helios"],
        "content_type": "video",
        "activity_type": "video",
        "ui_component": "body_scan_video",
        **_youtube_video(
            "OS_iqfGjL78",
            source_name="Mount Sinai Health System",
            source_url="https://www.youtube.com/watch?v=OS_iqfGjL78",
            license_note="YouTube embed — educational / non-commercial use",
            attribution_vi=(
                "Nguồn: Mount Sinai Health System — Compassionate Body Scan. "
                "Video nhúng từ YouTube; chỉ dùng cho mục đích giáo dục, không thương mại."
            ),
            attribution_en=(
                "Source: Mount Sinai Health System — Compassionate Body Scan. "
                "Embedded from YouTube; educational use only, non-commercial."
            ),
        ),
        "title": {"vi": "Body scan thư giãn", "en": "Relaxing body scan"},
        "description": {
            "vi": "Video hướng dẫn quét cơ thể từng vùng — giúp giảm lo âu và thư giãn trước ngủ.",
            "en": "Guided body scan video — helps reduce anxiety and relax before sleep.",
        },
        "benefits": ["body scan", "giảm lo âu", "awareness cơ thể", "thư giãn trước ngủ"],
        "benefits_en": ["body scan", "reduce anxiety", "body awareness", "pre-sleep relaxation"],
        "tags": ["anxiety", "sleep", "body_scan", "video", "relaxation"],
        "duration_min": 20,
        "avg_rating": 4.4,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "pmr_video",
        "scope": ["helios"],
        "content_type": "video",
        "activity_type": "video",
        "ui_component": "pmr_video",
        **_youtube_video(
            "2IJUD-e14FY",
            source_name="Hospital for Special Surgery (HSS)",
            source_url="https://www.youtube.com/watch?v=2IJUD-e14FY",
            license_note="YouTube embed — educational / non-commercial use",
            attribution_vi=(
                "Nguồn: Hospital for Special Surgery — Progressive Muscle Relaxation. "
                "Video nhúng từ YouTube; chỉ dùng cho mục đích giáo dục, không thương mại."
            ),
            attribution_en=(
                "Source: Hospital for Special Surgery — Progressive Muscle Relaxation. "
                "Embedded from YouTube; educational use only, non-commercial."
            ),
        ),
        "title": {"vi": "Thả lỏng cơ tiến triển (PMR)", "en": "Progressive muscle relaxation (PMR)"},
        "description": {
            "vi": "Video hướng dẫn căng rồi thả lỏng từng nhóm cơ — giảm căng thẳng cơ thể.",
            "en": "Video guiding tense-and-release for muscle groups — reduces physical tension.",
        },
        "benefits": ["thả lỏng cơ", "giảm căng thẳng cơ thể", "giảm lo âu", "PMR"],
        "benefits_en": ["muscle relaxation", "physical tension relief", "reduce anxiety", "PMR"],
        "tags": ["PMR", "muscle", "anxiety", "stress", "video"],
        "duration_min": 10,
        "avg_rating": 4.2,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "neck_stretch_video",
        "scope": ["helios"],
        "content_type": "video",
        "activity_type": "video",
        "ui_component": "neck_stretch_video",
        **_youtube_video(
            "6NOFwd3jJr0",
            source_name="Ask Doctor Jo",
            source_url="https://www.youtube.com/watch?v=6NOFwd3jJr0",
            license_note="YouTube embed — educational / non-commercial use",
            attribution_vi=(
                "Nguồn: Ask Doctor Jo — Neck Stretches (Physical Therapy). "
                "Video nhúng từ YouTube; chỉ dùng cho mục đích giáo dục, không thương mại."
            ),
            attribution_en=(
                "Source: Ask Doctor Jo — Neck Stretches (Physical Therapy). "
                "Embedded from YouTube; educational use only, non-commercial."
            ),
        ),
        "title": {"vi": "Giãn cơ cổ vai", "en": "Neck and shoulder stretch"},
        "description": {
            "vi": "Video hướng dẫn giãn cơ cổ vai — hữu ích khi làm việc văn phòng hoặc căng cơ.",
            "en": "Guided neck and shoulder stretch — helpful for desk work or muscle tightness.",
        },
        "benefits": ["giảm đau cổ vai", "stress công sở", "thư giãn cơ", "giãn cơ"],
        "benefits_en": ["neck shoulder relief", "desk stress", "muscle relaxation", "stretching"],
        "tags": ["neck", "shoulder", "desk", "stretch", "video", "stress"],
        "duration_min": 5,
        "avg_rating": 4.0,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
    {
        "id": "sleep_wind_down_video",
        "scope": ["helios"],
        "content_type": "video",
        "activity_type": "video",
        "ui_component": "sleep_wind_down_video",
        **_youtube_video(
            "inpok4MKVLM",
            source_name="Headspace",
            source_url="https://www.youtube.com/watch?v=inpok4MKVLM",
            license_note="YouTube embed — educational / non-commercial use",
            attribution_vi=(
                "Nguồn: Headspace — Guided Meditation for Sleep. "
                "Video nhúng từ YouTube; chỉ dùng cho mục đích giáo dục, không thương mại."
            ),
            attribution_en=(
                "Source: Headspace — Guided Meditation for Sleep. "
                "Embedded from YouTube; educational use only, non-commercial."
            ),
        ),
        "title": {"vi": "Thư giãn trước khi ngủ", "en": "Sleep wind-down"},
        "description": {
            "vi": "Video hướng dẫn thiền thư giãn trước khi ngủ — giúp giảm lo âu và dễ vào giấc.",
            "en": "Guided sleep meditation — helps reduce anxiety and ease into rest.",
        },
        "benefits": ["dễ ngủ", "vệ sinh giấc ngủ", "thư giãn buổi tối", "giảm mất ngủ"],
        "benefits_en": ["better sleep", "sleep hygiene", "evening relaxation", "insomnia support"],
        "tags": ["sleep", "insomnia", "evening", "video", "relaxation"],
        "duration_min": 10,
        "avg_rating": 4.3,
        "rating_count": 0,
        "active": True,
        "implemented": True,
    },
]
