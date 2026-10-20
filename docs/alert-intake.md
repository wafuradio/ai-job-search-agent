# Assisted job-board and alert intake

The dashboard's **Add a posting** form accepts one posting copied from an employer
site, LinkedIn, Indeed, an email alert, or another source. It does not fetch a link,
sign into a platform, read an inbox, use AI, or submit an application. Prefer copying
the full original description rather than an alert snippet. Missing facts remain
unknown; do not infer eligibility from the company's headquarters.

Preview shows screening reasons, flags, the normalized posting link, and whether
the record already exists. Saving requires a separate confirmation. It uses the
selected candidate's screening and existing SQLite review/audit safeguards.
Stable LinkedIn/Indeed job identifiers remove common tracking variations. Across
sites, company/title matches are warnings rather than proof of identical vacancies.
Existing rejection and notes are preserved; material changes revoke prior approval.
Concurrent edits require another preview instead of overwriting silently.

## Email alerts

Both platforms support alerts through their own accounts:

- [LinkedIn job alerts](https://www.linkedin.com/help/linkedin/answer/a508396)
  support daily or weekly email notifications.
- [Indeed job alerts](https://support.indeed.com/hc/en-gb/articles/204488890-Starting-stopping-and-managing-Job-Alerts)
  are email notifications based on saved preferences and require an Indeed account.

For now, create or manage alerts on those websites, select an opportunity, then
copy its details into the dashboard. Do not paste account credentials, complete
email headers or unrelated inbox content. Each candidate manages their own alerts.

Automatic email ingestion has been investigated but is **not connected**. A future
implementation should use an authorized email connector, with candidate-specific
mailbox/folder selection, a preview of extracted postings, explicit provenance and
duplicate handling, and safeguards against cross-candidate inbox access. Alert email
formats and abbreviated descriptions are not reliable enough to silently treat as
complete employer postings. No inbox messages were accessed during implementation.

## Employer source management

**Sources & searches** accepts a company/board name and a public HTTPS URL.
Greenhouse and Ashby hosted-board URLs are recognized and added to the candidate's
existing `company_boards.json` automatic `boards` list. The next discovery run reads
the list. Registration does not fetch or verify the board. Unavailable boards are
reported by discovery without deleting old jobs or changing decisions.

Other domains are saved in `career_sites` as assisted searches. Employer career sites can be configured per candidate; new candidate templates
start with an empty assisted list. Lever, custom career sites, LinkedIn and Indeed are not automatically
scraped. An arbitrary employer website is never treated as a working feed solely
because its URL was saved. Source descriptions show the difference in the dashboard.

Pause/enable controls affect future discovery or search generation; they do not
delete saved jobs or human decisions. Config writes use a file lock, a version check
and atomic replacement to preserve other candidate settings and concurrent changes.
Source changes use the same local session-token and origin checks as review writes.
