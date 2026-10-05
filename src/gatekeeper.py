"""
Deterministic gatekeeper for the AI Job Search Agent.

The Gatekeeper evaluates rules that should not require AI judgment.

Important V1 design decision:
Remote work is strongly preferred, but hybrid work is NOT automatically
rejected. A sufficiently strong opportunity may still deserve human review.

The Gatekeeper therefore distinguishes between:
- PASS: No blocking condition detected.
- FLAG: A meaningful concern exists, but the job should continue.
- NEEDS_INFORMATION: Important information is unclear.
- REJECT: A true hard exclusion was detected.
"""

from dataclasses import dataclass, field

from src.models import Job


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

        Flagged jobs continue because Lisa should retain the final decision
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


def evaluate_job(job: Job) -> GatekeeperResult:
    """
    Apply V1 deterministic screening rules to a normalized job.

    The Gatekeeper is intentionally conservative about rejection.
    Semantic questions such as whether a role is strategically attractive
    belong to the later AI evaluator.
    """

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
            for term in ("part-time", "part time", "intern", "internship")
        ):
            rejection_reasons.append(
                f"Employment type is outside target scope: {job.employment_type}."
            )

        if any(
            term in employment_type
            for term in ("contract", "temporary", "temp")
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

    if any(term in work_model_text for term in hybrid_terms):
        flags.append(
            "Hybrid or recurring office attendance detected. "
            "Remote work is preferred, so this requires human review."
        )

    elif any(term in work_model_text for term in onsite_terms):
        flags.append(
            "Onsite or office-based work detected. "
            "This is a significant practical-fit concern."
        )

    elif any(term in work_model_text for term in remote_terms):
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

    junior_title_terms = (
        "junior",
        "entry level",
        "entry-level",
        "associate program manager",
        "program coordinator",
        "project coordinator",
        "assistant program manager",
    )

    if any(term in job.title.lower() for term in junior_title_terms):
        rejection_reasons.append(
            "Role appears materially below target seniority."
        )

    # ---------------------------------------------------------
    # Roles centered primarily on event execution
    # ---------------------------------------------------------

    event_title_terms = (
        "event coordinator",
        "events coordinator",
        "event manager",
        "events manager",
        "event producer",
        "events producer",
        "conference manager",
        "conference producer",
    )

    if any(term in job.title.lower() for term in event_title_terms):
        rejection_reasons.append(
            "Role appears centered on event execution rather than the "
            "target AI, operations, systems, or transformation direction."
        )

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