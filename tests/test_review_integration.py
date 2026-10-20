from types import SimpleNamespace

import pytest

import run_live_shortlist as runner
import run_first_evaluation as first
from src.evaluator import AIJobEvaluation
from src.review_store import ReviewStore
from src.sources.greenhouse import GreenhouseJob
from test_evaluator import make_valid_ai_evaluation


@pytest.mark.parametrize('evaluate', [False, True])
def test_shortlist_saves_all_discoveries_and_optional_evaluation(tmp_path, monkeypatch, evaluate):
    jobs = [GreenhouseJob('Greenhouse', '1', 'anthropic', 'AI Transformation Lead',
                         'New York, NY', 'https://example.com/1',
                         'Lead AI transformation and governance. Hybrid full-time role.'),
            GreenhouseJob('Greenhouse', '2', 'anthropic', 'Junior event coordinator',
                         'London, UK', 'https://example.com/2', 'Event logistics')]
    monkeypatch.setattr(runner, 'fetch_greenhouse_jobs', lambda _: jobs)
    calls = []
    def fake_evaluate(job, **kwargs):
        calls.append(job)
        return AIJobEvaluation(**make_valid_ai_evaluation())
    monkeypatch.setattr(runner, 'evaluate_job_with_ai', fake_evaluate)
    monkeypatch.setattr('builtins.input', lambda _: 'EVALUATE')
    path = tmp_path / 'review.db'
    with ReviewStore(path) as store:
        runner.run_shortlist(SimpleNamespace(evaluate=evaluate, db=str(path)), store)
        rows = store.list_jobs()
        assert len(rows) == 2
        assert rows[0]['screening']['flags']
        assert rows[1]['screening']['status'] == 'Reject'
        assert len(rows[0]['evaluations']) == int(evaluate)
        assert len(calls) == int(evaluate)
        assert all(row['status'] == 'New' for row in rows)
        runner.run_shortlist(SimpleNamespace(evaluate=False, db=str(path)), store)
        assert len(store.list_jobs()) == 2


def test_failed_evaluation_keeps_saved_job(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, 'fetch_greenhouse_jobs', lambda _: [
        GreenhouseJob('Greenhouse', '1', 'anthropic', 'AI Transformation Lead',
                      'New York, NY', 'https://example.com/1', 'AI transformation governance')])
    def fail(_, **kwargs):
        raise RuntimeError('Offline simulated failure')
    monkeypatch.setattr(runner, 'evaluate_job_with_ai', fail)
    monkeypatch.setattr('builtins.input', lambda _: 'EVALUATE')
    with ReviewStore(tmp_path / 'review.db') as store:
        runner.run_shortlist(SimpleNamespace(evaluate=True, db='unused'), store)
        assert len(store.list_jobs()) == 1
        assert not store.list_jobs()[0]['evaluations']


def test_first_runner_persists_evaluation(tmp_path, monkeypatch):
    path = tmp_path / 'review.db'
    monkeypatch.setattr(first, 'ReviewStore', lambda *args, **kwargs: ReviewStore(path))
    monkeypatch.setattr(first, 'evaluate_job_with_ai', lambda *args, **kwargs: AIJobEvaluation(**make_valid_ai_evaluation()))
    first.main([])
    with ReviewStore(path) as store:
        assert len(store.list_jobs()) == 1
        assert store.list_jobs()[0]['evaluations'][0]['score'] == 87
