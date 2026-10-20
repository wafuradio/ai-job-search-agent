import json
from io import BytesIO
import pytest
from src.sources import ashby


def posting(**overrides):
    result = {'title': 'AI Enablement Lead', 'jobUrl': 'https://jobs.ashbyhq.com/example/abc',
              'location': 'Remote', 'address': {'postalAddress': {'addressCountry': 'USA'}},
              'workplaceType': 'Remote', 'employmentType': 'FullTime', 'isListed': True,
              'descriptionHtml': '<p>Lead AI adoption.</p>', 'publishedAt': '2026-10-20T00:00:00Z'}
    result.update(overrides)
    return result


def test_public_endpoint_quotes_token_and_requests_compensation():
    assert ashby.build_ashby_url('company/other') == 'https://api.ashbyhq.com/posting-api/job-board/company%2Fother?includeCompensation=true'
    with pytest.raises(ValueError):
        ashby.build_ashby_url(' ')


def test_maps_facts_and_skips_unlisted_or_incomplete():
    jobs = ashby.parse_ashby_jobs({'jobs': [posting(), posting(isListed=False), {'title': 'Incomplete'}]}, 'Example')
    assert len(jobs) == 1
    job = jobs[0]
    assert job.external_job_id == 'abc'
    assert job.raw_description == 'Lead AI adoption.'
    assert job.remote_status == 'Fully Remote' and job.country == 'United States'
    assert job.employment_type == 'Full-time'
    assert job.posted_date == '2026-10-20T00:00:00Z'


def test_secondary_location_eligibility_and_unknown_workplace():
    raw = posting(address={}, workplaceType=None, isRemote=False,
                  secondaryLocations=[{'location': 'Boston, MA', 'address': {'addressCountry': 'USA'}}])
    job = ashby.parse_ashby_jobs({'jobs': [raw]}, 'Example')[0]
    assert job.country == 'United States'
    assert job.location_text == 'Remote | Boston, MA'
    assert job.remote_status is None


def test_only_explicit_annual_usd_salary_numeric_range_is_used():
    component = {'compensationType': 'Salary', 'currencyCode': 'USD', 'interval': '1 YEAR', 'minValue': 180000, 'maxValue': 240000}
    raw = posting(compensation={'summaryComponents': [component], 'compensationTierSummary': '$180K–$240K plus equity'})
    comp = ashby.parse_ashby_jobs({'jobs': [raw]}, 'Example')[0].compensation
    assert (comp.published_min, comp.published_max) == (180000, 240000)
    assert comp.base_min is None and comp.compensation_type == 'Uncertain'
    for overrides in [{'currencyCode': 'EUR'}, {'interval': '1 HOUR'}, {'compensationType': 'Bonus'}, {'minValue': 300000}]:
        raw['compensation']['summaryComponents'] = [{**component, **overrides}]
        assert ashby.parse_ashby_jobs({'jobs': [raw]}, 'Example')[0].compensation.published_min is None


def test_fetch_uses_only_public_get_with_timeout(monkeypatch):
    calls = []
    def fake_open(request, timeout):
        calls.append((request, timeout))
        return BytesIO(json.dumps({'jobs': [posting()]}).encode())
    monkeypatch.setattr(ashby, 'urlopen', fake_open)
    assert len(ashby.fetch_ashby_jobs('example', 'Example')) == 1
    assert calls[0][0].get_method() == 'GET' and calls[0][1] == 20
    assert 'Authorization' not in calls[0][0].headers


def test_malformed_response_fails_clearly():
    with pytest.raises(ValueError):
        ashby.parse_ashby_jobs({}, 'Example')
