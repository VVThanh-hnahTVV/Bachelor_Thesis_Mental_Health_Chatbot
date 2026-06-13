from __future__ import annotations

from typing import Any, Dict, List, Optional


def _chunk_score(doc: Dict[str, Any]) -> float:
    if "combined_score" in doc:
        return float(doc["combined_score"])
    if "rerank_score" in doc:
        return float(doc["rerank_score"])
    # Qdrant cosine distance: lower is better
    return -float(doc.get("score", 0.0))


def normalize_sub_queries(
    sub_queries: Optional[List[str]],
    original_query: str,
    *,
    max_count: int = 4,
) -> List[str]:
    """Normalize route-agent sub-queries; fall back to the original query."""
    cleaned: List[str] = []
    for item in sub_queries or []:
        text = str(item).strip()
        if text and text not in cleaned:
            cleaned.append(text)

    if not cleaned:
        fallback = str(original_query).strip()
        return [fallback] if fallback else []

    return cleaned[:max_count]


def dedupe_chunks(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the highest-scoring chunk per document id."""
    best_by_id: Dict[str, Dict[str, Any]] = {}
    for doc in docs:
        doc_id = str(doc.get("id", ""))
        if not doc_id:
            continue
        existing = best_by_id.get(doc_id)
        if existing is None or _chunk_score(doc) > _chunk_score(existing):
            best_by_id[doc_id] = doc
    return list(best_by_id.values())


def cap_chunks(docs: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Sort by relevance score descending and keep the top N chunks."""
    if limit <= 0:
        return []
    return sorted(docs, key=_chunk_score, reverse=True)[:limit]


def dedupe_picture_paths(paths: List[str]) -> List[str]:
    """Remove duplicate picture URLs while preserving order."""
    seen: set[str] = set()
    unique: List[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique
