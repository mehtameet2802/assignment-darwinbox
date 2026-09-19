from __future__ import annotations

from flask import Flask, jsonify

from app.errors import AppError


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def handle_app_error(exc: AppError):
        return jsonify({"error": exc.message}), exc.status_code
