from src.models import Job
from src.normalizer import (
    clean_html,
    normalize_greenhouse_job,
    normalize_greenhouse_jobs,
)
from src.sources.greenhouse import GreenhouseJob


def make_greenhouse_job(
    description: str = "<p>Lead AI transformation.</p>",
) -> GreenhouseJob:
    return GreenhouseJob(
        source="Greenhouse",
        source_job_id="12345",
        company_board="anthropic",
        title="Strategy & Operations Lead",
        location="New York City, NY",
        job_url="https://example.com/job/12345",
        description=description,
    )


def test_clean_html_removes_tags():
    result = clean_html(
        "<p>Lead transformation.</p>"
        "<p>Build scalable processes.</p>"
    )

    assert "<p>" not in result
    assert "Lead transformation." in result
    assert "Build scalable processes." in result


def test_clean_html_decodes_entities():
    result = clean_html(
        "<p>Strategy &amp; Operations</p>"
    )

    assert "Strategy & Operations" in result


def test_clean_html_handles_empty_string():
    assert clean_html("") == ""


def test_normalize_greenhouse_job_returns_job():
    source_job = make_greenhouse_job()

    result = normalize_greenhouse_job(
        job=source_job,
        company="Anthropic",
        country="United States",
    )

    assert isinstance(result, Job)


def test_normalize_greenhouse_job_maps_identity():
    source_job = make_greenhouse_job()

    result = normalize_greenhouse_job(
        job=source_job,
        company="Anthropic",
        country="United States",
    )

    assert result.company == "Anthropic"
    assert result.title == "Strategy & Operations Lead"
    assert result.job_url == "https://example.com/job/12345"


def test_normalize_greenhouse_job_maps_source_metadata():
    source_job = make_greenhouse_job()

    result = normalize_greenhouse_job(
        job=source_job,
        company="Anthropic",
        country="United States",
    )

    assert result.source == "Greenhouse"
    assert result.external_job_id == "12345"


def test_normalize_greenhouse_job_maps_location():
    source_job = make_greenhouse_job()

    result = normalize_greenhouse_job(
        job=source_job,
        company="Anthropic",
        country="United States",
    )

    assert result.location_text == "New York City, NY"
    assert result.country == "United States"


def test_normalizer_cleans_description_html():
    source_job = make_greenhouse_job(
        "<p>Lead AI transformation.</p>"
        "<ul><li>Build governance</li></ul>"
    )

    result = normalize_greenhouse_job(
        job=source_job,
        company="Anthropic",
    )

    assert "<p>" not in result.raw_description
    assert "<li>" not in result.raw_description
    assert "Lead AI transformation." in result.raw_description
    assert "Build governance" in result.raw_description


def test_normalizer_does_not_invent_unknown_fields():
    source_job = make_greenhouse_job()

    result = normalize_greenhouse_job(
        job=source_job,
        company="Anthropic",
    )

    assert result.employment_type is None
    assert result.remote_status is None
    assert result.seniority is None
    assert result.compensation.base_min is None
    assert result.compensation.base_max is None


def test_normalizer_requires_company_name():
    source_job = make_greenhouse_job()

    try:
        normalize_greenhouse_job(
            job=source_job,
            company="",
        )
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_normalize_multiple_greenhouse_jobs():
    jobs = [
        make_greenhouse_job(),
        GreenhouseJob(
            source="Greenhouse",
            source_job_id="67890",
            company_board="anthropic",
            title="AI Operations Lead",
            location="San Francisco, CA",
            job_url="https://example.com/job/67890",
            description="<p>Build AI-enabled workflows.</p>",
        ),
    ]

    results = normalize_greenhouse_jobs(
        jobs=jobs,
        company="Anthropic",
        country="United States",
    )

    assert len(results) == 2
    assert all(isinstance(job, Job) for job in results)
    assert results[0].external_job_id == "12345"
    assert results[1].external_job_id == "67890"