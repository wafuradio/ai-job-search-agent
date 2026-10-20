# Local candidate-specific job search

One shared Python implementation serves explicitly selected candidate profiles.
There is no mutable process-wide selected candidate. `get_candidate` resolves the
configured default or a validated ID, checks the complete profile, and returns an
immutable location/identity object. Loaders and workflows accept this object and
pass it through discovery, Scout, Gatekeeper, evaluation, career-gap advice, review,
and report rendering. Missing profiles/files fail clearly, never falling back to
another person's configuration.

`profiles/<id>/` owns goals, verified evidence, discovery rules, company feeds,
relationships and development context. `config/app_config.json` is local, Git-ignored runtime
configuration: default selection and the stable legacy database owner. Neutral
scaffolding is separate under `templates/candidate-profile/`; an unconfigured
scaffold cannot run discovery. Candidate IDs cannot escape the profile directory,
and profile-file symlinks cannot borrow another person's files.

Public Greenhouse/Ashby adapters return factual postings. Deterministic discovery
uses only the selected candidate's preferences, stores all fetched jobs and
screening metadata, and never changes human decisions except the preexisting
material-posting-change approval revocation. AI evaluation is a separate optional
call using only that candidate's context. Career-gap proposals use generic shared
instructions plus candidate-specific work context. AI judgment never grants approval.

Each candidate has a distinct SQLite database. the configured candidate retains the legacy database
at `data/jobs.db`; additional candidates use `data/candidates/<id>/jobs.db`.
ReviewStore verifies a stored candidate owner before reading or mutating the
review tables. A populated database without ownership is accepted only at the
configured legacy path for its configured owner. First writable opening adds
owner metadata; read-only opening performs no migration. This preserves existing
IDs, evaluations, statuses and audit events and prevents a wrong `--db` from mixing
candidate records. Local file owners can still edit files; this is not an
identity/authentication service.

Approval is scoped to a candidate-owned database, job, and current posting revision.
Future submission must additionally verify explicit approval of the exact material
payload. Submission is absent and its guard fails closed. See the human-in-the-loop
decision for the complete policy.

Commands select `--candidate <id>`; omission uses the configured default. Browser
reports are read-only snapshots labeled with candidate identity. Candidate-specific
review commands include both profile and database path to avoid ambiguous job IDs.
The profile format is ready for a future validated intake importer, not yet a UI
form or spreadsheet import workflow.

Discovery geography and the validated score-category maxima retain the current
U.S./100-point V1 contract. The legacy AI relevance field is interpreted as the
selected candidate's domain relevance. No fresh network discovery, paid calls,
real human decisions, or Git commits are part of the candidate refactor.
