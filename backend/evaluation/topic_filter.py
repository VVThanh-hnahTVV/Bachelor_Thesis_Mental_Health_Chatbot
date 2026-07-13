"""Shared topic heuristics for the evaluation corpus.

The document store holds legacy HIV/general-medical chunks alongside the intended
mental-health corpus. These helpers classify a chunk's full text so the dataset
builder can sample only mental-health chunks and the filter can drop off-topic
questions, using one definition in both places.
"""

import re

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
    """Return (keep, mental_health_hits, medical_hits).

    A chunk is rejected only when medical/HIV markers clearly dominate, so a
    mental-health chunk that merely mentions a medical term is still kept.
    """
    med = len(MEDICAL.findall(text))
    mh = len(MENTAL_HEALTH.findall(text))
    rejected = med >= 3 and med >= mh
    return (not rejected), mh, med
