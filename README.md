# Darwinbox Migration Agent

Local AI-assisted employee-data migration prototype (Flask + Streamlit + SQLite).

Phase 1 is bootstrap only: both apps launch and SQLite connects. Ingestion, mapping, review, and push come in later phases.

## Prerequisites

- Python 3.11+
- Ollama (used from Phase 4 onward)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
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

## Running tests

```bash
pytest
```
