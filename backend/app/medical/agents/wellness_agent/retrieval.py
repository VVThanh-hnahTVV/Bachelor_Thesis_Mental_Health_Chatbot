"""Wellness activity retrieval with confidence gating."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal

from app.medical.agents.wellness_agent.activity_store import (
    keyword_search_scored,
    to_suggestion,
)
from app.medical.agents.wellness_agent.vectorstore import search_wellness_scored
from app.medical.config import get_medical_config

logger = logging.getLogger(__name__)

RetrievalSource = Literal["vector", "keyword", "none"]


@dataclass(frozen=True)
class WellnessRetrievalResult:
    suggestions: list[dict[str, str]]
    top_score: float
    source: RetrievalSource


def _wellness_debug_enabled() -> bool:
    return os.environ.get("WELLNESS_AGENT_DEBUG", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _print_wellness_retrieval(
    *,
    query: str,
    vector_hits: list[tuple[dict[str, Any], float]],
    keyword_hits: list[tuple[dict[str, Any], float]],
    merged: list[tuple[dict[str, Any], float, RetrievalSource]],
    threshold: float,
    require_threshold: bool,
    result: WellnessRetrievalResult,
    context: str = "",
) -> None:
    prefix = f"{context}: " if context else ""
    print(
        f"{prefix}Wellness retrieval — top_score={result.top_score:.4f}, "
        f"source={result.source}, threshold={threshold:.4f}, "
        f"show_suggestions={bool(result.suggestions)}, "
        f"activities={[s['id'] for s in result.suggestions]}"
    )
    logger.info(
        "%swellness_score=%.4f source=%s threshold=%.4f show=%s query=%r",
        prefix,
        result.top_score,
        result.source,
        threshold,
        bool(result.suggestions),
        query[:120],
    )

    if not _wellness_debug_enabled():
        return

    print(f"[WELLNESS_RETRIEVAL] query={query!r}")
    for doc, score in vector_hits:
        print(f"  vector hit: {doc.get('id')} wellness_score={score:.4f}")
    for doc, score in keyword_hits:
        print(f"  keyword hit: {doc.get('id')} wellness_score={score:.4f}")
    for doc, score, src in merged:
        print(f"  merged: {doc.get('id')} wellness_score={score:.4f} source={src}")
    print(f"  require_threshold={require_threshold}")


def _merge_scored(
    vector_hits: list[tuple[dict[str, Any], float]],
    keyword_hits: list[tuple[dict[str, Any], float]],
    *,
    limit: int,
) -> list[tuple[dict[str, Any], float, RetrievalSource]]:
    seen: set[str] = set()
    merged: list[tuple[dict[str, Any], float, RetrievalSource]] = []

    for doc, score in vector_hits:
        aid = str(doc.get("id", ""))
        if aid and aid not in seen:
            seen.add(aid)
            merged.append((doc, score, "vector"))

    for doc, score in keyword_hits:
        aid = str(doc.get("id", ""))
        if aid and aid not in seen:
            seen.add(aid)
            merged.append((doc, score, "keyword"))

    merged.sort(key=lambda row: -row[1])
    return merged[:limit]


def retrieve_wellness_suggestions(
    query: str,
    *,
    limit: int = 3,
    lang: str = "vi",
    min_score: float | None = None,
    require_threshold: bool = True,
    log_context: str = "",
) -> WellnessRetrievalResult:
    """
    Search wellness catalog and return UI suggestions when confidence is high enough.

    ``require_threshold=False`` skips the suggestion threshold (testing / manual calls only).
    """
    cfg = get_medical_config().wellness
    threshold = cfg.suggestion_min_score if min_score is None else min_score

    vector_hits = search_wellness_scored(query, top_k=limit)
    keyword_hits = keyword_search_scored(query, limit=limit)
    merged = _merge_scored(vector_hits, keyword_hits, limit=limit)

    if not merged:
        result = WellnessRetrievalResult([], 0.0, "none")
    elif require_threshold and merged[0][1] < threshold:
        result = WellnessRetrievalResult([], merged[0][1], merged[0][2])
    else:
        suggestions = [
            to_suggestion(doc, lang=lang)
            for doc, score, _ in merged
            if score >= cfg.min_score
        ]
        result = WellnessRetrievalResult(suggestions, merged[0][1], merged[0][2])

    _print_wellness_retrieval(
        query=query,
        vector_hits=vector_hits,
        keyword_hits=keyword_hits,
        merged=merged,
        threshold=threshold,
        require_threshold=require_threshold,
        result=result,
        context=log_context,
    )
    return result


def attach_wellness_after_retrieval(
    state: dict[str, Any],
    *,
    lang: str = "vi",
) -> dict[str, Any]:
    """After RAG / web search, attach activity buttons if wellness score passes threshold."""
    if state.get("suggested_activities"):
        return state

    agent_name = str(state.get("agent_name") or "")
    if "RAG_AGENT" not in agent_name and "WEB_SEARCH_PROCESSOR_AGENT" not in agent_name:
        return state

    from app.medical.validation_input import extract_input_text

    query = extract_input_text(state.get("current_input")) or ""
    if not query.strip():
        return state

    result = retrieve_wellness_suggestions(
        query,
        lang=lang,
        require_threshold=True,
        log_context="post_rag_web",
    )
    if not result.suggestions:
        return state

    return {
        **state,
        "suggested_activities": result.suggestions,
        "wellness_retrieval_score": result.top_score,
        "wellness_retrieval_source": result.source,
    }
