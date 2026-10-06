"""
Tests for deterministic job fact extraction.

These tests ensure that explicit posting facts can enrich normalized
jobs without inventing information or overwriting source data.
"""

from src.fact_extractor import (
    enrich_job_facts,
    extract_employment_type,
    extract_work_arrangement,
)
from src.models import Job


def make_job(**overrides):
    """Create a minimal normalized job for fact-extraction tests."""

    defaults = {
        "company": "Example AI Company",
        "title": "Director, AI Transformation",
        "job_url": "https://example.com/job/123",
        "source": "Greenhouse",
    }

    defaults.update(overrides)

    return Job(**defaults)


def test_extracts_fully_remote_work_arrangement():
    job = make_job(
        raw_description=(
            "This is a fully remote role available throughout "
            "the United States."
        )
    )

    extract_work_arrangement(job)

    assert job.remote_status == "Fully Remote"
    assert job.remote_policy_text is not None


def test_extracts_hybrid_before_remote_language():
    job = make_job(
        raw_description=(
            "This is a hybrid role with remote flexibility. "
            "Employees work in office 3 days per week."
        )
    )

    extract_work_arrangement(job)

    assert job.remote_status == "Hybrid"


def test_extracts_onsite_work_arrangement():
    job = make_job(
        raw_description=(
            "This is an office-based position in New York."
        )
    )

    extract_work_arrangement(job)

    assert job.remote_status == "On-site"


def test_does_not_invent_work_arrangement():
    job = make_job(
        raw_description=(
            "You will lead strategic transformation programs "
            "across the organization."
        )
    )

    extract_work_arrangement(job)

    assert job.remote_status is None
    assert job.remote_policy_text is None


def test_preserves_existing_work_arrangement():
    job = make_job(
        remote_status="Hybrid",
        remote_policy_text="Three days per week in office.",
        raw_description="This position supports remote collaboration.",
    )

    extract_work_arrangement(job)

    assert job.remote_status == "Hybrid"
    assert job.remote_policy_text == "Three days per week in office."


def test_extracts_full_time_employment():
    job = make_job(
        raw_description="This is a full-time position."
    )

    extract_employment_type(job)

    assert job.employment_type == "Full-time"


def test_extracts_contract_employment():
    job = make_job(
        raw_description="This is a contract role for twelve months."
    )

    extract_employment_type(job)

    assert job.employment_type == "Contract"


def test_extracts_part_time_employment():
    job = make_job(
        raw_description="This is a part-time position."
    )

    extract_employment_type(job)

    assert job.employment_type == "Part-time"


def test_extracts_internship():
    job = make_job(
        raw_description="This internship begins in June."
    )

    extract_employment_type(job)

    assert job.employment_type == "Internship"


def test_does_not_invent_employment_type():
    job = make_job(
        raw_description=(
            "Lead cross-functional AI transformation initiatives."
        )
    )

    extract_employment_type(job)

    assert job.employment_type is None


def test_preserves_existing_employment_type():
    job = make_job(
        employment_type="Full-time",
        raw_description="Contract partners may work with this team.",
    )

    extract_employment_type(job)

    assert job.employment_type == "Full-time"


def test_enrich_job_facts_applies_both_extractors():
    job = make_job(
        raw_description=(
            "This is a full-time, fully remote role in the "
            "United States."
        )
    )

    result = enrich_job_facts(job)

    assert result is job
    assert job.employment_type == "Full-time"
    assert job.remote_status == "Fully Remote"


def test_remote_policy_preserves_posting_evidence():
    evidence = (
        "Employees are expected in office 3 days per week."
    )

    job = make_job(
        raw_description=(
            "We support flexible collaboration. "
            f"{evidence} "
            "Teams also work together remotely."
        )
    )

    extract_work_arrangement(job)

    assert job.remote_status == "Hybrid"
    assert job.remote_policy_text == evidence


def test_remote_policy_preserves_remote_evidence():
    evidence = (
        "This role may be performed remotely in the United States."
    )

    job = make_job(
        raw_description=evidence
    )

    extract_work_arrangement(job)

    assert job.remote_status == "Fully Remote"
    assert job.remote_policy_text == evidence


def test_evidence_does_not_capture_unrelated_text():
    job = make_job(
        raw_description=(
            "Lead the company's transformation strategy. "
            "This is an office-based position in New York. "
            "You will partner closely with executives."
        )
    )

    extract_work_arrangement(job)

    assert job.remote_status == "On-site"
    assert job.remote_policy_text == (
        "This is an office-based position in New York."
    )
