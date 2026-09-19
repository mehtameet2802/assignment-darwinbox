from __future__ import annotations

from flask import Flask, jsonify

from app.config import (
    APP_VERSION,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    MAX_UPLOAD_BYTES,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
)
from app.database import init_db, ping_db
from app.routes.duplicates import duplicates_bp
from app.routes.mock_target import mock_target_bp
from app.routes.mappings import mappings_bp
from app.routes.migrations import migrations_bp
from app.routes.reviews import reviews_bp
from app.schema import target_schema_summary


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
    init_db()
    app.register_blueprint(migrations_bp)
    app.register_blueprint(mappings_bp)
    app.register_blueprint(reviews_bp)
    app.register_blueprint(duplicates_bp)
    app.register_blueprint(mock_target_bp)

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
