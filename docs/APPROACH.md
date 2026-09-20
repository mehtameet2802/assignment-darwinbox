# AI-assisted employee migration: approach and autonomy boundary

## Approach

I kept the scope to one realistic migration: messy employee exports, one fixed schema, and a local target API. The hard part was deciding which choices the agent could make safely and which needed a consultant. Streamlit provides supervision; Flask, Pandas/Pydantic and SQLite handle processing, lineage and audit history.

I use Ollama as a proposer, not as the authority. It suggests a mapping with confidence and a reason. Application rules then decide whether that suggestion can proceed or must stop for review.

## What the agent does on its own

The agent handles decisions that are deterministic, reversible, or supported by semantic and structural evidence:

- infer source types and propose mappings across differently shaped files;
- accept mappings only at confidence `>= 0.80` with compatible source and target types;
- fall back to normalized header aliases when Ollama is unavailable or unsafe;
- normalize whitespace, casing, nulls, simple full names, and unambiguous dates;
- collapse exact duplicates while retaining all contributing source-row lineage;
- validate and push each ready employee independently;
- retry only failed pushes and roll back successful writes from the latest batch.

I chose `0.80` as a practical MVP cutoff, not a calibrated probability. It keeps weaker suggestions in review without making the consultant confirm every clear mapping. Structural compatibility and collision checks can still block approval. With client data, I would recalibrate it against a larger labelled set and the cost of a false approval.

Rollback is batch-scoped: successfully created target rows are removed and returned to `READY_TO_PUSH`; a row that never reached the target remains `PUSH_FAILED`. The UI separates the latest operation from migration-wide state, preventing a rollback or re-push from hiding an earlier failure.

## Where I stop and ask

The agent escalates when choosing automatically could silently corrupt client data:

- a mapping is below `0.80`, structurally incompatible, unmapped, or collides with another source column;
- a date column remains genuinely ambiguous;
- records share an employee ID but disagree on normalized values;
- a supplied value cannot be cleaned safely; or
- a required value is missing or validation fails.

The review UI shows the rule, values and file/row lineage. The consultant can map or ignore a column, choose a date format, resolve duplicates, correct a value, or exclude a record. The model cannot approve its own escalation, while other valid employees continue.

Every automatic decision, escalation, human correction, push attempt, retry, and rollback is recorded with actor and reason.

## What the demo proves

- `employees_extra.csv` is safely inferred as DD/MM/YYYY from deterministic evidence, while the dual-parse dates for `E012`–`E014` require one column-level human decision.
- `E001` is automatically deduplicated while retaining both source rows.
- `E002` has conflicting emails and requires field-level human resolution.
- `E010` has an invalid email; `E011` is missing one, so both require correction or exclusion.
- `E009` fails its first target call. Rollback removes only successful writes, re-push sends only returned ready rows, and retry sends only E009, which then succeeds without duplication.

## What I would build next

Production priorities are target authentication and idempotency, RBAC, PII controls, resumable jobs, and observability. Later extensions include schema versioning, reusable mapping profiles, audit search, governed transformations, and more entity types. These were scope cuts so the autonomy boundary and recovery workflow could be completed end to end.
