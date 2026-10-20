import json
from dataclasses import replace
import pytest
from src.review_store import ReviewStore
from src.review_display import shortlist_records, render_summary, write_html_report
from src.models import Job
from review_jobs import main
from calibrate_screening import main as calibrate


def seed(path):
    with ReviewStore(path) as store:
        job = Job(company='Example', title='AI Enablement Lead', job_url='https://example.test/1',
                  source='test', location_text='Remote - US', remote_status='Fully Remote',
                  raw_description='Lead AI adoption and workflow automation. <script>alert(1)</script>')
        first = store.save_job(job)
        second = store.save_job(replace(job, job_url='https://example.test/2'))
        store.set_status(second, 'Rejected', 'Human note')
        return first, second


def test_shortlist_filters_and_report_are_readonly(tmp_path):
    path = tmp_path / 'jobs.db'
    first, second = seed(path)
    before = path.read_bytes()
    with ReviewStore(path, readonly=True) as store:
        assert [row['id'] for row in shortlist_records(store)] == [first]
        assert len(shortlist_records(store, include_filtered=True)) == 2
        assert len(shortlist_records(store, status='Rejected', include_filtered=True)) == 1
        assert not shortlist_records(store, company='Other')
        assert not shortlist_records(store, work_model='Hybrid')
        assert len(shortlist_records(store, query='workflow')) == 1
        rows = shortlist_records(store)
        report = write_html_report(rows, tmp_path / 'shortlist.html')
        html = report.read_text()
        assert '<script>alert(1)</script>' not in html
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
        assert 'script src=' not in html and 'stylesheet' not in html
        assert 'Not run' in render_summary(rows[0])
    assert before == path.read_bytes()


def test_unsafe_posting_url_not_rendered_as_link(tmp_path):
    path = tmp_path / 'jobs.db'
    with ReviewStore(path) as store:
        store.save_job(Job(company='Example', title='AI Enablement Lead', source='test',
                           job_url='javascript:alert(1)', location_text='Remote - US'))
        rows = shortlist_records(store)
        report = write_html_report(rows, tmp_path / 'report.html').read_text()
        assert 'href="javascript:' not in report


def test_cli_human_readable_and_json_views(tmp_path, capsys):
    path = tmp_path / 'jobs.db'
    first, second = seed(path)
    main(['--db', str(path), 'shortlist', '--html', str(tmp_path / 'report.html')])
    assert 'Scout relevance' in capsys.readouterr().out
    main(['--db', str(path), 'show', str(second)])
    assert 'Human note' in capsys.readouterr().out
    main(['--db', str(path), 'show', str(first), '--json'])
    assert json.loads(capsys.readouterr().out)['id'] == first
    with pytest.raises(SystemExit):
        main(['--db', str(path), 'shortlist', '--limit', '0'])


def test_missing_readonly_database_does_not_create_one(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        ReviewStore(path, readonly=True)
    assert not path.exists()


def test_calibration_changes_neither_decisions_nor_db_bytes(tmp_path):
    path = tmp_path / 'jobs.db'
    seed(path)
    before = path.read_bytes()
    report = calibrate(['--db', str(path), '--output', str(tmp_path / 'calibration.json')])
    assert report['saved_jobs'] == 2
    assert before == path.read_bytes()
