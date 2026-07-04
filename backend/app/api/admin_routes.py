from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from bson import ObjectId
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, EmailStr, Field

from app.auth.dependencies import require_admin, require_admin_panel
from app.auth.repository import (
    admin_user_public,
    count_admins,
    count_users,
    create_user,
    delete_user_by_id,
    get_user_by_email,
    get_user_by_id,
    list_users,
    update_user_by_id,
)
from app.auth.security import hash_password
from app.crawl.pipeline import run_crawl
from app.db.repository import (
    count_conversations_admin,
    count_wellness_activities,
    conversation_admin_dict,
    get_admin_overview_stats,
    get_conversation_admin_stats,
    get_conversation_by_session,
    get_wellness_activity_by_id,
    list_conversations_admin,
    list_conversations_support_queue,
    list_messages_chronological,
    list_wellness_activities,
    upsert_wellness_activity,
    wellness_activity_admin_dict,
)
from app.crawl.staging import (
    DEFAULT_STAGING_DIR,
    count_by_status,
    get_article,
    list_articles,
    move_article,
    update_article,
)
from app.admin.pdf_corpus import (
    count_pdf_collection_points,
    delete_pdf_file,
    list_pdf_files,
    raw_documents_dir,
)
from app.admin.vector_cleanup import (
    delete_web_article,
    unindex_pdf_vectors,
    unindex_web_article,
)
from app.crawl.web_ingest import build_web_vector_index, count_web_collection_points
from app.admin.settings_snapshot import build_admin_settings_snapshot
from app.llm.openai_platform_usage import get_admin_usage_stats

from app.medical.agents.rag_agent import MedicalRAG
from app.medical.config import get_medical_config

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])

_index_jobs: dict[str, dict[str, Any]] = {}


class CrawlRunBody(BaseModel):
    max_per_feed: int = Field(8, ge=1, le=50, description="Số bài tối đa lấy từ mỗi nguồn feed.")
    max_total: int = Field(25, ge=1, le=100, description="Tổng số bài tối đa cho một lần crawl.")
    max_age_days: int = Field(730, ge=30, le=3650, description="Chỉ lấy bài mới hơn số ngày này.")
    include_research: bool = Field(True, description="Có gồm nguồn nghiên cứu (research) hay không.")
    research_max: int = Field(8, ge=0, le=30, description="Số bài research tối đa.")


class ArticlePatchBody(BaseModel):
    action: Literal["approve", "reject"] | None = Field(
        None, description="Hành động duyệt: `approve` hoặc `reject`."
    )
    topics: list[str] | None = Field(
        None, description="Danh sách chủ đề gán cho bài.", examples=[["lo âu", "giấc ngủ"]]
    )


class BulkArticleBody(BaseModel):
    source_ids: list[str] = Field(
        ..., min_length=1, description="Danh sách ID bài cần xử lý hàng loạt."
    )
    action: Literal["approve", "reject"] = Field(description="Hành động áp dụng cho tất cả.")


class BuildIndexBody(BaseModel):
    source_ids: list[str] | None = Field(
        None,
        min_length=1,
        description="Omit to index all approved articles",
    )


class AdminUserCreateBody(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["Trần Thị B"])
    email: EmailStr = Field(examples=["support@example.com"])
    password: str = Field(..., min_length=8, max_length=128, examples=["MatKhau123"])
    role: Literal["user", "admin", "support"] = Field(
        "user", description="Vai trò của tài khoản."
    )


class AdminUserUpdateBody(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120, examples=["Trần Thị B"])
    role: Literal["user", "admin", "support"] | None = Field(
        None, description="Vai trò mới (nếu đổi)."
    )
    password: str | None = Field(
        None, min_length=8, max_length=128, description="Mật khẩu mới (nếu đổi)."
    )


class PdfIngestBody(BaseModel):
    path: str | None = Field(
        None,
        description="Relative path under data/medical/raw; omit to ingest all PDFs",
    )


