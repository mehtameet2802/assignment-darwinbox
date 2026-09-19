from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.cleaning import clean_for_target_field

reviews_bp = Blueprint("reviews", __name__)


@reviews_bp.post("/api/clean/preview")
def clean_preview():
    payload = request.get_json(silent=True) or {}
    field = payload.get("target_field")
    raw = payload.get("raw_value")
    if not field:
        return jsonify({"error": "target_field is required."}), 400
    result = clean_for_target_field(field, raw)
    return jsonify(
        {
            "target_field": field,
            "raw_value": raw,
            "cleaned_value": result.value,
            "ok": result.ok,
            "error": result.error,
        }
    )
