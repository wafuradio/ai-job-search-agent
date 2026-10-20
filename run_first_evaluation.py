"""
First live calibration run for the AI Job Search Agent.

This script sends one real job through the structured AI evaluator.
It is intentionally manual so we can calibrate judgment before
automating job discovery.
"""

from src.evaluator import evaluate_job_with_ai
from src.review_store import ReviewStore
from src.candidates import get_candidate
import argparse
from src.models import Compensation, Job


job = Job(
    company="Optum Health Technology",
    title="Principal Project-Program Manager for AI Transformation & Training",
    job_url="https://www.linkedin.com/jobs/view/4476146057/",
    source="LinkedIn",
    employment_type="Full-time",
    location_text="United States",
    remote_status="Remote",
    remote_policy_text=(
        "Telecommute from anywhere within the United States, "
        "subject to UnitedHealth Group's Telecommuter Policy."
    ),
    compensation=Compensation(
        compensation_text=(
            "$112,700-$193,200 annual salary based on full-time "
            "employment, plus eligible benefits, incentive and "
            "recognition programs, equity stock purchase, and "
            "401(k) contribution."
        ),
    ),
    summary=(
        "Principal program leadership role responsible for helping "
        "Optum Health Technology execute and drive adoption of "
        "AI-enabled delivery practices across the enterprise through "
        "transformation, workforce enablement, training, communications, "
        "employee engagement, operating models, governance, and "
        "measurable adoption outcomes."
    ),
    responsibilities=[
        (
            "Lead end-to-end program management and delivery for "
            "enterprise AI training and capability-enablement programs."
        ),
        (
            "Define program vision, scope, roadmaps, milestones, "
            "resource requirements, and delivery approaches with "
            "technical and business leadership."
        ),
        (
            "Partner across Technology, Operations, Clinical, "
            "Communications, Human Capital, and business teams to "
            "drive strategic alignment, readiness, and adoption."
        ),
        (
            "Establish program operating models, governance structures, "
            "decision rights, delivery standards, and executive "
            "reporting mechanisms."
        ),
        (
            "Create performance metrics, KPIs, and executive dashboards "
            "to measure AI training impact and adoption progress."
        ),
        (
            "Manage risks, dependencies, operational bottlenecks, "
            "scope, schedule, resources, quality, and business outcomes."
        ),
        (
            "Develop communications and employee-engagement strategies "
            "that accelerate awareness, understanding, and adoption "
            "of AI-enabled capabilities."
        ),
        (
            "Translate complex technical concepts into practical, "
            "actionable communications for technical, clinical, "
            "operational, and executive audiences."
        ),
        (
            "Use enterprise-approved AI tools to streamline workflows, "
            "automate tasks, and drive continuous improvement."
        ),
        (
            "Evaluate emerging trends to inform solution design and "
            "strategic innovation."
        ),
    ],
    requirements=[
        (
            "8+ years of progressive project, program, portfolio, "
            "transformation, or related management experience."
        ),
        (
            "5+ years leading large, complex, cross-functional "
            "initiatives in technology, healthcare, clinical, "
            "operational, or other regulated environments."
        ),
        (
            "5+ years developing and managing integrated program "
            "plans, milestones, dependencies, risks, issues, "
            "resources, and executive reporting."
        ),
        (
            "3+ years supporting organizational change, technology "
            "adoption, workforce enablement, learning, communications, "
            "or business-transformation initiatives."
        ),
        (
            "3+ years delivering complex cross-functional initiatives "
            "involving product, strategy, delivery, operations, and "
            "business stakeholders."
        ),
        (
            "Ability to operate effectively in a highly matrixed "
            "enterprise environment."
        ),
        (
            "Ability to engage and influence director, vice president, "
            "and senior executive stakeholders."
        ),
        (
            "Experience establishing governance, measurement frameworks, "
            "executive dashboards, decision processes, and escalation models."
        ),
        (
            "Ability to lead multiple concurrent workstreams through "
            "ambiguity, changing priorities, and organizational dependencies."
        ),
        (
            "Ability to translate complex technical, operational, or "
            "strategic concepts for diverse audiences."
        ),
    ],
    preferred_qualifications=[
        (
            "Experience leading AI, generative AI, automation, digital "
            "transformation, product-delivery transformation, or "
            "enterprise technology-adoption programs."
        ),
        (
            "Experience supporting AI-enabled delivery lifecycle, "
            "software-development lifecycle, Agile, product, or "
            "platform operating models."
        ),
        (
            "Experience in healthcare technology, clinical operations, "
            "care delivery, health services, or another highly "
            "regulated industry."
        ),
        (
            "Experience developing and scaling enterprise learning, "
            "workforce-development, clinical-education, or "
            "train-the-trainer programs."
        ),
        (
            "Experience creating integrated change-management, "
            "communications, employee-engagement, and adoption strategies."
        ),
        (
            "Experience developing adoption metrics, maturity "
            "assessments, employee listening mechanisms, scorecards, "
            "and value-realization measures."
        ),
        (
            "Familiarity with ServiceNow, SharePoint, Power BI, "
            "Viva Engage, or similar platforms."
        ),
        (
            "PMP, PgMP, CCMP, SAFe, Agile, or equivalent certification."
        ),
    ],
    raw_description=(
        "Optum Health Technology is advancing how its teams use "
        "artificial intelligence to design, build, deliver, and "
        "continuously improve technology-enabled products and services. "
        "The Principal Project-Program Manager for AI Transformation "
        "and Training will lead execution and adoption of AI-enabled "
        "delivery practices through complex transformation, workforce "
        "enablement, training, communications, employee engagement, "
        "operating models, governance, metrics, and cross-functional "
        "program leadership. The role works across Technology, "
        "Operations, Clinical, Communications, Human Capital, and "
        "business teams in a highly matrixed enterprise. Preferred "
        "experience includes AI and automation transformation, "
        "technology adoption, healthcare or regulated industries, "
        "enterprise learning, change management, adoption measurement, "
        "and PMP or related certification. The position can telecommute "
        "from anywhere in the United States. The disclosed annual "
        "salary range is $112,700-$193,200."
    ),
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', help='Candidate profile ID')
    parser.add_argument('--db', help='Optional candidate-owned database override')
    args = parser.parse_args(argv)
    selected = get_candidate(args.candidate)
    print("\nRunning first live AI job evaluation...\n")

    with ReviewStore(args.db, candidate=selected) as store:
        job_id = store.save_job(job)
        revision = store.get_job(job_id)["revision"]
        evaluation = evaluate_job_with_ai(job, candidate=selected)
        store.save_evaluation(job_id, evaluation, revision=revision)
    print(f"Local review ID: {job_id}")

    print("=" * 70)
    print(f"{job.company} | {job.title}")
    print("=" * 70)

    print(f"\nOVERALL: {evaluation.state}")
    print(f"CONFIDENCE: {evaluation.confidence}")
    print(f"SCORE: {evaluation.score_breakdown.total}/100")

    print("\nHUMAN-CENTERED ASSESSMENT")
    print(
        "Opportunity:",
        evaluation.opportunity.opportunity_quality,
    )
    print(
        "Ability to do job:",
        evaluation.opportunity.ability_to_do_job,
    )
    print(
        "Likely enjoyment:",
        evaluation.opportunity.likely_enjoyment,
    )
    print(
        "Compensation:",
        evaluation.opportunity.compensation_outlook,
    )

    print("\nROLE MISSION")
    print(evaluation.role_mission)

    print("\nWHY")
    print(evaluation.recommendation_reason)

    print("\nSTRENGTHS")
    for strength in evaluation.strengths:
        print(f"  + {strength}")

    print("\nGAPS")
    for gap in evaluation.gaps:
        print(f"  - {gap}")

    print("\nREQUIREMENT EVIDENCE")
    for item in evaluation.requirement_evidence:
        print(f"\n  {item.evidence_type}: {item.requirement}")

        if item.evidence:
            print(f"    Evidence: {item.evidence}")

        if item.explanation:
            print(f"    Why: {item.explanation}")

    print("\nQUESTIONS TO INVESTIGATE")
    for question in evaluation.questions_to_investigate:
        print(f"  ? {question}")

    print("\nSCORE BREAKDOWN")
    score = evaluation.score_breakdown

    print(
        f"  Career direction:       "
        f"{score.career_direction_alignment}/25"
    )
    print(
        f"  Experience evidence:    "
        f"{score.experience_evidence}/25"
    )
    print(
        f"  Scope & seniority:      "
        f"{score.scope_and_seniority}/15"
    )
    print(
        f"  AI/transformation:      "
        f"{score.ai_transformation_relevance}/15"
    )
    print(
        f"  Compensation:           "
        f"{score.compensation}/10"
    )
    print(
        f"  Company attractiveness: "
        f"{score.company_attractiveness}/5"
    )
    print(
        f"  Practical fit:          "
        f"{score.practical_fit}/5"
    )

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
