"""Qdrant semantic search for Helios wellness activities."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from app.medical.agents.rag_agent.vectorstore_qdrant import build_qdrant_client
from app.medical.config import get_medical_config
from app.medical.embeddings import build_embeddings, get_embedding_dim

logger = logging.getLogger(__name__)


def _client() -> QdrantClient:
    cfg = get_medical_config().wellness
    return build_qdrant_client(vector_local_path=cfg.vector_local_path)


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


def count_wellness_collection_points() -> int:
    client = _client()
    return _collection_point_count(client, _collection_name())


def clear_wellness_vectors() -> dict[str, object]:
    """Delete the entire wellness Qdrant collection (MongoDB unchanged)."""
    client = _client()
    collection = _collection_name()
    points_deleted = 0
    if client.collection_exists(collection):
        info = client.get_collection(collection)
        points_deleted = int(info.points_count or 0)
        client.delete_collection(collection)
    return {
        "success": True,
        "points_deleted": points_deleted,
        "collection": collection,
    }


def _collection_point_count(client: QdrantClient, collection: str) -> int:
    try:
        if not client.collection_exists(collection):
            return 0
        info = client.get_collection(collection)
        return int(info.points_count or 0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Wellness vector count failed: %s", exc)
        return 0


def delete_wellness_activity_vectors(activity_id: str) -> dict[str, object]:
    """Remove all Qdrant points for one activity (including legacy duplicate ids)."""
    client = _client()
    collection = _collection_name()
    if not client.collection_exists(collection):
        return {"success": True, "points_deleted": 0, "activity_id": activity_id}

    before = _collection_point_count(client, collection)

    client.delete(
        collection_name=collection,
        points_selector=Filter(
            should=[
                FieldCondition(key="activity_id", match=MatchValue(value=activity_id)),
                FieldCondition(key="id", match=MatchValue(value=activity_id)),
            ]
        ),
    )

    # Older indexes may have used the raw activity id as the point id.
    client.delete(
        collection_name=collection,
        points_selector=PointIdsList(points=[activity_id, _point_id(activity_id)]),
    )

    after = _collection_point_count(client, collection)
    return {
        "success": True,
        "points_deleted": max(0, before - after),
        "activity_id": activity_id,
    }


def rebuild_wellness_index(docs: list[dict[str, Any]]) -> dict[str, object]:
    """Drop and rebuild the wellness vector collection (one point per activity)."""
    client = _client()
    collection = _collection_name()
    if client.collection_exists(collection):
        client.delete_collection(collection)

    indexed = 0
    errors: list[str] = []
    for doc in docs:
        try:
            upsert_activity(doc, client=client)
            indexed += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{doc.get('id')}: {exc}")
            logger.exception("Failed to index %s", doc.get("id"))

    return {
        "success": indexed > 0 and not errors,
        "indexed": indexed,
        "total": len(docs),
        "errors": errors,
    }


def upsert_activity(
    doc: dict[str, Any],
    *,
    client: QdrantClient | None = None,
) -> None:
    qdrant = client or _client()
    collection = _collection_name()
    dim = get_embedding_dim()

    if not qdrant.collection_exists(collection):
        qdrant.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )

    activity_id = str(doc["id"])
    vector = _embed_text(_activity_embed_text(doc))
    qdrant.upsert(
        collection_name=collection,
        points=[
            PointStruct(
                id=_point_id(activity_id),
                vector=vector,
                payload={"activity_id": activity_id, "id": activity_id},
            )
        ],
    )