class WellnessActivityPatchBody(BaseModel):
    active: bool | None = None
    implemented: bool | None = None
    title_vi: str | None = Field(None, min_length=1, max_length=200)
    title_en: str | None = Field(None, min_length=1, max_length=200)
    description_vi: str | None = Field(None, max_length=2000)
    description_en: str | None = Field(None, max_length=2000)
    duration_min: int | None = Field(None, ge=1, le=180)
    tags: list[str] | None = None
    benefits: list[str] | None = None
    benefits_en: list[str] | None = None


def _staging_dir() -> str:
    return get_medical_config().web_corpus.staging_dir


def _get_db(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is None:
        raise HTTPException(503, "Database not ready")
    return db


@router.get(
    "/overview",
    summary="Tổng quan bảng điều khiển",
    description="Thống kê tổng quan hệ thống trong `days` ngày gần nhất, kèm tình trạng kho tri thức.",
)
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


@router.get(
    "/settings",
    summary="Cấu hình hệ thống",
    description="Trả về snapshot cấu hình hiện tại (LLM, embedding, RAG, tính năng...).",
)
async def admin_settings(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    return build_admin_settings_snapshot()


@router.get(
    "/settings/usage",
    summary="Thống kê sử dụng LLM",
    description="Thống kê mức sử dụng nền tảng OpenAI trong `days` ngày gần nhất.",
)
async def admin_settings_usage(
    days: int = Query(7, ge=1, le=90),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    return await get_admin_usage_stats(days=days)


@router.post(
    "/crawl/run",
    summary="Chạy crawl nội dung",
    description="Kích hoạt pipeline thu thập bài viết y tế từ các nguồn RSS/nghiên cứu vào staging.",
)
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


@router.get(
    "/articles",
    summary="Danh sách bài trong staging",
    description="Liệt kê bài viết theo trạng thái duyệt: `pending`, `approved`, `rejected`, `indexed`.",
)
async def admin_list_articles(
    status: Literal["pending", "approved", "rejected", "indexed"] = Query("pending"),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    rows = list_articles(status, base_dir=_staging_dir(), include_full_text=False)
    return {"status": status, "count": len(rows), "articles": rows}


@router.get(
    "/articles/{source_id}",
    summary="Chi tiết một bài",
    description="Trả về nội dung đầy đủ của một bài trong staging theo `source_id`.",
    responses={404: {"description": "Không tìm thấy bài."}},
)
async def admin_get_article(
    source_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    article = get_article(source_id, base_dir=_staging_dir())
    if article is None:
        raise HTTPException(404, "Article not found")
    return article.to_dict()


@router.patch(
    "/articles/{source_id}",
    summary="Duyệt / cập nhật bài",
    description="Cập nhật chủ đề và/hoặc duyệt (`approve`) hay từ chối (`reject`) một bài đang chờ.",
    responses={
        400: {"description": "Không thể chuyển trạng thái từ trạng thái hiện tại."},
        404: {"description": "Không tìm thấy bài."},
    },
)
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


@router.post(
    "/articles/bulk",
    summary="Duyệt / từ chối hàng loạt",
    description="Duyệt hoặc từ chối nhiều bài cùng lúc. Trả về danh sách đã đổi và các lỗi (nếu có).",
)
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


def _run_web_index_job(job_id: str, source_ids: list[str] | None = None) -> None:
    job = _index_jobs[job_id]

    def on_progress(**kwargs: Any) -> None:
        job["progress"] = kwargs

    try:
        result = build_web_vector_index(
            staging_dir=_staging_dir(),
            on_progress=on_progress,
            source_ids=source_ids,
        )
        job["status"] = "done" if result.get("success") else "error"
        job["result"] = result
        job["finished_at"] = datetime.now(UTC).isoformat()
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now(UTC).isoformat()


def _run_pdf_ingest_job(job_id: str, relative_path: str | None) -> None:
    job = _index_jobs[job_id]
    try:
        config = get_medical_config()
        rag = MedicalRAG(config)
        if relative_path:
            raw = raw_documents_dir()
            full = raw / relative_path
            if not full.is_file():
                raise FileNotFoundError(f"PDF not found: {relative_path}")
            result = rag.ingest_file(str(full))
        else:
            result = rag.ingest_directory(config.rag.raw_documents_dir)
        job["status"] = "done" if result.get("success") else "error"
        job["result"] = result
        job["finished_at"] = datetime.now(UTC).isoformat()
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(exc)
        job["finished_at"] = datetime.now(UTC).isoformat()


def _start_job(job_type: Literal["web", "pdf"], title: str, runner, *args: Any) -> str:
    job_id = str(uuid.uuid4())
    _index_jobs[job_id] = {
        "job_id": job_id,
        "job_type": job_type,
        "title": title,
        "status": "running",
        "progress": {"current": 0, "total": 0, "title": ""},
        "started_at": datetime.now(UTC).isoformat(),
    }
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, runner, job_id, *args)
    return job_id


@router.post(
    "/index/build",
    summary="Xây chỉ mục vector web",
    description=(
        "Khởi chạy job nền để lập chỉ mục vector cho các bài đã duyệt. "
        "Trả về `job_id` để theo dõi tiến độ qua `/index/jobs/{job_id}`."
    ),
)
async def admin_build_index(
    body: BuildIndexBody | None = None,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, str]:
    source_ids = body.source_ids if body else None
    if source_ids:
        title = f"Web corpus index: {len(source_ids)} article(s)"
    else:
        title = "Web corpus index"
    job_id = _start_job("web", title, _run_web_index_job, source_ids)
    return {"job_id": job_id}


@router.get(
    "/index/jobs",
    summary="Danh sách job chỉ mục",
    description="Liệt kê tối đa 50 job lập chỉ mục gần nhất (web/PDF).",
)
async def admin_list_index_jobs(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    jobs = sorted(
        _index_jobs.values(),
        key=lambda j: j.get("started_at") or "",
        reverse=True,
    )
    return {"jobs": jobs[:50]}


@router.get(
    "/index/jobs/{job_id}",
    summary="Trạng thái job chỉ mục",
    description="Theo dõi tiến độ/kết quả của một job lập chỉ mục theo `job_id`.",
    responses={404: {"description": "Không tìm thấy job."}},
)
async def admin_index_job_status(
    job_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    job = _index_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@router.get(
    "/index/stats",
    summary="Thống kê chỉ mục & kho tri thức",
    description="Số điểm vector web/PDF, số file PDF, cấu hình chunk và embedding.",
)
async def admin_index_stats(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    cfg = get_medical_config()
    counts = count_by_status(base_dir=_staging_dir())
    web_points, pdf_points = await asyncio.gather(
        asyncio.to_thread(count_web_collection_points),
        asyncio.to_thread(count_pdf_collection_points),
    )
    pdfs = await asyncio.to_thread(list_pdf_files)
    return {
        "staging": counts,
        "web_collection_points": web_points,
        "web_collection": cfg.web_corpus.collection_name,
        "pdf_collection_points": pdf_points,
        "pdf_collection": cfg.rag.collection_name,
        "pdf_files_count": len(pdfs),
        "raw_documents_dir": cfg.rag.raw_documents_dir,
        "chunk_size": cfg.rag.chunk_size,
        "chunk_overlap": cfg.rag.chunk_overlap,
        "embedding_provider": cfg.rag.embedding_provider,
    }


@router.get(
    "/pdf",
    summary="Danh sách file PDF",
    description="Liệt kê các file PDF trong kho tài liệu thô (`data/medical/raw`).",
)
async def admin_list_pdfs(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    files = await asyncio.to_thread(list_pdf_files)
    return {"files": files, "count": len(files)}


@router.post(
    "/pdf/upload",
    summary="Tải lên file PDF",
    description="Tải một file PDF vào kho tài liệu thô để chuẩn bị lập chỉ mục.",
    responses={400: {"description": "File không phải PDF hoặc rỗng."}},
)
async def admin_upload_pdf(
    file: UploadFile = File(...),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are allowed")
    raw_dir = raw_documents_dir()
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / filename
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    dest.write_bytes(content)
    stat = dest.stat()
    return {
        "name": filename,
        "path": filename,
        "size_bytes": stat.st_size,
        "modified_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
    }


@router.delete(
    "/articles/{source_id}",
    summary="Xóa bài web (cả vector)",
    description="Xóa một bài web khỏi staging và loại bỏ các vector liên quan.",
    responses={404: {"description": "Không tìm thấy bài."}},
)
async def admin_delete_web_article(
    source_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        delete_web_article,
        source_id,
        staging_dir=_staging_dir(),
    )
    if not result.get("found"):
        raise HTTPException(404, "Article not found")
    return result


@router.delete(
    "/articles/{source_id}/vectors",
    summary="Bỏ chỉ mục vector của bài web",
    description="Xóa các vector của một bài web nhưng vẫn giữ bài trong staging.",
    responses={404: {"description": "Không tìm thấy bài."}},
)
async def admin_unindex_web_article(
    source_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    result = await asyncio.to_thread(
        unindex_web_article,
        source_id,
        staging_dir=_staging_dir(),
    )
    if not result.get("found"):
        raise HTTPException(404, "Article not found")
    return result


@router.delete(
    "/pdf/vectors",
    summary="Bỏ chỉ mục vector của PDF",
    description="Xóa các vector sinh ra từ một file PDF (theo `path`), giữ nguyên file gốc.",
)
async def admin_unindex_pdf_vectors(
    path: str = Query(..., min_length=1),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    return await asyncio.to_thread(unindex_pdf_vectors, path)


@router.delete(
    "/pdf",
    summary="Xóa file PDF",
    description="Xóa một file PDF; mặc định xóa luôn các vector liên quan (`remove_vectors=true`).",
    responses={404: {"description": "Không tìm thấy PDF."}},
)
async def admin_delete_pdf(
    path: str = Query(..., min_length=1),
    remove_vectors: bool = Query(True),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    vectors_removed = 0
    if remove_vectors:
        vector_result = await asyncio.to_thread(unindex_pdf_vectors, path)
        vectors_removed = int(vector_result.get("points_deleted", 0))

    deleted = await asyncio.to_thread(delete_pdf_file, path)
    if not deleted:
        raise HTTPException(404, "PDF not found")
    return {
        "message": "PDF deleted",
        "vectors_removed": vectors_removed,
    }


@router.post(
    "/pdf/ingest",
    summary="Lập chỉ mục PDF",
    description=(
        "Khởi chạy job nền để nạp và lập chỉ mục PDF. Bỏ trống `path` để nạp toàn bộ. "
        "Trả về `job_id` để theo dõi qua `/index/jobs/{job_id}`."
    ),
)
async def admin_pdf_ingest(
    body: PdfIngestBody,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, str]:
    title = f"PDF ingest: {body.path}" if body.path else "PDF ingest: all files"
    job_id = _start_job("pdf", title, _run_pdf_ingest_job, body.path)
    return {"job_id": job_id}


def _parse_user_id(user_id: str) -> ObjectId:
    try:
        return ObjectId(user_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, "Invalid user id") from exc


async def _ensure_not_last_admin(
    db: Any,
    *,
    target_user_id: ObjectId,
    new_role: str | None = None,
    deleting: bool = False,
) -> None:
    target = await get_user_by_id(db, target_user_id)
    if not target or target.get("role") != "admin":
        return
    admin_count = await count_admins(db)
    if admin_count <= 1 and (deleting or new_role == "user"):
        raise HTTPException(400, "Cannot remove the last admin account")


@router.get(
    "/conversations/stats",
    summary="Thống kê hội thoại",
    description="Thống kê hội thoại trong `days` ngày gần nhất (dành cho admin/support).",
)
async def admin_conversation_stats(
    request: Request,
    days: int = Query(7, ge=1, le=30),
    _admin: dict[str, Any] = Depends(require_admin_panel),
) -> dict[str, Any]:
    db = _get_db(request)
    return await get_conversation_admin_stats(db, days=days)


@router.get(
    "/conversations",
    summary="Danh sách hội thoại (phân trang)",
    description="Liệt kê hội thoại có phân trang, hỗ trợ tìm kiếm và lọc theo loại chủ sở hữu.",
)
async def admin_list_conversations(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    owner: Literal["registered", "guest"] | None = Query(None),
    _admin: dict[str, Any] = Depends(require_admin_panel),
) -> dict[str, Any]:
    db = _get_db(request)
    skip = (page - 1) * page_size
    total = await count_conversations_admin(db, search=search, owner=owner)
    conversations = await list_conversations_admin(
        db,
        skip=skip,
        limit=page_size,
        search=search,
        owner=owner,
    )
    return {
        "conversations": conversations,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.get(
    "/conversations/queue",
    summary="Hàng đợi hỗ trợ",
    description="Danh sách hội thoại đang chờ hỗ trợ hoặc được gán cho chuyên viên hiện tại.",
)
async def admin_conversations_queue(
    request: Request,
    admin: dict[str, Any] = Depends(require_admin_panel),
) -> dict[str, Any]:
    db = _get_db(request)
    admin_id = admin.get("_id")
    assigned_id = admin_id if isinstance(admin_id, ObjectId) else None
    rows = await list_conversations_support_queue(db, assigned_support_id=assigned_id)
    return {
        "conversations": [conversation_admin_dict({**row, "message_count": 0}) for row in rows],
    }


@router.get(
    "/conversations/{session_id}",
    summary="Chi tiết hội thoại",
    description="Trả về thông tin quản trị của một hội thoại theo `session_id`.",
    responses={404: {"description": "Không tìm thấy hội thoại."}},
)
async def admin_get_conversation(
    session_id: str,
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin_panel),
) -> dict[str, Any]:
    db = _get_db(request)
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return conversation_admin_dict({**conv, "message_count": 0, "_user_doc": []})


@router.get(
    "/conversations/{session_id}/messages",
    summary="Tin nhắn của hội thoại (admin)",
    description="Lịch sử tin nhắn theo thời gian, bao gồm cả tin nội bộ dành cho support.",
    responses={404: {"description": "Không tìm thấy hội thoại."}},
)
async def admin_conversation_messages(
    session_id: str,
    request: Request,
    limit: int = Query(500, ge=1, le=1000),
    _admin: dict[str, Any] = Depends(require_admin_panel),
) -> list[dict[str, Any]]:
    db = _get_db(request)
    conv = await get_conversation_by_session(db, session_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    cid = conv.get("_id")
    if not isinstance(cid, ObjectId):
        raise HTTPException(404, "Conversation not found")
    rows = await list_messages_chronological(
        db, conversation_id=cid, limit=limit, include_support_only=True
    )
    out: list[dict[str, Any]] = []
    for doc in rows:
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        created = doc.get("created_at")
        out.append(
            {
                "id": str(doc.get("_id") or ""),
                "role": str(doc.get("role") or ""),
                "content": str(doc.get("content") or ""),
                "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
                "metadata": meta,
                "sender_name": meta.get("sender_name") or doc.get("role"),
            }
        )
    return out


@router.post(
    "/conversations/{session_id}/join",
    summary="Tham gia hỗ trợ hội thoại",
    description="Chuyên viên tiếp nhận phiên và chuyển sang chế độ hỗ trợ người thật (`human`).",
    responses={400: {"description": "Không thể tham gia ở trạng thái hiện tại."}},
)
async def admin_join_conversation(
    session_id: str,
    request: Request,
    admin: dict[str, Any] = Depends(require_admin_panel),
) -> dict[str, Any]:
    from app.handoff.service import join_support_session

    db = _get_db(request)
    redis = getattr(request.app.state, "redis", None)
    try:
        return await join_support_session(db, redis, session_id=session_id, admin_user=admin)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.post(
    "/conversations/{session_id}/leave",
    summary="Rời phiên hỗ trợ",
    description="Chuyên viên rời phiên; hội thoại có thể trở lại chế độ AI.",
    responses={400: {"description": "Không thể rời ở trạng thái hiện tại."}},
)
async def admin_leave_conversation(
    session_id: str,
    request: Request,
    admin: dict[str, Any] = Depends(require_admin_panel),
) -> dict[str, Any]:
    from app.handoff.service import leave_support_session

    db = _get_db(request)
    redis = getattr(request.app.state, "redis", None)
    try:
        return await leave_support_session(db, redis, session_id=session_id, admin_user=admin)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.get(
    "/users",
    summary="Danh sách người dùng",
    description="Liệt kê người dùng có phân trang, hỗ trợ tìm kiếm và lọc theo vai trò.",
)
async def admin_list_users(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None, max_length=120),
    role: Literal["user", "admin", "support"] | None = Query(None),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    db = _get_db(request)
    skip = (page - 1) * page_size
    total = await count_users(db, search=search, role=role)
    users = await list_users(
        db, skip=skip, limit=page_size, search=search, role=role
    )
    return {
        "users": users,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post(
    "/users",
    summary="Tạo người dùng",
    description="Tạo tài khoản mới với vai trò chỉ định (`user`/`admin`/`support`).",
    responses={409: {"description": "Email đã được đăng ký."}},
)
async def admin_create_user(
    request: Request,
    body: AdminUserCreateBody,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    db = _get_db(request)
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(409, "Email already registered")
    doc = await create_user(
        db,
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    return admin_user_public(doc)


@router.get(
    "/users/{user_id}",
    summary="Chi tiết người dùng",
    description="Trả về thông tin quản trị của một người dùng theo `user_id`.",
    responses={
        400: {"description": "`user_id` không hợp lệ."},
        404: {"description": "Không tìm thấy người dùng."},
    },
)
async def admin_get_user(
    request: Request,
    user_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    db = _get_db(request)
    oid = _parse_user_id(user_id)
    doc = await get_user_by_id(db, oid)
    if not doc:
        raise HTTPException(404, "User not found")
    return admin_user_public(doc)


@router.patch(
    "/users/{user_id}",
    summary="Cập nhật người dùng",
    description="Cập nhật tên, vai trò và/hoặc mật khẩu. Không thể hạ cấp admin cuối cùng.",
    responses={
        400: {"description": "Dữ liệu không hợp lệ hoặc là admin cuối cùng."},
        404: {"description": "Không tìm thấy người dùng."},
    },
)
async def admin_update_user(
    request: Request,
    user_id: str,
    body: AdminUserUpdateBody,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    db = _get_db(request)
    oid = _parse_user_id(user_id)
    if not await get_user_by_id(db, oid):
        raise HTTPException(404, "User not found")

    if body.role is not None:
        await _ensure_not_last_admin(db, target_user_id=oid, new_role=body.role)

    password_hash = hash_password(body.password) if body.password else None
    try:
        updated = await update_user_by_id(
            db,
            oid,
            name=body.name,
            role=body.role,
            password_hash=password_hash,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    if not updated:
        raise HTTPException(404, "User not found")
    return updated


@router.get(
    "/wellness/stats",
    summary="Thống kê bài tập wellness",
    description="Số bài tập trong DB/seed và số điểm vector của bộ sưu tập wellness.",
)
async def admin_wellness_stats(
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.medical.agents.wellness_agent.vectorstore import count_wellness_collection_points
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = _get_db(request)
    db_total = await count_wellness_activities(db)
    db_active = await count_wellness_activities(db, active_only=True)
    db_implemented = await count_wellness_activities(db, implemented_only=True)
    seed_count = len(DEFAULT_WELLNESS_ACTIVITIES)
    vector_points = await asyncio.to_thread(count_wellness_collection_points)
    cfg = get_medical_config()

    return {
        "db_total": db_total,
        "db_active": db_active,
        "db_implemented": db_implemented,
        "seed_catalog_count": seed_count,
        "using_seed_fallback": db_total == 0,
        "vector_points": vector_points,
        "vector_collection": cfg.wellness.collection_name,
    }


@router.get(
    "/wellness/activities",
    summary="Danh sách bài tập (admin)",
    description="Liệt kê bài tập wellness với bộ lọc trạng thái; fallback sang seed nếu DB trống.",
)
async def admin_list_wellness_activities(
    request: Request,
    active_only: bool = Query(False),
    implemented_only: bool = Query(False),
    scope: str | None = Query(None),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = _get_db(request)
    rows = await list_wellness_activities(
        db,
        scope=scope,
        active_only=active_only,
        implemented_only=implemented_only,
        limit=200,
    )
    source = "mongodb"
    if not rows:
        source = "seed"
        rows = [
            d
            for d in DEFAULT_WELLNESS_ACTIVITIES
            if (not scope or scope in (d.get("scope") or []))
            and (not active_only or d.get("active"))
            and (not implemented_only or d.get("implemented"))
        ]

    return {
        "source": source,
        "count": len(rows),
        "activities": [wellness_activity_admin_dict(r) for r in rows],
    }


@router.get(
    "/wellness/activities/{activity_id}",
    summary="Chi tiết bài tập (admin)",
    description="Trả về chi tiết một bài tập từ MongoDB hoặc danh mục seed.",
    responses={404: {"description": "Không tìm thấy bài tập."}},
)
async def admin_get_wellness_activity(
    request: Request,
    activity_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = _get_db(request)
    doc = await get_wellness_activity_by_id(db, activity_id)
    if doc:
        return {"source": "mongodb", "activity": wellness_activity_admin_dict(doc)}

    for seed_doc in DEFAULT_WELLNESS_ACTIVITIES:
        if str(seed_doc.get("id")) == activity_id:
            return {
                "source": "seed",
                "activity": wellness_activity_admin_dict(seed_doc),
            }

    raise HTTPException(404, "Activity not found")


@router.patch(
    "/wellness/activities/{activity_id}",
    summary="Cập nhật bài tập",
    description="Cập nhật nội dung song ngữ, trạng thái, thời lượng, tag và lợi ích của bài tập.",
    responses={404: {"description": "Không tìm thấy bài tập."}},
)
async def admin_patch_wellness_activity(
    request: Request,
    activity_id: str,
    body: WellnessActivityPatchBody,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = _get_db(request)
    doc = await get_wellness_activity_by_id(db, activity_id)
    if not doc:
        for seed_doc in DEFAULT_WELLNESS_ACTIVITIES:
            if str(seed_doc.get("id")) == activity_id:
                doc = dict(seed_doc)
                break
    if not doc:
        raise HTTPException(404, "Activity not found")

    if body.active is not None:
        doc["active"] = body.active
    if body.implemented is not None:
        doc["implemented"] = body.implemented
    if body.duration_min is not None:
        doc["duration_min"] = body.duration_min
    if body.tags is not None:
        doc["tags"] = body.tags
    if body.benefits is not None:
        doc["benefits"] = body.benefits
    if body.benefits_en is not None:
        doc["benefits_en"] = body.benefits_en

    title = doc.get("title")
    if not isinstance(title, dict):
        title = {"vi": str(title or ""), "en": str(title or "")}
    description = doc.get("description")
    if not isinstance(description, dict):
        description = {"vi": str(description or ""), "en": str(description or "")}

    if body.title_vi is not None:
        title["vi"] = body.title_vi
    if body.title_en is not None:
        title["en"] = body.title_en
    if body.description_vi is not None:
        description["vi"] = body.description_vi
    if body.description_en is not None:
        description["en"] = body.description_en

    doc["title"] = title
    doc["description"] = description

    await upsert_wellness_activity(db, doc)
    updated = await get_wellness_activity_by_id(db, activity_id)
    if not updated:
        raise HTTPException(500, "Failed to save activity")
    return {"activity": wellness_activity_admin_dict(updated)}


@router.post(
    "/wellness/seed",
    summary="Nạp danh mục bài tập mặc định",
    description="Ghi (upsert) toàn bộ danh mục bài tập mặc định vào MongoDB.",
)
async def admin_seed_wellness_activities(
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = _get_db(request)
    seeded = 0
    for doc in DEFAULT_WELLNESS_ACTIVITIES:
        await upsert_wellness_activity(db, dict(doc))
        seeded += 1

    return {"seeded": seeded, "total": len(DEFAULT_WELLNESS_ACTIVITIES)}


@router.delete(
    "/wellness/vectors",
    summary="Xóa toàn bộ vector wellness",
    description="Xóa sạch bộ sưu tập vector của các bài tập wellness.",
)
async def admin_clear_wellness_vectors(
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.medical.agents.wellness_agent.vectorstore import clear_wellness_vectors

    return await asyncio.to_thread(clear_wellness_vectors)


@router.delete(
    "/wellness/activities/{activity_id}/vectors",
    summary="Xóa vector của một bài tập",
    description="Xóa các vector thuộc về một bài tập wellness cụ thể.",
)
async def admin_delete_wellness_activity_vectors(
    activity_id: str,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.medical.agents.wellness_agent.vectorstore import delete_wellness_activity_vectors

    return await asyncio.to_thread(delete_wellness_activity_vectors, activity_id)


@router.post(
    "/wellness/reindex",
    summary="Xây lại chỉ mục wellness",
    description="Xây lại toàn bộ chỉ mục vector cho các bài tập đang bật và đã triển khai.",
)
async def admin_reindex_wellness_vectors(
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    from app.medical.agents.wellness_agent.vectorstore import rebuild_wellness_index
    from app.wellness.catalog_seed import DEFAULT_WELLNESS_ACTIVITIES

    db = _get_db(request)
    rows = await list_wellness_activities(
        db, active_only=True, implemented_only=True, limit=200
    )
    if not rows:
        rows = [
            d
            for d in DEFAULT_WELLNESS_ACTIVITIES
            if d.get("active") and d.get("implemented")
        ]

    return await asyncio.to_thread(rebuild_wellness_index, rows)


@router.delete(
    "/users/{user_id}",
    summary="Xóa người dùng",
    description="Xóa một tài khoản. Không thể tự xóa chính mình hoặc admin cuối cùng.",
    responses={
        400: {"description": "Tự xóa hoặc là admin cuối cùng."},
        404: {"description": "Không tìm thấy người dùng."},
    },
)
async def admin_delete_user(
    request: Request,
    user_id: str,
    admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, str]:
    db = _get_db(request)
    oid = _parse_user_id(user_id)
    admin_oid = admin.get("_id")
    if isinstance(admin_oid, ObjectId) and admin_oid == oid:
        raise HTTPException(400, "Cannot delete your own account")

    await _ensure_not_last_admin(db, target_user_id=oid, deleting=True)
    deleted = await delete_user_by_id(db, oid)
    if not deleted:
        raise HTTPException(404, "User not found")
    return {"message": "User deleted"}
