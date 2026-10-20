"""Loopback-only saved-job review server. No external requests or submissions."""
import json
import secrets
import sqlite3
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from src.candidates import get_candidate
from src.review_display import shortlist_records, compensation_label, posting_date_lines
from src.review_store import ReviewStore
from src.source_manager import source_settings, update_employer
from src.search_plan import search_links
from src.posting_intake import preview_posting, save_copied_posting


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, candidate=None, db=None, port=8765):
        self.candidate = get_candidate(candidate)
        with ReviewStore(db, readonly=True, candidate=self.candidate) as store:
            self.db = store.path
        self.token = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), ReviewHandler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)


class ReviewHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, status, value, content_type='application/json; charset=utf-8'):
        body = value.encode('utf-8') if isinstance(value, str) else json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(body)

    def host_allowed(self):
        return self.headers.get('Host') == self.server.origin.removeprefix('http://')

    def do_GET(self):
        if not self.host_allowed():
            return self.reply(403, {'error': 'Use the local dashboard address'})
        path = urlsplit(self.path).path
        if path in ('/', '/app.js', '/app.css'):
            filename, mime = {'/': ('dashboard.html', 'text/html; charset=utf-8'),
                              '/app.js': ('dashboard.js', 'text/javascript; charset=utf-8'),
                              '/app.css': ('dashboard.css', 'text/css; charset=utf-8')}[path]
            data = (Path(__file__).parent / 'dashboard_ui' / filename).read_text(encoding='utf-8')
            return self.reply(200, data.replace('__REVIEW_TOKEN__', self.server.token), mime)
        try:
            if path == '/api/sources':
                return self.reply(200, source_settings(self.server.candidate))
            if path == '/api/searches':
                return self.reply(200, {'links': search_links(self.server.candidate)})
            with ReviewStore(self.server.db, readonly=True, candidate=self.server.candidate) as store:
                if path == '/api/jobs':
                    rows = shortlist_records(store, include_filtered=True, limit=1000000)
                    jobs = []
                    for row in rows:
                        result = row['discovery']
                        jobs.append({key: row[key] for key in ('id', 'status', 'revision', 'needs_reevaluation', 'created_at', 'updated_at')})
                        jobs[-1].update(company=row['job']['company'], title=row['job']['title'],
                                        location=row['job'].get('location_text') or 'Location unknown',
                                        work_model=row['job'].get('remote_status') or 'Unknown',
                                        source=row['job']['source'], compensation=compensation_label(row['job']),
                                        dates=posting_date_lines(row), screening=asdict(result))
                    return self.reply(200, {'candidate_id': store.candidate.candidate_id,
                                           'candidate_name': store.candidate.display_name, 'jobs': jobs})
                if path.startswith('/api/jobs/') and path.removeprefix('/api/jobs/').isdigit():
                    row = store.get_job(int(path.rsplit('/', 1)[1]))
                    row['dates'] = posting_date_lines(row)
                    return self.reply(200, row)
        except KeyError:
            return self.reply(404, {'error': 'Job not found for this candidate'})
        except (ValueError, OSError) as exc:
            return self.reply(400, {'error': str(exc)})
        except sqlite3.Error:
            return self.reply(500, {'error': 'Could not read the database; refresh and try again'})
        self.reply(404, {'error': 'Page not found'})

    def do_POST(self):
        if (not self.host_allowed() or self.headers.get('Origin') != self.server.origin
                or not secrets.compare_digest(self.headers.get('X-Review-Token', '').encode(), self.server.token.encode())):
            return self.reply(403, {'error': 'Reload the local dashboard before saving'})
        if self.path not in ('/api/review', '/api/sources', '/api/import/preview', '/api/import'):
            return self.reply(404, {'error': 'Action not available'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 1000000 or self.headers.get_content_type() != 'application/json':
                return self.reply(400, {'error': 'Expected a small JSON review request'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or data.get('candidate_id') != self.server.candidate.candidate_id:
                return self.reply(400, {'error': 'Candidate does not match this dashboard'})
            if self.path == '/api/sources':
                result = update_employer(self.server.candidate, version=data.get('version'),
                                         company=data.get('company'), url=data.get('url'),
                                         source_id=data.get('source_id'), enabled=data.get('enabled'))
                return self.reply(200, result)
            if self.path in ('/api/import/preview', '/api/import'):
                if self.path == '/api/import' and data.get('confirmed') is not True:
                    return self.reply(400, {'error': 'Review the posting preview and confirm before saving'})
                with ReviewStore(self.server.db, readonly=self.path.endswith('/preview'), candidate=self.server.candidate) as store:
                    result = (preview_posting(store, data.get('job')) if self.path.endswith('/preview')
                              else save_copied_posting(store, data.get('job'), data.get('preview')))
                return self.reply(200, result)
            if (type(data.get('job_id')) is not int or type(data.get('revision')) is not int
                    or not isinstance(data.get('updated_at'), str) or not data['updated_at']
                    or not isinstance(data.get('notes', ''), str) or len(data.get('notes', '')) > 10000):
                return self.reply(400, {'error': 'Invalid review request; reload this job'})
            action = data.get('action')
            if action not in ('status', 'note') or (action == 'status' and data.get('status') not in ('New', 'Interested', 'Rejected')):
                return self.reply(400, {'error': 'Only review decisions and notes are available; approval and submission are separate'})
            with ReviewStore(self.server.db, candidate=self.server.candidate) as store:
                versions = {'expected_revision': data['revision'], 'expected_updated_at': data['updated_at']}
                if action == 'note':
                    store.add_note(data['job_id'], data.get('notes', ''), **versions)
                else:
                    store.set_status(data['job_id'], data['status'], data.get('notes', ''), **versions)
            self.reply(200, {'saved': True})
        except KeyError:
            self.reply(404, {'error': 'Job not found for this candidate'})
        except (ValueError, UnicodeError) as exc:
            self.reply(409, {'error': str(exc)})
        except (OSError, sqlite3.Error):
            self.reply(500, {'error': 'Could not save the review; reload and try again'})
