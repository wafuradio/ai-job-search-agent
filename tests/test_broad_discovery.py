"""Offline public-feed, candidate-isolation, search-plan and import checks."""
import json
import os
from io import BytesIO
from unittest.mock import Mock
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from src import discovery
from src.candidates import get_candidate
from src.review_store import ReviewStore
from src.review_display import posting_date_lines, shortlist_records, write_html_report
from src.screening import screen_job
from src.search_plan import search_links, write_search_plan
from src.sources import job_boards
from src.sources.job_boards import parse_remotive_jobs, parse_wwr_jobs, fetch_job_board
from run_discovery import main
from test_candidates import candidate_root, change_json


def payload(**updates):
    job = {'id': 12, 'title': 'AI Enablement Lead', 'company_name': 'Example',
           'url': 'https://remotive.com/remote-jobs/example-12', 'candidate_required_location': 'United States',
           'description': '<p>Lead AI adoption and workflow automation.</p>',
           'salary': 'EUR 90,000 – 120,000', 'publication_date': '2026-10-01T12:00:00', 'job_type': 'full_time'}
    job.update(updates)
    return {'jobs': [job]}


def rss(region='Anywhere in the World', published='Mon, 19 Oct 2026 12:00:00 +0000'):
    return f'''<rss><channel><item><title>Example: AI Enablement Lead</title>
    <link>https://weworkremotely.com/remote-jobs/example-lead</link><country>United States</country>
    <region>{region}</region><type>Full-Time</type><pubDate>{published}</pubDate>
    <description>&lt;p&gt;Lead AI adoption and workflow automation.&lt;/p&gt;</description>
    </item></channel></rss>'''.encode()


def test_remotive_normalization_retains_attribution_salary_and_date_provenance():
    job = parse_remotive_jobs(payload())[0]
    assert job.company == 'Example' and job.source == 'Remotive'
    assert job.remote_status == 'Fully Remote' and job.country is None
    assert job.compensation.compensation_text.startswith('EUR')
    assert job.compensation.base_min is None and job.compensation.published_min is None
    assert job.raw_description == 'Lead AI adoption and workflow automation.'
    assert job.posted_date_kind == 'board_published'
    assert parse_remotive_jobs(payload(url='javascript:alert(1)')) == []
    assert parse_remotive_jobs(payload(url='https://remotive.com.evil.test/job')) == []
    with pytest.raises(ValueError):
        parse_remotive_jobs({'jobs': {}})


def test_wwr_region_is_not_headquarters_country_and_dates_are_board_dates():
    job = parse_wwr_jobs(rss('Europe'))[0]
    assert job.company == 'Example' and job.title == 'AI Enablement Lead'
    assert job.location_text == 'Europe' and job.country is None
    assert job.posted_date == '2026-10-19T12:00:00+00:00'
    assert job.posted_date_kind == 'board_published'
    assert not screen_job(job).accepted
    assert parse_wwr_jobs(rss(published='invalid'))[0].posted_date is None
    assert not screen_job(parse_wwr_jobs(rss(region=''))[0]).accepted
    with pytest.raises(ValueError):
        parse_wwr_jobs(b'broken xml')


@pytest.mark.parametrize('location', ['Worldwide', 'Anywhere in the World'])
def test_explicit_worldwide_is_reviewable_but_flagged(location):
    job = parse_remotive_jobs(payload(candidate_required_location=location))[0]
    result = screen_job(job)
    assert result.accepted
    assert any('worldwide' in flag for flag in result.flags)
    assert job.country is None


def test_remote_alone_does_not_establish_us_eligibility():
    assert not screen_job(parse_remotive_jobs(payload(candidate_required_location='Remote'))[0]).accepted


