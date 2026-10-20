"""
Deterministic gatekeeper for the AI Job Search Agent.

The Gatekeeper evaluates rules that should not require AI judgment.

Employment/title exclusions and work preferences come from the selected
candidate profile. The default profile prefers remote work while retaining
hybrid and onsite opportunities for human review.

The Gatekeeper therefore distinguishes between:
- PASS: No blocking condition detected.
- FLAG: A meaningful concern exists, but the job should continue.
- NEEDS_INFORMATION: Important information is unclear.
- REJECT: A true hard exclusion was detected.
"""

from dataclasses import dataclass, field

from src.models import Job
from src.candidates import get_candidate


PASS = "Pass"
FLAG = "Flag"
NEEDS_INFORMATION = "Needs Information"
REJECT = "Reject"


@dataclass
class GatekeeperResult:
    """
    Result of deterministic screening.

    Flags identify concerns that should remain visible during later
    evaluation without automatically eliminating the opportunity.
    """

    status: str
    reasons: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """
        Return True when the job may continue to later evaluation.

        Flagged jobs continue because the candidate should retain the final decision
        on potentially attractive exceptions.
        """
        return self.status in {PASS, FLAG}


def _combined_job_text(job: Job) -> str:
    """
    Combine useful posting fields into normalized lowercase text.

    This allows deterministic rules to inspect both structured fields and
    the original posting language.
    """

    parts = [
        job.title,
        job.employment_type,
        job.location_text,
        job.remote_status,
        job.remote_policy_text,
        job.travel_requirement,
        job.summary,
        job.raw_description,
    ]

    return " ".join(part for part in parts if part).lower()


def evaluate_job(job: Job, *, candidate=None, profile=None) -> GatekeeperResult:
    """
    Apply V1 deterministic screening rules to a normalized job.

    The Gatekeeper is intentionally conservative about rejection.
    Semantic questions such as whether a role is strategically attractive
    belong to the later AI evaluator.
    """

    selected = get_candidate(candidate)
    rules = selected.load('screening_rules.json')
    profile = selected.load('career_profile.json') if profile is None else profile
    remote_preferred = profile.get('work_model', {}).get('remote_preferred', False)
    text = _combined_job_text(job)

    rejection_reasons: list[str] = []
    flags: list[str] = []
    information_needed: list[str] = []

    # ---------------------------------------------------------
    # Employment type
    # ---------------------------------------------------------

    if job.employment_type:
        employment_type = job.employment_type.lower()

        if any(
            term in employment_type
            for term in rules["employment_reject_terms"]
        ):
            rejection_reasons.append(
                f"Employment type is outside target scope: {job.employment_type}."
            )

        if any(
            term in employment_type
            for term in rules["employment_flag_terms"]
        ):
            flags.append(
                f"Non-permanent employment type requires review: "
                f"{job.employment_type}."
            )

    # ---------------------------------------------------------
    # Remote / hybrid / onsite work model
    # ---------------------------------------------------------

    remote_status = (job.remote_status or "").lower()
    remote_policy = (job.remote_policy_text or "").lower()

    work_model_text = f"{remote_status} {remote_policy}"

    hybrid_terms = (
        "hybrid",
        "days per week",
        "days a week",
        "in office",
        "in-office",
        "office attendance",
    )

    onsite_terms = (
        "onsite",
        "on-site",
        "office-based",
        "office based",
    )

    remote_terms = (
        "remote",
        "fully remote",
        "remote-first",
        "remote first",
        "work from home",
    )

    if any(term in work_model_text for term in hybrid_terms) and remote_preferred:
        flags.append(
            "Hybrid or recurring office attendance detected. "
            "Remote work is preferred, so this requires human review."
        )

    elif any(term in work_model_text for term in onsite_terms) and remote_preferred:
        flags.append(
            "Onsite or office-based work detected. "
            "This is a significant practical-fit concern."
        )

    elif any(term in work_model_text for term in remote_terms + hybrid_terms + onsite_terms):
        pass

    elif not work_model_text.strip():
        information_needed.append(
            "Work arrangement is unknown."
        )

    else:
        information_needed.append(
            "Work arrangement could not be confidently classified."
        )

    # ---------------------------------------------------------
    # Clearly junior roles
    # ---------------------------------------------------------

    for group in rules['reject_title_groups']:
        if any(term.casefold() in job.title.casefold() for term in group['terms']):
            rejection_reasons.append(group['reason'])

    # ---------------------------------------------------------
    # Final status
    # ---------------------------------------------------------

    if rejection_reasons:
        return GatekeeperResult(
            status=REJECT,
            reasons=rejection_reasons,
            flags=flags,
        )

    if information_needed:
        return GatekeeperResult(
            status=NEEDS_INFORMATION,
            reasons=information_needed,
            flags=flags,
        )

    if flags:
        return GatekeeperResult(
            status=FLAG,
            reasons=[],
            flags=flags,
        )

    return GatekeeperResult(
        status=PASS,
        reasons=[],
        flags=[],
    )