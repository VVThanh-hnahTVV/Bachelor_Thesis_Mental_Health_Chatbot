"""Tests for wellness activity embed text and keyword fallback search."""

from app.medical.agents.wellness_agent.activity_store import build_embed_text, build_qdrant_payload
from app.medical.agents.wellness_agent.wellness_agent import _fallback_keyword_search
from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES


def test_build_embed_text_includes_benefits():
    doc = DEFAULT_WELLNESS_ACTIVITIES[0]
    text = build_embed_text(doc)
    assert "giảm lo âu" in text or "reduce anxiety" in text.lower()
    assert "breathing_box" not in text  # id not required but title should appear


def test_build_qdrant_payload_fields():
    doc = DEFAULT_WELLNESS_ACTIVITIES[1]
    payload = build_qdrant_payload(doc)
    assert payload["activity_id"] == "ocean_sound"
    assert payload["activity_type"] == "audio"
    assert payload["implemented"] is True


def test_fallback_keyword_search_anxiety():
    results = _fallback_keyword_search("giảm lo âu", top_k=3)
    assert results
    ids = [r["activity_id"] for r in results]
    assert "breathing_box" in ids or "ocean_sound" in ids


def test_fallback_keyword_search_audio_filter():
    results = _fallback_keyword_search("nhạc thư giãn radio", activity_type="audio", top_k=5)
    for hit in results:
        assert hit.get("activity_type") == "audio"
