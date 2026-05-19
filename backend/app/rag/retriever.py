from __future__ import annotations

import logging
from typing import Any, TypedDict

from app.config import get_settings
from app.db.repository import list_knowledge_chunks
from app.rag.corpus import lexical_scores, load_chunks
from app.rag.embeddings import cosine_similarity, embed_text

logger = logging.getLogger(__name__)


class RetrievedChunk(TypedDict):
    id: str
    text: str
    topic: str
    source: str
    score: float
    mode: str


def _from_lexical(query: str, top_k: int) -> list[RetrievedChunk]:
    scored = lexical_scores(query, load_chunks(), top_k=top_k)
    return [
        RetrievedChunk(
            id=str(chunk.get("id", "")),
            text=str(chunk.get("text", "")),
            topic=str(chunk.get("topic", "")),
            source="chunks.json",
            score=float(score),
            mode="lexical",
        )
        for score, chunk in scored
        if score > 0
    ]


async def retrieve_chunks(db: Any, query: str) -> tuple[list[RetrievedChunk], str]:
    s = get_settings()
    top_k = max(1, s.rag_top_k)
    lexical = _from_lexical(query, top_k=top_k)
    if not s.enable_vector_rag or db is None:
        return lexical, "lexical" if lexical else "none"

    try:
        rows = await list_knowledge_chunks(db)
        query_embedding = await embed_text(query)
        scored: list[RetrievedChunk] = []
        for row in rows:
            embedding = row.get("embedding")
            if not isinstance(embedding, list):
                continue
            score = cosine_similarity(query_embedding, [float(v) for v in embedding])
            if score >= s.rag_min_score:
                scored.append(
                    RetrievedChunk(
                        id=str(row.get("id", "")),
                        text=str(row.get("text", "")),
                        topic=str(row.get("topic", "")),
                        source=str(row.get("source", "mongo")),
                        score=float(score),
                        mode="vector",
                    )
                )
        scored.sort(key=lambda item: item["score"], reverse=True)
        vector = scored[:top_k]
        if vector and lexical:
            by_id = {item["id"]: item for item in vector}
            for item in lexical:
                if item["id"] and item["id"] not in by_id:
                    vector.append(item)
                if len(vector) >= top_k:
                    break
            return vector[:top_k], "hybrid"
        if vector:
            return vector, "vector"
    except Exception as exc:  # noqa: BLE001
        logger.warning("vector RAG failed, using lexical fallback: %s", exc)

    return lexical, "lexical" if lexical else "none"
