"""Filter the generated retrieval dataset down to mental-health questions.

The document store currently holds legacy HIV/general-medical chunks alongside
the intended mental-health corpus, so raw generation picks up off-topic
questions. This script drops questions whose ground-truth chunk is dominated by
infectious-disease / general-medical content and keeps the mental-health ones.

A chunk is rejected when it contains many medical/HIV markers and at least as
many of those as mental-health markers. This is a content heuristic over the
full chunk text, not just the stored excerpt.

Usage:
    .venv/bin/python evaluation/filter_mental_health.py
"""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]

MEDICAL = re.compile(
    r"\b(HIV|AIDS|antiretroviral|ART|CD4|CD8|viral load|virus|viral|infection|"
    r"infect|pathogen|Clostridioides|difficile|opportunistic|monocyte|macrophage|"
    r"lymphocyte|epidemi|transmission|perinatal|vaccine|antibod|plasma|T[\s-]?cell|"
    r"tuberculosis|Mycobacterium|myelopathy|HBV|HCV|carcinoma|tumou?r)\b",
    re.I,
)
MENTAL_HEALTH = re.compile(
    r"\b(anxiety|depress|therapy|therapist|cognitive|behavior|CBT|DBT|mood|"
    r"emotion|panic|phobia|trauma|PTSD|stress|mindful|psycholog|psychiat|disorder|"
    r"distress|self[\s-]?esteem|coping|neurocognitive|mental|relax|breathing|"
    r"worry|thought|feeling|grief)\b",
    re.I,
)


def is_mental_health_chunk(text: str) -> tuple[bool, int, int]:
    med = len(MEDICAL.findall(text))
    mh = len(MENTAL_HEALTH.findall(text))
    # Reject only when medical content clearly dominates the chunk.
    rejected = med >= 3 and med >= mh
    return (not rejected), mh, med


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--in",
        dest="in_path",
        type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "retrieval_eval.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "retrieval_eval_mental_health.jsonl",
    )
    parser.add_argument(
        "--docs-db",
        type=Path,
        default=BACKEND_ROOT / "data" / "medical" / "docs_db",
    )
    args = parser.parse_args()

    lines = [json.loads(l) for l in args.in_path.open(encoding="utf-8")]
    meta = lines[0].get("_meta", {}) if lines and "_meta" in lines[0] else {}
    records = [r for r in lines if "_meta" not in r]

    by_chunk = defaultdict(list)
    for record in records:
        by_chunk[record["chunk_id"]].append(record)

    kept_records = []
    dropped_chunks = []
    for chunk_id, chunk_records in by_chunk.items():
        chunk_path = args.docs_db / chunk_id
        text = chunk_path.read_text(encoding="utf-8", errors="ignore")
        keep, mh, med = is_mental_health_chunk(text)
        if keep:
            kept_records.extend(chunk_records)
        else:
            dropped_chunks.append((chunk_id, mh, med))

    # Renumber ids so the filtered set is self-consistent.
    for i, record in enumerate(kept_records, start=1):
        record["id"] = f"q{i:04d}"

    meta = {
        **meta,
        "filtered_from": str(args.in_path.name),
        "filter": "mental_health_only",
        "num_chunks": len(by_chunk) - len(dropped_chunks),
        "num_questions": len(kept_records),
    }
    with args.out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"_meta": meta}, ensure_ascii=False) + "\n")
        for record in kept_records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(
        f"Kept {len(kept_records)} questions from "
        f"{len(by_chunk) - len(dropped_chunks)} chunks "
        f"(dropped {len(dropped_chunks)} off-topic chunks)."
    )
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
