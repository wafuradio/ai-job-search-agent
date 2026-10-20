"""Local review persistence. No network calls or application submission."""
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.models import Job
from src.candidates import get_candidate, app_settings

DEFAULT_DB = get_candidate().database_path
STATUSES = ("New", "Interested", "Rejected", "Approved to Apply")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalize(value):
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    return value


def _material(data):
    # Metadata and whitespace changes are routine. All role content is material,
    # including unknown facts becoming known. No semantic AI classification.
    return _normalize({key: value for key, value in data.items() if key not in {
        "discovered_at", "posted_date", "posted_date_kind", "source_updated_at", "source", "external_job_id", "job_url"
    }})


class ReviewStore:
    def __init__(self, path=None, readonly=False, *, candidate=None):
        self.candidate = get_candidate(candidate)
        path = self.candidate.database_path if path is None else Path(path)
        self.path = path.resolve()
        legacy_owner = app_settings(self.candidate.root)['legacy_database_owner']
        if self.path == self.candidate.legacy_database_path.resolve() and self.candidate.candidate_id != legacy_owner:
            raise ValueError(f'The legacy database belongs to candidate {legacy_owner}')
        if readonly:
            if not path.is_file():
                raise FileNotFoundError(f'No review database at {path}; run discovery first.')
            self.connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
            self.connection.row_factory = sqlite3.Row
            self._verify_candidate_owner()
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(path))
        self.connection.row_factory = sqlite3.Row
        self._verify_candidate_owner()
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS database_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY,
                job_url TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                company_key TEXT NOT NULL,
                external_job_id TEXT,
                job_json TEXT NOT NULL,
                screening_json TEXT,
                scout_score INTEGER,
                status TEXT NOT NULL DEFAULT 'New'
                    CHECK(status IN ('New','Interested','Rejected','Approved to Apply')),
                revision INTEGER NOT NULL DEFAULT 1,
                needs_reevaluation INTEGER NOT NULL DEFAULT 0,
                approved_revision INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source, company_key, external_job_id)
            );
            CREATE TABLE IF NOT EXISTS discovery_results (
                job_id INTEGER PRIMARY KEY REFERENCES jobs(id),
                revision INTEGER NOT NULL,
                result_json TEXT NOT NULL,
                screened_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY,
                job_id INTEGER NOT NULL REFERENCES jobs(id),
                revision INTEGER NOT NULL,
                evaluation_json TEXT NOT NULL,
                score INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY,
                job_id INTEGER NOT NULL REFERENCES jobs(id),
                event TEXT NOT NULL,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO database_metadata(key,value) VALUES('candidate_id',?)",
                (self.candidate.candidate_id,),
            )
        self._verify_candidate_owner()

    def _verify_candidate_owner(self):
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        owner = None
        if 'database_metadata' in tables:
            row = self.connection.execute("SELECT value FROM database_metadata WHERE key='candidate_id'").fetchone()
            owner = row[0] if row else None
        if owner is not None and owner != self.candidate.candidate_id:
            self.connection.close()
            raise ValueError(f'Database belongs to candidate {owner}, not {self.candidate.candidate_id}')
        if owner is None and 'jobs' in tables and self.connection.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]:
            expected_owner = app_settings(self.candidate.root)['legacy_database_owner']
            if self.path != self.candidate.legacy_database_path.resolve() or self.candidate.candidate_id != expected_owner:
                self.connection.close()
                raise ValueError('Existing unowned database is not the configured legacy database; refusing to assign candidate ownership')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    @contextmanager
    def _transaction(self):
        # Serialize read/modify/write decisions across separate local processes.
        self.connection.execute("BEGIN IMMEDIATE")
        with self.connection:
            yield

    def _event(self, job_id, event, details):
        self.connection.execute(
            "INSERT INTO history(job_id,event,details_json,created_at) VALUES(?,?,?,?)",
            (job_id, event, _json(details), _now()),
        )

    def get_job(self, job_id):
        row = self.connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown job: {job_id}")
        result = dict(row)
        result["candidate_id"] = self.candidate.candidate_id
        result["job"] = json.loads(result.pop("job_json"))
        result["screening"] = json.loads(result.pop("screening_json") or "null")
        result["evaluations"] = [
            {**dict(item), "evaluation": json.loads(item["evaluation_json"])}
            for item in self.connection.execute(
                "SELECT * FROM evaluations WHERE job_id=? ORDER BY id", (job_id,)
            )
        ]
        for item in result["evaluations"]:
            item.pop("evaluation_json")
        result["history"] = [
            {"event": item["event"], "details": json.loads(item["details_json"]),
             "created_at": item["created_at"]}
            for item in self.connection.execute(
                "SELECT * FROM history WHERE job_id=? ORDER BY id", (job_id,)
            )
        ]
        return result

    def list_jobs(self, status=None):
        if status is not None and status not in STATUSES:
            raise ValueError("Invalid review status")
        rows = self.connection.execute(
            "SELECT id FROM jobs" + (" WHERE status=?" if status else "") + " ORDER BY id",
            (status,) if status else (),
        ).fetchall()
        return [self.get_job(row["id"]) for row in rows]

    def save_job(self, job: Job, screening=None, scout_score=None, *, expected_new=False,
                 expected_revision=None, expected_updated_at=None):
        data = asdict(job)
        data["discovered_at"] = job.discovered_at.isoformat()
        url = job.job_url.strip().rstrip("/")
        if not url:
            raise ValueError("Job URL is required")
        source = job.source.strip().casefold()
        company = job.company.strip().casefold()
        external_id = str(job.external_job_id) if job.external_job_id is not None else None
        with self._transaction():
            matches = self.connection.execute(
                "SELECT * FROM jobs WHERE job_url=? OR "
                "(source=? AND company_key=? AND external_job_id=?)",
                (url, source, company, external_id),
            ).fetchall()
            if len(matches) > 1:
                raise ValueError("Conflicting job identities; manual reconciliation required")
            if matches and expected_new:
                raise ValueError('This posting was saved since your preview. Preview it again before updating.')
            if matches:
                self._check_review_version(matches[0], expected_revision, expected_updated_at)
            elif expected_revision is not None or expected_updated_at is not None:
                raise ValueError('The posting no longer matches your preview. Preview it again.')
            if not matches:
                cursor = self.connection.execute(
                    "INSERT INTO jobs(job_url,source,company_key,external_job_id,job_json,"
                    "created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    (url, source, company, external_id, _json(data), _now(), _now()),
                )
                job_id = cursor.lastrowid
                self._event(job_id, "discovered", {"job": data, "revision": 1})
            else:
                old = matches[0]
                job_id = old["id"]
                previous = json.loads(old["job_json"])
                # A list refresh may omit date detail captured in an earlier lookup.
                if not data.get('posted_date') and previous.get('posted_date'):
                    data['posted_date'] = previous['posted_date']
                    data['posted_date_kind'] = previous.get('posted_date_kind')
                if not data.get('source_updated_at') and previous.get('source_updated_at'):
                    data['source_updated_at'] = previous['source_updated_at']
                material = _material(previous) != _material(data)
                revision = old["revision"] + int(material)
                status = "New" if material and old["status"] == "Approved to Apply" else old["status"]
                self.connection.execute(
                    "UPDATE jobs SET job_url=?, job_json=?, external_job_id=COALESCE(?,external_job_id),"
                    "revision=?, needs_reevaluation=?, status=?, approved_revision=?, updated_at=? WHERE id=?",
                    (url, _json(data), external_id, revision,
                     1 if material else old["needs_reevaluation"], status,
                     None if material else old["approved_revision"], _now(), job_id),
                )
                if previous != data:
                    self._event(job_id, "material_update" if material else "routine_update", {
                        "previous_job": previous, "job": data, "revision": revision,
                        "previous_status": old["status"], "status": status,
                        "approval_revoked": material and old["approved_revision"] is not None,
                    })
            if screening is not None:
                self.connection.execute(
                    "UPDATE jobs SET screening_json=?,scout_score=? WHERE id=?",
                    (_json(asdict(screening)), scout_score, job_id),
                )
        return job_id

    def save_discovery_screening(self, job_id, result):
        """Persist discovery reasons independently of posting and human review."""
        with self._transaction():
            current = self.get_job(job_id)
            self.connection.execute(
                "INSERT INTO discovery_results(job_id,revision,result_json,screened_at) VALUES(?,?,?,?) "
                "ON CONFLICT(job_id) DO UPDATE SET revision=excluded.revision,"
                "result_json=excluded.result_json,screened_at=excluded.screened_at",
                (job_id, current['revision'], _json(asdict(result)), _now()),
            )

    def review_records(self):
        """Small read-only projection; avoid loading posting audit snapshots for lists."""
        records = []
        for row in self.connection.execute("SELECT * FROM jobs ORDER BY id"):
            item = dict(row)
            item['job'] = json.loads(item.pop('job_json'))
            item['screening'] = json.loads(item.pop('screening_json') or 'null')
            evaluation = self.connection.execute(
                "SELECT revision,evaluation_json,score FROM evaluations WHERE job_id=? ORDER BY id DESC LIMIT 1",
                (item['id'],),
            ).fetchone()
            item['evaluation'] = (dict(evaluation) if evaluation else None)
            if evaluation:
                item['evaluation']['data'] = json.loads(item['evaluation'].pop('evaluation_json'))
            records.append(item)
        return records

    def save_evaluation(self, job_id, evaluation, *, revision):
        """Require the evaluated revision so stale results cannot clear the flag."""
        with self._transaction():
            current = self.get_job(job_id)
            if revision != current["revision"]:
                raise ValueError("Evaluation is for an outdated posting revision")
            self.connection.execute(
                "INSERT INTO evaluations(job_id,revision,evaluation_json,score,created_at) VALUES(?,?,?,?,?)",
                (job_id, revision, _json(evaluation.model_dump(mode="json")),
                 evaluation.score_breakdown.total, _now()),
            )
            self.connection.execute("UPDATE jobs SET needs_reevaluation=0 WHERE id=?", (job_id,))
            self._event(job_id, "evaluated", {"revision": revision})

    def set_status(self, job_id, status, notes="", *, expected_revision=None, expected_updated_at=None):
        if status not in STATUSES:
            raise ValueError("Invalid review status")
        if status == "Approved to Apply":
            raise ValueError("Use explicit approve_job confirmation")
        with self._transaction():
            current = self.get_job(job_id)
            self._check_review_version(current, expected_revision, expected_updated_at)
            self.connection.execute(
                "UPDATE jobs SET status=?,approved_revision=NULL,updated_at=? WHERE id=?",
                (status, _now(), job_id),
            )
            self._event(job_id, "human_decision", {
                "previous_status": current["status"], "status": status, "notes": notes,
                "revision": current["revision"], "candidate_id": self.candidate.candidate_id,
            })

    @staticmethod
    def _check_review_version(current, revision, updated_at):
        if ((revision is not None and revision != current['revision'])
                or (updated_at is not None and updated_at != current['updated_at'])):
            raise ValueError('This record changed since you opened it. Reload and review it again.')

    def add_note(self, job_id, notes, *, expected_revision=None, expected_updated_at=None):
        """Append a human note without changing status or revoking approval."""
        if not isinstance(notes, str) or not notes.strip():
            raise ValueError('Enter a note before saving')
        with self._transaction():
            current = self.get_job(job_id)
            self._check_review_version(current, expected_revision, expected_updated_at)
            self.connection.execute('UPDATE jobs SET updated_at=? WHERE id=?', (_now(), job_id))
            self._event(job_id, 'human_note', {'notes': notes.strip(), 'revision': current['revision'],
                                              'candidate_id': self.candidate.candidate_id})

    def approve_job(self, job_id, *, confirmation, revision, notes=""):
        if confirmation != f"APPROVE {job_id}":
            raise ValueError(f"Explicit confirmation must be APPROVE {job_id}")
        with self._transaction():
            current = self.get_job(job_id)
            if revision != current["revision"]:
                raise ValueError("Posting changed since review; inspect it again")
            if current["needs_reevaluation"]:
                raise ValueError("Posting requires reevaluation before approval")
            self.connection.execute(
                "UPDATE jobs SET status='Approved to Apply',approved_revision=revision,updated_at=? WHERE id=?",
                (_now(), job_id),
            )
            self._event(job_id, "human_decision", {
                "previous_status": current["status"], "status": "Approved to Apply",
                "revision": current["revision"], "notes": notes, "candidate_id": self.candidate.candidate_id,
            })

    def require_job_approval(self, job_id):
        current = self.get_job(job_id)
        if (current["status"] != "Approved to Apply" or current["needs_reevaluation"]
                or current["approved_revision"] != current["revision"]):
            raise PermissionError("Explicit approval for the current job revision is required")

    def require_submission_approval(self, job_id, *, materials_digest):
        """Future submission boundary: fail closed until exact-material approval exists.

        A caller-supplied digest is identity, never proof of human approval.
        Future development must verify a persisted approval binding the job,
        current revision, and digest of the complete application payload.
        """
        self.require_job_approval(job_id)
        raise PermissionError("Exact application materials approval is not implemented; submit manually")
