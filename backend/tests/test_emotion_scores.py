from datetime import UTC, datetime, timedelta

from app.wellness.emotion_scores import aggregate_chat_emotions_today, emotion_to_score


def test_emotion_to_score_known_labels():
    assert emotion_to_score("joy") > emotion_to_score("sadness")
    assert emotion_to_score("hopeless") < 30


def test_aggregate_chat_emotions_today_filters_by_date():
    today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
    day_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    docs = [
        {
            "role": "assistant",
            "created_at": today,
            "metadata": {"emotion": "joy", "emotion_intensity": 0.8},
        },
        {
            "role": "assistant",
            "created_at": today,
            "metadata": {"emotion": "sadness", "emotion_intensity": 0.6},
        },
        {
            "role": "assistant",
            "created_at": yesterday,
            "metadata": {"emotion": "hopeless"},
        },
        {
            "role": "user",
            "created_at": today,
            "metadata": {"emotion": "joy"},
        },
    ]

    result = aggregate_chat_emotions_today(docs, day_start=day_start)
    assert result["samples"] == 2
    assert result["dominant_emotion"] in ("joy", "sadness")
    assert result["mood_score"] is not None
    assert 0 <= result["mood_score"] <= 100


def test_aggregate_empty_when_no_emotions():
    assert aggregate_chat_emotions_today([])["samples"] == 0
