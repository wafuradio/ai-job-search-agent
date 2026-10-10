"""
Core data models for the AI Job Search Agent.

These models define the normalized structure used by the system after a job
posting has been discovered and before it is evaluated against the candidate
profile.

V1 intentionally keeps job data separate from AI evaluation data.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Compensation:
    # Confirmed annual base salary
    base_min: Optional[int] = None
    base_max: Optional[int] = None

    # Range published by the employer, regardless of type
    published_min: Optional[int] = None
    published_max: Optional[int] = None

    # "Base Salary", "OTE", "Total Compensation", or "Uncertain"
    compensation_type: Optional[str] = None

    # Other compensation components
    bonus: Optional[str] = None
    equity: Optional[str] = None
    total_comp_estimate: Optional[int] = None

    # Original posting evidence
    compensation_text: Optional[str] = None


@dataclass
class Job:
    """
    Normalized representation of a discovered job posting.

    This object contains facts about the job itself.
    Candidate-specific evaluation and scoring belong in a separate model.
    """

    # Identity
    company: str
    title: str
    job_url: str

    # Source information
    source: str
    discovered_at: datetime = field(default_factory=datetime.now)
    external_job_id: Optional[str] = None

    # Employment details
    employment_type: Optional[str] = None
    location_text: Optional[str] = None
    country: Optional[str] = None

    # Work model
    remote_status: Optional[str] = None
    remote_policy_text: Optional[str] = None
    travel_requirement: Optional[str] = None

    # Compensation
    compensation: Compensation = field(default_factory=Compensation)

    # Role content
    summary: Optional[str] = None
    responsibilities: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    preferred_qualifications: list[str] = field(default_factory=list)

    # Organizational context
    department: Optional[str] = None
    reports_to: Optional[str] = None
    seniority: Optional[str] = None

    # Original posting
    raw_description: Optional[str] = None

    # Posting metadata
    posted_date: Optional[str] = None
    application_deadline: Optional[str] = None


@dataclass
class RequirementEvidence:
    """
    Connects one job requirement to evidence from the candidate's experience.

    evidence_type should be one of:
    - Direct Evidence
    - Transferable Evidence
    - Gap
    """

    requirement: str
    evidence_type: str
    evidence: Optional[str] = None
    explanation: Optional[str] = None


@dataclass
class OpportunityAssessment:
    """
    Human-centered assessment of whether the role is worth pursuing.

    These dimensions deliberately sit above the numerical score. The score
    helps rank large numbers of jobs, but these fields explain whether the
    opportunity is actually attractive to the candidate.
    """

    # Strong / Moderate / Weak
    opportunity_quality: Optional[str] = None

    # Strong / Moderate / Stretch / Poor
    ability_to_do_job: Optional[str] = None

    # High / Medium / Low / Uncertain
    likely_enjoyment: Optional[str] = None

    # Strong / Possible / Below Target / Unknown
    compensation_outlook: Optional[str] = None

    # Short explanations supporting each judgment
    opportunity_reason: Optional[str] = None
    ability_reason: Optional[str] = None
    enjoyment_reason: Optional[str] = None
    compensation_reason: Optional[str] = None


@dataclass
class ScoreBreakdown:
    """
    V1 100-point job-fit scoring model.

    The numerical score is a ranking aid rather than the final decision.

    Relationship strength is deliberately excluded because access to a
    company must not artificially increase the quality of the job match.
    """

    career_direction_alignment: int = 0       # 25 points
    experience_evidence: int = 0              # 25 points
    scope_and_seniority: int = 0              # 15 points
    ai_transformation_relevance: int = 0      # 15 points
    compensation: int = 0                     # 10 points
    company_attractiveness: int = 0           # 5 points
    practical_fit: int = 0                    # 5 points

    @property
    def total(self) -> int:
        """Return the total job-fit score."""
        return (
            self.career_direction_alignment
            + self.experience_evidence
            + self.scope_and_seniority
            + self.ai_transformation_relevance
            + self.compensation
            + self.company_attractiveness
            + self.practical_fit
        )


@dataclass
class JobEvaluation:
    """
    Candidate-specific evaluation of a normalized job.

    This remains separate from Job so that factual posting data and AI
    judgment are never confused.
    """

    # Gatekeeper result
    hard_filter_passed: bool
    hard_filter_reasons: list[str] = field(default_factory=list)

    # Human-centered opportunity assessment
    opportunity: OpportunityAssessment = field(
        default_factory=OpportunityAssessment
    )

    # Overall evaluation
    state: Optional[str] = None
    fit_score: Optional[int] = None
    confidence: Optional[str] = None

    # Independent relationship signal
    relationship_score: int = 0
    relationship_notes: Optional[str] = None

    # Detailed scoring
    score_breakdown: ScoreBreakdown = field(default_factory=ScoreBreakdown)

    # Experience matching
    requirement_evidence: list[RequirementEvidence] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    # Agent reasoning presented to the human reviewer
    role_mission: Optional[str] = None
    recommendation_reason: Optional[str] = None
    questions_to_investigate: list[str] = field(default_factory=list)

    # Human-in-the-loop decision
    human_decision: Optional[str] = None
    human_notes: Optional[str] = None