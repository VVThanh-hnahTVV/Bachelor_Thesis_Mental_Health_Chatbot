from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "chunks.json"


@lru_cache
def load_chunks() -> list[dict[str, str]]:
    if not _CORPUS_PATH.exists():
        return []
    raw = _CORPUS_PATH.read_text(encoding="utf-8")
    data = json.loads(raw)
    out: list[dict[str, str]] = []
    for item in data:
        if isinstance(item, dict) and "text" in item:
            out.append(
                {
                    "id": str(item.get("id", "")),
                    "text": str(item["text"]),
                    "topic": str(item.get("topic", "")),
                }
            )
    return out


def _tokens(s: str) -> set[str]:
    s = s.lower()
    return {t for t in re.split(r"[^a-z0-9]+", s) if len(t) > 2}


def lexical_scores(
    query: str,
    chunks: list[dict[str, str]],
    top_k: int = 5,
) -> list[tuple[float, dict[str, str]]]:
    q = _tokens(query)
    if not q:
        return []
    scored: list[tuple[float, dict[str, str]]] = []
    for c in chunks:
        t = _tokens(c["text"] + " " + c.get("topic", ""))
        if not t:
            continue
        inter = len(q & t)
        if inter == 0:
            continue
        score = inter / (1 + len(t) ** 0.5)
        scored.append((score, c))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]
