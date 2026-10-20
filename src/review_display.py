"""Readable offline shortlist and standalone HTML report. No review mutations."""
from html import escape
from datetime import datetime
from shlex import quote
from src.candidates import get_candidate
from pathlib import Path
from urllib.parse import urlsplit

from src.screening import job_from_dict, screen_job
from src.scout import load_scout_config
from src.search_settings import load_search_settings
from src.role_priority import PRIORITY_LABELS, PRIORITY_ORDER


def shortlist_records(store, *, status=None, company=None, work_model=None,
                      query=None, include_filtered=False, limit=20, priority=None):
    selected = store.candidate
    config = load_scout_config(candidate=selected)
    search, profile = load_search_settings(candidate=selected)
    rows = []
    for row in store.review_records():
        job = row['job']
        if status and row['status'] != status:
            continue
        if company and company.casefold() != job['company'].casefold():
            continue
        if work_model and work_model.casefold() not in (job.get('remote_status') or 'Unknown').casefold():
            continue
        if query and query.casefold() not in (job['company'] + ' ' + job['title'] + ' ' + (job.get('raw_description') or '')).casefold():
            continue
        result = screen_job(job_from_dict(job), config, search, profile, candidate=selected)
        if not include_filtered and (not result.accepted or row['status'] == 'Rejected'):
            continue
        if priority and result.priority.get('band') != priority:
            continue
        row['discovery'] = result
        row['candidate_id'] = selected.candidate_id
        row['candidate_name'] = selected.display_name
        row['review_db'] = str(store.path)
        row['relationship_note'] = ('Known relationship company; does not affect relevance.'
                                    if job['company'].casefold() in {c.casefold() for c in profile.get('known_relationship_companies', [])}
                                    else '')
        rows.append(row)
    # Review category precedes keyword relevance; no candidate status is changed.
    rows.sort(key=lambda row: (PRIORITY_ORDER.get(row['discovery'].priority.get('band'), 1),
                               -row['discovery'].score,
                               0 if 'remote' in (row['job'].get('remote_status') or '').lower() else 1,
                               row['id']))
    return rows[:limit]


def compensation_label(job):
    comp = job.get('compensation') or {}
    lo, hi = comp.get('published_min'), comp.get('published_max')
    if lo is None:
        lo, hi = comp.get('base_min'), comp.get('base_max')
    if lo is not None and hi is not None:
        return f'${lo:,}–${hi:,} ({comp.get("compensation_type") or "type unconfirmed"})'
    return comp.get('compensation_text') or 'Unknown — investigate'


def date_label(value):
    """Display the source calendar date, retaining the full timestamp in storage."""
    if not isinstance(value, str) or not value.strip():
        return 'Unknown'
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
    except ValueError:
        return 'Unknown (invalid source timestamp)'


def posting_date_lines(row):
    job = row['job']
    source, kind = job.get('source', ''), job.get('posted_date_kind')
    if kind == 'first_published':
        label = 'First published'
    elif kind == 'last_published' or (source.casefold() == 'ashby' and job.get('posted_date')):
        # Legacy saved Ashby records used publishedAt before provenance was explicit.
        label = 'Published / republished'
    elif kind == 'board_published':
        label = 'Published on job board (employer posting date unconfirmed)'
    else:
        label = 'Employer posting date'
    lines = ['  ' + label + ': ' + date_label(job.get('posted_date'))]
    if job.get('source_updated_at'):
        lines.append('  Employer record updated: ' + date_label(job['source_updated_at']) + ' (not the posting date)')
    lines.append('  First saved locally: ' + date_label(row.get('created_at')) + ' (not the posting date)')
    return lines


