from __future__ import annotations

import re

# Must appear in title for a news article to qualify.
PRIMARY_MENTAL_HEALTH_TERMS: tuple[str, ...] = (
    "rối loạn tâm thần",
    "rối loạn lo âu",
    "tư vấn tâm lý",
    "tâm lý học",
    "sức khỏe tâm thần",
    "mental health",
    "mental illness",
    "tâm thần",
    "tâm lý",
    "trầm cảm",
    "lo âu",
    "depression",
    "anxiety",
    "bipolar",
    "schizophrenia",
    "psychiatr",
    "psycholog",
    "suicide",
    "self-harm",
    "tự tử",
    "tự hại",
    "mood disorder",
    "personality disorder",
    "eating disorder",
    "burnout",
    "ptsd",
    "ocd",
    "tự kỷ",
)

# Secondary — only count when combined with primary in body, not alone in title.
SECONDARY_MENTAL_HEALTH_TERMS: tuple[str, ...] = (
    "tâm trạng",
    "tinh thần",
    "stress",
    "căng thẳng",
    "mất ngủ",
    "trị liệu",
    "therapy",
    "counseling",
    "wellbeing",
    "well-being",
    "loneliness",
    "substance use",
    "buồn bã",
)

_PRIMARY_PATTERN = re.compile(
    "|".join(re.escape(t) for t in sorted(PRIMARY_MENTAL_HEALTH_TERMS, key=len, reverse=True)),
    re.IGNORECASE,
)
_SECONDARY_PATTERN = re.compile(
    "|".join(re.escape(t) for t in sorted(SECONDARY_MENTAL_HEALTH_TERMS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _find_matches(pattern: re.Pattern[str], text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in pattern.finditer(text)})


def passes_strict_mental_health_filter(
    title: str,
    body: str = "",
    *,
    content_type: str = "news_article",
) -> tuple[bool, float, list[str]]:
    """
    News articles must have at least one primary keyword in the title.
    Research articles may qualify via title OR abstract (body).
    Returns (passes, score, matched_keywords).
    """
    title_primary = _find_matches(_PRIMARY_PATTERN, title)
    if title_primary:
        body_primary = _find_matches(_PRIMARY_PATTERN, body)
        body_secondary = _find_matches(_SECONDARY_PATTERN, body)
        all_kw = sorted(set(title_primary + body_primary + body_secondary))
        score = min(1.0, 0.5 + len(all_kw) * 0.1)
        return True, score, all_kw

    if content_type in ("research_article", "health_guide"):
        body_primary = _find_matches(_PRIMARY_PATTERN, body)
        if body_primary:
            body_secondary = _find_matches(_SECONDARY_PATTERN, body)
            all_kw = sorted(set(body_primary + body_secondary))
            score = min(1.0, 0.45 + len(all_kw) * 0.1)
            return True, score, all_kw

    return False, 0.0, []


def score_mental_health_relevance(text: str) -> tuple[float, list[str]]:
    """Loose score for display; strict gate uses passes_strict_mental_health_filter."""
    primary = _find_matches(_PRIMARY_PATTERN, text)
    secondary = _find_matches(_SECONDARY_PATTERN, text)
    matches = sorted(set(primary + secondary))
    if not matches:
        return 0.0, []
    score = min(1.0, 0.4 + (len(matches) - 1) * 0.15)
    return score, matches
