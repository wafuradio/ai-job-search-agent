"""Free public feeds shared by candidates; no candidate data sent to sources."""
import json
import os
import tempfile
import time
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from src.models import Job, Compensation
from src.normalizer import clean_html

FEEDS = {
    'remotive': ('Remotive', 'https://remotive.com/api/remote-jobs', 6 * 3600),
    'weworkremotely': ('We Work Remotely', 'https://weworkremotely.com/remote-jobs.rss', 3600),
}


def _valid_url(value, domain):
    if not isinstance(value, str):
        return False
    try:
        parts = urlsplit(value)
        return parts.scheme == 'https' and parts.hostname == domain and not parts.username
    except ValueError:
        return False


def parse_remotive_jobs(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('jobs'), list):
        raise ValueError('Remotive response requires a jobs list')
    jobs = []
    for raw in payload['jobs']:
        if (not isinstance(raw, dict) or not raw.get('id') or not raw.get('title')
                or not raw.get('company_name') or not _valid_url(raw.get('url'), 'remotive.com')):
            continue
        jobs.append(Job(
            company=raw['company_name'].strip(), title=raw['title'].strip(),
            source='Remotive', external_job_id=str(raw['id']), job_url=raw['url'],
            location_text=raw.get('candidate_required_location') or None,
            remote_status='Fully Remote', employment_type=(raw.get('job_type') or '').replace('_', '-') or None,
            department=raw.get('category'), raw_description=clean_html(raw.get('description') or '') or None,
            compensation=Compensation(compensation_text=raw.get('salary') or None),
            posted_date=raw.get('publication_date'),
            posted_date_kind='board_published' if raw.get('publication_date') else None,
        ))
    return jobs


def parse_wwr_jobs(data):
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise ValueError('Invalid We Work Remotely RSS') from exc
    channel = root.find('channel')
    if channel is None:
        raise ValueError('We Work Remotely RSS requires a channel')
    jobs = []
    for item in channel.findall('item'):
        company, separator, title = (item.findtext('title') or '').partition(':')
        url = (item.findtext('link') or '').strip()
        if not separator or not company.strip() or not title.strip() or not _valid_url(url, 'weworkremotely.com'):
            continue
        published = None
        try:
            value = item.findtext('pubDate')
            if value:
                published = parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, OverflowError):
            pass
        jobs.append(Job(
            company=company.strip(), title=title.strip(), source='We Work Remotely',
            external_job_id=urlsplit(url).path.rstrip('/'), job_url=url,
            # RSS country/state can describe headquarters. Only region is used
            # for candidate eligibility; full description remains available.
            location_text=(item.findtext('region') or '').strip() or None,
            remote_status='Fully Remote', employment_type=item.findtext('type') or None,
            department=item.findtext('category') or None,
            raw_description=clean_html(item.findtext('description') or '') or None,
            posted_date=published, posted_date_kind='board_published' if published else None,
        ))
    return jobs


def parse_job_board(source, data):
    if source == 'remotive':
        return parse_remotive_jobs(json.loads(data))
    if source == 'weworkremotely':
        return parse_wwr_jobs(data)
    raise ValueError(f'Unsupported public job board: {source}')


def fetch_job_board(source, cache_dir, timeout=30):
    """Cache public responses across candidates to limit requests; no stale fallback."""
    if source not in FEEDS:
        raise ValueError(f'Unsupported public job board: {source}')
    _, url, ttl = FEEDS[source]
    cache = Path(cache_dir) / (source + '.feed')
    if cache.is_file() and 0 <= time.time() - cache.stat().st_mtime < ttl:
        return parse_job_board(source, cache.read_bytes())
    request = Request(url, headers={'User-Agent': 'ai-job-search-agent/1.0',
                                   'Accept': 'application/json, application/rss+xml'})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise ValueError('Public feed exceeds 10 MiB limit')
    jobs = parse_job_board(source, data)
    cache.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=cache.parent, delete=False) as file:
        file.write(data)
        temporary = file.name
    os.replace(temporary, cache)
    return jobs
