import json
from dataclasses import replace
from urllib.error import URLError
import pytest
from src import discovery
from src.review_store import ReviewStore
from src.models import Job
from src.sources.greenhouse import GreenhouseJob
from run_discovery import main

BOARDS = [{'company': 'One', 'source': 'greenhouse', 'board_token': 'one'},
          {'company': 'Two', 'source': 'ashby', 'board_token': 'two'}]


def mock_feeds(monkeypatch):
    monkeypatch.setattr(discovery, 'fetch_greenhouse_jobs', lambda _: [
        GreenhouseJob('Greenhouse', 'same-id', 'one', 'AI Enablement Lead', 'Remote - US', 'https://one.test/1', 'Lead AI adoption and workflow automation.')])
    monkeypatch.setattr(discovery, 'fetch_ashby_jobs', lambda *args: [
        Job(company='Two', title='AI Enablement Lead', job_url='https://two.test/1', source='Ashby',
            external_job_id='same-id', location_text='Remote - US', remote_status='Fully Remote', raw_description='Lead AI adoption and workflow automation.')])


def test_multiple_boards_save_deduplicate_and_preserve_decisions(tmp_path, monkeypatch):
    mock_feeds(monkeypatch)
    with ReviewStore(tmp_path / 'jobs.db') as store:
        result = discovery.discover_boards(store, BOARDS)
        assert result.retrieved == len(result.saved_ids) == len(result.accepted_ids) == 2
        assert len(result.new_ids) == 2
        store.set_status(1, 'Interested', 'Keep this note')
        store.approve_job(2, confirmation='APPROVE 2', revision=1)
        repeat = discovery.discover_boards(store, BOARDS)
        assert len(repeat.new_ids) == 0
        assert len(store.list_jobs()) == 2
        assert store.get_job(1)['status'] == 'Interested'
        store.require_job_approval(2)
        assert store.connection.execute('SELECT COUNT(*) FROM discovery_results').fetchone()[0] == 2
        assert store.connection.execute('SELECT COUNT(*) FROM evaluations').fetchone()[0] == 0


def test_source_failure_is_visible_and_other_board_continues(tmp_path, monkeypatch):
    mock_feeds(monkeypatch)
    def fail(_):
        raise URLError('Offline simulated failure')
    monkeypatch.setattr(discovery, 'fetch_greenhouse_jobs', fail)
    with ReviewStore(tmp_path / 'jobs.db') as store:
        result = discovery.discover_boards(store, BOARDS)
        assert len(result.errors) == 1 and len(result.saved_ids) == 1
        assert 'Offline simulated failure' in result.errors[0]


def test_disabled_source_never_fetches(tmp_path, monkeypatch):
    search, profile = discovery.load_search_settings()
    search['discovery_sources']['ashby'] = False
    monkeypatch.setattr(discovery, 'load_search_settings', lambda **kwargs: (search, profile))
    monkeypatch.setattr(discovery, 'fetch_ashby_jobs', lambda *args: pytest.fail('Disabled source fetched'))
    with ReviewStore(tmp_path / 'jobs.db') as store:
        assert discovery.discover_boards(store, BOARDS[1:]).errors


def test_config_validation_and_selection(tmp_path):
    path = tmp_path / 'boards.json'
    path.write_text(json.dumps({'boards': BOARDS}))
    assert discovery.load_boards(path, ['two']) == BOARDS[1:]
    with pytest.raises(ValueError, match='No enabled'):
        discovery.load_boards(path, ['unknown'])
    path.write_text(json.dumps({'boards': [BOARDS[0], BOARDS[0]]}))
    with pytest.raises(ValueError, match='Duplicate'):
        discovery.load_boards(path)
    path.write_text(json.dumps({'boards': [{**BOARDS[0], 'source': 'unknown'}]}))
    with pytest.raises(ValueError, match='Unsupported'):
        discovery.load_boards(path)


def test_free_only_cli_rejects_ai_evaluation_option(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(['--evaluate'])
    assert error.value.code == 2


def test_legacy_database_upgrade_preserves_review_history(tmp_path):
    path = tmp_path / 'jobs.db'
    with ReviewStore(path) as store:
        job_id = store.save_job(Job(company='Example', title='AI Enablement Lead',
                                   job_url='https://example.test/1', source='test'))
        store.set_status(job_id, 'Rejected', 'Original human decision')
        before = store.get_job(job_id)
        store.connection.execute('DROP TABLE discovery_results')
        store.connection.commit()
    with ReviewStore(path) as store:
        assert store.get_job(job_id) == before
        assert store.connection.execute('SELECT COUNT(*) FROM discovery_results').fetchone()[0] == 0


def test_discovery_cli_exports_current_run_and_remote_reports(tmp_path,monkeypatch):
    mock_feeds(monkeypatch)
    board_file=tmp_path/'boards.json'
    board_file.write_text(json.dumps({'boards':BOARDS}))
    db=tmp_path/'review.db'
    with ReviewStore(db) as store:
        store.save_job(Job(company='Historical',title='AI Enablement Lead',source='test',
                           job_url='https://historical.test/1',location_text='Remote - US',remote_status='Remote'))
    all_report=tmp_path/'current.html';remote_report=tmp_path/'remote.html'
    assert main(['--db',str(db),'--boards',str(board_file),'--html',str(all_report),'--remote-html',str(remote_report)])==0
    assert 'Historical' not in all_report.read_text()
    assert 'Historical' not in remote_report.read_text()
    assert 'Two' in remote_report.read_text()
    assert 'AI Enablement Lead' in all_report.read_text()
