"""Run a retrieval ablation over the mental-health eval dataset.

For each question we compute the ranked list of retrieved chunk ids under four
configurations and score them against the ground-truth chunk id:

    baseline   single original query, no reranking
    +subquery  multilingual sub-queries, no reranking
    +rerank    single original query, cross-encoder reranking
    both       sub-queries + reranking (the production setup)

Metrics: Recall@1/3/5 and MRR, overall and split by question language.

This reuses the live RAG components (embeddings, Qdrant hybrid retrieval,
cross-encoder), so it retrieves against the current index. It does NOT call the
answer generator, so cost is limited to embeddings + sub-query generation.

Usage:
    .venv/bin/python evaluation/run_retrieval_eval.py
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

# Silence the RAG components' INFO chatter so progress stays readable.
logging.disable(logging.INFO)

from app.medical.agents.rag_agent import MedicalRAG  # noqa: E402
from app.medical.agents.rag_agent.query_expander import (  # noqa: E402
    cap_chunks,
    dedupe_chunks,
)
from app.medical.config import get_medical_config  # noqa: E402

CONFIGS = ["baseline", "+subquery", "+rerank", "both"]
K_VALUES = (1, 3, 5)

SUBQUERY_PROMPT = """You are the retrieval planner of a mental-health chatbot. Given a \
user question, produce self-contained retrieval sub-queries for vector search over a \
mental-health document corpus.

Rules:
- Return 1-4 sub-queries covering the distinct information needs (definition, symptoms, \
treatment, mechanism, ...). Simple questions get 1.
- Each sub-query must be self-contained: name the condition/topic explicitly, no pronouns.
- The corpus has both English and Vietnamese material, so for each intent add BOTH an \
English and a Vietnamese sub-query.
- Return strict JSON: {"sub_queries": ["...", "..."]}

