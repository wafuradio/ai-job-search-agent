import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen


GREENHOUSE_API_BASE = "https://boards-api.greenhouse.io/v1/boards"


@dataclass(frozen=True)
class GreenhouseJob:
    source: str
    source_job_id: str
    company_board: str
    title: str
    location: str
    job_url: str
    description: str
    first_published: Optional[str] = None
    updated_at: Optional[str] = None


def build_greenhouse_url(
    board_token: str,
    content: bool = True,
) -> str:
    """
    Build the public Greenhouse Job Board API URL for a company.

    content=True asks Greenhouse to include the full job description.
    """

    if not board_token or not board_token.strip():
        raise ValueError("Greenhouse board token cannot be empty.")

    board_token = board_token.strip()

    query = urlencode(
        {
            "content": str(content).lower(),
        }
    )

    return (
        f"{GREENHOUSE_API_BASE}/{board_token}/jobs"
        f"?{query}"
    )


def parse_greenhouse_jobs(
    payload: Dict[str, Any],
    board_token: str,
) -> List[GreenhouseJob]:
    """
    Convert a Greenhouse API response into source-specific job records.

    This function performs no candidate-fit evaluation.
    """

    raw_jobs = payload.get("jobs", [])

    if not isinstance(raw_jobs, list):
        raise ValueError(
            "Greenhouse response must contain a jobs list."
        )

    jobs: List[GreenhouseJob] = []

    for raw_job in raw_jobs:
        job_id = raw_job.get("id")
        title = raw_job.get("title")
        absolute_url = raw_job.get("absolute_url")

        if job_id is None or not title or not absolute_url:
            continue

        location_data = raw_job.get("location") or {}
        location = location_data.get("name", "")

        description = raw_job.get("content") or ""

        jobs.append(
            GreenhouseJob(
                source="Greenhouse",
                source_job_id=str(job_id),
                company_board=board_token,
                title=title.strip(),
                location=location.strip(),
                job_url=absolute_url.strip(),
                description=description,
                first_published=raw_job.get("first_published"),
                updated_at=raw_job.get("updated_at"),
            )
        )

    return jobs


def fetch_greenhouse_jobs(
    board_token: str,
    timeout: int = 20,
) -> List[GreenhouseJob]:
    """
    Retrieve all public jobs from a Greenhouse company board.
    """

    url = build_greenhouse_url(
        board_token=board_token,
        content=True,
    )

    request = Request(
        url,
        headers={
            "User-Agent": "ai-job-search-agent/1.0",
            "Accept": "application/json",
        },
    )

    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(
            response.read().decode("utf-8")
        )

    return parse_greenhouse_jobs(
        payload=payload,
        board_token=board_token,
    )

def fetch_greenhouse_job_dates(board_token: str, job_id: str, timeout: int = 20) -> dict:
    """Optional public GET for first publication; list updated_at is not posting age."""
    if not str(job_id).strip():
        raise ValueError('Greenhouse job ID cannot be empty')
    base = build_greenhouse_url(board_token).split('?', 1)[0]
    request = Request(base + '/' + quote(str(job_id), safe=''), headers={
        'User-Agent': 'ai-job-search-agent/1.0', 'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('Greenhouse job detail must be an object')
    return {'first_published': payload.get('first_published'), 'updated_at': payload.get('updated_at')}
