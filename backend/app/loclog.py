"""Print helpers that prefix each line with the caller's ``filename:lineno``."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path


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