QUESTION: %s"""


def generate_sub_queries(client: OpenAI, model: str, question: str) -> list[str]:
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": SUBQUERY_PROMPT % question}],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        data = json.loads(response.choices[0].message.content)
        subs = [str(s).strip() for s in data.get("sub_queries", []) if str(s).strip()]
        return subs or [question]
    except Exception as exc:  # noqa: BLE001
        print(f"  ! sub-query generation failed: {exc}", file=sys.stderr)
        return [question]


def make_query_runners(rag: MedicalRAG):
    """Per-query retrieval/rerank with caching so the 4 configs share work.

    Each unique query string is retrieved once and reranked at most once; the
    four configurations then just recombine these cached per-query results.
    """
    raw_cache: dict[str, list[dict]] = {}
    rerank_cache: dict[str, list[dict]] = {}

    def raw(query: str) -> list[dict]:
        if query not in raw_cache:
            raw_cache[query] = rag._retrieve_for_subquery(query)
        return raw_cache[query]

    def reranked(query: str) -> list[dict]:
        if query not in rerank_cache:
            docs = raw(query)
            if rag.reranker and len(docs) > 1:
                out = rag.reranker.rerank(query, docs, rag.parsed_content_dir)
                # rerank() returns (docs, picture_paths); fallback returns just docs.
                docs = out[0] if isinstance(out, tuple) else out
            rerank_cache[query] = docs
        return rerank_cache[query]

    def ids_for(queries: list[str], getter) -> list[str]:
        all_docs: list[dict] = []
        for query in queries:
            all_docs.extend(getter(query))
        merged = cap_chunks(dedupe_chunks(all_docs), rag.config.rag.context_limit)
        return [str(d.get("id", "")) for d in merged]

    return raw, reranked, ids_for


def rank_of(chunk_id: str, ranked_ids: list[str]) -> int | None:
    for i, rid in enumerate(ranked_ids, start=1):
        if rid == chunk_id:
            return i
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "retrieval_eval_mental_health.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "retrieval_results.json",
    )
    parser.add_argument("--subquery-model", default="gpt-4o-mini")
    parser.add_argument(
        "--reranker-model",
        default=None,
        help="Override the cross-encoder reranker model (e.g. BAAI/bge-reranker-v2-m3)",
    )
    parser.add_argument("--limit", type=int, default=0, help="Evaluate first N questions (0 = all)")
    args = parser.parse_args()

    rows = [json.loads(l) for l in args.dataset.open(encoding="utf-8")]
    records = [r for r in rows if "_meta" not in r]
    if args.limit:
        records = records[: args.limit]

    print(f"Loading RAG components and evaluating {len(records)} questions...", flush=True)
    config = get_medical_config()
    if args.reranker_model:
        print(f"Overriding reranker model -> {args.reranker_model}", flush=True)
        config.rag.reranker_model = args.reranker_model
    rag = MedicalRAG(config)
    client = OpenAI()
    raw, reranked, ids_for = make_query_runners(rag)

    # Stream per-question scoring to a progress file so partial runs survive.
    progress_path = args.out.with_suffix(".progress.jsonl")
    progress_fh = progress_path.open("w", encoding="utf-8")

    per_record = []
    for idx, record in enumerate(records, start=1):
        question = record["question"]
        chunk_id = record["chunk_id"]
        sub_queries = generate_sub_queries(client, args.subquery_model, question)

        ranked = {
            "baseline": ids_for([question], raw),
            "+subquery": ids_for(sub_queries, raw),
            "+rerank": ids_for([question], reranked),
            "both": ids_for(sub_queries, reranked),
        }
        ranks = {cfg: rank_of(chunk_id, ids) for cfg, ids in ranked.items()}
        row = {
            "id": record["id"],
            "language": record["language"],
            "chunk_id": chunk_id,
            "num_sub_queries": len(sub_queries),
            "ranks": ranks,
        }
        per_record.append(row)
        progress_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        progress_fh.flush()
        print(
            f"[{idx}/{len(records)}] {record['id']} ({record['language']}) "
            + " ".join(f"{c}={ranks[c] or '-'}" for c in CONFIGS),
            flush=True,
        )

    progress_fh.close()

    # Aggregate overall and by language.
    def aggregate(subset: list[dict]) -> dict:
        n = len(subset)
        out = {}
        for cfg in CONFIGS:
            ranks = [r["ranks"][cfg] for r in subset]
            out[cfg] = {
                **{
                    f"recall@{k}": sum(1 for x in ranks if x is not None and x <= k) / n
                    for k in K_VALUES
                },
                "mrr": sum((1.0 / x) for x in ranks if x is not None) / n,
            }
        return out

    languages = sorted({r["language"] for r in per_record})
    summary = {
        "dataset": str(args.dataset.name),
        "num_questions": len(per_record),
        "overall": aggregate(per_record),
        "by_language": {
            lang: {
                "n": sum(1 for r in per_record if r["language"] == lang),
                "metrics": aggregate([r for r in per_record if r["language"] == lang]),
            }
            for lang in languages
        },
    }

    args.out.write_text(
        json.dumps({"summary": summary, "per_record": per_record}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print_report(summary)
    print(f"\nWrote detailed results to {args.out}")
    return 0


def print_report(summary: dict) -> None:
    def table(title: str, agg: dict, n: int) -> None:
        print(f"\n{title} (n={n})")
        header = f"{'config':<11}" + "".join(f"{'R@'+str(k):>8}" for k in K_VALUES) + f"{'MRR':>8}"
        print(header)
        print("-" * len(header))
        for cfg in CONFIGS:
            m = agg[cfg]
            row = f"{cfg:<11}" + "".join(f"{m['recall@'+str(k)]:>8.3f}" for k in K_VALUES)
            row += f"{m['mrr']:>8.3f}"
            print(row)

    print("\n" + "=" * 44)
    print("RETRIEVAL ABLATION RESULTS")
    print("=" * 44)
    table("Overall", summary["overall"], summary["num_questions"])
    for lang, block in summary["by_language"].items():
        table(f"Language: {lang}", block["metrics"], block["n"])


if __name__ == "__main__":
    raise SystemExit(main())
