"""Print helpers that prefix each line with the caller's ``filename:lineno``."""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

from langchain_core.messages import BaseMessage, HumanMessage


_SKIP_CALLER_FILES = frozenset({"factory.py", "loclog.py", "llm.py"})


def infer_caller_label(*, prefix: str | None = None) -> str:
    """Return ``module.function`` of the nearest app frame outside logging helpers."""
    for frame_info in inspect.stack()[2:]:
        path = Path(frame_info.filename)
        if path.name in _SKIP_CALLER_FILES:
            continue
        if "site-packages" in path.as_posix():
            continue
        if "app" not in path.parts:
            continue
        label = f"{path.stem}.{frame_info.function}"
        return f"{prefix}.{label}" if prefix else label
    return f"{prefix}.llm" if prefix else "llm"


def coerce_llm_input_to_messages(input: object) -> list[BaseMessage]:
    """Normalize LangChain model input to a list of messages for logging."""
    if isinstance(input, str):
        return [HumanMessage(content=input)]
    if isinstance(input, list) and input and isinstance(input[0], BaseMessage):
        return input
    to_messages = getattr(input, "to_messages", None)
    if callable(to_messages):
        return to_messages()
    return [HumanMessage(content=str(input))]


def loc_print(*args: object, sep: str = " ", end: str = "\n", file=sys.stderr, flush: bool = True) -> None:
    """Like ``print``, but prefix with ``[file.py:123]`` of the *call site*."""
    frame = inspect.currentframe()
    if frame is None or frame.f_back is None:
        prefix = "[?:?]"
    else:
        caller = frame.f_back
        name = Path(caller.f_code.co_filename).name
        prefix = f"[{name}:{caller.f_lineno}]"
    print(prefix, *args, sep=sep, end=end, file=file, flush=flush)


def _message_role(msg: BaseMessage) -> str:
    name = type(msg).__name__
    if name.endswith("Message"):
        return name[: -len("Message")].upper()
    return name.upper()


def _message_content_text(msg: BaseMessage) -> str:
    content = msg.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False, indent=2)
    return str(content)


def print_llm_prompt(label: str, provider: str, messages: list[BaseMessage]) -> None:
    """Print LLM input messages to stderr (visible in uvicorn terminal)."""
    sep = "=" * 72
    loc_print(sep)
    loc_print(f"LLM PROMPT  label={label}  provider={provider}")
    loc_print(sep)
    for index, msg in enumerate(messages, start=1):
        loc_print(f"--- {_message_role(msg)} ({index}) ---")
        loc_print(_message_content_text(msg))
        loc_print("")
    loc_print(sep)
