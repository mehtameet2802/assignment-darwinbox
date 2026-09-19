from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services.mock_target import delete_batch, receive_employee

mock_target_bp = Blueprint("mock_target", __name__)


@mock_target_bp.post("/mock-target/employees")
def post_employee():
    payload = request.get_json(silent=True) or {}
    batch_id = request.headers.get("X-Batch-Id") or payload.get("batch_id") or "default"
    status, body, _error = receive_employee(payload, batch_id=batch_id)
    return jsonify(body), status


@mock_target_bp.delete("/mock-target/batches/<batch_id>")
def delete_batch_route(batch_id: str):
    return jsonify(delete_batch(batch_id))
