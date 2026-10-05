"""
Tests for the deterministic Gatekeeper.

These tests protect the rules that determine whether a discovered job:
- continues normally,
- continues with a warning,
- needs more information,
- or is rejected before AI evaluation.
"""

from src.gatekeeper import (
    FLAG,
    NEEDS_INFORMATION,
    PASS,
    REJECT,
    evaluate_job,
)
from src.models import Job


def make_job(**overrides):
    """
    Create a basic senior remote job for testing.

    Individual tests can override only the fields relevant to the rule
    being tested.
    """

    defaults = {
        "company": "Example AI Company",
        "title": "Director, AI Transformation",
        "job_url": "https://example.com/job/123",
        "source": "Company Career Site",
        "employment_type": "Full-time",
        "location_text": "United States",
        "remote_status": "Fully Remote",
        "remote_policy_text": "This role may be performed remotely in the US.",
    }

    defaults.update(overrides)

    return Job(**defaults)


def test_fully_remote_job_passes():
    """A fully remote senior role should pass the Gatekeeper."""

    job = make_job()

    result = evaluate_job(job)

    assert result.status == PASS
    assert result.passed is True
    assert result.reasons == []
    assert result.flags == []


def test_remote_job_with_travel_passes():
    """Occasional travel should not be confused with office attendance."""

    job = make_job(
        travel_requirement="Occasional travel for team offsites and customer meetings."
    )

    result = evaluate_job(job)

    assert result.status == PASS
    assert result.passed is True


def test_hybrid_job_is_flagged_not_rejected():
    """
    Hybrid work conflicts with the remote preference but should remain
    available for human review.
    """

    job = make_job(
        location_text="New York, NY",
        remote_status="Hybrid",
        remote_policy_text="Employees are expected in office 3 days per week.",
    )

    result = evaluate_job(job)

    assert result.status == FLAG
    assert result.passed is True
    assert len(result.flags) >= 1


def test_onsite_job_is_flagged_not_rejected():
    """
    V1 keeps even an attractive onsite opportunity visible rather than
    allowing the software to eliminate it automatically.
    """

    job = make_job(
        location_text="New York, NY",
        remote_status="On-site",
        remote_policy_text="This position is office-based in New York.",
    )

    result = evaluate_job(job)

    assert result.status == FLAG
    assert result.passed is True
    assert len(result.flags) >= 1


def test_unknown_work_arrangement_needs_information():
    """A missing work policy should not be guessed."""

    job = make_job(
        remote_status=None,
        remote_policy_text=None,
    )

    result = evaluate_job(job)

    assert result.status == NEEDS_INFORMATION
    assert result.passed is False
    assert "Work arrangement is unknown." in result.reasons


def test_ambiguous_work_arrangement_needs_information():
    """Unclear work-model language should be investigated."""

    job = make_job(
        remote_status="Flexible",
        remote_policy_text="Work arrangements depend on team needs.",
    )

    result = evaluate_job(job)

    assert result.status == NEEDS_INFORMATION
    assert result.passed is False


def test_junior_role_is_rejected():
    """A clearly junior role should not proceed to expensive AI analysis."""

    job = make_job(
        title="Junior Program Manager",
    )

    result = evaluate_job(job)

    assert result.status == REJECT
    assert result.passed is False
    assert any("seniority" in reason.lower() for reason in result.reasons)


def test_event_execution_role_is_rejected():
    """
    A role centered on event execution is outside the intended career
    direction even though the candidate has extensive event experience.
    """

    job = make_job(
        title="Senior Events Manager",
    )

    result = evaluate_job(job)

    assert result.status == REJECT
    assert result.passed is False
    assert any("event execution" in reason.lower() for reason in result.reasons)


def test_contract_role_is_flagged_not_rejected():
    """
    Contract work is not the primary target, but V1 keeps potentially
    exceptional opportunities visible.
    """

    job = make_job(
        employment_type="Contract",
    )

    result = evaluate_job(job)

    assert result.status == FLAG
    assert result.passed is True
    assert any("non-permanent" in flag.lower() for flag in result.flags)


def test_relationship_or_compensation_cannot_override_rejection():
    """
    Gatekeeper decisions depend on job facts, not how attractive the
    company, compensation, or referral path might eventually be.
    """

    job = make_job(
        title="Event Coordinator",
    )

    result = evaluate_job(job)

    assert result.status == REJECT
    assert result.passed is False