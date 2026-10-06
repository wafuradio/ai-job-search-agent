"""
Core pipeline orchestration for the AI Job Search Agent.

This module connects discovery, Scout filtering, normalization,
fact extraction, and deterministic Gatekeeper screening without
performing AI evaluation.
"""

from dataclasses import dataclass
from typing import List

from src.fact_extractor import enrich_job_facts
from src.gatekeeper import GatekeeperResult, REJECT, evaluate_job
from src.models import Job
from src.normalizer import normalize_greenhouse_job
from src.scout import (
    is_us_job,
    load_scout_config,
    score_job_relevance,
)
from src.sources.greenhouse import GreenhouseJob


@dataclass(frozen=True)
class ScreenedJob:
    job: Job
    scout_score: int
    gatekeeper: GatekeeperResult


def screen_greenhouse_jobs(
    jobs: List[GreenhouseJob],
    company: str,
    country: str = "United States",
) -> List[ScreenedJob]:
    """
    Run Greenhouse jobs through the deterministic V1 screening pipeline.

    Flow:
        geography
        -> Scout relevance
        -> normalization
        -> fact extraction
        -> Gatekeeper

    Only Gatekeeper REJECT results are removed.
    PASS, FLAG, and NEEDS_INFORMATION continue.
    """

    config = load_scout_config()
    screened_jobs: List[ScreenedJob] = []

    for source_job in jobs:
        if not is_us_job(source_job.location):
            continue

        relevance = score_job_relevance(
            title=source_job.title,
            description=source_job.description,
            config=config,
        )

        if not relevance.relevant:
            continue

        normalized_job = normalize_greenhouse_job(
            job=source_job,
            company=company,
            country=country,
        )

        enrich_job_facts(normalized_job)

        gatekeeper_result = evaluate_job(normalized_job)

        if gatekeeper_result.status == REJECT:
            continue

        screened_jobs.append(
            ScreenedJob(
                job=normalized_job,
                scout_score=relevance.score,
                gatekeeper=gatekeeper_result,
            )
        )

    return screened_jobs