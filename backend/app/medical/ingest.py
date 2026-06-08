"""CLI: ingest medical PDFs into Qdrant."""

from __future__ import annotations

import argparse
import json
import logging
import os
import warnings

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from app.medical.agents.rag_agent.doc_parser import resolve_ingest_parse_provider
from app.medical.agents.rag_agent import MedicalRAG
from app.medical.config import get_medical_config
from app.medical.llm import resolve_ingest_provider

logger = logging.getLogger(__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest medical documents into Qdrant RAG.")
    parser.add_argument("--file", type=str, help="Single file path")
    parser.add_argument("--dir", type=str, help="Directory of files")
    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.error("Provide --file or --dir")

    config = get_medical_config()
    ingest_model = os.getenv("INGEST_OPENAI_MODEL") or os.getenv("OPENAI_MODEL", "")
    logger.info(
        "Ingest LLM: provider=%s model=%s | parse=%s",
        resolve_ingest_provider(),
        ingest_model or "(provider default)",
        resolve_ingest_parse_provider(),
    )
    rag = MedicalRAG(config)

    if args.file:
        result = rag.ingest_file(args.file)
    else:
        result = rag.ingest_directory(args.dir)

    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
