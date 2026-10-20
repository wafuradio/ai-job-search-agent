# AI Job Search Agent

A local Python application for discovering jobs, screening them against a candidate's
preferences, and supporting explicit human review. One codebase serves separate
candidate profiles and SQLite databases. Applications remain manual.

## Set up a private profile

Install Python dependencies from requirements.txt into a virtual environment. Copy
`config/app_config.example.json` to `config/app_config.json`, then create a profile
with the matching example ID (or edit both IDs to a suitable private identifier):

```sh
cp config/app_config.example.json config/app_config.json
.venv/bin/python candidate_profiles.py init --candidate example --display-name "Example Candidate"
```

Complete the files in `profiles/example/` with your own goals, verified evidence,
search rules and sources. Templates are intentionally neutral and unconfigured;
specify at least one target role, Scout role family and an enabled supported discovery
source before validating. Unknown compensation can remain null and unknown experience
can remain an empty list. Do not invent qualifications.

```sh
.venv/bin/python candidate_profiles.py validate --candidate example
.venv/bin/python candidate_profiles.py list
```

All real profiles, local app settings, databases, review notes, exports and local
handoff notes are Git-ignored. Do not force-add them. Only the neutral templates,
synthetic test fixtures and example application configuration are shareable.
See [privacy and history cleanup](docs/privacy.md).

The app settings select the default candidate and separately identify the legacy
database owner. Once data exists, do not change ownership IDs to reassign a database.
The legacy owner uses `data/jobs.db`; other candidates use
`data/candidates/<candidate-id>/jobs.db`. Database checks reject cross-candidate access.
This is local separation, not multiuser authentication. Country screening currently
supports U.S. eligibility only. `AI_JOB_SEARCH_ROOT` can explicitly select an alternate
local configuration/data root; it is primarily used to isolate offline tests.

## Discover jobs

```sh
.venv/bin/python run_discovery.py --candidate example \
  --html output/shortlist.html --remote-html output/remote-shortlist.html \
  --search-html output/broader-searches.html
.venv/bin/python run_discovery.py --candidate example --job-boards-only
.venv/bin/python run_discovery.py --candidate example --company "Example Employer"
```

This runner has no AI evaluation option. It retrieves free public Greenhouse/Ashby
employer feeds and configured Remotive/We Work Remotely feeds, extracts facts, applies
deterministic candidate-specific rules, and saves all returned postings, including
filtered ones. Source failures are reported and cause a nonzero exit; other sources
continue. Missing jobs are not automatically deleted or declared closed.

Configure automatic employer feeds in the selected profile's `company_boards.json`.
Source toggles, `public_job_boards`, role/concept searches, work-model preferences and
other discovery settings live in that candidate's `search_config.json`. Registering
an employer does not verify its board or immediately fetch jobs. Public responses are
cached across candidates for six hours (Remotive) and one hour (WWR), without sending
candidate data. Expired-cache failures are visible; no silent stale fallback is used.
Public feeds may provide only part of a website's inventory.

Search scores and operational/adjacent/specialist/limited review categories are
heuristics, not AI fit verdicts. Relationships do not boost relevance scores.
Known exclusions and explicit source restrictions are respected; missing compensation
is never estimated. "Remote" alone is not U.S. eligibility. Explicit worldwide listings
may reach review with a flag to verify hiring eligibility and description restrictions.

First employer publication, publication/republication, board publication, employer
updates and first local discovery are separately labeled. Dates are informational,
not age filters. Optional `--enrich-dates` makes additional free Greenhouse GETs for
missing first-publication dates on screening survivors. Current-run HTML exports
exclude jobs not retrieved on that run, while old database records remain available.

## Review in the dashboard

After first discovery creates the database:

```sh
.venv/bin/python run_dashboard.py --candidate example
```

Open http://127.0.0.1:8765/ while the command runs; stop it with Ctrl+C. Use a different
`--port` for another candidate. The standard-library server binds to loopback only,
checks Host/Origin and requires a session token for writes. Posting content is rendered
as text. No external requests occur merely by opening or refreshing saved jobs.

- **Opportunities:** inspect full postings, dates, compensation, screening evidence,
  flags and audit history. Mark Interested, Rejected or New and add notes. Rejected
  jobs are hidden from the default shortlist; the status filter keeps them findable.
  New is a review status, not necessarily a recently published job.
- **Add a posting:** copy one full posting from an employer, LinkedIn, Indeed, an alert
  or another source. Preview screening and existing-record status, then confirm saving.
  No URL fetching, account access or JSON editing is needed. Stable LinkedIn/Indeed IDs
  remove common tracking variations.
- **Sources & searches:** add/pause employer sources. Greenhouse/Ashby hosted boards
  join future discovery; other career sites become assisted browser searches. Startup
  boards, LinkedIn/Indeed and unsupported employer sites are not automatically ingested.
  Alert setup guidance is provided, but no inbox is connected.

Refresh saved jobs only reloads SQLite. An on-demand discovery button, run-history
panel and automatic dashboard startup are not implemented. A local weekly automation
can run the discovery command; schedules are workstation-specific and not shipped in
Git. Local scheduled work depends on the host/app and network being available.

## Review history and application approvals

SQLite preserves job descriptions, extracted facts, screening scores/flags, optional
AI evaluations, human decisions, notes and posting revisions. Saving a note alone
preserves status and approval. Dashboard writes and import updates reject stale
versions rather than overwriting concurrent changes.

Stable URLs/source IDs deduplicate repeated postings. Across websites, company/title
matches are possible-duplicate warnings, not automatic merges. Approvals never move
between records or candidates. Posting-date metadata and whitespace changes are routine;
other content changes conservatively require reevaluation and revoke active approval.
Original approval events and older evaluations remain in history. Rejected and Interested
statuses remain intact. Reevaluation never restores approval automatically.

**Applications remain manual.** Interested is not approval to apply. Job approval is
available only through explicit confirmation in the CLI. Any future submission must
verify approval of the specific job/current revision AND approval of the exact application
materials. The submission guard always refuses because materials approval is not built.
See the [human approval policy](docs/decisions/001-human-in-the-loop.md).

```sh
.venv/bin/python review_jobs.py --candidate example shortlist
.venv/bin/python review_jobs.py --candidate example shortlist --status Rejected
.venv/bin/python review_jobs.py --candidate example show 1
.venv/bin/python review_jobs.py --candidate example status 1 Interested --notes "Investigate scope"
.venv/bin/python review_jobs.py --candidate example approve 1
.venv/bin/python calibrate_screening.py --candidate example --output output/calibration.json
```

CLI `--candidate` and optional candidate-owned `--db` arguments precede subcommands.
The approval command displays the record and requires typing its exact confirmation.
The optional advisory [career-gap analysis](docs/career-gap-intelligence.md) and older
AI runners can make paid API calls when explicitly enabled; the default discovery,
dashboard and calibration workflows do not.

## Offline tests

```sh
.venv/bin/python -m pytest -q -p no:cacheprovider
```

Tests create temporary profiles from explicitly synthetic fixtures, override the
configuration root before application imports, and never read real profiles or mutate
real review records. No credentials or live services are required. The fixture salary,
experience and preferences are fictional test inputs, not candidate facts.

Additional references: [architecture](docs/architecture.md),
[screening calibration](docs/screening-calibration.md),
[posting/alert intake](docs/alert-intake.md), and [privacy](docs/privacy.md).
