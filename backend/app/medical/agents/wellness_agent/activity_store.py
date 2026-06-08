"""In-memory Helios wellness catalog access (seed fallback)."""

from __future__ import annotations

import re
from typing import Any

from app.db.repository import activity_to_api


def list_helios_activities() -> list[dict[str, Any]]:
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    return [
        d
        for d in DEFAULT_WELLNESS_ACTIVITIES
        if d.get("active")
        and d.get("implemented")
        and "helios" in (d.get("scope") or [])
    ]


def get_activity_by_id(activity_id: str) -> dict[str, Any] | None:
    for doc in list_helios_activities():
        if str(doc.get("id")) == activity_id:
            return doc
    return None


def _activity_search_blob(doc: dict[str, Any]) -> str:
    parts: list[str] = [str(doc.get("id", ""))]
    for field in ("benefits", "benefits_en", "tags"):
        val = doc.get(field)
        if isinstance(val, list):
            parts.extend(str(v) for v in val)
    for field in ("title", "description"):
        val = doc.get(field)
        if isinstance(val, dict):
            parts.extend(str(v) for v in val.values())
        elif val:
            parts.append(str(val))
    return " ".join(parts).lower()


def keyword_search_activities(query: str, *, limit: int = 3) -> list[dict[str, Any]]:
    return [doc for doc, _ in keyword_search_scored(query, limit=limit)]


def keyword_search_scored(
    query: str,
    *,
    limit: int = 3,
) -> list[tuple[dict[str, Any], float]]:
    """Keyword overlap fallback; score in ~0.35–0.85 when tokens match."""
    q = query.strip().lower()
    if not q:
        return [(doc, 0.4) for doc in list_helios_activities()[:limit]]

    tokens = [t for t in re.split(r"\W+", q) if len(t) >= 2]
    if not tokens:
        return []

    scored: list[tuple[float, dict[str, Any]]] = []
    for doc in list_helios_activities():
        blob = _activity_search_blob(doc)
        hits = sum(1 for tok in tokens if tok in blob)
        if hits:
            # Normalized confidence — needs multiple hits to approach suggestion threshold
            score = min(0.85, 0.32 + (hits / len(tokens)) * 0.45)
            scored.append((score, doc))

    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
    if scored:
        return [(doc, score) for score, doc in scored[:limit]]

    return []


def to_suggestion(doc: dict[str, Any], *, lang: str = "vi") -> dict[str, str]:
    api = activity_to_api(doc, lang=lang)
    return {
        "id": str(api["id"]),
        "title": str(api["title"]),
        "description": str(api["description"]),
    }
