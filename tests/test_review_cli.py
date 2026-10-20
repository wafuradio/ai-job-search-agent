import pytest

from review_jobs import main
from src.review_store import ReviewStore
from test_evaluator import make_job


def test_offline_review_commands_and_exact_confirmation(tmp_path, monkeypatch, capsys):
    db = str(tmp_path / 'review.db')
    with ReviewStore(db) as store:
        job_id = store.save_job(make_job())
    prefix = ['--db', db]
    main(prefix + ['list'])
    assert 'New' in capsys.readouterr().out
    main(prefix + ['status', str(job_id), 'Interested', '--notes', 'Looks promising'])
    main(prefix + ['show', str(job_id)])
    assert 'Looks promising' in capsys.readouterr().out
    monkeypatch.setattr('builtins.input', lambda _: 'yes')
    with pytest.raises(SystemExit) as error:
        main(prefix + ['approve', str(job_id)])
    assert error.value.code == 1
    with ReviewStore(db) as store:
        assert store.get_job(job_id)['status'] == 'Interested'
    monkeypatch.setattr('builtins.input', lambda _: f'APPROVE {job_id}')
    main(prefix + ['approve', str(job_id)])
    with ReviewStore(db) as store:
        store.require_job_approval(job_id)
    main(prefix + ['list', '--status', 'Approved to Apply'])
    assert 'Approved to Apply' in capsys.readouterr().out


def test_missing_job_is_clear_error(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(['--db', str(tmp_path / 'review.db'), 'show', '999'])
    assert error.value.code == 1
