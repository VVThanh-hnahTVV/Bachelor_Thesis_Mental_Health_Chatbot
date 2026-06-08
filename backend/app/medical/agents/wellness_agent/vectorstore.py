"""Qdrant semantic search for Helios wellness activities."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

from app.medical.config import get_medical_config
from app.medical.embeddings import build_embeddings, get_embedding_dim

logger = logging.getLogger(__name__)


def _client() -> QdrantClient:
    cfg = get_medical_config().wellness
    return QdrantClient(path=cfg.vector_local_path)


def _collection_name() -> str:
    return get_medical_config().wellness.collection_name


def _embed_text(text: str) -> list[float]:
    return build_embeddings().embed_query(text)


def _activity_embed_text(doc: dict[str, Any]) -> str:
    parts = [
        str(doc.get("id", "")),
        " ".join(doc.get("benefits") or []),
        " ".join(doc.get("benefits_en") or []),
        " ".join(doc.get("tags") or []),
    ]
    title = doc.get("title")
    if isinstance(title, dict):
        parts.extend(str(v) for v in title.values())
    desc = doc.get("description")
    if isinstance(desc, dict):
        parts.extend(str(v) for v in desc.values())
    return "\n".join(p for p in parts if p.strip())


def search_wellness_scored(
    query: str,
    *,
    top_k: int | None = None,
) -> list[tuple[dict[str, Any], float]]:
    """Return (activity_doc, cosine_score) pairs, highest score first."""
    from app.medical.agents.wellness_agent.activity_store import get_activity_by_id

    cfg = get_medical_config().wellness
    k = top_k or cfg.top_k
    client = _client()
    collection = _collection_name()

    try:
        if not client.collection_exists(collection):
            return []
        vector = _embed_text(query)
        response = client.query_points(
            collection_name=collection,
            query=vector,
            limit=k,
            with_payload=True,
        )
        hits = response.points
    except Exception as exc:  # noqa: BLE001
        logger.warning("Wellness vector search failed: %s", exc)
        return []

    out: list[tuple[dict[str, Any], float]] = []
    for hit in hits:
        score = float(hit.score or 0.0)
        if score < cfg.min_score:
            continue
        payload = hit.payload or {}
        activity_id = str(payload.get("activity_id") or payload.get("id") or "")
        doc = get_activity_by_id(activity_id) if activity_id else None
        if doc:
            out.append((doc, score))
    return out


def search_wellness_activities(query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    return [doc for doc, _ in search_wellness_scored(query, top_k=top_k)]


def _point_id(activity_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"helios-wellness:{activity_id}"))


def upsert_activity(doc: dict[str, Any]) -> None:
    cfg = get_medical_config().wellness
    client = _client()
    collection = _collection_name()
    dim = get_embedding_dim()

    if not client.collection_exists(collection):
        client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    activity_id = str(doc["id"])
    vector = _embed_text(_activity_embed_text(doc))
    client.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=_point_id(activity_id),
                vector=vector,
                payload={"activity_id": activity_id, "id": activity_id},
            )
        ],
    )
