from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.medical.agents.rag_agent.vectorstore_qdrant import CorpusVectorStore
from app.medical.config import get_medical_config

PDF_EXTENSIONS = {".pdf"}


def raw_documents_dir() -> Path:
    return Path(get_medical_config().rag.raw_documents_dir)


def _safe_relative_path(raw_dir: Path, relative_path: str) -> Path:
    rel = Path(relative_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("Invalid path")
    full = (raw_dir / rel).resolve()
    if not str(full).startswith(str(raw_dir.resolve())):
        raise ValueError("Invalid path")
    return full


def list_pdf_files() -> list[dict[str, Any]]:
    raw_dir = raw_documents_dir()
    if not raw_dir.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in raw_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in PDF_EXTENSIONS:
            continue
        stat = path.stat()
        rel = path.relative_to(raw_dir)
        rows.append(
            {
                "name": path.name,
                "path": str(rel).replace("\\", "/"),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
            }
        )
    rows.sort(key=lambda r: r.get("modified_at") or "", reverse=True)
    return rows


def count_pdf_collection_points() -> int | None:
    cfg = get_medical_config()
    store = CorpusVectorStore.for_pdf_corpus(cfg)
    if not store.collection_exists():
        return 0
    try:
        info = store.client.get_collection(store.collection_name)
        return int(getattr(info, "points_count", 0) or 0)
    except Exception:  # noqa: BLE001
        return None


def delete_pdf_file(relative_path: str) -> bool:
    raw_dir = raw_documents_dir()
    try:
        target = _safe_relative_path(raw_dir, relative_path)
    except ValueError:
        return False
    if not target.is_file():
        return False
    target.unlink()
    return True
