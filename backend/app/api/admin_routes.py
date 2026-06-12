from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.auth.dependencies import require_admin
from app.crawl.pipeline import run_crawl
from app.db.repository import get_admin_overview_stats
from app.crawl.staging import (
    DEFAULT_STAGING_DIR,
    count_by_status,
    get_article,
    list_articles,
    move_article,
    update_article,
)
from app.crawl.web_ingest import build_web_vector_index, count_web_collection_points
from app.medical.config import get_medical_config

router = APIRouter(prefix="/api/v1/admin")

_index_jobs: dict[str, dict[str, Any]] = {}


class CrawlRunBody(BaseModel):
    max_per_feed: int = Field(8, ge=1, le=50)
    max_total: int = Field(25, ge=1, le=100)
    max_age_days: int = Field(730, ge=30, le=3650)
    include_research: bool = True
    research_max: int = Field(8, ge=0, le=30)


class ArticlePatchBody(BaseModel):
    action: Literal["approve", "reject"] | None = None
    topics: list[str] | None = None


class BulkArticleBody(BaseModel):
    source_ids: list[str] = Field(..., min_length=1)
    action: Literal["approve", "reject"]


def _staging_dir() -> str:
    return get_medical_config().web_corpus.staging_dir


def _get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Database not ready")
    return db


@router.get("/overview")
async def admin_overview(
    request: Request,
    days: int = Query(7, ge=1, le=30),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    db = _get_db(request)
    stats = await get_admin_overview_stats(db, days=days)
    staging = count_by_status(base_dir=_staging_dir())
    stats["knowledge_staging"] = {
        "pending": staging.get("pending", 0),
        "approved": staging.get("approved", 0),
        "rejected": staging.get("rejected", 0),
        "indexed": staging.get("indexed", 0),
    }
    approved = staging.get("approved", 0) + staging.get("indexed", 0)
    total_staged = sum(staging.values()) or 1
    stats["knowledge_staging_health_pct"] = round((approved / total_staged) * 100)
    return stats


@router.post("/crawl/run")
async def admin_crawl_run(
    body: CrawlRunBody,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        run_crawl,
        max_per_feed=body.max_per_feed,
        max_total=body.max_total,
        max_age_days=body.max_age_days,
        include_research=body.include_research,
        research_max=body.research_max,
        staging_dir=_staging_dir(),
    )
    return result


@router.get("/articles")
async def admin_list_articles(
    status: Literal["pending", "approved", "rejected", "indexed"] = Query("pending"),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    rows = list_articles(status, base_dir=_staging_dir(), include_full_text=False)
    return {"status": status, "count": len(rows), "articles": rows}


@router.get("/articles/{source_id}")
async def admin_get_article(
    source_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    article = get_article(source_id, base_dir=_staging_dir())
    if article is None:
        raise HTTPException(404, "Article not found")
    return article.to_dict()


@router.patch("/articles/{source_id}")
async def admin_patch_article(
    source_id: str,
    body: ArticlePatchBody,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    article = get_article(source_id, base_dir=_staging_dir())
    if article is None:
        raise HTTPException(404, "Article not found")

    if body.topics is not None:
        updated = update_article(source_id, base_dir=_staging_dir(), topics=body.topics)
        if updated is None:
            raise HTTPException(404, "Article not found")
        article = updated

    if body.action == "approve":
        if article.status != "pending":
            raise HTTPException(400, f"Cannot approve from status {article.status}")
        moved = move_article(
            source_id,
            from_status="pending",
            to_status="approved",
            base_dir=_staging_dir(),
            reviewed_by=str(admin.get("_id", "")),
        )
        if moved is None:
            raise HTTPException(400, "Approve failed")
        return moved.to_dict()

    if body.action == "reject":
        if article.status != "pending":
            raise HTTPException(400, f"Cannot reject from status {article.status}")
        moved = move_article(
            source_id,
            from_status="pending",
            to_status="rejected",
            base_dir=_staging_dir(),
            reviewed_by=str(admin.get("_id", "")),
        )
        if moved is None:
            raise HTTPException(400, "Reject failed")
        return moved.to_dict()

    return article.to_dict()


@router.post("/articles/bulk")
async def admin_bulk_articles(
    body: BulkArticleBody,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    to_status = "approved" if body.action == "approve" else "rejected"
    from_status = "pending"
    changed: list[str] = []
    errors: list[str] = []

    for source_id in body.source_ids:
        article = get_article(source_id, base_dir=_staging_dir())
        if article is None:
            errors.append(f"{source_id}: not found")
            continue
        if article.status != from_status:
            errors.append(f"{source_id}: wrong status {article.status}")
            continue
        moved = move_article(
            source_id,
            from_status=from_status,
            to_status=to_status,
            base_dir=_staging_dir(),
            reviewed_by=str(admin.get("_id", "")),
        )
        if moved is None:
            errors.append(f"{source_id}: move failed")
        else:
            changed.append(source_id)

    return {"changed": changed, "errors": errors}


def _run_index_job(job_id: str) -> None:
    job = _index_jobs[job_id]

    def on_progress(**kwargs: Any) -> None:
        job["progress"] = kwargs

    try:
        result = build_web_vector_index(staging_dir=_staging_dir(), on_progress=on_progress)
        job["status"] = "done" if result.get("success") else "error"
        job["result"] = result
        job["finished_at"] = datetime.now(UTC).isoformat()
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now(UTC).isoformat()


@router.post("/index/build")
async def admin_build_index(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, str]:
    job_id = str(uuid.uuid4())
    _index_jobs[job_id] = {
        "job_id": job_id,
        "status": "running",
        "progress": {"current": 0, "total": 0, "title": ""},
        "started_at": datetime.now(UTC).isoformat(),
    }
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _run_index_job, job_id)
    return {"job_id": job_id}


@router.get("/index/jobs/{job_id}")
async def admin_index_job_status(
    job_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    job = _index_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/index/stats")
async def admin_index_stats(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    counts = count_by_status(base_dir=_staging_dir())
    points = await asyncio.to_thread(count_web_collection_points)
    return {
        "staging": counts,
        "web_collection_points": points,
        "web_collection": get_medical_config().web_corpus.collection_name,
    }
