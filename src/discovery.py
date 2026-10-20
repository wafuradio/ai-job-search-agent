"""Configurable free public-feed discovery. No AI evaluator or submission path."""
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import URLError

from src.fact_extractor import enrich_job_facts
from src.compensation_extractor import extract_compensation
from src.normalizer import normalize_greenhouse_job
from src.scout import is_us_job, load_scout_config
from src.screening import screen_job
from src.search_settings import load_search_settings
from src.candidates import get_candidate
from src.sources.greenhouse import fetch_greenhouse_jobs, fetch_greenhouse_job_dates
from src.sources.ashby import fetch_ashby_jobs
from src.sources.job_boards import FEEDS, fetch_job_board
from src.models import Job, Compensation

DEFAULT_BOARDS = get_candidate().directory / 'company_boards.json'


def load_boards(path=None, companies=None, *, candidate=None, allow_empty=False):
    selected = get_candidate(candidate)
    path = selected.directory / 'company_boards.json' if path is None else Path(path)
    with path.open() as file:
        config = json.load(file)
    boards = config.get('boards')
    if not isinstance(boards, list):
        raise ValueError('Company board configuration requires a boards list')
    result, seen = [], set()
    for board in boards:
        if not isinstance(board, dict) or any(not isinstance(board.get(k), str) or not board[k].strip()
                                             for k in ('company', 'source', 'board_token')):
            raise ValueError('Each board requires company, source, and board_token strings')
        if board['source'] not in ('greenhouse', 'ashby'):
            raise ValueError(f'Unsupported source: {board["source"]}')
        identity = (board['source'], board['board_token'])
        if identity in seen:
            raise ValueError('Duplicate board configuration')
        seen.add(identity)
        if board.get('enabled', True) and (not companies or board['company'].casefold() in {c.casefold() for c in companies}):
            result.append(board)
    if not result and not allow_empty:
        raise ValueError('No enabled boards match the selected companies')
    return result


def load_job_boards(*, candidate=None):
    selected = get_candidate(candidate)
    return selected.load('search_config.json').get('public_job_boards', [])


