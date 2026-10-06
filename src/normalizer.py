"""
Normalize source-specific job records into the canonical Job model.

Source adapters know how to retrieve jobs from external systems.
Normalizers convert those source-specific records into the common Job
structure used by the rest of the AI Job Search Agent.
"""

import html
import re
from typing import Optional

from src.models import Job
from src.sources.greenhouse import GreenhouseJob


def clean_html(raw_html: str) -> str:
    """
    Convert basic HTML job-description content into readable plain text.

    V1 intentionally avoids external HTML parsing dependencies.
    """

    if not raw_html:
        return ""

    text = html.unescape(raw_html)

    # Preserve useful separation before removing tags.
    text = re.sub(
        r"<\s*br\s*/?\s*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"</\s*(p|div|li|ul|ol|h[1-6])\s*>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )

    # Remove remaining HTML tags.
    text = re.sub(r"<[^>]+>", "", text)

    # Clean whitespace without destroying paragraph separation.
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.splitlines()
    ]

    cleaned_lines = []
    previous_blank = False

    for line in lines:
        if line:
            cleaned_lines.append(line)
            previous_blank = False
        elif not previous_blank:
            cleaned_lines.append("")
            previous_blank = True

    return "\n".join(cleaned_lines).strip()


def normalize_greenhouse_job(
    job: GreenhouseJob,
    company: str,
    country: Optional[str] = None,
) -> Job:
    """
    Convert a GreenhouseJob into the canonical Job model.

    Only facts supplied by the source or caller are populated.
    Unknown values remain None or use the Job model defaults.
    """

    if not company or not company.strip():
        raise ValueError(
            "Company name is required when normalizing a Greenhouse job."
        )

    description = clean_html(job.description)

    return Job(
        company=company.strip(),
        title=job.title,
        job_url=job.job_url,
        source=job.source,
        external_job_id=job.source_job_id,
        location_text=job.location or None,
        country=country,
        raw_description=description or None,
    )


def normalize_greenhouse_jobs(
    jobs: list[GreenhouseJob],
    company: str,
    country: Optional[str] = None,
) -> list[Job]:
    """
    Normalize multiple Greenhouse jobs into canonical Job records.
    """

    return [
        normalize_greenhouse_job(
            job=job,
            company=company,
            country=country,
        )
        for job in jobs
    ]