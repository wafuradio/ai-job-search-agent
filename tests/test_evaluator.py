"""
Tests for the AI evaluator preparation layer.

These tests verify that candidate configuration, evidence, normalized job
data, and evaluator instructions are assembled correctly before any external
AI model is called.
"""

from src.evaluator import (
    build_evaluation_context,
    build_evaluation_instructions,
    build_evaluation_payload,
    load_candidate_evidence,
    load_career_profile,
)
from src.models import Compensation, Job


def make_job(**overrides):
    """Create a representative job for evaluator tests."""

    defaults = {
        "company": "Example AI Company",
        "title": "Director, AI Transformation",
        "job_url": "https://example.com/jobs/123",
        "source": "company_careers",
        "employment_type": "Full-time",
        "location_text": "New York, NY",
        "remote_status": "Hybrid",
        "remote_policy_text": "Three days per week in office",
        "travel_requirement": "Up to 10%",
        "compensation": Compensation(
            base_min=210000,
            base_max=240000,
            bonus="Eligible for annual bonus",
            equity="Equity eligible",
        ),
        "summary": (
            "Lead cross-functional AI transformation and operational "
            "improvement initiatives."
        ),
        "responsibilities": [
            "Design AI-enabled operating models",
            "Lead cross-functional transformation programs",
            "Identify opportunities for workflow automation",
        ],
        "requirements": [
            "10+ years of program or operations leadership",
            "Experience leading enterprise transformation",
            "Experience applying AI to business workflows",
        ],
    }

    defaults.update(overrides)
    return Job(**defaults)


def test_career_profile_loads():
    """The evaluator should load the career profile configuration."""

    profile = load_career_profile()

    assert isinstance(profile, dict)
    assert len(profile) > 0


def test_candidate_evidence_loads():
    """The evaluator should load structured candidate evidence."""

    evidence = load_candidate_evidence()

    assert isinstance(evidence, dict)
    assert "experience_evidence" in evidence
    assert len(evidence["experience_evidence"]) > 0


def test_candidate_evidence_contains_ai_boundary():
    """
    The evidence layer should explicitly prevent inflation of the
    candidate's AI experience.
    """

    evidence = load_candidate_evidence()

    boundary = evidence["candidate"]["important_boundary"]

    assert "AI" in boundary
    assert "technology" in boundary
    assert "operations" in boundary


def test_evaluation_context_contains_all_three_inputs():
    """
    AI evaluation should receive the career profile, candidate evidence,
    and normalized job posting.
    """

    job = make_job()

    context = build_evaluation_context(job)

    assert "career_profile" in context
    assert "candidate_evidence" in context
    assert "job" in context


def test_job_is_serialized_for_ai_context():
    """Normalized Job data should survive conversion into AI context."""

    job = make_job()

    context = build_evaluation_context(job)
    job_data = context["job"]

    assert job_data["company"] == "Example AI Company"
    assert job_data["title"] == "Director, AI Transformation"
    assert job_data["remote_status"] == "Hybrid"
    assert job_data["compensation"]["base_min"] == 210000
    assert job_data["compensation"]["base_max"] == 240000


def test_evaluator_instructions_include_human_centered_questions():
    """
    Instructions should preserve the human-centered decision framework
    rather than reducing evaluation to a numerical score.
    """

    instructions = build_evaluation_instructions()

    assert "CAN THE CANDIDATE DO THE JOB?" in instructions
    assert "IS THIS A GOOD OPPORTUNITY?" in instructions
    assert "WOULD THE CANDIDATE LIKELY ENJOY THE WORK?" in instructions
    assert "IS THE COMPENSATION POTENTIALLY RIGHT?" in instructions


def test_evaluator_does_not_allow_compensation_guessing():
    """Undisclosed compensation must never be invented."""

    instructions = build_evaluation_instructions()

    assert "Never invent or estimate undisclosed compensation." in instructions


def test_evaluator_protects_against_ai_title_seduction():
    """
    AI terminology in a title should not automatically make a role
    attractive.
    """

    instructions = build_evaluation_instructions()

    assert "Do not reward a role merely because AI appears in the title." in instructions


def test_remote_is_preference_not_absolute_rejection():
    """
    Hybrid work should remain reviewable rather than becoming an automatic
    evaluator rejection.
    """

    instructions = build_evaluation_instructions()

    assert (
        "Remote work is strongly preferred, but hybrid work is not automatically"
        in instructions
    )


def test_payload_contains_instructions_and_context():
    """The final pre-AI payload should contain both reasoning rules and data."""

    job = make_job()

    payload = build_evaluation_payload(job)

    assert "instructions" in payload
    assert "context" in payload
    assert payload["context"]["job"]["company"] == "Example AI Company"