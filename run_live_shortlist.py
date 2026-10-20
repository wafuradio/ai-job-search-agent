"""
First live AI-ranked job shortlist.

Fetches Anthropic jobs, runs deterministic screening,
and evaluates up to three selected opportunities with AI.

No applications are submitted.
"""

import argparse

from src.evaluator import evaluate_job_with_ai
from src.review_store import DEFAULT_DB, ReviewStore
from src.scout import is_us_job
from src.candidates import get_candidate
from src.normalizer import normalize_greenhouse_job
from src.fact_extractor import enrich_job_facts
from src.compensation_extractor import extract_compensation
from src.gatekeeper import evaluate_job as screen_job
from src.pipeline import screen_greenhouse_jobs
from src.sources.greenhouse import fetch_greenhouse_jobs


MAX_EVALUATIONS = 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Call the OpenAI API to evaluate selected jobs.",
    )
    parser.add_argument("--candidate", help="Candidate profile ID")
    parser.add_argument("--db", help="Optional candidate-owned database override")
    args = parser.parse_args()
    with ReviewStore(args.db, candidate=get_candidate(args.candidate)) as store:
        args.db = str(store.path)
        run_shortlist(args, store)


def run_shortlist(args, store):

    print("\nFetching live Anthropic jobs...")

    source_jobs = fetch_greenhouse_jobs("anthropic")

    # Preserve all discoveries, including jobs removed by discovery filters.
    job_ids = {}
    for source_job in source_jobs:
        job = normalize_greenhouse_job(
            source_job, company="Anthropic",
            country="United States" if is_us_job(source_job.location) else None,
        )
        enrich_job_facts(job)
        extract_compensation(job)
        job_ids[source_job.source_job_id] = store.save_job(job, screening=screen_job(job, candidate=store.candidate))

    screened = screen_greenhouse_jobs(
        jobs=source_jobs,
        company="Anthropic",
        candidate=store.candidate,
    )

    for item in screened:
        store.save_job(item.job, screening=item.gatekeeper, scout_score=item.scout_score)

    # Scout is a discovery filter, not a final fit score.
    candidates = sorted(
        screened,
        key=lambda item: item.scout_score,
        reverse=True,
    )[:MAX_EVALUATIONS]

    print(f"\nJobs surviving screening: {len(screened)}")
    print(f"Selected for AI evaluation: {len(candidates)}")

    if not candidates:
        print("\nNo eligible jobs found.")
        return

    print("\nSELECTED JOBS")
    print("=" * 65)

    for index, item in enumerate(candidates, start=1):
        job = item.job
        comp = job.compensation

        print(f"\n{index}. {job.title}")
        print(f"   Local review ID: {job_ids[job.external_job_id]}")
        print(f"   Screening: {item.gatekeeper.status}; {item.gatekeeper.reasons}; {item.gatekeeper.flags}")
        print(f"   Scout relevance: {item.scout_score}")
        print(f"   Location: {job.location_text}")
        print(f"   Work arrangement: {job.remote_status}")
        print(
            f"   Published compensation: "
            f"{comp.published_min} - {comp.published_max}"
        )
        print(f"   Compensation type: {comp.compensation_type}")
        print(f"   URL: {job.job_url}")

    if not args.evaluate:
        print(
            "\nPREVIEW ONLY. No OpenAI API calls were made.\n"
            "To evaluate these jobs, run:\n"
            "python3 run_live_shortlist.py --evaluate"
        )
        return

    confirmation = input(
        "\nThis will make up to 3 paid OpenAI API calls. "
        "Type EVALUATE to continue: "
    )

    if confirmation != "EVALUATE":
        print("Evaluation cancelled.")
        return

    evaluations = []

    for index, item in enumerate(candidates, start=1):
        job = item.job

        print(
            f"\nEvaluating {index}/{len(candidates)}: "
            f"{job.title}"
        )

        try:
            job_id = job_ids[job.external_job_id]
            revision = store.get_job(job_id)["revision"]
            evaluation = evaluate_job_with_ai(job, candidate=store.candidate)
            store.save_evaluation(job_id, evaluation, revision=revision)

        except Exception as exc:
            print(f"Evaluation failed for {job.title}: {exc}")
            continue

        evaluations.append(
            (
                evaluation.score_breakdown.total,
                job,
                evaluation,
            )
        )

    evaluations.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    print("\n" + "=" * 65)
    print("FIRST LIVE AI-RANKED SHORTLIST")
    print("=" * 65)

    if not evaluations:
        print("No evaluations completed successfully.")
        return

    for rank, (score, job, evaluation) in enumerate(
        evaluations,
        start=1,
    ):
        comp = job.compensation

        print(f"\n{rank}. {job.company} | {job.title}")
        print(f"   AI score: {score}/100")
        print(f"   Recommendation: {evaluation.state}")
        print(f"   Confidence: {evaluation.confidence}")
        print(f"   Work arrangement: {job.remote_status}")

        if comp.published_min is not None:
            print(
                f"   Published compensation: "
                f"${comp.published_min:,} - "
                f"${comp.published_max:,}"
            )
            print(f"   Compensation type: {comp.compensation_type}")
        else:
            print("   Compensation: Unknown")

        print(f"\n   Why: {evaluation.recommendation_reason}")

        print("\n   Strengths:")
        for strength in evaluation.strengths[:3]:
            print(f"     + {strength}")

        print("\n   Gaps:")
        for gap in evaluation.gaps[:3]:
            print(f"     - {gap}")

        print("\n   Questions:")
        for question in evaluation.questions_to_investigate[:2]:
            print(f"     ? {question}")

        print(f"\n   Job posting: {job.job_url}")
        print(f"   Review locally: python3 review_jobs.py --candidate {store.candidate.candidate_id} --db {args.db} show {job_ids[job.external_job_id]}")
        print("-" * 65)


if __name__ == "__main__":
    main()