#!/usr/bin/env python3
"""CLI: crawl mental-health news into staging pending.json."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.crawl.pipeline import run_crawl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl mental-health news into staging.")
    parser.add_argument("--max-per-feed", type=int, default=8)
    parser.add_argument("--max-total", type=int, default=15)
    parser.add_argument("--staging-dir", type=str, default="data/crawl/staging")
    args = parser.parse_args()

    result = run_crawl(
        max_per_feed=args.max_per_feed,
        max_total=args.max_total,
        staging_dir=args.staging_dir,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
