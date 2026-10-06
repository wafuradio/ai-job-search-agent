"""
Deterministic fact extraction for normalized job postings.

The extractor identifies explicit facts in posting text that can improve
Gatekeeper screening without requiring AI judgment.

V1 is intentionally conservative:
- Extract only facts supported by clear posting language.
- Do not infer ambiguous facts.
- Preserve supporting posting text where useful.
"""

import re
from typing import Optional

from src.models import Job


REMOTE_PATTERNS = (
    r"\bfully remote\b",
    r"\bremote[- ]first\b",
    r"\bwork from home\b",
    r"\bmay be performed remotely\b",
    r"\bcan be performed remotely\b",
    r"\bremote position\b",
    r"\bremote role\b",
)

HYBRID_PATTERNS = (
    r"\bhybrid\b",
    r"\bin[- ]office\s+\d+\s+days?\b",
    r"\b\d+\s+days?\s+(?:per|a)\s+week\s+in(?:\s+the)?\s+office\b",
    r"\boffice attendance\b",
)

ONSITE_PATTERNS = (
    r"\bonsite\b",
    r"\bon-site\b",
    r"\boffice[- ]based\b",
    r"\bmust work from (?:our|the) office\b",
)

FULL_TIME_PATTERNS = (
    r"\bfull[- ]time\b",
    r"\bfull time employee\b",
)

PART_TIME_PATTERNS = (
    r"\bpart[- ]time\b",
)

CONTRACT_PATTERNS = (
    r"\bcontract position\b",
    r"\bcontract role\b",
    r"\bcontractor position\b",
    r"\btemporary position\b",
    r"\btemporary role\b",
)

INTERNSHIP_PATTERNS = (
    r"\binternship\b",
    r"\bintern position\b",
    r"\bintern role\b",
)


def _matches_any(
    text: str,
    patterns: tuple[str, ...],
) -> bool:
    """Return True when text matches any configured regex pattern."""

    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in patterns
    )


def _find_evidence_sentence(
    text: str,
    patterns: tuple[str, ...],
) -> Optional[str]:
    """
    Return the sentence or line containing the first matching pattern.

    The evidence is preserved from the posting rather than replaced
    with an inferred explanation.
    """

    if not text:
        return None

    segments = re.split(
        r"(?<=[.!?])\s+|\n+",
        text,
    )

    for segment in segments:
        cleaned_segment = " ".join(segment.split()).strip()

        if not cleaned_segment:
            continue

        if _matches_any(cleaned_segment, patterns):
            return cleaned_segment

    return None


def extract_work_arrangement(job: Job) -> Job:
    """
    Populate work-arrangement fields when the posting states them clearly.

    Existing structured values are preserved.
    """

    if job.remote_status:
        return job

    text = job.raw_description or ""

    if not text:
        return job

    hybrid_evidence = _find_evidence_sentence(
        text,
        HYBRID_PATTERNS,
    )

    onsite_evidence = _find_evidence_sentence(
        text,
        ONSITE_PATTERNS,
    )

    remote_evidence = _find_evidence_sentence(
        text,
        REMOTE_PATTERNS,
    )

    if hybrid_evidence:
        job.remote_status = "Hybrid"
        job.remote_policy_text = hybrid_evidence

    elif onsite_evidence:
        job.remote_status = "On-site"
        job.remote_policy_text = onsite_evidence

    elif remote_evidence:
        job.remote_status = "Fully Remote"
        job.remote_policy_text = remote_evidence

    return job


def extract_employment_type(job: Job) -> Job:
    """
    Populate employment type when the posting states it clearly.

    Existing structured values are preserved.
    """

    if job.employment_type:
        return job

    text = job.raw_description or ""

    if not text:
        return job

    if _matches_any(text, INTERNSHIP_PATTERNS):
        job.employment_type = "Internship"

    elif _matches_any(text, PART_TIME_PATTERNS):
        job.employment_type = "Part-time"

    elif _matches_any(text, CONTRACT_PATTERNS):
        job.employment_type = "Contract"

    elif _matches_any(text, FULL_TIME_PATTERNS):
        job.employment_type = "Full-time"

    return job


def enrich_job_facts(job: Job) -> Job:
    """
    Apply all deterministic V1 fact extraction to a normalized job.
    """

    extract_work_arrangement(job)
    extract_employment_type(job)

    return job