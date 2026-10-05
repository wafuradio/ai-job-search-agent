"""
Tests for the AI evaluator.

These tests verify candidate configuration, evidence, normalized job data,
evaluator instructions, and the structured-output contract used by the
AI evaluation layer.

No test in this file makes a live API call.
"""

import pytest
from pydantic import ValidationError

from src.evaluator import (
    AIJobEvaluation,
    OpportunityAssessmentOutput,
    RequirementEvidenceOutput,
    ScoreBreakdownOutput,
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


def make_valid_ai_evaluation():
    """Return a valid structured AI evaluation for schema tests."""

    return {
        "role_mission": (
            "Lead enterprise AI transformation and redesign operational "
            "workflows across business teams."
        ),
        "opportunity": {
            "opportunity_quality": "Strong",
            "ability_to_do_job": "Strong",
            "likely_enjoyment": "High",
            "compensation_outlook": "Possible",
            "opportunity_reason": (
                "The role offers meaningful transformation ownership."
            ),
            "ability_reason": (
                "The candidate has strong direct and transferable evidence."
            ),
            "enjoyment_reason": (
                "The work centers on systems, automation, and transformation."
            ),
            "compensation_reason": (
                "Base salary is strong and bonus and equity are disclosed."
            ),
        },
        "requirement_evidence": [
            {
                "requirement": (
                    "Experience leading enterprise transformation"
                ),
                "evidence_type": "Direct Evidence",
                "evidence": (
                    "Led operational and systems transformation across "
                    "MongoDB and Publishers Clearing House."
                ),
                "explanation": (
                    "The candidate has repeatedly redesigned workflows, "
                    "systems, governance, and operating models."
                ),
            },
            {
                "requirement": (
                    "Experience applying AI to business workflows"
                ),
                "evidence_type": "Transferable Evidence",
                "evidence": (
                    "Built AI-assisted automations and grounded AI tools."
                ),
                "explanation": (
                    "The candidate has practical AI workflow experience "
                    "without claiming deep ML engineering expertise."
                ),
            },
        ],
        "strengths": [
            "Operational transformation",
            "Cross-functional leadership",
            "Systems and workflow design",
        ],
        "gaps": [
            "AI transformation experience is newer than the broader "
            "technology and operations background."
        ],
        "questions_to_investigate": [
            "What is the expected total compensation including equity?",
        ],
        "score_breakdown": {
            "career_direction_alignment": 23,
            "experience_evidence": 22,
            "scope_and_seniority": 14,
            "ai_transformation_relevance": 13,
            "compensation": 8,
            "company_attractiveness": 4,
            "practical_fit": 3,
        },
        "state": "Strong Match",
        "confidence": "High",
        "recommendation_reason": (
            "The role strongly aligns with the candidate's direction and "
            "is supported by substantial direct and transferable evidence."
        ),
    }


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

    assert (
        "Do not reward a role merely because AI appears in the title."
        in instructions
    )


def test_remote_is_preference_not_absolute_rejection():
    """
    Hybrid work should remain reviewable rather than becoming an automatic
    evaluator rejection.
    """

    instructions = build_evaluation_instructions()

    assert (
        "Remote work is strongly preferred, but hybrid work is not "
        "automatically"
        in instructions
    )


def test_payload_contains_instructions_and_context():
    """The pre-AI payload should contain reasoning rules and data."""

    job = make_job()

    payload = build_evaluation_payload(job)

    assert "instructions" in payload
    assert "context" in payload
    assert payload["context"]["job"]["company"] == "Example AI Company"


def test_requirement_evidence_accepts_valid_classification():
    """The schema should accept an approved evidence classification."""

    evidence = RequirementEvidenceOutput(
        requirement="Experience leading enterprise transformation",
        evidence_type="Transferable Evidence",
        evidence="Led complex operational transformation programs.",
        explanation="Adjacent experience provides a credible bridge.",
    )

    assert evidence.evidence_type == "Transferable Evidence"


def test_requirement_evidence_rejects_invalid_classification():
    """The schema should reject classifications outside our contract."""

    with pytest.raises(ValidationError):
        RequirementEvidenceOutput(
            requirement="Experience with AI workflows",
            evidence_type="Sort Of",
            evidence="Some relevant experience.",
        )


def test_opportunity_assessment_rejects_invalid_quality():
    """
    The model should not be able to invent a new opportunity category.
    """

    with pytest.raises(ValidationError):
        OpportunityAssessmentOutput(
            opportunity_quality="Amazing",
            ability_to_do_job="Strong",
            likely_enjoyment="High",
            compensation_outlook="Possible",
            opportunity_reason="Strong role.",
            ability_reason="Strong evidence.",
            enjoyment_reason="Interesting work.",
            compensation_reason="Potentially competitive.",
        )


def test_score_breakdown_calculates_total():
    """
    Our code should calculate the total score rather than trusting
    AI arithmetic.
    """

    score = ScoreBreakdownOutput(
        career_direction_alignment=23,
        experience_evidence=22,
        scope_and_seniority=14,
        ai_transformation_relevance=13,
        compensation=8,
        company_attractiveness=4,
        practical_fit=3,
    )

    assert score.total == 87


def test_score_breakdown_rejects_score_above_maximum():
    """The AI should not be able to exceed a category maximum."""

    with pytest.raises(ValidationError):
        ScoreBreakdownOutput(
            career_direction_alignment=37,
            experience_evidence=22,
            scope_and_seniority=14,
            ai_transformation_relevance=13,
            compensation=8,
            company_attractiveness=4,
            practical_fit=3,
        )


def test_score_breakdown_rejects_negative_score():
    """The AI should not be able to return negative category scores."""

    with pytest.raises(ValidationError):
        ScoreBreakdownOutput(
            career_direction_alignment=23,
            experience_evidence=-1,
            scope_and_seniority=14,
            ai_transformation_relevance=13,
            compensation=8,
            company_attractiveness=4,
            practical_fit=3,
        )


def test_complete_ai_evaluation_accepts_valid_structure():
    """
    A complete evaluation that follows our contract should validate.
    """

    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())

    assert evaluation.state == "Strong Match"
    assert evaluation.confidence == "High"
    assert evaluation.opportunity.ability_to_do_job == "Strong"
    assert evaluation.score_breakdown.total == 87


def test_complete_ai_evaluation_rejects_invalid_state():
    """
    The AI should not be able to invent an unsupported recommendation state.
    """

    data = make_valid_ai_evaluation()
    data["state"] = "Definitely Apply"

    with pytest.raises(ValidationError):
        AIJobEvaluation(**data)