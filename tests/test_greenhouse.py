import pytest

from src.sources.greenhouse import (
    GreenhouseJob,
    build_greenhouse_url,
    parse_greenhouse_jobs,
)


def test_build_greenhouse_url():
    url = build_greenhouse_url("example-company")

    assert url == (
        "https://boards-api.greenhouse.io/v1/boards/"
        "example-company/jobs?content=true"
    )


def test_build_greenhouse_url_without_content():
    url = build_greenhouse_url(
        "example-company",
        content=False,
    )

    assert url.endswith("?content=false")


def test_empty_board_token_raises_error():
    with pytest.raises(ValueError):
        build_greenhouse_url("")


def test_parse_greenhouse_jobs():
    payload = {
        "jobs": [
            {
                "id": 12345,
                "title": "Principal Program Manager",
                "absolute_url": (
                    "https://example.com/jobs/12345"
                ),
                "location": {
                    "name": "Remote, United States"
                },
                "content": (
                    "Lead complex transformation programs."
                ),
            }
        ]
    }

    jobs = parse_greenhouse_jobs(
        payload=payload,
        board_token="example-company",
    )

    assert len(jobs) == 1

    job = jobs[0]

    assert isinstance(job, GreenhouseJob)
    assert job.source == "Greenhouse"
    assert job.source_job_id == "12345"
    assert job.company_board == "example-company"
    assert job.title == "Principal Program Manager"
    assert job.location == "Remote, United States"
    assert (
        job.description
        == "Lead complex transformation programs."
    )


def test_parse_multiple_jobs():
    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "AI Transformation Lead",
                "absolute_url": "https://example.com/jobs/1",
                "location": {"name": "Remote"},
                "content": "AI transformation role.",
            },
            {
                "id": 2,
                "title": "Director, Business Operations",
                "absolute_url": "https://example.com/jobs/2",
                "location": {"name": "New York, NY"},
                "content": "Business operations role.",
            },
        ]
    }

    jobs = parse_greenhouse_jobs(
        payload=payload,
        board_token="example-company",
    )

    assert len(jobs) == 2
    assert jobs[0].source_job_id == "1"
    assert jobs[1].source_job_id == "2"


def test_missing_location_is_allowed():
    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Strategic Projects Lead",
                "absolute_url": (
                    "https://example.com/jobs/123"
                ),
                "content": "Strategic transformation.",
            }
        ]
    }

    jobs = parse_greenhouse_jobs(
        payload=payload,
        board_token="example-company",
    )

    assert len(jobs) == 1
    assert jobs[0].location == ""


def test_missing_content_is_allowed():
    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "AI Operations Lead",
                "absolute_url": (
                    "https://example.com/jobs/123"
                ),
                "location": {"name": "Remote"},
            }
        ]
    }

    jobs = parse_greenhouse_jobs(
        payload=payload,
        board_token="example-company",
    )

    assert len(jobs) == 1
    assert jobs[0].description == ""


def test_incomplete_job_is_skipped():
    payload = {
        "jobs": [
            {
                "id": 123,
                "title": "Valid Job",
                "absolute_url": (
                    "https://example.com/jobs/123"
                ),
            },
            {
                "id": 456,
                "title": "Missing URL",
            },
        ]
    }

    jobs = parse_greenhouse_jobs(
        payload=payload,
        board_token="example-company",
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Valid Job"


def test_invalid_jobs_value_raises_error():
    payload = {
        "jobs": "this should be a list"
    }

    with pytest.raises(ValueError):
        parse_greenhouse_jobs(
            payload=payload,
            board_token="example-company",
        )


def test_empty_jobs_list():
    jobs = parse_greenhouse_jobs(
        payload={"jobs": []},
        board_token="example-company",
    )

    assert jobs == []
    