"""End-to-end RAGAS evaluation of the medical RAG pipeline.

Unlike run_retrieval_eval.py (which only scores retrieval rank against a
ground-truth chunk id), this drives the *full* answer path — sub-query
generation, hybrid retrieval, reranking, and answer generation by the production
LLM — then scores answer + context quality with an independent judge (gpt-4o-mini).

Metrics (RAGAS):
    faithfulness        answer claims grounded in retrieved context (no hallucination)
    answer_relevancy    answer addresses the question (embedding similarity)
    context_precision   retrieved contexts relevant to the reference, ranked high
    context_recall      retrieved contexts cover the reference chunk's claims

The system under test uses whatever LLM_PROVIDER the app is configured with
(e.g. Groq Llama-4). The RAGAS judge is a separate OpenAI model, so the
evaluation is not self-graded.

Usage:
    .venv/bin/python evaluation/run_ragas_eval.py --limit 15   # smoke test
    .venv/bin/python evaluation/run_ragas_eval.py              # full 86
"""

import argparse
import json
import logging
import sys
import types
from pathlib import Path

# --- Compatibility shim -----------------------------------------------------
# ragas 0.4.3 hard-imports langchain_community.chat_models.vertexai, which was
# removed in langchain-community 0.4.x. Register a stub before importing ragas.
_vertexai_stub = types.ModuleType("langchain_community.chat_models.vertexai")
_vertexai_stub.ChatVertexAI = type("ChatVertexAI", (), {})
sys.modules.setdefault("langchain_community.chat_models.vertexai", _vertexai_stub)
# ---------------------------------------------------------------------------

from dotenv import load_dotenv
from openai import OpenAI

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(BACKEND_ROOT / ".env")

logging.disable(logging.INFO)

from app.medical.agents.rag_agent import MedicalRAG  # noqa: E402
from app.medical.agents.rag_agent.query_expander import (  # noqa: E402
    cap_chunks,
    dedupe_chunks,
)
from app.medical.config import get_medical_config  # noqa: E402
from evaluation.run_retrieval_eval import generate_sub_queries  # noqa: E402


def build_sample(rag: MedicalRAG, client: OpenAI, subquery_model: str, record: dict,
                 docstore) -> dict | None:
    """Run the full RAG pipeline for one question and package a RAGAS sample."""
    question = record["question"]

    sub_queries = generate_sub_queries(client, subquery_model, question)

    # Retrieve + rerank each sub-query, merge and cap (mirrors process_query).
    all_docs: list[dict] = []
    for sq in sub_queries:
        docs = rag._retrieve_for_subquery(sq)
        if rag.reranker and len(docs) > 1:
            out = rag.reranker.rerank(sq, docs, rag.parsed_content_dir)
            docs = out[0] if isinstance(out, tuple) else out
        all_docs.extend(docs)
    merged = cap_chunks(dedupe_chunks(all_docs), rag.config.rag.context_limit)
    contexts = [str(d.get("content", "")) for d in merged if d.get("content")]
    if not contexts:
        return None

    # Generate the answer with the production response generator.
    try:
        result = rag.response_generator.generate_response(
            query=question, retrieved_docs=merged, picture_paths=[], chat_history=None,
        )
        answer = str(result.get("response", "")).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  ! generation failed for {record['id']}: {exc}", file=sys.stderr)
        return None
    if not answer:
        return None

    # Reference: full ground-truth chunk from the docstore (fallback: excerpt).
    reference = record.get("chunk_excerpt", "")
    try:
        blob = docstore.mget([record["chunk_id"]])[0]
        if blob:
            reference = blob.decode("utf-8")
    except Exception:  # noqa: BLE001
        pass

    return {
        "id": record["id"],
        "language": record["language"],
        "user_input": question,
        "response": answer,
        "retrieved_contexts": contexts,
        "reference": reference,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "retrieval_eval_mental_health.jsonl",
    )
    parser.add_argument(
        "--out", type=Path,
        default=BACKEND_ROOT / "data" / "evaluation" / "ragas_results.json",
    )
    parser.add_argument("--subquery-model", default="gpt-4o-mini")
    parser.add_argument("--judge-model", default="gpt-4o-mini")
    parser.add_argument("--embed-model", default="text-embedding-3-small")
    parser.add_argument("--limit", type=int, default=0)
    # Cap contexts passed to the judge. context_precision runs one LLM call per
    # context, so the full ~20 chunks per question causes per-row timeouts.
    parser.add_argument("--score-context-cap", type=int, default=6)
    # Low concurrency avoids OpenAI 429s (which trigger long backoff -> timeout).
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--job-timeout", type=int, default=600)
    # The ground-truth chunk can be ~3.5k chars; the judge re-reads it on every
    # context_precision/recall call, so truncating speeds scoring materially.
    parser.add_argument("--reference-max-chars", type=int, default=1500)
    # Comma list subset of: faithfulness,answer_relevancy,context_precision,context_recall
    parser.add_argument("--metrics", default="all")
    # Skip pipeline; load pre-built samples and only run RAGAS scoring.
    parser.add_argument("--samples", type=Path, default=None)
    args = parser.parse_args()

    if args.samples:
        samples = json.loads(args.samples.read_text(encoding="utf-8"))
        print(f"Loaded {len(samples)} cached samples from {args.samples}; "
              f"skipping pipeline.", flush=True)
        return score_samples(samples, args)

    rows = [json.loads(l) for l in args.dataset.open(encoding="utf-8")]
    records = [r for r in rows if "_meta" not in r]
    if args.limit:
        records = records[: args.limit]

    print(f"Loading RAG pipeline and building {len(records)} samples...", flush=True)
    config = get_medical_config()
    rag = MedicalRAG(config)
    client = OpenAI()

    loaded = rag.vector_store.try_load_vectorstore()
    docstore = loaded[1] if loaded else None

    samples: list[dict] = []
    for idx, record in enumerate(records, start=1):
        sample = build_sample(rag, client, args.subquery_model, record, docstore)
        status = "ok" if sample else "SKIP"
        print(f"[{idx}/{len(records)}] {record['id']} ({record['language']}) {status}",
              flush=True)
        if sample:
            samples.append(sample)

    if not samples:
        print("No samples built; aborting.", file=sys.stderr)
        return 1

    # Persist raw samples so the scoring step is reproducible / re-runnable.
    samples_path = args.out.with_suffix(".samples.json")
    samples_path.write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return score_samples(samples, args)


