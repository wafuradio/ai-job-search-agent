"""Read-only adapter for Ashby's public job postings API (no API key)."""
import json
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from src.models import Job, Compensation
from src.normalizer import clean_html

API_BASE = 'https://api.ashbyhq.com/posting-api/job-board'


def build_ashby_url(board_token):
    if not board_token or not board_token.strip():
        raise ValueError('Ashby board token cannot be empty')
    return f'{API_BASE}/{quote(board_token.strip(), safe="")}?includeCompensation=true'


def parse_ashby_jobs(payload, company):
    raw_jobs = payload.get('jobs')
    if not isinstance(raw_jobs, list):
        raise ValueError('Ashby response must contain a jobs list')
    if not company.strip():
        raise ValueError('Company is required')
    jobs = []
    for raw in raw_jobs:
        if not isinstance(raw, dict) or raw.get('isListed') is False:
            continue
        title, url = raw.get('title'), raw.get('jobUrl')
        if not title or not url:
            continue
        locations = [raw.get('location', '')]
        secondary = raw.get('secondaryLocations') or []
        locations += [item.get('location', '') for item in secondary]
        address = (raw.get('address') or {}).get('postalAddress') or {}
        countries = [address.get('addressCountry')]
        countries += [(item.get('address') or {}).get('addressCountry') for item in secondary]
        country = 'United States' if any(c in ('US', 'USA', 'United States') for c in countries) else address.get('addressCountry')
        compensation_data = raw.get('compensation') or {}
        comp = Compensation(compensation_text=compensation_data.get('compensationTierSummary')
                            or compensation_data.get('scrapeableCompensationSalarySummary'))
        # Numeric values are meaningful only with an explicit USD annual salary unit.
        for component in compensation_data.get('summaryComponents') or []:
            if (component.get('compensationType') == 'Salary'
                    and component.get('currencyCode') == 'USD'
                    and component.get('interval') == '1 YEAR'):
                minimum, maximum = component.get('minValue'), component.get('maxValue')
                if (isinstance(minimum, (int, float)) and not isinstance(minimum, bool)
                        and isinstance(maximum, (int, float)) and not isinstance(maximum, bool)
                        and 0 <= minimum <= maximum):
                    comp.published_min, comp.published_max = int(minimum), int(maximum)
                    comp.compensation_type = 'Uncertain'
                    comp.compensation_text = comp.compensation_text or f'Published annual USD salary: {minimum} - {maximum}'
                    break
        work_model = {'Remote': 'Fully Remote', 'Hybrid': 'Hybrid', 'OnSite': 'On-site'}.get(raw.get('workplaceType'))
        if work_model is None and raw.get('isRemote') is True:
            work_model = 'Fully Remote'
        employment = {'FullTime': 'Full-time', 'PartTime': 'Part-time', 'Intern': 'Internship',
                      'Contract': 'Contract', 'Temporary': 'Temporary'}.get(raw.get('employmentType'))
        jobs.append(Job(
            company=company.strip(), title=title.strip(), job_url=url.strip(), source='Ashby',
            external_job_id=urlsplit(url).path.rstrip('/').split('/')[-1],
            location_text=' | '.join(dict.fromkeys(loc for loc in locations if loc)) or None,
            country=country, department=raw.get('department'), employment_type=employment,
            remote_status=work_model, posted_date=raw.get('publishedAt'),
            posted_date_kind='last_published' if raw.get('publishedAt') else None, compensation=comp,
            raw_description=raw.get('descriptionPlain') or clean_html(raw.get('descriptionHtml', '')) or None,
        ))
    return jobs


def fetch_ashby_jobs(board_token, company, timeout=20):
    request = Request(build_ashby_url(board_token), headers={
        'User-Agent': 'ai-job-search-agent/1.0', 'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return parse_ashby_jobs(payload, company)
