"""
AI evaluator for the Job Search Agent.

This module prepares normalized job data, candidate career preferences,
and candidate experience evidence for semantic evaluation by an AI model.

The evaluator uses structured output so AI judgments can be validated,
tested, stored, ranked, and reviewed consistently.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal, Optional

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from src.models import Job
from src.candidates import get_candidate


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CAREER_PROFILE_PATH = get_candidate().directory / "career_profile.json"
CANDIDATE_EVIDENCE_PATH = get_candidate().directory / "candidate_evidence.json"


class RequirementEvidenceOutput(BaseModel):
    """AI assessment of one important job requirement."""

    requirement: str
    evidence_type: Literal[
        "Direct Evidence",
        "Transferable Evidence",
        "Gap",
    ]
    evidence: Optional[str] = None
    explanation: Optional[str] = None


class OpportunityAssessmentOutput(BaseModel):
    """Human-centered assessment of the opportunity."""

    opportunity_quality: Literal[
        "Strong",
        "Moderate",
        "Weak",
    ]

    ability_to_do_job: Literal[
        "Strong",
        "Moderate",
        "Stretch",
        "Poor",
    ]

    likely_enjoyment: Literal[
        "High",
        "Medium",
        "Low",
        "Uncertain",
    ]

    compensation_outlook: Literal[
        "Strong",
        "Possible",
        "Below Target",
        "Unknown",
    ]

    opportunity_reason: str
    ability_reason: str
    enjoyment_reason: str
    compensation_reason: str


class ScoreBreakdownOutput(BaseModel):
    """Validated 100-point fit-score components."""

    career_direction_alignment: int = Field(ge=0, le=25)
    experience_evidence: int = Field(ge=0, le=25)
    scope_and_seniority: int = Field(ge=0, le=15)
    ai_transformation_relevance: int = Field(ge=0, le=15)
    compensation: int = Field(ge=0, le=10)
    company_attractiveness: int = Field(ge=0, le=5)
    practical_fit: int = Field(ge=0, le=5)

    @property
    def total(self) -> int:
        """Return the calculated total rather than trusting AI arithmetic."""

        return (
            self.career_direction_alignment
            + self.experience_evidence
            + self.scope_and_seniority
            + self.ai_transformation_relevance
            + self.compensation
            + self.company_attractiveness
            + self.practical_fit
        )


class AIJobEvaluation(BaseModel):
    """
    Structured output returned by the AI evaluator.

    Relationship information is deliberately excluded from the AI fit
    calculation. It is handled independently elsewhere in the system.
    """

    role_mission: str

    opportunity: OpportunityAssessmentOutput

    requirement_evidence: list[RequirementEvidenceOutput]

    strengths: list[str]
    gaps: list[str]
    questions_to_investigate: list[str]

    score_breakdown: ScoreBreakdownOutput

    state: Literal[
        "Strong Match",
        "Possible Match",
        "Watch",
        "Reject",
        "Needs Information",
    ]

    confidence: Literal[
        "High",
        "Medium",
        "Low",
    ]

    recommendation_reason: str


def load_json_file(path: Path) -> dict[str, Any]:
    """
    Load and return a JSON configuration file.

    Raises clear errors rather than silently continuing when configuration
    is missing or malformed.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Required configuration file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_career_profile(candidate=None) -> dict[str, Any]:
    """Load the candidate's career goals and job-search preferences."""

    return get_candidate(candidate).load("career_profile.json")


def load_candidate_evidence(candidate=None) -> dict[str, Any]:
    """Load structured evidence from the candidate's actual experience."""

    return get_candidate(candidate).load("candidate_evidence.json")


def job_to_dict(job: Job) -> dict[str, Any]:
    """
    Convert a Job dataclass into a JSON-compatible dictionary.

    datetime values are converted to ISO-formatted strings.
    """

    job_data = asdict(job)

    if job.discovered_at:
        job_data["discovered_at"] = job.discovered_at.isoformat()

    return job_data


def build_evaluation_context(job: Job, candidate=None) -> dict[str, Any]:
    """
    Build the complete evidence package sent to the AI evaluator.

    Keeping this context structured allows us to inspect and test exactly
    what information the model receives.
    """

    selected = get_candidate(candidate)
    return {
        "candidate_id": selected.candidate_id,
        "career_profile": load_career_profile(selected),
        "candidate_evidence": load_candidate_evidence(selected),
        "job": job_to_dict(job),
    }


