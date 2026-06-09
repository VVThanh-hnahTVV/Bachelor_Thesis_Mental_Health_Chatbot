"""Curated web crawl for mental-health news (admin staging pipeline)."""

from app.crawl.pipeline import run_crawl

__all__ = ["run_crawl"]
