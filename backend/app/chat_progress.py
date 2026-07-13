"""Emit chat processing status for SSE streaming."""

from __future__ import annotations

import threading
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Callable

ProgressCallback = Callable[["ProgressEvent"], None]

_progress_callback: ContextVar[ProgressCallback | None] = ContextVar(
    "chat_progress_callback", default=None
)
_thread_lock = threading.Lock()
_thread_callback: ProgressCallback | None = None


@dataclass(frozen=True)
class ProgressEvent:
    step: str
    detail: str | None = None


STEP_LABELS_VI: dict[str, str] = {
    "analyzing_request": "Đang phân tích yêu cầu",
    "medical_analyze_input": "Đang kiểm tra nội dung",
    "medical_route": "Đang chọn hướng hỗ trợ",
    "CONVERSATION_AGENT": "Đang soạn phản hồi",
    "RAG_AGENT": "Đang tra cứu tài liệu tham khảo",
    "WEB_SEARCH_PROCESSOR_AGENT": "Đang tìm kiếm thông tin",
    "web_search_query": "Đang chuẩn bị truy vấn tìm kiếm",
    "web_search_tavily": "Đang tìm trên web",
    "web_search_pubmed": "Đang tra cứu y khoa",
    "web_search_found": "Đã tìm thấy nguồn",
    "web_search_synthesize": "Đang tổng hợp kết quả",
    "WELLNESS_AGENT": "Đang gợi ý bài tập thư giãn",
    "apply_guardrails": "Đang kiểm tra an toàn nội dung",
    "HUMAN_HANDOFF": "Đang chuyển tới chuyên viên",
}

STEP_LABELS_EN: dict[str, str] = {
    "analyzing_request": "Analyzing your request",
    "medical_analyze_input": "Checking your message",
    "medical_route": "Choosing support approach",
    "CONVERSATION_AGENT": "Composing response",
    "RAG_AGENT": "Searching reference materials",
    "WEB_SEARCH_PROCESSOR_AGENT": "Searching for information",
    "web_search_query": "Preparing search query",
    "web_search_tavily": "Searching the web",
    "web_search_pubmed": "Searching medical literature",
    "web_search_found": "Source found",
    "web_search_synthesize": "Summarizing results",
    "WELLNESS_AGENT": "Suggesting wellness activities",
    "apply_guardrails": "Checking content safety",
    "HUMAN_HANDOFF": "Connecting you with a counselor",
}


def set_progress_callback(callback: ProgressCallback | None) -> Token:
    return _progress_callback.set(callback)


def set_thread_progress_callback(callback: ProgressCallback | None) -> None:
    global _thread_callback
    with _thread_lock:
        _thread_callback = callback


def reset_progress_callback(token: Token) -> None:
    _progress_callback.reset(token)


def emit_progress(step: str, detail: str | None = None) -> None:
    event = ProgressEvent(step=step, detail=detail)
    cb = _progress_callback.get()
    if cb is not None:
        cb(event)
        return
    with _thread_lock:
        tcb = _thread_callback
    if tcb is not None:
        tcb(event)


def label_for_step(step: str, lang: str = "en") -> str:
    table = STEP_LABELS_EN if lang == "en" else STEP_LABELS_VI
    return table.get(step, table.get("analyzing_request", "Processing"))
