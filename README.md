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

Load demo files from `data/demo/` or use **Load spec demo files** in the UI. Run deterministic analysis, then **Run Ollama semantic mapping** (Ollama must be running).

## Running tests

```bash
pytest
```

Unit tests mock Ollama; live checks use `scripts/verify_ollama.py` and `scripts/eval_mapping_samples.py`.

## Tech stack

Flask, Streamlit, SQLite, Pandas, Pydantic, Ollama (`llama3.2:3b`), pytest.
