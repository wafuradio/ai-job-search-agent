"""Offline CLI for human review. Does not submit applications."""
import argparse
import json

from src.review_store import DEFAULT_DB, STATUSES, ReviewStore
from src.candidates import get_candidate
from src.role_priority import PRIORITY_LABELS
from src.review_display import shortlist_records, render_summary, render_detail, write_html_report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", help="Candidate profile ID; defaults to configured candidate")
    parser.add_argument("--db", help="Optional candidate-owned database override")
    commands = parser.add_subparsers(dest="command", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--status", choices=STATUSES)
    show = commands.add_parser("show")
    show.add_argument("job_id", type=int)
    show.add_argument("--json", action="store_true", help="Show the complete machine-readable record")
    shortlist = commands.add_parser("shortlist", help="Rank and explain saved jobs offline")
    shortlist.add_argument("--status", choices=STATUSES)
    shortlist.add_argument("--company")
    shortlist.add_argument("--work-model")
    shortlist.add_argument("--search")
    shortlist.add_argument("--include-filtered", action="store_true")
    shortlist.add_argument("--limit", type=int, default=20)
    shortlist.add_argument("--priority", choices=list(PRIORITY_LABELS), help="Filter by heuristic role category")
    shortlist.add_argument("--html", help="Also save a standalone browser report")
    status = commands.add_parser("status")
    status.add_argument("job_id", type=int)
    status.add_argument("status", choices=STATUSES[:3])
    status.add_argument("--notes", default="")
    approve = commands.add_parser("approve")
    approve.add_argument("job_id", type=int)
    approve.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    try:
        selected = get_candidate(args.candidate)
        with ReviewStore(args.db, readonly=args.command in ("list", "show", "shortlist"), candidate=selected) as store:
            if args.command == "list":
                for row in store.list_jobs(args.status):
                    job = row["job"]
                    score = row["evaluations"][-1]["score"] if row["evaluations"] else "unevaluated"
                    flag = " | REEVALUATION REQUIRED" if row["needs_reevaluation"] else ""
                    print(f'{row["id"]} | {row["status"]} | {job["company"]} | {job["title"]} | {score}{flag}')
            elif args.command == "shortlist":
                if args.limit < 1:
                    raise ValueError("Limit must be positive")
                rows = shortlist_records(store, status=args.status, company=args.company,
                                         work_model=args.work_model, query=args.search,
                                         include_filtered=args.include_filtered, limit=args.limit, priority=args.priority)
                print(f"{len(rows)} saved opportunities. No new fetch or AI calls.")
                for row in rows:
                    print("\n" + render_summary(row))
                if args.html:
                    print(f"\nBrowser report: {write_html_report(rows, args.html, candidate=selected)}")
            elif args.command == "show":
                record = store.get_job(args.job_id)
                print(json.dumps(record, indent=2, ensure_ascii=False) if args.json else render_detail(record, selected))
            elif args.command == "status":
                store.set_status(args.job_id, args.status, args.notes)
                print("Review decision saved.")
            else:
                row = store.get_job(args.job_id)
                print(json.dumps(row, indent=2, ensure_ascii=False))
                confirmation = input(f'Type APPROVE {args.job_id} for {selected.display_name} ({selected.candidate_id}) to approve this job (submission remains manual): ')
                store.approve_job(args.job_id, confirmation=confirmation,
                                  revision=row["revision"], notes=args.notes)
                print("Job approval recorded. Exact application materials still require separate approval; submission is manual.")
    except (KeyError, ValueError, PermissionError, OSError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
