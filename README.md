# Darwinbox Migration Agent

An AI-assisted employee-data migration prototype built with Flask, Streamlit, SQLite and Ollama.

The scope is intentionally narrow: take several messy employee CSV/XLSX exports, reconcile them into one fixed schema, and send the valid records to a mock target system. The interesting part is the decision boundary—routine cleanup should not need approval, but an ambiguous mapping or conflicting employee record should never be guessed silently.

## Architecture

```text
Streamlit supervision UI
        ↓
Flask API → migration services → Ollama mapping proposals
        ↓                         ↓
SQLite state + audit trail   deterministic policy
        ↓
mock target API
```

Ollama supplies semantic interpretation; deterministic application code owns validation, escalation, state transitions, and target writes.

## Autonomy boundary

The working rule is simple: **automate decisions that are safe and explainable; escalate decisions that could silently corrupt client data.**

| Agent handles autonomously | Human review required |
|---|---|
| Type inference and alias fallback | Mapping confidence below `0.80` |
| Mapping with confidence `>= 0.80` and structural compatibility | Structural incompatibility or target-field collision |
| Whitespace/casing/null cleanup and simple full-name splitting | A supplied value that cannot be cleaned safely |
| Unambiguous date normalization | Genuinely ambiguous date format |
| Exact deduplication with combined lineage | Same employee ID with conflicting normalized values |
| Per-record validation and push | Missing required or invalid values |
| Retry only failed records and roll back successful writes from the latest batch | Consultant correction, exclusion, or retry decision |

The model never decides whether it may bypass review. Once a case is escalated, the human owns the final resolution. Record-level failures do not block unrelated valid employees.

`0.80` is an MVP operating cutoff, not a claim that the model is calibrated to an 80% probability of being correct. It is high enough to keep uncertain semantic suggestions in review, while still allowing clear proposals to move without field-by-field confirmation. A score above the cutoff is necessary but never sufficient: type compatibility, target collisions and deterministic validation can still force review. See [docs/OLLAMA.md](docs/OLLAMA.md) for the separate 75% model smoke-test gate.

For the panel-facing one-page explanation and concrete examples, see [docs/APPROACH.md](docs/APPROACH.md).

## Prerequisites

- Python 3.11+
- [Ollama](https://ollama.com) with **`llama3.2:3b`** (locked project model — see [docs/OLLAMA.md](docs/OLLAMA.md))

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

ollama serve
ollama pull llama3.2:3b
.venv/bin/python scripts/verify_ollama.py
```

Optional quality check on golden columns:

```bash
.venv/bin/python scripts/eval_mapping_samples.py
```

## Running the backend

```bash
python flask_app.py
```

Health check: `GET http://127.0.0.1:5000/health`

## Running Streamlit

In a second terminal:

```bash
streamlit run streamlit_app.py
```

Load the four demo files (16 source rows) from `data/demo/`, or use **Load demo files into this migration** on **New migration**. On **Mappings & review**, click **Generate column mappings** (Ollama first, alias fallback if Ollama fails; Ollama should be running for best results).

Genuinely ambiguous date columns always require **human** format confirmation; the model may suggest DD/MM/YYYY or MM/DD/YYYY but never auto-applies a suggestion on ambiguity alone. The bundled `employees_extra.csv` date column auto-resolves safely because `13/09/2024` provides deterministic DD/MM/YYYY evidence. Use `employees_ambiguous_dates.csv` (loaded with the other demo files) to exercise the escalation path: every sample is dual-parse (`03/04/2024`, `05/06/2024`, `07/08/2024`).

## Demo scenario

- `E001`: exact duplicate, automatically collapsed with both source rows retained.
- `E002`: conflicting duplicate email, resolved by a human.
- `E009`: first target call fails with HTTP 500, then succeeds on retry.
- `E010`: invalid email, corrected or excluded.
- `E011`: missing required email, corrected or excluded.
- `E012`–`E014`: a column containing only dual-parse dates, requiring one human format decision for the column.

Rollback is deliberately batch-scoped: it removes only records that the latest push actually created in the target and returns those rows to `READY_TO_PUSH`. A row that previously failed remains `PUSH_FAILED` because there is nothing to delete from the target. The UI separates the **latest operation** from the **migration overall** state so this mixed condition is visible before the consultant chooses **Push ready records** or **Retry failed records**.

## Demo recording

Follow [docs/DEMO_RECORDING.md](docs/DEMO_RECORDING.md) for a single take-home video covering autonomous reconciliation, one human escalation, E009 failure, rollback, selective re-push, retry, and the final audit trail.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

Lint (same as CI):

```bash
ruff check app tests ui app_pages flask_app.py streamlit_app.py scripts
```

API acceptance flow (mocked Ollama via `unittest.mock`):

```bash
pytest -q tests/test_e2e_acceptance.py
```

Streamlit UI smoke tests (headless `AppTest`, mocked backend):

```bash
pytest -q tests/test_streamlit_apptest.py
```

Unit tests mock Ollama; live checks use `scripts/verify_ollama.py` and `scripts/eval_mapping_samples.py`.

## Tech stack

Flask, Streamlit, SQLite, Pandas, Pydantic, Ollama (`llama3.2:3b`), pytest.

## What I would build next

For production use, the next priorities are target-API authentication and idempotency, RBAC, employee-PII encryption and retention controls, background/resumable jobs, and production observability. Product extensions would include schema versioning, reusable client mapping profiles, richer batch/audit search, governed transformation rules, and support for additional entities.