def load_import_jobs(path):
    """Validate a full local import before any persistence; never fetch its URLs."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return parse_import_jobs(data)


def parse_import_jobs(data):
    """Shared validation for copied postings from the CLI and local dashboard."""
    if not isinstance(data, dict) or not isinstance(data.get('jobs'), list):
        raise ValueError('Local import requires a jobs list')
    jobs = []
    for raw in data['jobs']:
        from urllib.parse import urlsplit
        required = ('company', 'title', 'job_url', 'raw_description')
        optional = ('location_text', 'employment_type', 'remote_status')
        if (not isinstance(raw, dict) or any(not isinstance(raw.get(key), str) or not raw[key].strip() for key in required)
                or any(raw.get(key) is not None and not isinstance(raw[key], str) for key in optional)):
            raise ValueError('Each imported job requires company, title, job_url, and raw_description strings')
        url = urlsplit(raw['job_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password:
            raise ValueError('Imported job URLs must be public HTTPS links without credentials')
        values = {key: raw[key].strip() for key in required}
        if any(len(values[key]) > (250000 if key == 'raw_description' else 3000) for key in required):
            raise ValueError('Posting fields are too long; paste one posting at a time')
        values.update({key: raw.get(key) for key in optional})
        salary = raw.get('compensation_text')
        if salary is not None and not isinstance(salary, str):
            raise ValueError('compensation_text must be a string')
        origin = raw.get('copied_from', 'Other')
        if origin not in ('Other', 'Employer site', 'LinkedIn', 'Indeed', 'Email alert'):
            raise ValueError('Choose a supported copied-from source')
        jobs.append(Job(**values, source='Manual discovery' if origin == 'Other' else 'Copied from ' + origin,
                        compensation=Compensation(compensation_text=salary)))
    return jobs


@dataclass
class DiscoveryRun:
    retrieved: int = 0
    saved_ids: set = field(default_factory=set)
    new_ids: set = field(default_factory=set)
    accepted_ids: set = field(default_factory=set)
    filtered: Counter = field(default_factory=Counter)
    errors: list = field(default_factory=list)
    boards: list = field(default_factory=list)


def discover_boards(store, boards, *, enrich_dates=False, job_boards=(), imported_jobs=()):
    selected = store.candidate
    search, profile = load_search_settings(candidate=selected)
    config = load_scout_config(candidate=selected)
    enabled_sources = search.get('discovery_sources', {})
    # Validate every board before any fetch or mutation.
    for board in boards:
        if board['source'] not in ('greenhouse', 'ashby'):
            raise ValueError(f'Unsupported source: {board["source"]}')
    for source in job_boards:
        if source not in FEEDS:
            raise ValueError(f'Unsupported public job board: {source}')
    run = DiscoveryRun()
    existing_ids = {row[0] for row in store.connection.execute('SELECT id FROM jobs')}
    for board in boards:
        source, company = board['source'], board['company']
        if not enabled_sources.get(source, False):
            run.errors.append(f'{company}: {source} is disabled in search_config.json')
            continue
        try:
            if source == 'greenhouse':
                raw_jobs = fetch_greenhouse_jobs(board['board_token'])
                jobs = [normalize_greenhouse_job(
                    item, company, 'United States' if is_us_job(item.location) else None)
                    for item in raw_jobs]
            else:
                jobs = fetch_ashby_jobs(board['board_token'], company)
        except (URLError, TimeoutError, OSError, ValueError, TypeError, KeyError) as exc:
            run.errors.append(f'{company} ({source}): {exc}')
            continue
        run.boards.append({'company': company, 'source': source, 'retrieved': len(jobs)})
        run.retrieved += len(jobs)
        _save_jobs(store, jobs, run, existing_ids, config, search, profile,
                   enrich_dates=enrich_dates, board=board)
    for source in job_boards:
        try:
            jobs = fetch_job_board(source, selected.root / 'data/discovery_cache')
        except (URLError, TimeoutError, OSError, ValueError, TypeError, KeyError) as exc:
            run.errors.append(f'{FEEDS[source][0]}: {exc}')
            continue
        run.boards.append({'company': FEEDS[source][0], 'source': source, 'retrieved': len(jobs)})
        run.retrieved += len(jobs)
        _save_jobs(store, jobs, run, existing_ids, config, search, profile)
    if imported_jobs:
        run.retrieved += len(imported_jobs)
        run.boards.append({'company': 'Local import', 'source': 'manual', 'retrieved': len(imported_jobs)})
        _save_jobs(store, imported_jobs, run, existing_ids, config, search, profile)
    return run


def _save_jobs(store, jobs, run, existing_ids, config, search, profile, *, enrich_dates=False, board=None):
    selected = store.candidate
    for job in jobs:
        enrich_job_facts(job)
        extract_compensation(job)
        result = screen_job(job, config, search, profile, candidate=selected)
        # Titles alone cannot establish identity across sites. Flag likely repeats
        # for human comparison rather than merging distinct vacancies or approvals.
        related = store.connection.execute(
            'SELECT id,job_json FROM jobs WHERE company_key=? AND job_url<>?',
            (job.company.strip().casefold(), job.job_url.strip().rstrip('/'))).fetchall()
        duplicate_ids = [str(row['id']) for row in related
                         if json.loads(row['job_json'])['title'].strip().casefold() == job.title.strip().casefold()]
        if duplicate_ids:
            result.flags.append('Possible related or duplicate posting: compare saved job(s) #' + ', #'.join(duplicate_ids) + '; approvals are never shared.')
        if enrich_dates and board and board['source'] == 'greenhouse' and result.accepted and not job.posted_date:
            try:
                dates = fetch_greenhouse_job_dates(board['board_token'], job.external_job_id)
                if dates.get('first_published'):
                    job.posted_date = dates['first_published']
                    job.posted_date_kind = 'first_published'
                job.source_updated_at = dates.get('updated_at') or job.source_updated_at
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                run.errors.append(f'{board["company"]} date lookup {job.external_job_id}: {exc}')
        # Gatekeeper stays distinct from discovery exclusions and human decisions.
        from src.gatekeeper import GatekeeperResult
        job_id = store.save_job(job, GatekeeperResult(**result.gatekeeper), result.score)
        store.save_discovery_screening(job_id, result)
        run.saved_ids.add(job_id)
        if job_id not in existing_ids:
            run.new_ids.add(job_id)
        if result.accepted:
            run.accepted_ids.add(job_id)
        else:
            run.filtered[result.reasons[0]] += 1
