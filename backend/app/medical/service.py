"""Medical chat service — wraps vendored LangGraph in async-friendly API."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Union

from langchain_core.messages import AIMessage, BaseMessage

from app.medical.agents.agent_decision import process_query
from app.medical.config import UPLOADS_MEDICAL, get_medical_config

logger = logging.getLogger(__name__)

ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


@dataclass
class MedicalTurnResult:
    reply: str
    agent_name: str
    needs_validation: bool = False
    result_image_url: str | None = None


def _extract_reply(result: dict[str, Any]) -> str:
    output = result.get("output")
    if isinstance(output, AIMessage):
        return str(output.content or "")
    if isinstance(output, str):
        return output
    messages = result.get("messages") or []
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage):
            return str(last.content or "")
        if hasattr(last, "content"):
            return str(last.content)
    return ""


def _agent_name(result: dict[str, Any]) -> str:
    return str(result.get("agent_name") or "MEDICAL")


def _needs_validation(agent_name: str) -> bool:
    return "HUMAN_VALIDATION" in agent_name.upper()


def _result_image_url(agent_name: str) -> str | None:
    if "SKIN_LESION" not in agent_name.upper():
        return None
    out_path = Path(get_medical_config().medical_cv.skin_lesion_segmentation_output_path)
    if out_path.is_file():
        return "/uploads/medical/skin_lesion_output/segmentation_plot.png"
    return None


def _run_sync(
    query: Union[str, dict[str, str]],
    *,
    thread_id: str,
    conversation_summary: str = "",
) -> MedicalTurnResult:
    result = process_query(
        query,
        thread_id=thread_id,
        conversation_summary=conversation_summary,
    )
    agent = _agent_name(result)
    return MedicalTurnResult(
        reply=_extract_reply(result),
        agent_name=agent,
        needs_validation=_needs_validation(agent),
        result_image_url=_result_image_url(agent),
    )


class MedicalChatService:
    async def handle_message(
        self,
        session_id: str,
        message: str,
        *,
        conversation_summary: str = "",
    ) -> MedicalTurnResult:
        return await asyncio.to_thread(
            _run_sync,
            message,
            thread_id=session_id,
            conversation_summary=conversation_summary,
        )

    async def handle_upload(
        self,
        session_id: str,
        image_bytes: bytes,
        filename: str,
        text: str = "",
        *,
        conversation_summary: str = "",
    ) -> MedicalTurnResult:
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError("Unsupported file type. Allowed: PNG, JPG, JPEG")

        upload_dir = UPLOADS_MEDICAL / "backend"
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4()}_{Path(filename).name}"
        file_path = upload_dir / safe_name
        file_path.write_bytes(image_bytes)

        query: dict[str, str] = {"text": text, "image": str(file_path)}
        try:
            return await asyncio.to_thread(
                _run_sync,
                query,
                thread_id=session_id,
                conversation_summary=conversation_summary,
            )
        finally:
            try:
                file_path.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning("Failed to remove temp upload %s: %s", file_path, exc)

    async def handle_validation(
        self,
        session_id: str,
        validation_result: str,
        comments: str | None = None,
        *,
        conversation_summary: str = "",
    ) -> MedicalTurnResult:
        validation_query = f"Validation result: {validation_result}"
        if comments:
            validation_query += f" Comments: {comments}"
        return await asyncio.to_thread(
            _run_sync,
            validation_query,
            thread_id=session_id,
            conversation_summary=conversation_summary,
        )


_medical_service: MedicalChatService | None = None


def get_medical_service() -> MedicalChatService:
    global _medical_service
    if _medical_service is None:
        _medical_service = MedicalChatService()
    return _medical_service
