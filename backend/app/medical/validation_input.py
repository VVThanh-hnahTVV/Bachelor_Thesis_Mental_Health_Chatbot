"""Parse human-in-the-loop validation submissions from the /chat/validate API."""

from __future__ import annotations

from typing import Any


def extract_input_text(current_input: str | dict[str, Any] | None) -> str:
    if isinstance(current_input, str):
        return current_input.strip()
    if isinstance(current_input, dict):
        return str(current_input.get("text", "")).strip()
    return ""


def parse_validation_submission(text: str) -> dict[str, str] | None:
    """
    Parse payloads like:
    - Validation result: yes
    - Validation result: no Comments: Needs review
    - Validation: no — Needs review
    """
    raw = text.strip()
    if not raw:
        return None

    lower = raw.lower()
    body = ""
    if lower.startswith("validation result:"):
        body = raw.split(":", 1)[1].strip()
    elif lower.startswith("validation:"):
        body = raw.split(":", 1)[1].strip()
    else:
        return None

    comments = ""
    if "—" in body:
        parts = body.split("—", 1)
        body = parts[0].strip()
        comments = parts[1].strip() if len(parts) > 1 else comments

    marker = " comments:"
    marker_idx = body.lower().find(marker)
    if marker_idx >= 0:
        comments = body[marker_idx + len(marker) :].strip()
        body = body[:marker_idx].strip()

    verdict = body.strip().lower()
    if verdict.startswith("yes"):
        return {"result": "yes", "comments": comments}
    if verdict.startswith("no"):
        return {"result": "no", "comments": comments}
    return None


def is_validation_submission(text: str) -> bool:
    return parse_validation_submission(text) is not None
