from dataclasses import replace
from io import BytesIO
import json
from urllib.error import URLError

import pytest

from src.models import Job
from src.normalizer import normalize_greenhouse_job
from src.sources import greenhouse
from src.review_store import ReviewStore
from src.review_display import posting_date_lines, date_label
from src import discovery


def posting(**extra):
    return {'id':123,'title':'AI Enablement Lead','absolute_url':'https://example.test/123',
            'location':{'name':'Remote - US'},'content':'Lead AI adoption and workflow automation.', **extra}


def test_greenhouse_dates_keep_publication_and_update_separate():
    raw=greenhouse.parse_greenhouse_jobs({'jobs':[posting(first_published='2026-09-01T12:00:00Z',updated_at='2026-10-20T12:00:00Z')]},'example')[0]
    job=normalize_greenhouse_job(raw,'Example')
    assert job.posted_date=='2026-09-01T12:00:00Z'
    assert job.posted_date_kind=='first_published'
    assert job.source_updated_at=='2026-10-20T12:00:00Z'
    without=normalize_greenhouse_job(greenhouse.parse_greenhouse_jobs({'jobs':[posting(updated_at='2026-10-20T12:00:00Z')]},'example')[0],'Example')
    assert without.posted_date is None
    assert without.source_updated_at


def test_individual_date_lookup_is_free_public_get(monkeypatch):
    def fake_open(request,timeout):
        assert request.get_method()=='GET'
        assert request.full_url=='https://boards-api.greenhouse.io/v1/boards/example/jobs/123'
        assert 'Authorization' not in request.headers
        assert timeout==20
        return BytesIO(json.dumps({'first_published':'2026-09-01T12:00:00Z','updated_at':'2026-10-20T12:00:00Z'}).encode())
    monkeypatch.setattr(greenhouse,'urlopen',fake_open)
    assert greenhouse.fetch_greenhouse_job_dates('example','123')['first_published']=='2026-09-01T12:00:00Z'


def test_missing_date_lookup_does_not_substitute_update(monkeypatch):
    monkeypatch.setattr(greenhouse,'urlopen',lambda *args,**kwargs:BytesIO(b'{"updated_at":"2026-10-20T12:00:00Z"}'))
    assert greenhouse.fetch_greenhouse_job_dates('example','123')['first_published'] is None


def test_render_ashby_legacy_date_as_publication_or_republication():
    row={'job':{'source':'Ashby','posted_date':'2026-09-14T19:56:59.278+00:00'},'created_at':'2026-10-20T14:00:00+00:00'}
    lines=posting_date_lines(row)
    assert 'Published / republished: 2026-09-14' in lines[0]
    assert 'First saved locally: 2026-10-20 (not the posting date)' in lines[-1]
    assert not any('First published' in line for line in lines)


def test_unknown_posting_date_remains_unknown_even_when_local_and_update_dates_exist():
    row={'job':{'source':'Greenhouse','source_updated_at':'2026-10-20T12:00:00Z'},'created_at':'2026-10-11T12:00:00Z'}
    lines=posting_date_lines(row)
    assert lines[0]=='  Employer posting date: Unknown'
    assert 'Employer record updated: 2026-10-20 (not the posting date)' in lines[1]
    assert date_label('not-a-date').startswith('Unknown')
    assert date_label(None)=='Unknown'
    assert date_label('2026-09-14')=='2026-09-14'


def test_adding_date_metadata_does_not_revoke_approval_and_missing_refresh_preserves_it(tmp_path):
    path=tmp_path/'review.db'
    job=Job(company='Example',title='AI Enablement Lead',source='Greenhouse',job_url='https://example.test/123')
    with ReviewStore(path) as store:
        job_id=store.save_job(job)
        store.approve_job(job_id,confirmation=f'APPROVE {job_id}',revision=1)
        dated=replace(job,posted_date='2026-09-01T12:00:00Z',posted_date_kind='first_published',source_updated_at='2026-10-20T12:00:00Z')
        store.save_job(dated)
        store.require_job_approval(job_id)
        store.save_job(job)
        saved=store.get_job(job_id)
        assert saved['revision']==1 and saved['status']=='Approved to Apply'
        assert saved['job']['posted_date']==dated.posted_date
        assert saved['job']['posted_date_kind']=='first_published'
        assert saved['job']['source_updated_at']==dated.source_updated_at
        store.save_job(replace(dated,raw_description='A material requirement change'))
        with pytest.raises(PermissionError):store.require_job_approval(job_id)


def test_legacy_json_without_new_date_fields_does_not_cause_material_change(tmp_path):
    with ReviewStore(tmp_path/'review.db') as store:
        job=Job(company='Example',title='AI Enablement Lead',source='test',job_url='https://example.test/123')
        job_id=store.save_job(job)
        data=store.get_job(job_id)['job'];data.pop('posted_date_kind');data.pop('source_updated_at')
        store.connection.execute('UPDATE jobs SET job_json=? WHERE id=?',(json.dumps(data),job_id));store.connection.commit()
        store.approve_job(job_id,confirmation=f'APPROVE {job_id}',revision=1)
        store.save_job(job)
        store.require_job_approval(job_id)
        assert store.get_job(job_id)['revision']==1


@pytest.mark.parametrize('enrich',[False,True])
def test_optional_date_enrichment_only_looks_up_survivors(tmp_path,monkeypatch,enrich):
    raw=greenhouse.parse_greenhouse_jobs({'jobs':[posting(),posting(id=456,absolute_url='https://example.test/456',location={'name':'London, UK'})]},'example')
    monkeypatch.setattr(discovery,'fetch_greenhouse_jobs',lambda _:raw)
    calls=[]
    def dates(board,job_id):
        calls.append(job_id)
        return {'first_published':'2026-09-01T12:00:00Z','updated_at':None}
    monkeypatch.setattr(discovery,'fetch_greenhouse_job_dates',dates)
    with ReviewStore(tmp_path/'review.db') as store:
        run=discovery.discover_boards(store,[{'source':'greenhouse','company':'Example','board_token':'example'}],enrich_dates=enrich)
        assert run.retrieved==2 and len(run.accepted_ids)==1
        assert calls==(['123'] if enrich else [])
        assert bool(store.get_job(1)['job']['posted_date'])==enrich


def test_date_lookup_failure_does_not_discard_posting(tmp_path,monkeypatch):
    raw=greenhouse.parse_greenhouse_jobs({'jobs':[posting()]},'example')
    monkeypatch.setattr(discovery,'fetch_greenhouse_jobs',lambda _:raw)
    def fail(*args):raise URLError('Offline simulated date failure')
    monkeypatch.setattr(discovery,'fetch_greenhouse_job_dates',fail)
    with ReviewStore(tmp_path/'review.db') as store:
        run=discovery.discover_boards(store,[{'source':'greenhouse','company':'Example','board_token':'example'}],enrich_dates=True)
        assert len(run.saved_ids)==1 and len(run.errors)==1
        assert store.get_job(1)['job']['posted_date'] is None
