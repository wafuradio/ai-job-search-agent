"""Compare current deterministic screening with saved results, without DB writes."""
import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from src.review_store import DEFAULT_DB, ReviewStore
from src.review_display import shortlist_records
from src.candidates import get_candidate


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', help='Candidate profile ID')
    parser.add_argument('--db', help='Optional candidate-owned database override')
    parser.add_argument('--output', help='Optional local JSON report')
    args = parser.parse_args(argv)
    selected = get_candidate(args.candidate)
    with ReviewStore(args.db, readonly=True, candidate=selected) as store:
        rows = shortlist_records(store, include_filtered=True, limit=1000000)
    old = {row['id'] for row in rows if row['scout_score'] is not None
           and row['screening'] and row['screening']['status'] != 'Reject'}
    current = {row['id'] for row in rows if row['discovery'].accepted}
    entries = [{'id': row['id'], 'title': row['job']['title'],
                'previously_shortlisted': row['id'] in old,
                'screening': asdict(row['discovery'])} for row in rows]
    survivors = [row for row in rows if row['discovery'].accepted and row['status'] != 'Rejected']
    score_only = sorted(survivors, key=lambda row: (-row['discovery'].score,
                        0 if 'remote' in (row['job'].get('remote_status') or '').lower() else 1, row['id']))
    def summary(row):
        return {'id': row['id'], 'title': row['job']['title'], 'score': row['discovery'].score,
                'priority': row['discovery'].priority.get('band', 'unconfigured')}
    report = {'candidate_id': selected.candidate_id, 'saved_jobs': len(rows), 'previously_shortlisted': len(old),
              'current_screening_survivors': len(current), 'newly_surfaced': len(current - old),
              'previously_surfaced_now_filtered': len(old - current),
              'primary_filter_reasons': dict(Counter(row['discovery'].reasons[0] for row in rows
                                                     if not row['discovery'].accepted)),
              'review_priority_counts': dict(Counter(row['discovery'].priority.get('band', 'unconfigured') for row in survivors)),
              'top_by_keywords': [summary(row) for row in score_only[:10]],
              'top_by_review_priority': [summary(row) for row in survivors[:10]],
              'note': 'Heuristic calibration, not human-labeled accuracy. Saved scores may reflect earlier or newer runs. No decisions or database records changed.',
              'jobs': entries}
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'jobs'}, indent=2))
    return report


if __name__ == '__main__':
    main()
