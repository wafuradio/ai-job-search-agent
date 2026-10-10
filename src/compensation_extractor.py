"""
Conservative compensation extraction from job postings.

Preserves published annual compensation ranges while distinguishing
confirmed base salary, OTE, total compensation, and uncertain ranges.
"""

import html
import re

from src.models import Job


RANGE_PATTERN = re.compile(
    r"\$\s*([\d,]+)\s*[-–—]\s*\$\s*([\d,]+)",
    re.IGNORECASE,
)

COMPENSATION_LABELS = (
    "annual salary",
    "base salary",
    "base pay",
    "salary range",
    "pay range",
    "on target earnings",
    "on-target earnings",
    "ote:",
    "total compensation",
)

SALES_TITLE_PATTERN = re.compile(
    r"\b(?:sales|account executive|partnerships?|"
    r"business development|gtm partnership)\b",
    re.IGNORECASE,
)

GENERIC_OTE_DISCLAIMER = re.compile(
    r"for sales roles.{0,150}(?:on.target earnings|ote)",
    re.IGNORECASE | re.DOTALL,
)


def _classify_compensation(text, label, title):
    """
    Classify the published range without inventing its components.
    """

    label_lower = label.lower()

    if re.search(r"\bote\b|on.target earnings", label_lower):
        return "OTE"

    if "total compensation" in label_lower:
        return "Total Compensation"

    if "base salary" in label_lower or "base pay" in label_lower:
        return "Base Salary"

    # Anthropic-style conditional OTE disclaimer.
    if GENERIC_OTE_DISCLAIMER.search(text):
        if SALES_TITLE_PATTERN.search(title or ""):
            return "Uncertain"

    # "Annual Salary" is not always proof of base salary.
    if "annual salary" in label_lower:
        return "Uncertain"

    return "Uncertain"


def extract_compensation(job: Job) -> Job:
    """
    Extract a published annual compensation range.

    Only populate base_min/base_max when the posting explicitly
    identifies the range as base salary.
    """

    comp = job.compensation

    # Preserve previously extracted or structured compensation.
    if (
        comp.published_min is not None
        or comp.published_max is not None
        or comp.base_min is not None
        or comp.base_max is not None
    ):
        return job

    text = html.unescape(job.raw_description or "")

    if not text:
        return job

    lines = [line.strip() for line in text.splitlines()]

    for index, line in enumerate(lines):
        lower_line = line.lower()

        if not any(label in lower_line for label in COMPENSATION_LABELS):
            continue

        # Limit extraction to the labeled line and the next line.
        candidate = line

        if index + 1 < len(lines):
            candidate += " " + lines[index + 1]

        match = RANGE_PATTERN.search(candidate)

        if not match:
            continue

        minimum = int(match.group(1).replace(",", ""))
        maximum = int(match.group(2).replace(",", ""))

        # Ignore obvious placeholders and invalid ranges.
        if minimum < 30000 or maximum < minimum:
            continue

        compensation_type = _classify_compensation(
            text=text,
            label=line,
            title=job.title,
        )

        comp.published_min = minimum
        comp.published_max = maximum
        comp.compensation_type = compensation_type
        comp.compensation_text = candidate.strip()

        if compensation_type == "Base Salary":
            comp.base_min = minimum
            comp.base_max = maximum

        return job

    return job