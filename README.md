# Darwinbox Migration Agent

Local AI-assisted employee-data migration prototype (Flask + Streamlit + SQLite + Ollama).

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

Load demo files from `data/demo/` or use **Load demo files into this migration** on **New migration**. On **Mappings & review**, click **Generate column mappings** (Ollama first, alias fallback if Ollama fails; Ollama should be running for best results).

Ambiguous date columns (for example `employees_extra.csv` / `Date`) always require **human** format confirmation; the model may suggest DD/MM/YYYY or MM/DD/YYYY but will not auto-apply on ambiguity alone.

## Demo recording

Follow [docs/DEMO_RECORDING.md](docs/DEMO_RECORDING.md) for a single take-home video: one escalation resolution, E009 push failure, and retry success.

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
