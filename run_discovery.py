"""Fetch configured public job feeds and save results. Never calls paid AI APIs."""
import argparse
from src.discovery import load_boards, discover_boards, load_job_boards, load_import_jobs
from src.review_store import DEFAULT_DB, ReviewStore
from src.candidates import get_candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', help='Candidate profile ID; defaults to configured candidate')
    parser.add_argument('--db', help='Optional candidate-owned database override')
    parser.add_argument('--boards', help='Optional board file override')
    parser.add_argument('--html', help='Save this run’s current shortlist as a local browser report')
    parser.add_argument('--remote-html', help='Save a remote-only report for this run')
    parser.add_argument('--search-html', help='Save candidate-specific browser searches for broader discovery')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--job-boards-only', action='store_true', help='Read configured public job boards without fetching company feeds')
    mode.add_argument('--search-plan-only', action='store_true', help='Generate searches only; no network requests or database writes')
    mode.add_argument('--import-jobs', help='Import copied postings from a local JSON file; no network requests')
    parser.add_argument('--enrich-dates', action='store_true', help='Make additional free Greenhouse GETs for first-publication dates of screening survivors')
    parser.add_argument('--company', action='append', help='Company name; repeat to select several')
    args = parser.parse_args(argv)
    try:
        selected = get_candidate(args.candidate)
        if args.search_html:
            from src.search_plan import write_search_plan
            print(f'Browser search plan: {write_search_plan(args.search_html, candidate=selected)}')
        if args.search_plan_only:
            if not args.search_html:
                raise ValueError('--search-plan-only requires --search-html')
            return 0
        if (args.job_boards_only or args.import_jobs) and (args.company or args.boards):
            raise ValueError('Company filters cannot be combined with job-boards-only or import mode')
        feeds = load_job_boards(candidate=selected) if not (args.company or args.boards or args.import_jobs) else []
        boards = [] if args.job_boards_only or args.import_jobs else load_boards(args.boards, args.company, candidate=selected, allow_empty=bool(feeds))
        imported = load_import_jobs(args.import_jobs) if args.import_jobs else []
        if not boards and not feeds and not imported:
            raise ValueError('No discovery sources or imported jobs configured for this candidate')
        print(f"Candidate: {selected.display_name} ({selected.candidate_id})")
        with ReviewStore(args.db, candidate=selected) as store:
            result = discover_boards(store, boards, enrich_dates=args.enrich_dates,
                                     job_boards=feeds, imported_jobs=imported)
            if args.html or args.remote_html:
                from src.review_display import shortlist_records, write_html_report
                rows = [row for row in shortlist_records(store, limit=1000000)
                        if row['id'] in result.saved_ids]
                if args.html:
                    print(f"Current-run report: {write_html_report(rows, args.html, candidate=selected)}")
                if args.remote_html:
                    remote = [row for row in rows if 'remote' in (row['job'].get('remote_status') or '').lower()]
                    print(f"Remote report: {write_html_report(remote, args.remote_html, candidate=selected)}")
        for board in result.boards:
            print(f'{board["company"]} ({board["source"]}): {board["retrieved"]} retrieved')
        print(f'Retrieved: {result.retrieved}; saved unique jobs: {len(result.saved_ids)} '
              f'({len(result.new_ids)} new); passed screening: {len(result.accepted_ids)}')
        for reason, count in result.filtered.items():
            print(f'Filtered {count}: {reason}')
        for error in result.errors:
            print(f'ERROR: {error}')
        print('Discovery only. No AI evaluations or applications. Human review decisions are preserved; material posting changes revoke approval.')
        if result.errors:
            return 1
        return 0
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
