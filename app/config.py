from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


FLASK_HOST = _env("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(_env("FLASK_PORT", "5000"))
FLASK_DEBUG = _env("FLASK_DEBUG", "true").lower() in {"1", "true", "yes"}

DATABASE_PATH = PROJECT_ROOT / _env("DATABASE_PATH", "data/migration.db")
UPLOAD_DIR = PROJECT_ROOT / _env("UPLOAD_DIR", "data/uploads")

OLLAMA_BASE_URL = _env("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "llama3.1")

BACKEND_URL = _env("BACKEND_URL", f"http://{FLASK_HOST}:{FLASK_PORT}")
APP_VERSION = "0.1.0"
