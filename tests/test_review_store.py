from dataclasses import replace

import pytest

from src.evaluator import AIJobEvaluation
from src.gatekeeper import GatekeeperResult, FLAG
from src.review_store import ReviewStore
from test_evaluator import make_job, make_valid_ai_evaluation


def test_persists_complete_job_screening_and_evaluations(tmp_path):
    path = tmp_path / 'review.db'
    job = make_job(raw_description='Original full posting', external_job_id='123')
    evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
    with ReviewStore(path) as store:
        job_id = store.save_job(job, GatekeeperResult(FLAG, ['Question'], ['Hybrid']), 7)
        store.save_evaluation(job_id, evaluation, revision=1)
        store.save_evaluation(job_id, evaluation, revision=1)
    with ReviewStore(path) as store:
        saved = store.get_job(job_id)
        assert saved['status'] == 'New'
        assert saved['job']['raw_description'] == 'Original full posting'
        assert saved['screening'] == {'status': FLAG, 'reasons': ['Question'], 'flags': ['Hybrid']}
        assert saved['scout_score'] == 7
        assert len(saved['evaluations']) == 2
        assert saved['evaluations'][0]['evaluation'] == evaluation.model_dump(mode='json')
        assert saved['evaluations'][0]['score'] == evaluation.score_breakdown.total


def test_duplicate_url_and_source_identity(tmp_path):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job(external_job_id='123')
        original = store.save_job(job)
        assert store.save_job(replace(job, job_url=job.job_url + '/')) == original
        assert store.save_job(replace(job, job_url='https://example.com/new-url')) == original
        assert len(store.list_jobs()) == 1
        # External IDs are scoped to company, not globally unique.
        assert store.save_job(replace(job, company='Other', job_url='https://other/jobs/123')) != original


def test_conflicting_identities_do_not_merge_or_erase_records(tmp_path):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job(external_job_id='1')
        store.save_job(job)
        store.save_job(replace(job, external_job_id='2', job_url='https://example.com/jobs/2'))
        with pytest.raises(ValueError, match='Conflicting'):
            store.save_job(replace(job, external_job_id='2'))
        assert len(store.list_jobs()) == 2


def test_review_history_and_routine_update_preserve_approval(tmp_path):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job(raw_description='Lead the program.')
        job_id = store.save_job(job)
        for status in ['Interested', 'Rejected', 'Interested']:
            store.set_status(job_id, status, 'Human note')
        store.approve_job(job_id, revision=store.get_job(job_id)["revision"], confirmation=f'APPROVE {job_id}', notes='Reviewed')
        store.save_job(replace(job, raw_description='Lead  the\nprogram.', posted_date='2026-10-11'))
        saved = store.get_job(job_id)
        assert saved['status'] == 'Approved to Apply'
        assert saved['revision'] == 1
        assert not saved['needs_reevaluation']
        decisions = [event for event in saved['history'] if event['event'] == 'human_decision']
        assert [event['details']['status'] for event in decisions] == [
            'Interested', 'Rejected', 'Interested', 'Approved to Apply']
        assert decisions[-1]['details']['notes'] == 'Reviewed'
        assert all(event['created_at'] for event in decisions)
        store.require_job_approval(job_id)


@pytest.mark.parametrize('change', [
    {'title': 'Director'}, {'raw_description': 'Mandatory relocation'},
    {'location_text': 'Boston, MA'}, {'requirements': ['Production ML ownership']},
    {'remote_policy_text': 'Five days onsite'}, {'application_deadline': '2026-11-01'},
])
def test_material_changes_revoke_approval_and_preserve_original(tmp_path, change):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job()
        job_id = store.save_job(job)
        store.approve_job(job_id, revision=store.get_job(job_id)["revision"], confirmation=f'APPROVE {job_id}')
        store.save_job(replace(job, **change))
        saved = store.get_job(job_id)
        assert saved['status'] == 'New'
        assert saved['needs_reevaluation'] == 1
        assert saved['revision'] == 2
        assert saved['approved_revision'] is None
        assert saved['history'][1]['details']['status'] == 'Approved to Apply'
        assert saved['history'][-1]['details']['approval_revoked']
        with pytest.raises(PermissionError):
            store.require_job_approval(job_id)
        with pytest.raises(ValueError, match='reevaluation'):
            store.approve_job(job_id, revision=store.get_job(job_id)["revision"], confirmation=f'APPROVE {job_id}')
        evaluation = AIJobEvaluation(**make_valid_ai_evaluation())
        with pytest.raises(ValueError, match='outdated'):
            store.save_evaluation(job_id, evaluation, revision=1)
        store.save_evaluation(job_id, evaluation, revision=2)
        assert store.get_job(job_id)['status'] == 'New'
        store.approve_job(job_id, revision=store.get_job(job_id)["revision"], confirmation=f'APPROVE {job_id}')
        store.require_job_approval(job_id)


@pytest.mark.parametrize('status', ['Interested', 'Rejected'])
def test_material_change_keeps_nonapproval_human_decision(tmp_path, status):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job()
        job_id = store.save_job(job)
        store.set_status(job_id, status)
        store.save_job(replace(job, title='Changed role'))
        assert store.get_job(job_id)['status'] == status
        assert store.get_job(job_id)['needs_reevaluation']
        assert len(store.list_jobs(status)) == 1


def test_approval_guards_fail_closed(tmp_path):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job_id = store.save_job(make_job())
        for status in ['New', 'Interested', 'Rejected']:
            store.set_status(job_id, status)
            with pytest.raises(PermissionError):
                store.require_submission_approval(job_id, materials_digest='abc')
        with pytest.raises(ValueError):
            store.set_status(job_id, 'Approved to Apply')
        with pytest.raises(ValueError):
            store.approve_job(job_id, revision=store.get_job(job_id)["revision"], confirmation='yes')
        store.approve_job(job_id, revision=store.get_job(job_id)["revision"], confirmation=f'APPROVE {job_id}')
        for digest in ['', 'abc', 'different-materials']:
            with pytest.raises(PermissionError, match='materials approval is not implemented'):
                store.require_submission_approval(job_id, materials_digest=digest)
        store.set_status(job_id, 'Interested')
        with pytest.raises(PermissionError):
            store.require_job_approval(job_id)
        with pytest.raises(ValueError):
            store.set_status(job_id, 'Maybe')
        with pytest.raises(KeyError):
            store.require_job_approval(999)


def test_rediscovery_does_not_erase_evaluation_or_screening(tmp_path):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job()
        job_id = store.save_job(job, GatekeeperResult(FLAG, flags=['Hybrid']))
        store.save_evaluation(job_id, AIJobEvaluation(**make_valid_ai_evaluation()), revision=1)
        store.save_job(job)
        assert store.get_job(job_id)['screening']['flags'] == ['Hybrid']
        assert len(store.get_job(job_id)['evaluations']) == 1


def test_cannot_approve_posting_changed_since_display(tmp_path):
    with ReviewStore(tmp_path / 'jobs.db') as store:
        job = make_job()
        job_id = store.save_job(job)
        reviewed_revision = store.get_job(job_id)['revision']
        store.save_job(replace(job, title='Changed role'))
        store.save_evaluation(job_id, AIJobEvaluation(**make_valid_ai_evaluation()), revision=2)
        with pytest.raises(ValueError, match='changed since review'):
            store.approve_job(job_id, confirmation=f'APPROVE {job_id}', revision=reviewed_revision)
        assert store.get_job(job_id)['status'] == 'New'