def render_summary(row):
    job, result = row['job'], row['discovery']
    lines = [f'#{row["id"]} | {job["company"]} | {job["title"]}',
             f'  Candidate: {row.get("candidate_name", row.get("candidate_id", "selected profile"))}',
             f'  Review: {row["status"]} | Scout relevance: {result.score} (not an AI fit score)',
             f'  {job.get("location_text") or "Location unknown"} | {job.get("remote_status") or "Work model unknown"}',
             f'  Compensation: {compensation_label(job)}',
             '  Matches: ' + ', '.join(result.matches['role_terms'] + result.matches['positive_signals']),
             '  Screening: ' + ('Continue to human review' if result.accepted else '; '.join(result.reasons))]
    lines.append('  Source: ' + job['source'])
    lines[4:4] = posting_date_lines(row)
    priority = result.priority
    if priority and priority.get('band') != 'unconfigured':
        lines.insert(2, '  Review category: ' + PRIORITY_LABELS[priority['band']] + ' (heuristic, not a fit verdict)')
        lines.append('  Why this category: ' + priority['reason'])
        for item in (priority.get('specialist_evidence') or priority.get('evidence') or [])[:2]:
            lines.append('  Posting evidence [' + item['signal'] + ']: ' + item['text'][:320])
        for question in priority.get('questions', []):
            lines.append('  Investigate: ' + question)
    lines += ['  Concern: ' + flag for flag in result.flags]
    if row['needs_reevaluation']:
        lines.append('  REEVALUATION REQUIRED; previous approval is not active.')
    evaluation = row.get('evaluation')
    if evaluation:
        stale = 'STALE — previous posting revision' if evaluation['revision'] != row['revision'] else 'current revision'
        lines.append(f'  Saved AI score: {evaluation["score"]}/100 ({stale})')
        for key in ('strengths', 'gaps', 'questions_to_investigate'):
            lines.append(f'  {key.replace("_", " ").title()}: ' + '; '.join(evaluation['data'].get(key, [])))
    else:
        lines.append('  AI evaluation: Not run')
    if row.get('relationship_note'):
        lines.append('  ' + row['relationship_note'])
    lines.append('  Posting: ' + job['job_url'])
    return '\n'.join(lines)


def render_detail(record, candidate=None):
    selected = get_candidate(candidate)
    config = load_scout_config(candidate=selected)
    record = dict(record)
    record['discovery'] = screen_job(job_from_dict(record['job']), config, candidate=selected)
    record['candidate_id'] = selected.candidate_id
    record['candidate_name'] = selected.display_name
    record['evaluation'] = None
    if record['evaluations']:
        item = record['evaluations'][-1]
        record['evaluation'] = {'score': item['score'], 'revision': item['revision'], 'data': item['evaluation']}
    lines = [render_summary(record), '\nFULL DESCRIPTION', record['job'].get('raw_description') or 'Not supplied', '\nREVIEW HISTORY']
    for event in record['history']:
        if event['event'] in ('human_decision', 'material_update'):
            lines.append(f'{event["created_at"]} | {event["event"]} | {event["details"]}')
    return '\n'.join(lines)


def write_html_report(rows, path, *, candidate=None):
    candidate_name = (get_candidate(candidate).display_name if candidate is not None
                      else rows[0].get('candidate_name', 'selected candidate') if rows else 'selected candidate')
    cards = []
    for row in rows:
        url = row['job']['job_url']
        link_label = 'View on ' + row['job']['source'] if row['job']['source'] in ('Remotive', 'We Work Remotely') else 'View posting'
        link = (f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(link_label)}</a>'
                if urlsplit(url).scheme in ('http', 'https') else 'Posting URL unavailable')
        command = 'python3 review_jobs.py --candidate ' + quote(row.get('candidate_id', ''))
        if row.get('review_db'):
            command += ' --db ' + quote(row['review_db'])
        command += ' status ' + str(row['id']) + ' Interested'
        cards.append('<article><pre>' + escape(render_summary(row)) + '</pre>' + link
                     + '<details><summary>Full description</summary><pre>'
                     + escape(row['job'].get('raw_description') or 'Not supplied')
                     + '</pre></details><p>Record your decision locally: <code>'
                     + escape(command) + '</code></p></article>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Local job shortlist</title><style>
body{font:16px system-ui;margin:32px auto;max-width:1100px;padding:0 20px;color:#172537;background:#f4f7fa}
article{background:white;padding:24px;margin:18px 0;border:1px solid #d8e0e8;border-radius:12px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.6}a{color:#165b8c}
input{font:inherit;padding:12px;width:90%;max-width:650px}summary{cursor:pointer;font-weight:600}
</style><h1>Your local job shortlist</h1><p>Snapshot from saved postings, not a check that jobs are still open.
Scout relevance is not a career-fit assessment. Review decisions are unchanged.
Applications remain manual; job and exact-material approvals are required before any future submission.</p>
<label>Filter this report <input id="filter" type="search" placeholder="Company, title, location, concern…"></label>
<p id="count"></p>''' + ''.join(cards) + '''<script>
const filter=document.getElementById('filter');const cards=[...document.querySelectorAll('article')];
function update(){let visible=0;for(const card of cards){card.hidden=!card.textContent.toLowerCase().includes(filter.value.toLowerCase());if(!card.hidden)visible++;}document.getElementById('count').textContent=visible+' opportunities shown';}
filter.addEventListener('input',update);update();
</script></html>'''
    document = document.replace('<h1>Your local job shortlist</h1>', '<h1>Local job shortlist — ' + escape(candidate_name) + '</h1>')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding='utf-8')
    return path.resolve()
