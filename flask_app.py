from __future__ import annotations

from flask import Flask, jsonify

from app.config import APP_VERSION, FLASK_DEBUG, FLASK_HOST, FLASK_PORT, OLLAMA_BASE_URL, OLLAMA_MODEL
from app.database import init_db, ping_db
from app.schema import target_schema_summary


def create_app() -> Flask:
    app = Flask(__name__)
    init_db()

    @app.get("/health")
    def health():
        db = ping_db()
        return jsonify(
            {
                "status": "ok",
                "service": "darwinbox-migration-agent",
                "version": APP_VERSION,
                "sqlite": db,
                "ollama": {
                    "base_url": OLLAMA_BASE_URL,
                    "model": OLLAMA_MODEL,
                },
            }
        )

    @app.get("/api/target-schema")
    def target_schema():
        return jsonify(target_schema_summary())

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
