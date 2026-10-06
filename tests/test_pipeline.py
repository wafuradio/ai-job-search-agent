from src.pipeline import ScreenedJob, screen_greenhouse_jobs
from src.sources.greenhouse import GreenhouseJob


def make_job(
    title: str,
    location: str = "New York City, NY",
    description: str = (
        "Lead AI transformation, governance, "
        "and cross-functional leadership."
    ),
) -> GreenhouseJob:
    return GreenhouseJob(
        source="Greenhouse",
        source_job_id="12345",
        company_board="test-company",
        title=title,
        location=location,
        job_url="https://example.com/job/12345",
        description=description,
    )


def test_pipeline_returns_screened_job():
    jobs = [
        make_job("AI Transformation Lead"),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Test Company",
    )

    assert len(results) == 1
    assert isinstance(results[0], ScreenedJob)


def test_pipeline_filters_non_us_job():
    jobs = [
        make_job(
            title="AI Transformation Lead",
            location="London, UK",
        ),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Test Company",
    )

    assert results == []


def test_pipeline_filters_irrelevant_job():
    jobs = [
        make_job(
            title="Accounts Payable Clerk",
            description=(
                "Process invoices and reconcile vendor payments."
            ),
        ),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Test Company",
    )

    assert results == []


def test_pipeline_filters_excluded_profession():
    jobs = [
        make_job(
            title="Commercial Counsel, GTM",
            description=(
                "Lead strategic initiatives, governance, "
                "and cross-functional leadership."
            ),
        ),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Test Company",
    )

    assert results == []


def test_pipeline_normalizes_job():
    jobs = [
        make_job("AI Transformation Lead"),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Anthropic",
    )

    job = results[0].job

    assert job.company == "Anthropic"
    assert job.source == "Greenhouse"
    assert job.external_job_id == "12345"
    assert job.country == "United States"


def test_pipeline_preserves_scout_score():
    jobs = [
        make_job("AI Transformation Lead"),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Test Company",
    )

    assert results[0].scout_score >= 3


def test_needs_information_continues_pipeline():
    jobs = [
        make_job("AI Transformation Lead"),
    ]

    results = screen_greenhouse_jobs(
        jobs=jobs,
        company="Test Company",
    )

    assert len(results) == 1
    assert results[0].gatekeeper.status == "Needs Information"
    assert (
        "Work arrangement is unknown."
        in results[0].gatekeeper.reasons
    )