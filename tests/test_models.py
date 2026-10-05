"""
Tests for the core data models used by the AI Job Search Agent.
"""

from src.models import (
    Compensation,
    Job,
    JobEvaluation,
    RequirementEvidence,
    ScoreBreakdown,
)


def test_job_can_be_created():
    """A normalized job can be created with the minimum required fields."""

    job = Job(
        company="Example AI Company",
        title="Director, AI Transformation",
        job_url="https://example.com/job/123",
        source="Company Career Site",
    )

    assert job.company == "Example AI Company"
    assert job.title == "Director, AI Transformation"
    assert job.job_url == "https://example.com/job/123"
    assert job.source == "Company Career Site"


def test_missing_information_is_not_guessed():
    """Unknown posting information should remain empty."""

    job = Job(
        company="Example Company",
        title="Principal Program Manager",
        job_url="https://example.com/job/456",
        source="Greenhouse",
    )

    assert job.remote_status is None
    assert job.location_text is None
    assert job.compensation.base_min is None
    assert job.compensation.base_max is None


def test_compensation_can_store_salary_range():
    """Compensation should preserve structured salary information."""

    compensation = Compensation(
        base_min=210000,
        base_max=260000,
        bonus="Eligible for annual bonus",
        equity="Equity eligible",
        compensation_text="$210,000-$260,000 base plus bonus and equity",
    )

    job = Job(
        company="Example Company",
        title="Staff AI Operations Lead",
        job_url="https://example.com/job/789",
        source="Company Career Site",
        compensation=compensation,
    )

    assert job.compensation.base_min == 210000
    assert job.compensation.base_max == 260000
    assert job.compensation.bonus == "Eligible for annual bonus"
    assert job.compensation.equity == "Equity eligible"


def test_score_breakdown_calculates_total():
    """The scoring model should correctly calculate the 100-point fit score."""

    score = ScoreBreakdown(
        career_direction_alignment=23,
        experience_evidence=22,
        scope_and_seniority=14,
        ai_transformation_relevance=13,
        compensation=8,
        company_attractiveness=4,
        practical_fit=5,
    )

    assert score.total == 89


def test_relationship_score_is_separate_from_fit_score():
    """
    Relationship strength must not change the job-fit score.

    A strong referral path can improve access to a company, but it cannot
    transform a mediocre job into a stronger career match.
    """

    score = ScoreBreakdown(
        career_direction_alignment=20,
        experience_evidence=20,
        scope_and_seniority=10,
        ai_transformation_relevance=10,
        compensation=5,
        company_attractiveness=3,
        practical_fit=2,
    )

    evaluation = JobEvaluation(
        hard_filter_passed=True,
        fit_score=score.total,
        relationship_score=5,
        score_breakdown=score,
    )

    assert evaluation.fit_score == 70
    assert evaluation.relationship_score == 5
    assert evaluation.score_breakdown.total == 70


def test_requirement_evidence_can_classify_transferable_experience():
    """Requirements can be matched to transferable rather than exact-title evidence."""

    evidence = RequirementEvidence(
        requirement="Lead enterprise AI transformation programs",
        evidence_type="Transferable Evidence",
        evidence=(
            "Led enterprise technology programs and operational transformation "
            "while building AI-assisted workflow automation."
        ),
        explanation=(
            "The candidate has direct transformation leadership experience and "
            "newer hands-on AI implementation experience."
        ),
    )

    assert evidence.evidence_type == "Transferable Evidence"
    assert evidence.evidence is not None


def test_opportunity_assessment_preserves_human_centered_judgment():
    """
    The evaluator should preserve the four human-centered questions that
    matter when deciding whether an opportunity is worth pursuing.
    """

    from src.models import OpportunityAssessment

    assessment = OpportunityAssessment(
        opportunity_quality="Strong",
        ability_to_do_job="Strong",
        likely_enjoyment="High",
        compensation_outlook="Possible",
        opportunity_reason=(
            "The role offers meaningful ownership of AI-enabled "
            "operational transformation."
        ),
        ability_reason=(
            "The candidate has strong direct and transferable evidence "
            "across systems, automation, and program leadership."
        ),
        enjoyment_reason=(
            "The work emphasizes solving operational problems, building "
            "systems, and applying AI rather than repetitive coordination."
        ),
        compensation_reason=(
            "The disclosed base salary is below the total compensation "
            "target, but bonus and equity may close the gap."
        ),
    )

    assert assessment.opportunity_quality == "Strong"
    assert assessment.ability_to_do_job == "Strong"
    assert assessment.likely_enjoyment == "High"
    assert assessment.compensation_outlook == "Possible"    