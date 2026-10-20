"""Synthetic candidate source editing and offline posting intake."""
from dataclasses import replace
from types import SimpleNamespace
import json

import pytest

from src.candidates import get_candidate
from src.discovery import load_boards
from src.models import Job
from src.review_store import ReviewStore
from src.source_manager import employer_from_url, source_settings, update_employer
from src.posting_intake import preview_posting, save_copied_posting, copied_job
from src.search_plan import search_links
from test_candidates import candidate_root
from test_dashboard import call


@pytest.fixture
def selected(candidate_root):
    return get_candidate('alex', root=candidate_root)


def posting(**changes):
    data = {'company': 'Synthetic Employer', 'title': 'Data Engineer',
            'job_url': 'https://example.test/job/123?utm_source=alert', 'location_text': 'United States',
            'raw_description': 'Build data pipelines and reliable databases.', 'copied_from': 'Email alert'}
    return data | changes


def test_adds_automatic_board_for_selected_candidate_only(selected, candidate_root):
    sam = get_candidate('sam', root=candidate_root)
    before = (sam.directory / 'company_boards.json').read_bytes()
    result = update_employer(selected, version=source_settings(selected)['version'], company='New Employer',
                              url='https://job-boards.greenhouse.io/new-employer/jobs/123')
    assert result['sources'][-1]['mode'] == 'automatic'
    assert any(board['board_token'] == 'new-employer' for board in load_boards(candidate=selected))
    assert (sam.directory / 'company_boards.json').read_bytes() == before
    assert not selected.database_path.exists()


def test_arbitrary_employer_is_assisted_and_search_uses_candidate_roles(selected):
    result = update_employer(selected, version=source_settings(selected)['version'], company='Example Employer',
                              url='https://careers.example.test/openings')
    site = result['sources'][-1]
    assert site['mode'] == 'assisted'
    links = [link for link in search_links(selected) if link['group'] == 'Example Employer careers']
    assert links and all('Data Engineer' in link['query'] for link in links)
    assert 'careers.example.test/openings' in links[0]['query']
    update_employer(selected, version=result['version'], source_id=site['id'], enabled=False)
    assert not any(link['group'] == 'Example Employer careers' for link in search_links(selected))


def test_sources_deduplicate_and_reject_stale_updates(selected):
    before = source_settings(selected)
    after = update_employer(selected, version=before['version'], company='A', url='https://jobs.ashbyhq.com/example')
    with pytest.raises(ValueError, match='changed'):
        update_employer(selected, version=before['version'], company='B', url='https://other.test/careers')
    with pytest.raises(ValueError, match='already saved'):
        update_employer(selected, version=after['version'], company='Alias', url='https://jobs.ashbyhq.com/example/some-job')
    assert source_settings(selected) == after


@pytest.mark.parametrize('url', ['http://example.com/jobs', 'https://127.0.0.1/jobs', 'https://localhost/jobs',
                                 'https://user:secret@example.com/jobs', 'https://example.com:9000/jobs',
                                 'javascript:alert(1)', 'https://private.local/jobs', 'https://bad host.com/jobs'])
def test_invalid_source_urls_rejected_without_writes(selected, url):
    before = source_settings(selected)
    with pytest.raises(ValueError):
        update_employer(selected, version=before['version'], company='Bad', url=url)
    assert source_settings(selected) == before


def test_host_spoof_is_never_an_automatic_source():
    group, _ = employer_from_url('Test', 'https://jobs.ashbyhq.com.evil.test/board')
    assert group == 'career_sites'


def test_preview_does_not_save_and_save_applies_candidate_screening(selected):
    with ReviewStore(candidate=selected) as store:
        preview = preview_posting(store, posting())
        assert preview['existing'] is None and not store.list_jobs()
        result = save_copied_posting(store, posting(), {'is_new': True})
        assert result['accepted'] and result['status'] == 'New'
        job = store.get_job(result['job_id'])
        assert job['job']['source'] == 'Copied from Email alert'
        assert job['job']['job_url'] == 'https://example.test/job/123'
        assert not job['evaluations']
        with pytest.raises(PermissionError):
            store.require_submission_approval(result['job_id'], materials_digest='not-approved')


def test_reimport_preserves_rejection_notes_and_history(selected):
    with ReviewStore(candidate=selected) as store:
        save_copied_posting(store, posting(), {'is_new': True})
        store.set_status(1, 'Rejected', 'Not for this candidate')
        preview = preview_posting(store, posting())['existing']
        result = save_copied_posting(store, posting(), {'is_new': False, **preview})
        assert result['status'] == 'Rejected' and len(store.list_jobs()) == 1
        assert any(event['details'].get('notes') == 'Not for this candidate' for event in store.get_job(1)['history'])


def test_material_reimport_revokes_approval_and_stale_preview_is_rejected(selected):
    with ReviewStore(candidate=selected) as store:
        save_copied_posting(store, posting(), {'is_new': True})
        store.approve_job(1, confirmation='APPROVE 1', revision=1)
        preview = preview_posting(store, posting())['existing']
        expected = {'is_new': False, **preview}
        result = save_copied_posting(store, posting(raw_description='Changed responsibilities and requirements.'), expected)
        assert result['needs_reevaluation'] and result['status'] == 'New'
        with pytest.raises(ValueError, match='changed'):
            save_copied_posting(store, posting(), expected)
        assert any(event['details'].get('status') == 'Approved to Apply' for event in store.get_job(1)['history'])


def test_new_preview_cannot_overwrite_concurrently_saved_job(selected):
    with ReviewStore(candidate=selected) as store:
        save_copied_posting(store, posting(), {'is_new': True})
        with pytest.raises(ValueError, match='since your preview'):
            save_copied_posting(store, posting(raw_description='Other version'), {'is_new': True})
        assert store.get_job(1)['revision'] == 1


def test_platform_tracking_links_use_stable_job_identity():
    assert copied_job(posting(job_url='https://www.linkedin.com/jobs/view/example-role-123456?trackingId=abc')).job_url == 'https://www.linkedin.com/jobs/view/123456'
    assert copied_job(posting(job_url='https://www.indeed.com/rc/clk?vjk=abc123&from=alert')).job_url == 'https://www.indeed.com/viewjob?jk=abc123'
    with pytest.raises(ValueError):
        copied_job(posting(job_url='https://127.0.0.1/job'))


def test_dashboard_source_and_import_endpoints_are_candidate_bound_and_confirmed(selected):
    with ReviewStore(candidate=selected):
        pass
    server = SimpleNamespace(candidate=selected, db=selected.database_path, origin='http://127.0.0.1:8765', token='test')
    payload = {'candidate_id': 'alex', 'job': posting()}
    assert call(server, '/api/import/preview', 'POST', payload)[0] == 200
    assert call(server, '/api/import', 'POST', payload)[0] == 400
    assert call(server, '/api/import', 'POST', payload | {'confirmed': True, 'preview': {'is_new': True}})[0] == 200
    assert call(server, '/api/import/preview', 'POST', payload | {'candidate_id': 'sam'})[0] == 400
    assert call(server, '/api/import', 'POST', payload, Origin='https://external.test')[0] == 403
    version = call(server, '/api/sources')[1]['version']
    assert call(server, '/api/sources', 'POST', {'candidate_id': 'alex', 'version': version, 'company': 'Extra', 'url': 'https://extra.test/careers'})[0] == 200
    assert call(server, '/api/searches')[0] == 200
