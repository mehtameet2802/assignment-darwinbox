from __future__ import annotations

import requests
import streamlit as st

from app.config import BACKEND_URL


@st.cache_resource
def _session() -> requests.Session:
    return requests.Session()


def api_get(path: str, timeout: int = 10, **kwargs) -> requests.Response:
    return _session().get(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def api_post(path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 30)
    return _session().post(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def api_patch(path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 10)
    return _session().patch(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


def api_delete(path: str, **kwargs) -> requests.Response:
    timeout = kwargs.pop("timeout", 10)
    return _session().delete(f"{BACKEND_URL}{path}", timeout=timeout, **kwargs)


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
