"""Candidate-owned employer sources. Registering a URL never fetches it."""
import fcntl
import hashlib
import ipaddress
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from src.candidates import get_candidate
from src.sources.job_boards import FEEDS


def public_https_url(value):
    if not isinstance(value, str) or len(value) > 3000:
        raise ValueError('Enter a public HTTPS careers or posting URL')
    try:
        parts = urlsplit(value.strip())
        host = parts.hostname or ''
        if (parts.scheme != 'https' or not host or '.' not in host or parts.username or parts.password
                or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host, re.I)
                or parts.port not in (None, 443) or host.endswith(('.local', '.localhost', '.internal'))):
            raise ValueError('Enter a public HTTPS URL without credentials or a custom port')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError('Use the public website domain, not an IP address')
    except (ValueError, TypeError) as exc:
        raise ValueError('Enter a public HTTPS website URL without credentials or a custom port') from exc
    return urlunsplit(('https', host.lower(), parts.path.rstrip('/') or '/', parts.query, ''))


def employer_from_url(company, url):
    if not isinstance(company, str) or not company.strip() or len(company) > 200:
        raise ValueError('Enter an employer name (200 characters or fewer)')
    url = public_https_url(url)
    parts = urlsplit(url)
    source = {'boards.greenhouse.io': 'greenhouse', 'job-boards.greenhouse.io': 'greenhouse',
              'jobs.ashbyhq.com': 'ashby'}.get(parts.hostname)
    if source:
        token = parts.path.strip('/').split('/')[0]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', token):
            raise ValueError('Paste the employer’s hosted board URL, including its board name')
        return 'boards', {'company': company.strip(), 'source': source, 'board_token': token, 'enabled': True}
    return 'career_sites', {'company': company.strip(), 'url': url, 'enabled': True}


def _entry_id(group, item):
    identity = item['source'] + ':' + item['board_token'] if group == 'boards' else item['url']
    return hashlib.sha256((group + ':' + identity).encode()).hexdigest()[:24]


def source_settings(candidate=None):
    selected = get_candidate(candidate)
    path = selected.directory / 'company_boards.json'
    raw = path.read_bytes()
    config = json.loads(raw)
    items = []
    search = selected.load('search_config.json')
    for group in ('boards', 'career_sites'):
        for item in config.get(group, []):
            automated = group == 'boards'
            source = item.get('source')
            url = (f'https://job-boards.greenhouse.io/{item["board_token"]}' if source == 'greenhouse'
                   else f'https://jobs.ashbyhq.com/{item["board_token"]}') if automated else item['url']
            permitted = not automated or search.get('discovery_sources', {}).get(source, False)
            items.append({'id': _entry_id(group, item), 'company': item['company'], 'url': url,
                          'enabled': item.get('enabled', True), 'mode': 'automatic' if automated else 'assisted',
                          'active': bool(item.get('enabled', True) and permitted), 'editable': True,
                          'source': source or 'career_site',
                          'description': ('Included in scheduled discovery; board access is checked when discovery runs.' if permitted
                                          else 'This adapter is disabled in the candidate’s search settings.') if automated
                          else 'Search this career site, then copy a posting into Add a posting. Not fetched on schedule.'})
    for source in search.get('public_job_boards', []):
        name, url, _ = FEEDS[source]
        items.append({'id': 'public:' + source, 'company': name, 'url': url, 'enabled': True,
                      'mode': 'automatic', 'active': True, 'editable': False, 'source': source,
                      'description': 'Public job-board feed included in scheduled discovery.'})
    return {'candidate_id': selected.candidate_id, 'version': hashlib.sha256(raw).hexdigest(), 'sources': items}


def update_employer(candidate, *, version, company=None, url=None, source_id=None, enabled=None):
    selected = get_candidate(candidate)
    path = selected.directory / 'company_boards.json'
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        raw = path.read_bytes()
        if not isinstance(version, str) or hashlib.sha256(raw).hexdigest() != version:
            raise ValueError('Source settings changed. Reload Sources and try again.')
        config = json.loads(raw)
        if source_id is not None:
            if type(enabled) is not bool:
                raise ValueError('Enabled must be true or false')
            found = False
            for group in ('boards', 'career_sites'):
                for item in config.get(group, []):
                    if _entry_id(group, item) == source_id:
                        item['enabled'] = enabled
                        found = True
            if not found:
                raise ValueError('Employer source not found for this candidate')
        else:
            group, item = employer_from_url(company, url)
            entries = config.setdefault(group, [])
            if any(_entry_id(group, entry) == _entry_id(group, item) for entry in entries):
                raise ValueError('This employer board is already saved; use its enable/pause control')
            entries.append(item)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as file:
                temporary = file.name
                json.dump(config, file, indent=2, ensure_ascii=False)
                file.write('\n')
            os.replace(temporary, path)
        finally:
            if temporary and Path(temporary).exists():
                Path(temporary).unlink()
    return source_settings(selected)
