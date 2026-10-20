"""Offline request tests: synthetic jobs, no listener or live review decisions."""
import json
from email.message import Message
from io import BytesIO
from types import SimpleNamespace

import pytest

from src.dashboard import ReviewHandler, ReviewServer
from src.models import Job
from src.review_store import ReviewStore
from src.candidates import get_candidate
from test_candidates import candidate_root


@pytest.fixture
def server(tmp_path):
    path = tmp_path / 'review.db'
    with ReviewStore(path) as store:
        store.save_job(Job(company='Synthetic <script>example</script>',title='AI Enablement Lead',source='test',
                           job_url='https://example.test/job',location_text='Remote, United States',remote_status='Remote',
                           raw_description='AI adoption and workflow automation.'))
    return SimpleNamespace(origin='http://127.0.0.1:8765',token='test-secret',candidate=get_candidate(),db=path)


def call(server, path, method='GET', data=None, **overrides):
    handler = ReviewHandler.__new__(ReviewHandler)
    handler.server=server; handler.path=path; handler.request_version='HTTP/1.1'; handler.command=method
    handler.requestline=method+' '+path+' HTTP/1.1'
    body=json.dumps(data).encode() if data is not None else b''
    headers={'Host':'127.0.0.1:8765','Origin':server.origin,'X-Review-Token':server.token,
             'Content-Type':'application/json','Content-Length':str(len(body))}
    headers.update(overrides)
    handler.headers=Message()
    for key,value in headers.items():
        if value is not None:handler.headers[key]=value
    handler.rfile=BytesIO(body);handler.wfile=BytesIO()
    getattr(handler,'do_'+method)()
    head,payload=handler.wfile.getvalue().split(b'\r\n\r\n',1)
    status=int(head.split()[1])
    return status,json.loads(payload) if b'application/json' in head else payload.decode(),head


def review(server, **changes):
    with ReviewStore(server.db,readonly=True) as store:row=store.get_job(1)
    data=dict(candidate_id=server.candidate.candidate_id,job_id=1,revision=row['revision'],
              updated_at=row['updated_at'],action='status',status='Interested',notes='Synthetic decision')
    data.update(changes)
    return data


def test_lists_jobs_and_details_without_mutations(server):
    with ReviewStore(server.db,readonly=True) as store:before=store.get_job(1)
    status,listing,headers=call(server,'/api/jobs')
    assert status==200 and listing['candidate_id']=='example'
    assert listing['jobs'][0]['screening']['accepted']
    assert b'no-store' in headers and b"frame-ancestors 'none'" in headers
    assert call(server,'/api/jobs/1')[1]['job']['raw_description']
    with ReviewStore(server.db,readonly=True) as store:assert store.get_job(1)==before


def test_status_and_notes_persist_and_stale_second_save_refused(server):
    data=review(server)
    assert call(server,'/api/review','POST',data)[0]==200
    assert call(server,'/api/review','POST',data)[0]==409
    with ReviewStore(server.db,readonly=True) as store:
        row=store.get_job(1)
        assert row['status']=='Interested'
        assert row['history'][-1]['details']['notes']=='Synthetic decision'
        assert not row['evaluations']


def test_note_only_preserves_existing_approval(server):
    with ReviewStore(server.db) as store:store.approve_job(1,confirmation='APPROVE 1',revision=1)
    assert call(server,'/api/review','POST',review(server,action='note',notes='Investigate scope'))[0]==200
    with ReviewStore(server.db,readonly=True) as store:
        store.require_job_approval(1)
        assert store.get_job(1)['history'][-1]['event']=='human_note'
        with pytest.raises(PermissionError):store.require_submission_approval(1,materials_digest='test')


def test_changed_posting_prevents_stale_review(server):
    data=review(server)
    with ReviewStore(server.db) as store:
        store.save_job(Job(company='Synthetic <script>example</script>',title='Changed role',source='test',job_url='https://example.test/job'))
    assert call(server,'/api/review','POST',data)[0]==409
    with ReviewStore(server.db,readonly=True) as store:assert store.get_job(1)['status']=='New'


@pytest.mark.parametrize('headers',[{'Origin':'https://evil.test'},{'Origin':None},{'X-Review-Token':'wrong'},
                                    {'Host':'evil.test:8765'},{'Host':'127.0.0.1.evil.test:8765'}])
def test_untrusted_browser_requests_cannot_change_review(server,headers):
    assert call(server,'/api/review','POST',review(server),**headers)[0]==403
    with ReviewStore(server.db,readonly=True) as store:assert store.get_job(1)['status']=='New'


@pytest.mark.parametrize('changes',[{'status':'Approved to Apply'},{'action':'apply'},{'action':'approve'},
                                    {'candidate_id':'someone_else'},{'revision':None},{'updated_at':None},
                                    {'job_id':True},{'notes':['invalid']},{'action':'note','notes':''}])
def test_invalid_actions_and_approval_bypass_rejected(server,changes):
    assert call(server,'/api/review','POST',review(server,**changes))[0] in (400,409)
    with ReviewStore(server.db,readonly=True) as store:assert store.get_job(1)['status']=='New'


def test_static_dashboard_served_and_unknown_routes_denied(server):
    status,html,_=call(server,'/')
    assert status==200 and 'test-secret' in html and '__REVIEW_TOKEN__' not in html
    assert call(server,'/app.js')[0]==call(server,'/app.css')[0]==200
    assert call(server,'/api/jobs/99999')[0]==404
    assert call(server,'/../../.env')[0]==404
    assert call(server,'/api/jobs',Host='external.test')[0]==403


def test_server_binds_only_loopback_and_rejects_other_candidates_database(server, candidate_root, monkeypatch):
    def fake_init(self,address,handler):
        assert address==('127.0.0.1',8765)
        self.server_port=8765
    monkeypatch.setattr('src.dashboard.ThreadingHTTPServer.__init__',fake_init)
    listener=ReviewServer(db=server.db)
    assert listener.origin=='http://127.0.0.1:8765'
    sam=get_candidate('sam',root=candidate_root)
    with ReviewStore(candidate=sam):pass
    with pytest.raises(ValueError,match='belongs to candidate'):
        ReviewServer(candidate=get_candidate('alex',root=candidate_root),db=sam.database_path)
