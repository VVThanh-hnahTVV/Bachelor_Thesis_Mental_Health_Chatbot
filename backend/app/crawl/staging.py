from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.crawl.models import CrawledArticle

logger = logging.getLogger(__name__)

StagingStatus = Literal["pending", "approved", "rejected", "indexed"]

STATUSES: tuple[StagingStatus, ...] = ("pending", "approved", "rejected", "indexed")

DEFAULT_STAGING_DIR = Path("data/crawl/staging")

_lock = threading.Lock()


def _resolve_base_dir(base_dir: str | Path) -> Path:
    return Path(base_dir)


def _staging_path(status: StagingStatus, base_dir: str | Path) -> Path:
    return _resolve_base_dir(base_dir) / f"{status}.json"


def _blocklist_path(base_dir: str | Path) -> Path:
    return _resolve_base_dir(base_dir) / "blocklist.json"


def _empty_store() -> dict[str, Any]:
    return {"updated_at": "", "articles": []}


def _read_store(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return _empty_store()
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read staging file %s: %s", path, exc)
        return _empty_store()
    if not isinstance(data, dict):
        return _empty_store()
    articles = data.get("articles")
    if not isinstance(articles, list):
        data["articles"] = []
    return data


def _write_store(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(UTC).isoformat()
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _articles_by_id(status: StagingStatus, base_dir: str | Path) -> dict[str, CrawledArticle]:
    store = _read_store(_staging_path(status, base_dir))
    result: dict[str, CrawledArticle] = {}
    for raw in store.get("articles", []):
        if isinstance(raw, dict) and raw.get("source_id"):
            article = CrawledArticle.from_dict(raw)
            article.status = status
            result[article.source_id] = article
    return result


def _all_known_ids(base_dir: str | Path) -> set[str]:
    base = _resolve_base_dir(base_dir)
    known: set[str] = set()
    for status in STATUSES:
        known.update(_articles_by_id(status, base).keys())
    return known


def blocked_source_ids(*, base_dir: str | Path = DEFAULT_STAGING_DIR) -> set[str]:
    path = _blocklist_path(base_dir)
    store = _read_store(path)
    entries = store.get("entries", [])
    if not isinstance(entries, list):
        return set()
    return {
        str(entry.get("source_id", ""))
        for entry in entries
        if isinstance(entry, dict) and entry.get("source_id")
    }


def is_source_blocked(
    source_id: str,
    *,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
) -> bool:
    return source_id in blocked_source_ids(base_dir=base_dir)


def list_articles(
    status: StagingStatus,
    *,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
    include_full_text: bool = False,
) -> list[dict[str, Any]]:
    base = _resolve_base_dir(base_dir)
    articles = list(_articles_by_id(status, base).values())
    articles.sort(key=lambda a: (a.fetched_at, a.title), reverse=True)
    rows: list[dict[str, Any]] = []
    for article in articles:
        row = article.to_dict()
        if not include_full_text:
            row.pop("full_text", None)
            row["preview"] = article.summary or article.full_text[:280]
        rows.append(row)
    return rows


def get_article(
    source_id: str,
    *,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
) -> CrawledArticle | None:
    base = _resolve_base_dir(base_dir)
    for status in STATUSES:
        article = _articles_by_id(status, base).get(source_id)
        if article is not None:
            return article
    return None


def count_by_status(*, base_dir: str | Path = DEFAULT_STAGING_DIR) -> dict[str, int]:
    base = _resolve_base_dir(base_dir)
    return {status: len(_articles_by_id(status, base)) for status in STATUSES}


def upsert_to_pending(
    article: CrawledArticle,
    *,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
) -> bool:
    """Insert article into pending if URL not seen in any bucket. Returns True if added."""
    base = _resolve_base_dir(base_dir)
    with _lock:
        if article.source_id in _all_known_ids(base) or article.source_id in blocked_source_ids(
            base_dir=base
        ):
            return False

        article.status = "pending"
        path = _staging_path("pending", base)
        store = _read_store(path)
        articles = store.setdefault("articles", [])
        articles.append(article.to_dict())
        _write_store(path, store)
        return True


def move_article(
    source_id: str,
    *,
    from_status: StagingStatus,
    to_status: StagingStatus,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
    reviewed_by: str = "",
    extra: dict[str, Any] | None = None,
) -> CrawledArticle | None:
    base = _resolve_base_dir(base_dir)
    with _lock:
        from_path = _staging_path(from_status, base)
        to_path = _staging_path(to_status, base)
        from_store = _read_store(from_path)
        to_store = _read_store(to_path)

        articles = from_store.get("articles", [])
        moved: dict[str, Any] | None = None
        remaining: list[dict[str, Any]] = []
        for raw in articles:
            if isinstance(raw, dict) and raw.get("source_id") == source_id:
                moved = dict(raw)
            else:
                remaining.append(raw)

        if moved is None:
            return None

        now = datetime.now(UTC).isoformat()
        moved["status"] = to_status
        if reviewed_by and to_status in ("approved", "rejected"):
            moved["reviewed_by"] = reviewed_by
            moved["reviewed_at"] = now
        if to_status == "indexed":
            moved["indexed_at"] = now
        elif from_status == "indexed":
            moved["indexed_at"] = ""
        if to_status == "pending":
            moved["reviewed_at"] = ""
            moved["reviewed_by"] = ""
        if extra:
            moved.update(extra)

        from_store["articles"] = remaining
        to_articles = to_store.setdefault("articles", [])
        to_articles = [a for a in to_articles if a.get("source_id") != source_id]
        to_articles.append(moved)
        to_store["articles"] = to_articles

        _write_store(from_path, from_store)
        _write_store(to_path, to_store)
        return CrawledArticle.from_dict(moved)


def update_article(
    source_id: str,
    *,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
    **fields: Any,
) -> CrawledArticle | None:
    base = _resolve_base_dir(base_dir)
    with _lock:
        for status in STATUSES:
            path = _staging_path(status, base)
            store = _read_store(path)
            changed = False
            for raw in store.get("articles", []):
                if isinstance(raw, dict) and raw.get("source_id") == source_id:
                    raw.update(fields)
                    changed = True
                    updated = CrawledArticle.from_dict(raw)
                    break
            else:
                continue
            if changed:
                _write_store(path, store)
                return updated
    return None


def remove_article(
    source_id: str,
    *,
    from_status: StagingStatus | None = None,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
) -> CrawledArticle | None:
    """Remove an article from a staging bucket and return it."""
    base = _resolve_base_dir(base_dir)
    statuses: tuple[StagingStatus, ...] = (from_status,) if from_status else STATUSES
    with _lock:
        for status in statuses:
            path = _staging_path(status, base)
            store = _read_store(path)
            articles = store.get("articles", [])
            removed: dict[str, Any] | None = None
            remaining: list[dict[str, Any]] = []
            for raw in articles:
                if isinstance(raw, dict) and raw.get("source_id") == source_id:
                    removed = dict(raw)
                else:
                    remaining.append(raw)
            if removed is not None:
                store["articles"] = remaining
                _write_store(path, store)
                article = CrawledArticle.from_dict(removed)
                article.status = status
                return article
    return None


def add_to_blocklist(
    article: CrawledArticle,
    *,
    base_dir: str | Path = DEFAULT_STAGING_DIR,
) -> None:
    """Permanently block an article from being re-crawled."""
    base = _resolve_base_dir(base_dir)
    with _lock:
        path = _blocklist_path(base)
        store = _read_store(path)
        entries = store.setdefault("entries", [])
        if not isinstance(entries, list):
            entries = []
        entries = [
            entry
            for entry in entries
            if not (isinstance(entry, dict) and entry.get("source_id") == article.source_id)
        ]
        entries.append(
            {
                "source_id": article.source_id,
                "canonical_url": article.canonical_url,
                "title": article.title,
                "deleted_at": datetime.now(UTC).isoformat(),
            }
        )
        store["entries"] = entries
        _write_store(path, store)


def list_indexed_content_hashes(*, base_dir: str | Path = DEFAULT_STAGING_DIR) -> set[str]:
    base = _resolve_base_dir(base_dir)
    hashes: set[str] = set()
    for article in _articles_by_id("indexed", base).values():
        if article.content_hash:
            hashes.add(article.content_hash)
    return hashes
