"""Tests for activity rating stats and routing prompt."""

from app.medical.rag_catalog import build_decision_system_prompt
from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES


def test_decision_prompt_routes_symptoms_not_wellness_agent():
    prompt = build_decision_system_prompt(
        raw_dir="/nonexistent/raw",
        metadata_path="/nonexistent/meta.json",
    )
    assert "WELLNESS_AGENT" not in prompt
    assert "automatically after RAG or web search" in prompt
    assert "lo âu mất ngủ" in prompt or "anxiety, insomnia" in prompt


def test_catalog_has_eight_helios_activities():
    helios = [d for d in DEFAULT_WELLNESS_ACTIVITIES if "helios" in d.get("scope", [])]
    assert len(helios) == 8


def test_catalog_video_and_interactive_mix():
    videos = [d for d in DEFAULT_WELLNESS_ACTIVITIES if d.get("content_type") == "video"]
    interactive = [
        d for d in DEFAULT_WELLNESS_ACTIVITIES if d.get("content_type") == "interactive"
    ]
    assert len(videos) == 4
    assert len(interactive) == 4