def test_public_cache_reused_across_candidates_and_refresh_failure_not_hidden(tmp_path, monkeypatch):
    request = Mock(return_value=BytesIO(json.dumps(payload()).encode()))
    monkeypatch.setattr(job_boards, 'urlopen', request)
    assert fetch_job_board('remotive', tmp_path)[0].source == 'Remotive'
    assert fetch_job_board('remotive', tmp_path)[0].title == 'AI Enablement Lead'
    assert request.call_count == 1
    assert request.call_args.args[0].full_url == 'https://remotive.com/api/remote-jobs'
    os.utime(tmp_path / 'remotive.feed', (1, 1))
    request.side_effect = URLError('offline')
    with pytest.raises(URLError):
        fetch_job_board('remotive', tmp_path)


def test_public_feed_pipeline_deduplicates_preserves_approval_and_guards_material_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, 'fetch_job_board', lambda *args: parse_remotive_jobs(payload()))
    with ReviewStore(tmp_path / 'review.db') as store:
        first = discovery.discover_boards(store, [], job_boards=['remotive'])
        assert first.retrieved == len(first.saved_ids) == len(first.accepted_ids) == 1
        store.approve_job(1, confirmation='APPROVE 1', revision=1)
        assert not discovery.discover_boards(store, [], job_boards=['remotive']).new_ids
        store.require_job_approval(1)
        monkeypatch.setattr(discovery, 'fetch_job_board', lambda *args: parse_remotive_jobs(payload(description='Changed responsibilities.')))
        discovery.discover_boards(store, [], job_boards=['remotive'])
        row = store.get_job(1)
        assert row['status'] == 'New' and row['needs_reevaluation']
        assert any(event['event'] == 'human_decision' and event['details'].get('status') == 'Approved to Apply' for event in row['history'])
        assert not row['evaluations']


def test_failed_public_source_does_not_block_other_feed(tmp_path, monkeypatch):
    def fetch(source, _):
        if source == 'remotive':
            raise URLError('test failure')
        return parse_wwr_jobs(rss())
    monkeypatch.setattr(discovery, 'fetch_job_board', fetch)
    with ReviewStore(tmp_path / 'review.db') as store:
        run = discovery.discover_boards(store, [], job_boards=['remotive', 'weworkremotely'])
        assert run.retrieved == 1 and len(run.errors) == 1
        with pytest.raises(ValueError):
            discovery.discover_boards(store, [], job_boards=['unknown'])


def test_feed_selection_and_screening_are_candidate_specific(candidate_root, monkeypatch):
    change_json(candidate_root / 'profiles/alex', 'search_config.json', lambda data: data.update(public_job_boards=['remotive']))
    sam = get_candidate('sam', root=candidate_root)
    alex = get_candidate('alex', root=candidate_root)
    assert discovery.load_job_boards(candidate=sam) == []
    assert discovery.load_job_boards(candidate=alex) == ['remotive']
    monkeypatch.setattr(discovery, 'fetch_job_board', lambda *args: parse_remotive_jobs(payload(title='Data Engineer')))
    with ReviewStore(candidate=sam) as store:
        run = discovery.discover_boards(store, [], job_boards=['remotive'])
        assert not run.accepted_ids
        store.set_status(1, 'Interested')
    with ReviewStore(candidate=alex) as store:
        run = discovery.discover_boards(store, [], job_boards=['remotive'])
        assert run.accepted_ids == {1} and store.get_job(1)['status'] == 'New'


def test_search_plan_uses_only_selected_candidate_and_no_network(candidate_root, tmp_path):
    sam = get_candidate('sam', root=candidate_root)
    links = search_links(sam)
    assert len(links) == 4
    assert all('Junior Account Executive' in link['query'] for link in links)
    assert not any('Data Engineer' in link['query'] or 'AI Transformation' in link['query'] for link in links)
    query = parse_qs(urlsplit(links[0]['url']).query)['q'][0]
    assert query == links[0]['query']
    report = write_search_plan(tmp_path / 'searches.html', candidate=sam).read_text()
    assert 'Sam' in report and 'not retrieved jobs' in report
    assert 'Example Candidate' not in report


def test_search_plan_only_does_not_open_database(tmp_path, monkeypatch):
    import run_discovery
    monkeypatch.setattr(run_discovery, 'ReviewStore', lambda *args, **kwargs: pytest.fail('Database opened'))
    assert main(['--search-plan-only', '--search-html', str(tmp_path / 'plan.html')]) == 0


