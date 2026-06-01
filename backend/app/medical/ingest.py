"""CLI: ingest medical PDFs into Qdrant."""

from __future__ import annotations

import argparse
import json
import logging
import warnings

warnings.filterwarnings("ignore")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

from app.medical.agents.rag_agent import MedicalRAG
from app.medical.config import get_medical_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest medical documents into Qdrant RAG.")
    parser.add_argument("--file", type=str, help="Single file path")
    parser.add_argument("--dir", type=str, help="Directory of files")
    args = parser.parse_args()

    if not args.file and not args.dir:
        parser.error("Provide --file or --dir")

    config = get_medical_config()
    rag = MedicalRAG(config)

    if args.file:
        result = rag.ingest_file(args.file)
    else:
        result = rag.ingest_directory(args.dir)

    print(json.dumps(result, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
