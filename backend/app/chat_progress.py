"""Emit chat processing status for SSE streaming."""

from __future__ import annotations

import threading
from contextvars import ContextVar, Token
from typing import Callable

ProgressCallback = Callable[[str], None]

_progress_callback: ContextVar[ProgressCallback | None] = ContextVar(
    "chat_progress_callback", default=None
)
_thread_lock = threading.Lock()
_thread_callback: ProgressCallback | None = None

STEP_LABELS_VI: dict[str, str] = {
    "analyzing_request": "Đang phân tích yêu cầu",
    "safety_check": "Đang kiểm tra an toàn",
    "input_normalize": "Đang phân tích yêu cầu",
    "emotion_intent": "Đang nhận diện cảm xúc",
    "objection_detector": "Đang hiểu ngữ cảnh",
    "memory_retrieval": "Đang tìm ngữ cảnh liên quan",
    "therapy_router": "Đang lên kế hoạch hỗ trợ",
    "response_generator": "Đang soạn phản hồi",
    "response_filter": "Đang hoàn thiện phản hồi",
    "off_topic_reply": "Đang soạn phản hồi",
    "medical_analyze_input": "Đang phân tích yêu cầu",
    "medical_route": "Đang chọn chuyên gia phù hợp",
    "CONVERSATION_AGENT": "Đang soạn phản hồi",
    "RAG_AGENT": "Đang tra cứu tài liệu y khoa",
    "WEB_SEARCH_PROCESSOR_AGENT": "Đang tìm kiếm trên web",
    "BRAIN_TUMOR_AGENT": "Đang phân tích ảnh MRI não",
    "CHEST_XRAY_AGENT": "Đang phân tích ảnh X-quang",
    "SKIN_LESION_AGENT": "Đang phân tích ảnh da",
    "human_validation": "Đang xử lý xác nhận",
    "apply_guardrails": "Đang kiểm tra an toàn nội dung",
    "check_validation": "Đang kiểm tra kết quả",
}

STEP_LABELS_EN: dict[str, str] = {
    "analyzing_request": "Analyzing your request",
    "safety_check": "Running safety check",
    "input_normalize": "Analyzing your request",
    "emotion_intent": "Detecting emotions",
    "objection_detector": "Understanding context",
    "memory_retrieval": "Retrieving relevant context",
    "therapy_router": "Planning support approach",
    "response_generator": "Composing response",
    "response_filter": "Finalizing response",
    "off_topic_reply": "Composing response",
    "medical_analyze_input": "Analyzing your request",
    "medical_route": "Selecting the right specialist",
    "CONVERSATION_AGENT": "Composing response",
    "RAG_AGENT": "Searching medical knowledge",
    "WEB_SEARCH_PROCESSOR_AGENT": "Searching the web",
    "BRAIN_TUMOR_AGENT": "Analyzing brain MRI",
    "CHEST_XRAY_AGENT": "Analyzing chest X-ray",
    "SKIN_LESION_AGENT": "Analyzing skin image",
    "human_validation": "Processing validation",
    "apply_guardrails": "Checking content safety",
    "check_validation": "Reviewing results",
}


def set_progress_callback(callback: ProgressCallback | None) -> Token:
    return _progress_callback.set(callback)


def set_thread_progress_callback(callback: ProgressCallback | None) -> None:
    global _thread_callback
    with _thread_lock:
        _thread_callback = callback


def reset_progress_callback(token: Token) -> None:
    _progress_callback.reset(token)


def emit_progress(step: str) -> None:
    cb = _progress_callback.get()
    if cb is not None:
        cb(step)
        return
    with _thread_lock:
        tcb = _thread_callback
    if tcb is not None:
        tcb(step)


def label_for_step(step: str, lang: str = "vi") -> str:
    table = STEP_LABELS_EN if lang == "en" else STEP_LABELS_VI
    return table.get(step, table.get("analyzing_request", "Processing"))
