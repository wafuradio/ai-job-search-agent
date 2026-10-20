# Screening calibration

`calibrate_screening.py` reads saved jobs and compares deterministic screening with
persisted results without mutating jobs, human decisions, notes or approvals. Reports
are local/private and should stay under the ignored output directory.

Use explicit candidate selection and review both Interested and Rejected decisions
alongside comments. Identify role-content mismatch, compensation uncertainty, work-model
restrictions, seniority, specialist requirements and career-direction preferences.
Human rejection is not automatically a universal exclusion rule.

Synthetic regression cases cover operational ownership, generic program roles,
specialist tax/engineering requirements, commercial context, explicit quota ownership,
required-versus-preferred qualifications and negation. A generic sales-compensation
footer alone does not establish quota ownership. Program leadership alone does not
establish deep engineering qualifications. Known relationships never boost relevance.

Propose small, explainable candidate-specific changes, compare before/after outcomes
on offline examples, and protect relevant adjacent roles from over-filtering. Categories
and scores are review aids, not a human-labeled accuracy measurement or approval to apply.
Other candidates must not inherit these preferences implicitly. Use only synthetic or
explicitly sanitized examples in committed tests/documentation; keep real review records
and calibration exports local.