def test_local_import_is_offline_repeatable_and_uses_same_screening(tmp_path):
    data = {'company': 'Startup', 'title': 'AI Enablement Lead', 'job_url': 'https://startup.test/jobs/1',
            'raw_description': 'Lead AI adoption and workflow automation.', 'location_text': 'United States', 'remote_status': 'Remote'}
    path = tmp_path / 'import.json'
    path.write_text(json.dumps({'jobs': [data]}))
    args = ['--import-jobs', str(path), '--db', str(tmp_path / 'review.db')]
    assert main(args) == 0
    with ReviewStore(tmp_path / 'review.db') as store:
        store.set_status(1, 'Interested', 'Keep')
    assert main(args) == 0
    with ReviewStore(tmp_path / 'review.db') as store:
        assert len(store.list_jobs()) == 1 and store.get_job(1)['status'] == 'Interested'
        assert not store.get_job(1)['evaluations']
    path.write_text(json.dumps({'jobs': [data, {'title': 'Incomplete'}]}))
    with pytest.raises(ValueError):
        discovery.load_import_jobs(path)


def test_board_report_attribution_and_date_label(tmp_path):
    with ReviewStore(tmp_path / 'review.db') as store:
        discovery.discover_boards(store, [], imported_jobs=parse_remotive_jobs(payload()))
        rows = shortlist_records(store)
        report = write_html_report(rows, tmp_path / 'report.html').read_text()
        assert 'View on Remotive' in report and 'https://remotive.com/remote-jobs/example-12' in report
        assert 'Published on job board' in '\n'.join(posting_date_lines(rows[0]))
        assert 'employer posting date unconfirmed' in report


@pytest.mark.parametrize('value', [['unknown'], ['remotive', 'remotive'], 'remotive'])
def test_invalid_candidate_feeds_fail_validation(candidate_root, value):
    change_json(candidate_root / 'profiles/sam', 'search_config.json', lambda data: data.update(public_job_boards=value))
    with pytest.raises(ValueError, match='public_job_boards'):
        get_candidate('sam', root=candidate_root)


def test_public_boards_only_cli_does_not_fetch_employers(tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, 'fetch_greenhouse_jobs', lambda *args: pytest.fail('Employer fetched'))
    monkeypatch.setattr(discovery, 'fetch_ashby_jobs', lambda *args: pytest.fail('Employer fetched'))
    monkeypatch.setattr(discovery, 'fetch_job_board', lambda *args: parse_remotive_jobs(payload()))
    assert main(['--job-boards-only', '--db', str(tmp_path / 'review.db')]) == 0


def test_candidate_without_company_list_can_use_public_boards(candidate_root, capsys):
    from candidate_profiles import main as profiles_main
    directory = candidate_root / 'profiles/sam'
    change_json(directory, 'company_boards.json', lambda data: data.update(boards=[]))
    change_json(directory, 'search_config.json', lambda data: data.update(public_job_boards=['remotive']))
    profiles_main(['validate', '--candidate', 'sam'], root=candidate_root)
    assert 'Valid: Sam' in capsys.readouterr().out


def test_same_title_on_different_sites_is_flagged_without_sharing_approval(tmp_path, monkeypatch):
    def fetch(source, _):
        return parse_remotive_jobs(payload()) if source == 'remotive' else parse_wwr_jobs(rss())
    monkeypatch.setattr(discovery, 'fetch_job_board', fetch)
    with ReviewStore(tmp_path / 'review.db') as store:
        discovery.discover_boards(store, [], job_boards=['remotive'])
        store.approve_job(1, confirmation='APPROVE 1', revision=1)
        discovery.discover_boards(store, [], job_boards=['weworkremotely'])
        assert store.get_job(2)['status'] == 'New'
        rows = list(store.connection.execute('SELECT result_json FROM discovery_results WHERE job_id=2'))
        assert 'Possible related or duplicate posting' in rows[0][0]
