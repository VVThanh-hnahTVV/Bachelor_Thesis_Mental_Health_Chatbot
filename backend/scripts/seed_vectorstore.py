#!/usr/bin/env python3
"""Optional: rebuild lexical corpus file (placeholder for future vector/Chroma seed)."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "app" / "data" / "knowledge" / "chunks.json"


def main() -> None:
    if not CHUNKS.exists():
        print("chunks.json missing; nothing to do.")
        return
    data = json.loads(CHUNKS.read_text(encoding="utf-8"))
    print(f"Loaded {len(data)} chunks from {CHUNKS}")
    print("Lexical RAG uses this file at runtime; optional OpenAI/Chroma extension can be added here.")


if __name__ == "__main__":
    main()
