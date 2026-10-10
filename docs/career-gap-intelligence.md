# Career Gap Intelligence — first increment

Career Gap Intelligence adds advisory guidance after a job evaluation. The
existing evaluator, its output format, score weights, recommendation states,
Gatekeeper, and screening pipeline remain unchanged.

## What the reviewer sees

| Type | Meaning | Illustrative response |
| --- | --- | --- |
| Evidence | Existing experience needs stronger proof. | Document an existing MongoDB automation's baseline, personal contribution, and measured savings. |
| Development | A capability could be built through a bounded project. | If systematic AI quality evaluation is not already demonstrated, propose a small reviewed question set for the existing grounded knowledge tool. Capture answer accuracy, unsupported answers, human corrections, and limitations. |
| Structural | A substantial requirement or constraint needs investigation or a career decision. | Ask whether production ML engineering ownership is central to the role; a workflow pilot cannot substitute for years of that experience. |

These are illustrations, not a live job assessment or claims of new completed
work. The analyzer uses the actual posting, completed evaluation, career
profile, and candidate evidence to choose relevant guidance. A supported role
can return no gaps. Missing evidence should prompt questions rather than a
certain claim that a skill is absent.

Each gap includes its requirement, rationale, supporting evidence, confidence,
questions, and next step. Evidence and Development gaps also include a proposed
MongoDB opportunity with steps, evidence to capture, a success measure, and
prerequisites to confirm. Structural gaps have no project opportunity.

Missing information is recorded separately in `open_questions`, with a topic,
reason it remains unresolved, and a question to answer. Unknown residence,
undisclosed total compensation, and ambiguous industry requirements should
not be labeled Structural without evidence of a mismatch. Existing saved
analyses without this field remain readable. These are model instructions;
human review still needs to check that classifications follow them.

Opportunities build on documented Jira workflows, existing automations,
grounded product knowledge tools, integrated analytics, governance, and
cross-functional operations. They do not assume access or approval. Capture
sanitized artifacts; confirm appropriate handling before sharing employer work.
Proposals never become candidate evidence automatically.

## Use with an existing evaluation

```python
from src.career_gaps import analyze_career_gaps

# job is a normalized Job; evaluation is an existing AIJobEvaluation.
intelligence = analyze_career_gaps(job, evaluation)
print(intelligence.model_dump_json(indent=2))
```

This makes one additional model call. It does not rerun scoring. The original
evaluation remains available if the advisory call fails; save it before this
call if you need persistence across process exits.

For a new job, the optional convenience entry point makes two model calls:

```python
from src.career_gaps import evaluate_job_with_career_gaps

result = evaluate_job_with_career_gaps(job)
print(result.evaluation.score_breakdown.total)
print(result.career_gap_intelligence.model_dump_json(indent=2))
```

Both functions use the existing `.env`/OpenAI configuration and default model.
The convenience function raises if either call fails; callers needing partial
results should use the two functions separately. No existing caller opts in
automatically. The absent local `run_live_shortlist.py` can adopt the first
example after its actual implementation is available for inspection.

## Review and validation

Run `.venv/bin/python -m pytest -q` from the repository root. New offline tests
cover all three categories, evidence/action requirements, structured-output
schema compatibility, the additional API call, empty responses, and exact
preservation of the completed evaluation and score through the opt-in path.
Existing tests are kept unchanged. Offline tests cannot establish the quality
of live model classifications; review real outputs before relying on them.

This increment includes no weekly scheduling, applications, or outreach.
