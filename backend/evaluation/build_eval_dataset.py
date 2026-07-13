"""Build a retrieval evaluation dataset from the Helios document store.

Samples parent chunks from the LocalFileStore docstore (data/medical/docs_db),
asks an LLM to generate realistic user questions answerable by each chunk, and
writes (question, ground-truth chunk) pairs as JSONL.

The resulting dataset supports retrieval metrics (Recall@k, MRR): a retrieval
run is correct when the ground-truth chunk appears among the top-k parents.

Usage:
    .venv/bin/python evaluation/build_eval_dataset.py --num-chunks 25
"""

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from topic_filter import is_mental_health_chunk

BACKEND_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_ROOT / ".env")

GENERATION_PROMPT = """You are helping build an evaluation dataset for a mental-health \
support chatbot that answers user questions via retrieval over a document corpus.

Below is one chunk from that corpus. If the chunk contains substantive content that a \
real user question could be answered from, generate exactly 2 questions:
- one in Vietnamese ("vi") and one in English ("en");
- phrased the way a real end user would ask (everyday language, NOT copied phrasing \
from the text, no references to "the document/text/chunk");
- each question must be answerable from this chunk alone.

If the chunk is NOT suitable (reference list, table of contents, index, boilerplate, \
fragmented text), mark it unsuitable.

Return strict JSON:
{"suitable": true/false, "questions": [{"language": "vi", "question": "..."}, {"language": "en", "question": "..."}]}

CHUNK:
---
%s
---"""


def is_candidate(text: str) -> bool:
    """Filter out chunks unlikely to yield good questions before spending tokens."""
    if len(text) < 400:
        return False
    if text.count("doi:") + text.count("DOI:") > 3:
        return False
    letters = sum(c.isalpha() for c in text)
    return letters / max(len(text), 1) > 0.6


def generate_for_chunk(client: OpenAI, model: str, text: str) -> dict:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": GENERATION_PROMPT % text[:4000]}],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    return json.loads(response.choices[0].message.content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docs-db",
        type=Path,
        default=BACKEND_ROOT / "data" / "medical" / "docs_db",
        help="LocalFileStore directory holding parent chunks",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "retrieval_eval.jsonl",
    )
    parser.add_argument("--num-chunks", type=int, default=25)
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--all-topics",
        action="store_true",
        help="Sample from every chunk instead of mental-health chunks only",
    )
    args = parser.parse_args()

    chunk_files = sorted(p for p in args.docs_db.iterdir() if p.is_file())
    if not chunk_files:
        print(f"No chunk files found in {args.docs_db}", file=sys.stderr)
        return 1

    random.seed(args.seed)
    random.shuffle(chunk_files)

    client = OpenAI()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    records = []
    used_chunks = 0
    skipped_filter = 0
    skipped_topic = 0
    skipped_llm = 0
    for path in chunk_files:
        if used_chunks >= args.num_chunks:
            break
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        text = re.sub(r"\s+", " ", text)
        if not is_candidate(text):
            skipped_filter += 1
            continue
        if not args.all_topics and not is_mental_health_chunk(text)[0]:
            skipped_topic += 1
            continue
        try:
            result = generate_for_chunk(client, args.model, text)
        except Exception as exc:  # noqa: BLE001 - skip bad generations, keep going
            print(f"  ! generation failed for {path.name}: {exc}", file=sys.stderr)
            skipped_llm += 1
            continue
        if not result.get("suitable") or not result.get("questions"):
            skipped_llm += 1
            continue

        used_chunks += 1
        content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        for item in result["questions"]:
            question = str(item.get("question", "")).strip()
            language = str(item.get("language", "")).strip().lower()
            if not question or language not in {"vi", "en"}:
                continue
            records.append(
                {
                    "id": f"q{len(records) + 1:04d}",
                    "question": question,
                    "language": language,
                    "chunk_id": path.name,
                    "chunk_hash": content_hash,
                    "chunk_excerpt": text[:300],
                }
            )
        print(f"  + {path.name} ({used_chunks}/{args.num_chunks})")

    dataset = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "generator_model": args.model,
        "seed": args.seed,
        "docs_db": str(args.docs_db),
        "num_chunks": used_chunks,
        "num_questions": len(records),
    }
    with args.out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": dataset}, ensure_ascii=False) + "\n")
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"\nWrote {len(records)} questions from {used_chunks} chunks to {args.out}\n"
        f"(skipped: {skipped_filter} by pre-filter, {skipped_topic} off-topic, "
        f"{skipped_llm} by LLM/suitability)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
