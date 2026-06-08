"""Extract user text from medical agent inputs."""

from __future__ import annotations

from typing import Any


def extract_input_text(current_input: str | dict[str, Any] | None) -> str:
    if isinstance(current_input, str):
        return current_input.strip()
    if isinstance(current_input, dict):
        return str(current_input.get("text", "")).strip()
    return ""
