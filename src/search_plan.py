"""Candidate-specific search links. Generating a plan makes no web requests."""
from html import escape
from pathlib import Path
from urllib.parse import urlencode
from urllib.parse import urlsplit

from src.candidates import get_candidate

SEARCH_GROUPS = (
    ('Remote boards', ('remotive.com/remote-jobs', 'weworkremotely.com/remote-jobs')),
    ('Startup and technology boards', ('wellfound.com', 'workatastartup.com', 'ycombinator.com/jobs')),
    ('Employer career sites', ('boards.greenhouse.io', 'job-boards.greenhouse.io', 'jobs.ashbyhq.com', 'jobs.lever.co')),
    ('LinkedIn and Indeed', ('linkedin.com/jobs', 'indeed.com')),
)


def search_groups(candidate=None):
    selected = get_candidate(candidate)
    groups = list(SEARCH_GROUPS)
    for site in selected.load('company_boards.json').get('career_sites', []):
        if site.get('enabled', True):
            parts = urlsplit(site['url'])
            groups.append((site['company'] + ' careers', (parts.netloc + parts.path.rstrip('/'),)))
    return groups


def search_links(candidate=None):
    selected = get_candidate(candidate)
    search = selected.load('search_config.json')
    profile = selected.load('career_profile.json')
    terms = search.get('discovery_plan', {}).get('terms')
    if terms is None:
        terms = search.get('role_searches', []) + profile.get('target_roles', {}).get('primary', [])
    terms = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
    country = search.get('search_scope', {}).get('country', '')
    remote = bool(search.get('search_scope', {}).get('remote_preferred') or search.get('search_scope', {}).get('remote_only'))
    links = []
    for label, domains in search_groups(selected):
        for term in terms:
            query = '(' + ' OR '.join('site:' + domain for domain in domains) + ') "' + term.replace('"', '') + '"'
            query += ' ' + country
            if remote:
                query += ' remote'
            links.append({'group': label, 'term': term, 'query': query,
                          'url': 'https://www.google.com/search?' + urlencode({'q': query})})
    return links


def write_search_plan(path, *, candidate=None):
    selected = get_candidate(candidate)
    links = search_links(selected)
    sections = []
    for group, _ in search_groups(selected):
        items = ''.join('<li><a target="_blank" rel="noopener noreferrer" href="' + escape(link['url'], quote=True)
                        + '">' + escape(link['term']) + '</a></li>' for link in links if link['group'] == group)
        sections.append('<section><h2>' + group + '</h2><ul>' + items + '</ul></section>')
    document = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Broader job discovery</title><style>body{font:17px system-ui;max-width:1000px;margin:40px auto;padding:20px;background:#f4f7fa;color:#172537}section{background:white;padding:24px;margin:20px 0;border-radius:12px}li{margin:12px 0}a{color:#165b8c}</style>
<h1>Broader discovery — ''' + escape(selected.display_name) + '''</h1>
<p>Searches use this candidate’s configured roles and geography. These are search links, not retrieved jobs or verified matches.
Open a search to discover new employers. Results may be stale; check the original posting and remote eligibility.</p>
<p>Remotive and We Work Remotely have automated feeds. Startup boards and employer searches here are browser searches.
To save a found posting, use Add a posting in the local dashboard, or the documented local JSON import; the same candidate screening and review rules apply.
No applications are submitted. Human job approval and exact-material approval remain mandatory.</p>''' + ''.join(sections) + '</html>'
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document, encoding='utf-8')
    return path.resolve()
