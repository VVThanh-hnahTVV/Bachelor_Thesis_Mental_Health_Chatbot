"""Wellness retrieval confidence gating."""

from __future__ import annotations

import pytest

from app.medical.agents.wellness_agent.retrieval import (
    attach_wellness_after_retrieval,
    retrieve_wellness_suggestions,
)
from app.medical.config import get_medical_config


@pytest.fixture(autouse=True)
def _clear_medical_config_cache():
    get_medical_config.cache_clear()
    yield
    get_medical_config.cache_clear()


def test_retrieve_blocks_low_confidence_keyword(monkeypatch):
    monkeypatch.setenv("WELLNESS_SUGGESTION_MIN_SCORE", "0.9")
    result = retrieve_wellness_suggestions("xyz unrelated medical terms only")
    assert result.suggestions == []
    assert result.top_score < 0.9


def test_retrieve_allows_anxiety_keyword(monkeypatch):
    monkeypatch.setenv("WELLNESS_SUGGESTION_MIN_SCORE", "0.35")
    result = retrieve_wellness_suggestions("tôi bị lo âu và căng thẳng")
    assert result.suggestions
    assert result.top_score >= 0.35
    assert any(s["id"] for s in result.suggestions)


def test_attach_only_after_rag_or_web():
    state = {
        "agent_name": "CONVERSATION_AGENT",
        "current_input": "tôi lo âu",
        "suggest_activities": True,
        "suggested_activities": [],
    }
    out = attach_wellness_after_retrieval(state)
    assert not out.get("suggested_activities")


def test_attach_blocked_when_agent_declines_activities(monkeypatch):
    monkeypatch.setenv("WELLNESS_SUGGESTION_MIN_SCORE", "0.35")
    state = {
        "agent_name": "RAG_AGENT",
        "current_input": "Sao để giảm ADHD",
        "suggest_activities": False,
        "suggested_activities": [],
    }
    out = attach_wellness_after_retrieval(state)
    assert not out.get("suggested_activities")


def test_attach_after_rag_when_score_ok(monkeypatch):
    monkeypatch.setenv("WELLNESS_SUGGESTION_MIN_SCORE", "0.35")
    state = {
        "agent_name": "RAG_AGENT",
        "current_input": "bệnh lo âu có bài tập gì không",
        "suggest_activities": True,
        "suggested_activities": [],
    }
    out = attach_wellness_after_retrieval(state)
    assert out.get("suggested_activities")
    assert out.get("wellness_retrieval_score", 0) >= 0.35
