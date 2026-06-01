"""Medical multi-agent chat (vendored from Multi-Agent-Medical-Assistant)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.medical.service import MedicalChatService, MedicalTurnResult


def get_medical_service():
    from app.medical.service import get_medical_service as _get

    return _get()


__all__ = ["MedicalChatService", "MedicalTurnResult", "get_medical_service"]
