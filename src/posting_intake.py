"""Preview and save copied postings without fetching URLs or using AI."""
from dataclasses import asdict
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode
import re

from src.discovery import parse_import_jobs
from src.fact_extractor import enrich_job_facts
from src.compensation_extractor import extract_compensation
from src.gatekeeper import GatekeeperResult
from src.screening import screen_job
from src.source_manager import public_https_url


def copied_job(data):
    jobs = parse_import_jobs({'jobs': [data]})
    job = jobs[0]
    job.job_url = public_https_url(job.job_url)
    parts = urlsplit(job.job_url)
    if parts.hostname in ('linkedin.com', 'www.linkedin.com') and parts.path.startswith('/jobs/view/'):
        match = re.search(r'(\d+)/?$', parts.path)
        if match:
            job.job_url = 'https://www.linkedin.com/jobs/view/' + match.group(1)
    elif parts.hostname in ('indeed.com', 'www.indeed.com'):
        query = parse_qs(parts.query)
        identity = query.get('jk') or query.get('vjk')
        if identity and re.fullmatch(r'[A-Za-z0-9]+', identity[0]):
            job.job_url = 'https://www.indeed.com/viewjob?' + urlencode({'jk': identity[0]})
    else:
        # Keep identity-bearing query values, dropping common tracking parameters.
        query = parse_qs(parts.query, keep_blank_values=True)
        query = {key: value for key, value in query.items() if not key.lower().startswith('utm_')}
        job.job_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ''))
    enrich_job_facts(job)
    extract_compensation(job)
    return job


def preview_posting(store, data):
    job = copied_job(data)
    result = screen_copied_job(store, job)
    existing = store.connection.execute('SELECT id,revision,updated_at,status FROM jobs WHERE job_url=?',
                                         (job.job_url.rstrip('/'),)).fetchone()
    return {'job': asdict(job) | {'discovered_at': job.discovered_at.isoformat()}, 'screening': asdict(result),
            'existing': dict(existing) if existing else None}


def screen_copied_job(store, job):
    result = screen_job(job, candidate=store.candidate)
    related = store.connection.execute('SELECT id,job_json FROM jobs WHERE company_key=? AND job_url<>?',
                                       (job.company.strip().casefold(), job.job_url.rstrip('/'))).fetchall()
    import json
    matches = [str(row['id']) for row in related if json.loads(row['job_json'])['title'].strip().casefold() == job.title.strip().casefold()]
    if matches:
        result.flags.append('Possible related or duplicate posting: compare saved job(s) #' + ', #'.join(matches) + '; approvals are never shared.')
    return result


def save_copied_posting(store, data, preview):
    if not isinstance(preview, dict) or type(preview.get('is_new')) is not bool:
        raise ValueError('Preview this posting before saving')
    if not preview['is_new'] and (type(preview.get('revision')) is not int or not isinstance(preview.get('updated_at'), str)):
        raise ValueError('Reload the preview before updating this posting')
    job = copied_job(data)
    result = screen_copied_job(store, job)
    job_id = store.save_job(job, GatekeeperResult(**result.gatekeeper), result.score,
                            expected_new=preview['is_new'], expected_revision=preview.get('revision'),
                            expected_updated_at=preview.get('updated_at'))
    store.save_discovery_screening(job_id, result)
    row = store.get_job(job_id)
    return {'saved': True, 'job_id': job_id, 'accepted': result.accepted, 'status': row['status'],
            'needs_reevaluation': row['needs_reevaluation'], 'reasons': result.reasons}