def score_samples(samples: list[dict], args) -> int:
    """Run RAGAS metrics over pre-built samples and write the summary."""
    print(f"\nScoring {len(samples)} samples with RAGAS "
          f"(judge={args.judge_model})...", flush=True)

    # --- RAGAS scoring ------------------------------------------------------
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    from ragas.run_config import RunConfig

    judge = LangchainLLMWrapper(ChatOpenAI(model=args.judge_model, temperature=0.0))
    embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings(model=args.embed_model))

    dataset = EvaluationDataset.from_list(
        [
            {
                "user_input": s["user_input"],
                "response": s["response"],
                "retrieved_contexts": s["retrieved_contexts"][: args.score_context_cap],
                "reference": str(s["reference"])[: args.reference_max_chars],
            }
            for s in samples
        ]
    )
    available = {
        "faithfulness": faithfulness,
        "answer_relevancy": answer_relevancy,
        "context_precision": context_precision,
        "context_recall": context_recall,
    }
    selected = (list(available) if args.metrics == "all"
                else [m.strip() for m in args.metrics.split(",") if m.strip()])
    metrics = [available[m] for m in selected]
    print(f"Metrics: {selected}", flush=True)
    run_config = RunConfig(
        timeout=args.job_timeout,
        max_workers=args.max_workers,
        max_retries=10,
    )
    result = evaluate(
        dataset, metrics=metrics, llm=judge, embeddings=embeddings,
        run_config=run_config,
    )

    df = result.to_pandas()
    df["id"] = [s["id"] for s in samples]
    df["language"] = [s["language"] for s in samples]

    metric_cols = [c for c in df.columns
                   if c not in {"id", "language", "user_input", "response",
                                "retrieved_contexts", "reference"}]

    def agg(sub):
        # mean() skips NaN; valid_n exposes how many rows actually scored.
        return {c: {"mean": float(sub[c].mean()), "valid_n": int(sub[c].notna().sum())}
                for c in metric_cols}

    summary = {
        "num_samples": len(samples),
        "judge_model": args.judge_model,
        "overall": agg(df),
        "by_language": {
            lang: {"n": int((df["language"] == lang).sum()),
                   "metrics": agg(df[df["language"] == lang])}
            for lang in sorted(df["language"].unique())
        },
    }

    per_record = df[["id", "language"] + metric_cols].to_dict(orient="records")
    args.out.write_text(
        json.dumps({"summary": summary, "per_record": per_record},
                   ensure_ascii=False, indent=2, default=float),
        encoding="utf-8",
    )

    print_report(summary, metric_cols)
    print(f"\nWrote RAGAS results to {args.out}")
    return 0


def print_report(summary: dict, metric_cols: list[str]) -> None:
    def table(title: str, metrics: dict, n: int) -> None:
        print(f"\n{title} (n={n})")
        for c in metric_cols:
            cell = metrics.get(c)
            if isinstance(cell, dict):
                print(f"  {c:<22} {cell['mean']:.3f}  (valid_n={cell['valid_n']})")
                continue
            print(f"  {c:<22} {metrics.get(c, float('nan')):.3f}")

    print("\n" + "=" * 44)
    print("RAGAS EVALUATION RESULTS")
    print("=" * 44)
    table("Overall", summary["overall"], summary["num_samples"])
    for lang, block in summary["by_language"].items():
        table(f"Language: {lang}", block["metrics"], block["n"])


if __name__ == "__main__":
    raise SystemExit(main())
