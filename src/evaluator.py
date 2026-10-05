"""
AI evaluator for the Job Search Agent.

This module prepares normalized job data, candidate career preferences,
and candidate experience evidence for semantic evaluation by an AI model.

V1 keeps prompt construction separate from the actual model/API call so
that the evaluation contract can be tested before external AI is introduced.
"""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.models import Job


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CAREER_PROFILE_PATH = PROJECT_ROOT / "config" / "career_profile.json"
CANDIDATE_EVIDENCE_PATH = PROJECT_ROOT / "config" / "candidate_evidence.json"


def load_json_file(path: Path) -> dict[str, Any]:
    """
    Load and return a JSON configuration file.

    Raises clear errors rather than silently continuing when configuration
    is missing or malformed.
    """

    if not path.exists():
        raise FileNotFoundError(f"Required configuration file not found: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_career_profile() -> dict[str, Any]:
    """Load the candidate's career goals and job-search preferences."""

    return load_json_file(CAREER_PROFILE_PATH)


def load_candidate_evidence() -> dict[str, Any]:
    """Load structured evidence from the candidate's actual experience."""

    return load_json_file(CANDIDATE_EVIDENCE_PATH)


def job_to_dict(job: Job) -> dict[str, Any]:
    """
    Convert a Job dataclass into a JSON-compatible dictionary.

    datetime values are converted to ISO-formatted strings.
    """

    job_data = asdict(job)

    if job.discovered_at:
        job_data["discovered_at"] = job.discovered_at.isoformat()

    return job_data


def build_evaluation_context(job: Job) -> dict[str, Any]:
    """
    Build the complete evidence package that will eventually be sent
    to the AI evaluator.

    Keeping this context structured allows us to inspect and test exactly
    what information the model receives.
    """

    return {
        "career_profile": load_career_profile(),
        "candidate_evidence": load_candidate_evidence(),
        "job": job_to_dict(job),
    }


def build_evaluation_instructions() -> str:
    """
    Return the core reasoning instructions for the AI evaluator.

    These instructions define how the model should reason about an
    opportunity. They deliberately prioritize human-centered opportunity
    assessment over keyword or title matching.
    """

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
   Classify evidence as:
   - Direct Evidence
   - Transferable Evidence
   - Gap

   Exact prior job titles are not required.
   Transferable experience counts.
   A gap is not automatically disqualifying.
   Distinguish a learnable gap from a gap that would prevent successful
   performance.

2. IS THIS A GOOD OPPORTUNITY?
   Consider scope, ownership, influence, strategic value, learning potential,
   career growth, interesting problems, and whether the role expands the
   candidate's direction toward operations, systems, transformation,
   automation, and practical AI application.

3. WOULD THE CANDIDATE LIKELY ENJOY THE WORK?
   Use the candidate's positive and negative enjoyment signals.
   Do not assume enjoyment from title or prestige.
   If the posting does not provide enough information, return Uncertain.

4. IS THE COMPENSATION POTENTIALLY RIGHT?
   Evaluate disclosed base salary, bonus, equity, and total compensation.
   The target is approximately $250,000 total compensation, not necessarily
   $250,000 base salary.
   Unknown compensation must remain Unknown.
   Never invent or estimate undisclosed compensation.

IMPORTANT REASONING RULES:

- Do not invent candidate experience.
- Do not exaggerate the candidate's AI background.
- Do not treat general technology leadership as machine-learning expertise.
- Do not assume deep engineering, data science, or model-development skills
  unless supported by candidate evidence.
- Do not reward a role merely because AI appears in the title.
- A strong transformation or operations opportunity can be attractive even
  when AI is only one component of the work.
- Remote work is strongly preferred, but hybrid work is not automatically
  disqualifying.
- Relationship strength must remain separate from job-fit scoring.
- Missing information should lower confidence or create a question to
  investigate rather than being guessed.
- The numerical score is a ranking aid, not the final human decision.
- The human reviewer always makes the final decision.

The final evaluation must ultimately support these outputs:

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
""".strip()


def build_evaluation_payload(job: Job) -> dict[str, Any]:
    """
    Build the complete structured payload for future AI evaluation.

    This function does not call an AI model. It creates the exact package
    that a model will receive so it can be tested independently.
    """

    return {
        "instructions": build_evaluation_instructions(),
        "context": build_evaluation_context(job),
    }