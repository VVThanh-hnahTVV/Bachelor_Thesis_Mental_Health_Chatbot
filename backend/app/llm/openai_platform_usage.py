"""Fetch OpenAI organization usage/costs (platform dashboard data)."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

OPENAI_USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"
OPENAI_COSTS_URL = "https://api.openai.com/v1/organization/costs"


async def _fetch_paginated(
    url: str,
    *,
    admin_key: str,
    start_time: int,
    bucket_width: str = "1d",
) -> list[dict[str, Any]]:
    headers = {"Authorization": f"Bearer {admin_key}"}
    all_rows: list[dict[str, Any]] = []
    page: str | None = None

    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            params: dict[str, Any] = {
                "start_time": start_time,
                "bucket_width": bucket_width,
                "limit": 31,
            }
            if page:
                params["page"] = page

            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                raise RuntimeError(
                    f"OpenAI API {response.status_code}: {response.text[:200]}"
                )

            payload = response.json()
            all_rows.extend(payload.get("data") or [])
            page = payload.get("next_page")
            if not page:
                break

    return all_rows


def _sum_usage_buckets(buckets: list[dict[str, Any]]) -> dict[str, Any]:
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    requests = 0
    by_day: list[dict[str, Any]] = []

    for bucket in buckets:
        start = bucket.get("start_time") or bucket.get("start_time_iso")
        day_input = 0
        day_output = 0
        day_requests = 0

        for result in bucket.get("results") or []:
            day_input += int(result.get("input_tokens") or 0)
            day_output += int(result.get("output_tokens") or 0)
            day_requests += int(result.get("num_model_requests") or result.get("requests") or 0)

        day_tokens = day_input + day_output
        total_tokens += day_tokens
        input_tokens += day_input
        output_tokens += day_output
        requests += day_requests

        if start:
            date_label = (
                str(start)[:10]
                if isinstance(start, str)
                else time.strftime("%Y-%m-%d", time.gmtime(int(start)))
            )
            by_day.append(
                {
                    "date": date_label,
                    "total_tokens": day_tokens,
                    "prompt_tokens": day_input,
                    "completion_tokens": day_output,
                    "calls": day_requests,
                    "cost_usd": 0.0,
                }
            )

    return {
        "total_tokens": total_tokens,
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "calls": requests,
        "by_day": by_day,
    }


def _sum_cost_buckets(buckets: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    total_cents = 0.0
    by_day: dict[str, float] = {}

    for bucket in buckets:
        start = bucket.get("start_time")
        day_cost = 0.0
        for result in bucket.get("results") or []:
            amount = result.get("amount") or {}
            value = amount.get("value")
            if value is not None:
                day_cost += float(value)
            else:
                day_cost += float(result.get("cost_usd") or result.get("cost") or 0) * 100

        total_cents += day_cost
        if start:
            date_label = time.strftime("%Y-%m-%d", time.gmtime(int(start)))
            by_day[date_label] = by_day.get(date_label, 0.0) + day_cost / 100.0

    return total_cents / 100.0, by_day


def _merge_costs_into_days(
    by_day: list[dict[str, Any]], cost_by_day: dict[str, float]
) -> list[dict[str, Any]]:
    for row in by_day:
        row["cost_usd"] = round(cost_by_day.get(row["date"], 0.0), 6)
    return by_day


async def fetch_openai_platform_usage(*, days: int = 7) -> dict[str, Any]:
    admin_key = get_settings().openai_admin_api_key
    if not admin_key:
        return {
            "available": False,
            "message": (
                "Chưa cấu hình OPENAI_ADMIN_API_KEY (sk-admin-…). "
                "Project key sk-proj-… không đọc được billing dashboard."
            ),
        }

    start_time = int(time.time()) - (days * 24 * 60 * 60)
    try:
        usage_buckets = await _fetch_paginated(
            OPENAI_USAGE_URL,
            admin_key=admin_key,
            start_time=start_time,
        )
        cost_buckets = await _fetch_paginated(
            OPENAI_COSTS_URL,
            admin_key=admin_key,
            start_time=start_time,
        )
        usage = _sum_usage_buckets(usage_buckets)
        cost_usd, cost_by_day = _sum_cost_buckets(cost_buckets)
        by_day = _merge_costs_into_days(usage["by_day"], cost_by_day)

        return {
            "available": True,
            "days": days,
            "period": {
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
                "cost_usd": round(cost_usd, 4),
                "calls": usage["calls"],
            },
            "by_day": by_day,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("OpenAI platform usage fetch failed: %s", exc)
        return {
            "available": False,
            "message": str(exc),
        }


async def get_admin_usage_stats(*, days: int = 7) -> dict[str, Any]:
    platform = await fetch_openai_platform_usage(days=days)
    empty_totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "calls": 0,
    }

    if not platform.get("available"):
        return {
            "days": days,
            "updated_at": datetime.now(UTC).isoformat(),
            "available": False,
            "message": platform.get("message"),
            "today": empty_totals,
            "period": empty_totals,
            "by_day": [],
            "pricing_note": "Dữ liệu từ OpenAI Organization API — cần OPENAI_ADMIN_API_KEY.",
        }

    period = platform["period"]
    by_day = platform.get("by_day") or []
    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    today = dict(empty_totals)
    for row in by_day:
        if row.get("date") == today_str:
            today = {
                "prompt_tokens": row.get("prompt_tokens", 0),
                "completion_tokens": row.get("completion_tokens", 0),
                "total_tokens": row.get("total_tokens", 0),
                "cost_usd": row.get("cost_usd", 0.0),
                "calls": row.get("calls", 0),
            }
            break

    return {
        "days": days,
        "updated_at": datetime.now(UTC).isoformat(),
        "available": True,
        "today": today,
        "period": period,
        "by_day": by_day,
        "pricing_note": "Dữ liệu billing thật từ OpenAI Organization API.",
    }
