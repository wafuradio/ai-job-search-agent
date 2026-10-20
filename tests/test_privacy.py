"""Prevent private local data from becoming eligible for ordinary Git additions."""
import shutil
import subprocess
from pathlib import Path

from src.candidates import PROJECT_ROOT, get_candidate


def test_ignore_rules_cover_private_profiles_credentials_and_database_copies(tmp_path):
    repository = Path(__file__).resolve().parent.parent
    shutil.copy2(repository / '.gitignore', tmp_path / '.gitignore')
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    private = ['profiles/owner/career_profile.json', 'profiles/another/relationships.json',
               'config/app_config.json', 'config/career_profile.json', '.env', '.env.production',
               'data/jobs.db', 'data/jobs.db-wal', 'data/jobs.db-shm', 'copy/backup.sqlite3',
               'anywhere/review.db', 'exports/reviews.sql', 'output/shortlist.html',
               'CLAUDE_HANDOFF.md', 'backups/source.bundle', 'credentials-local.json', 'local/review-notes.md']
    result = subprocess.run(['git', 'check-ignore', '--no-index', *private], cwd=tmp_path,
                            check=True, capture_output=True, text=True)
    assert set(result.stdout.splitlines()) == set(private)
    for public in ['config/app_config.example.json', 'templates/candidate-profile/career_profile.json',
                   'tests/fixtures/default-profile/career_profile.json', 'README.md']:
        assert subprocess.run(['git', 'check-ignore', '--no-index', public], cwd=tmp_path,
                              capture_output=True).returncode == 1


def test_default_test_profile_is_temporary_and_explicitly_fictional():
    assert PROJECT_ROOT.name.startswith('job-agent-test-project-')
    assert get_candidate().candidate_id == 'example'
    evidence = get_candidate().load('candidate_evidence.json')
    assert 'Fictional' in str(evidence)
