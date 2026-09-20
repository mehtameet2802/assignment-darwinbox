from __future__ import annotations

import requests
import streamlit as st

from app.config import BACKEND_URL


@st.cache_resource
def _session() -> requests.Session:
    session = requests.Session()
    # Avoid reusing dead sockets after Flask restarts (common with FLASK_DEBUG).
    session.headers["Connection"] = "close"
    return session


def _reset_session() -> None:
    _session.clear()


def _request(method: str, path: str, *, timeout: int, **kwargs) -> requests.Response:
    url = f"{BACKEND_URL}{path}"
    last_error: requests.RequestException | None = None
    for attempt in range(2):
        try:
            return _session().request(method, url, timeout=timeout, **kwargs)
        except requests.ConnectionError as exc:
            last_error = exc
            _reset_session()
            if attempt == 0:
                continue
            raise
    if last_error is not None:
        raise last_error
    raise RuntimeError("unreachable")


def api_get(path: str, timeout: int = 10, **kwargs) -> requests.Response:
    return _request("GET", path, timeout=timeout, **kwargs)


def api_post(path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 30)
    return _request("POST", path, timeout=timeout, **kwargs)


def api_patch(path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 10)
    return _request("PATCH", path, timeout=timeout, **kwargs)


def api_delete(path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 10)
    return _request("DELETE", path, timeout=timeout, **kwargs)


def fetch_backend_health() -> tuple[bool, dict]:
    try:
        response = api_get("/health", timeout=2)
        response.raise_for_status()
        return True, response.json()
    except requests.RequestException as exc:
        return False, {"status": "down", "error": str(exc)}


def show_api_error(response: requests.Response | None = None, fallback: str = "Request failed.") -> None:
    if response is None:
        st.error(fallback)
        return
    try:
        payload = response.json()
        st.error(payload.get("error") or fallback)
    except ValueError:
        st.error(fallback)