def build_evaluation_instructions(candidate=None) -> str:
    """
    Return the core reasoning instructions for the AI evaluator.

    These instructions prioritize human-centered opportunity assessment
    over keyword or title matching.
    """

    selected = get_candidate(candidate)
    profile = selected.load('career_profile.json')
    compensation = profile.get('compensation', {})
    target = compensation.get('target_total_compensation_usd')
    compensation_guidance = (f'The target is approximately ${target:,.0f} total compensation, not necessarily\n${target:,.0f} base salary.'
                             if isinstance(target, (int, float)) and not isinstance(target, bool)
                             else 'No compensation target is supplied. Do not assume one; ask the candidate.')
    work = profile.get('work_model', {})
    if work.get('remote_is_hard_requirement'):
        work_guidance = 'Confirmed remote work is required by this candidate. Treat incompatible arrangements as a mismatch.'
    elif work.get('remote_preferred'):
        work_guidance = 'Remote work is strongly preferred, but hybrid work is not automatically disqualifying. Surface onsite work as a significant practical-fit concern.'
    else:
        work_guidance = 'Assess work arrangement against this candidate’s stated preferences; do not assume remote work is preferred.'
    return """
You are evaluating a job opportunity for one specific candidate.

Your primary question is:

Is this a genuinely good opportunity for this candidate?

Evaluate the actual work described in the posting, not merely the job title
or the presence of fashionable terms such as AI.

You must assess four human-centered questions:

1. CAN THE CANDIDATE DO THE JOB?

Determine what the company is actually hiring this person to accomplish.

Compare the major requirements with the candidate evidence.

Classify each important requirement as:

- Direct Evidence
- Transferable Evidence
- Gap

Exact prior job titles are not required.
Transferable experience counts.
A gap is not automatically disqualifying.

Distinguish a learnable gap from a gap that would prevent successful
performance.

2. IS THIS A GOOD OPPORTUNITY?

Consider:

- scope
- ownership
- influence
- strategic value
- learning potential
- career growth
- interesting problems
- whether the role advances the candidate toward their documented career direction

Do not allow an impressive title alone to make an opportunity Strong.

3. WOULD THE CANDIDATE LIKELY ENJOY THE WORK?

Use the candidate's positive and negative enjoyment signals.

Do not assume enjoyment from title, company prestige, compensation, or
AI terminology.

If the posting does not provide enough information about the actual work,
return Uncertain.

4. IS THE COMPENSATION POTENTIALLY RIGHT?

Evaluate only disclosed:

- base salary
- bonus
- equity
- total compensation

{compensation_guidance}

Unknown compensation must remain Unknown.

Never invent or estimate undisclosed compensation.

IMPORTANT REASONING RULES:

- Do not invent candidate experience.
- Do not exaggerate the candidate's AI background.
- Do not treat general technology leadership as machine-learning expertise.
- Do not assume deep engineering, data science, or model-development skills
  unless supported by candidate evidence.
- Do not reward a role merely because AI appears in the title.
- Evaluate relevance to the candidate’s actual target domain; AI is not required.
- {work_guidance}
- Work arrangement should affect practical fit.
- Missing information should lower confidence or create a question to
  investigate rather than being guessed.
- The numerical score is a ranking aid, not the final human decision.
- Relationship strength must remain separate from job-fit scoring.
- Do not give a relationship advantage in the score.
- The human reviewer always makes the final decision.

SCORING:

Career direction alignment: 0-25
Experience evidence: 0-25
Scope and seniority: 0-15
Target-domain relevance: 0-15 (the legacy output field is ai_transformation_relevance; it applies to this candidate’s domain, which need not involve AI)
Compensation: 0-10
Company attractiveness: 0-5
Practical fit: 0-5

Do not manufacture precision.

Scores should reflect the evidence available in the posting and candidate
profile.

FINAL CLASSIFICATIONS:

Opportunity:
- Strong
- Moderate
- Weak

Ability to do the job:
- Strong
- Moderate
- Stretch
- Poor

Likely enjoyment:
- High
- Medium
- Low
- Uncertain

Compensation:
- Strong
- Possible
- Below Target
- Unknown

Overall recommendation:
- Strong Match
- Possible Match
- Watch
- Reject
- Needs Information

Confidence:
- High
- Medium
- Low
""".strip().format(compensation_guidance=compensation_guidance, work_guidance=work_guidance)


def build_evaluation_payload(job: Job, candidate=None) -> dict[str, Any]:
    """
    Build the complete structured payload for AI evaluation.

    This function does not call the model, allowing the evaluation package
    to be inspected and tested independently.
    """

    return {
        "instructions": build_evaluation_instructions(candidate),
        "context": build_evaluation_context(job, candidate),
    }


def evaluate_job_with_ai(
    job: Job,
    model: str = "gpt-5.6",
    *, candidate=None,
) -> AIJobEvaluation:
    """
    Evaluate one normalized job using the OpenAI API.

    The API response is parsed directly into AIJobEvaluation so malformed
    or unexpected output cannot silently enter the rest of the system.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    client = OpenAI()

    payload = build_evaluation_payload(job, candidate)

    response = client.responses.parse(
        model=model,
        input=[
            {
                "role": "system",
                "content": payload["instructions"],
            },
            {
                "role": "user",
                "content": (
                    "Evaluate the following job using only the supplied "
                    "career profile, candidate evidence, and job posting.\n\n"
                    + json.dumps(
                        payload["context"],
                        indent=2,
                        ensure_ascii=False,
                    )
                ),
            },
        ],
        text_format=AIJobEvaluation,
    )

    if response.output_parsed is None:
        raise RuntimeError(
            "The AI evaluator returned no structured evaluation."
        )

    return response.output_parsed