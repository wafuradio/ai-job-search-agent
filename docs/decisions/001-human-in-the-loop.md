# Decision: explicit human approval before application submission

Phase 1 provides local SQLite persistence and a command-line human review tool.
It implements no application submission and no document approval workflow.
Application submission remains manual.

## Job approval

New discoveries start as New. Human review can set New, Interested, or Rejected.
Only the dedicated approval action can set Approved to Apply, after explicit
confirmation identifying the particular local job. Approval is bound to the
current material posting revision. AI scores, recommendation states, and
Interested status never constitute approval.

Human decisions and notes are appended to audit history with UTC timestamps.
Subsequent decisions and revocations do not delete original approvals.
Material posting updates flag reevaluation and invalidate active approval;
previously approved jobs return to New. Interested and Rejected remain as human
preferences while still being flagged. A new evaluation clears the reevaluation
flag without granting approval. Stale evaluations cannot clear the flag.

Routine changes are discovery timestamps, posting dates, source/external-ID/URL
metadata, or whitespace-only changes. Changes to all other normalized posting
fields are conservatively material. This includes title, employer, description,
responsibilities, requirements, compensation, location, work policy, and deadline.
Unknown facts becoming known are material. Semantic text equivalence is not
inferred. The store retains posting changes and evaluations by revision.
SQLite transactions serialize updates and review decisions across processes.

## Future exact application materials approval

Every future application submission must pass a single submission boundary that
verifies BOTH:

1. Explicit human approval for the specific job and its current posting revision,
   with no pending reevaluation or subsequent revocation.
2. A persisted explicit human approval bound to that same job/revision AND the
   exact materials being submitted. This must cover the complete application
   payload: resume, cover letter, attachments, form answers, and any other content
   sent to the employer.

A future implementation must define deterministic payload serialization and a
cryptographic digest, persist the human-approved digest and approval audit event,
and compute and compare the actual payload digest immediately before submission.
Changing any material or answer invalidates its approval. A digest supplied by a
caller, a boolean flag, an AI recommendation, or job approval alone is not proof
that a human approved those materials. Submission must fail closed for missing,
revoked, outdated, mismatched, or unknown approvals and prevent changes between
verification and transmission.

`ReviewStore.require_job_approval` checks ONLY job approval; it must never be used
alone to authorize submission. `ReviewStore.require_submission_approval` is the
future submission guard and currently ALWAYS refuses, even for approved jobs
and supplied materials digests. No method records materials approval in Phase 1.
All future automated/API/browser submission paths must use the complete guard.
Manual actions outside this program cannot be enforced by a local Python guard.

The SQLite audit is local application history, not a tamper-proof security log.

## Candidate scope

Every database is owned by one candidate profile. ReviewStore checks ownership
before review access; a different `--candidate` cannot reuse another person's job
approval via `--db`. New decision audit events include the candidate ID. Existing
events remain intact in the original candidate-owned database. New candidates
start with separate, empty databases and receive no inherited approvals.

The future exact-material approval binding must include candidate identity as
well as database/job identity, posting revision and payload digest. Passing job ID
1 from another candidate's database is never sufficient authorization. Every
candidate configuration must require human approval and prohibit automatic
applications; the current submission guard still always refuses submission.
