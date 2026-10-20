"""Run every test against synthetic profiles, never a developer's private data."""
import atexit
import os
import shutil
import tempfile
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parent.parent
SANDBOX = Path(tempfile.mkdtemp(prefix='job-agent-test-project-'))
shutil.copytree(REPOSITORY / 'templates', SANDBOX / 'templates')
shutil.copytree(REPOSITORY / 'tests/fixtures/default-profile', SANDBOX / 'profiles/example')
(SANDBOX / 'config').mkdir()
(SANDBOX / 'config/app_config.json').write_text(
    '{"default_candidate":"example","legacy_database_owner":"example"}\n', encoding='utf-8')
# Set before importing any src modules: production defaults remain local unless
# an explicit root override is supplied. Tests do not reuse an inherited root.
os.environ['AI_JOB_SEARCH_ROOT'] = str(SANDBOX)
atexit.register(shutil.rmtree, SANDBOX, ignore_errors=True)
