"""Comprehensive route-walking tests for API v1 authentication coverage (Finding A1).

Ensures that every registered endpoint under /api/v1 is strictly protected by
require_planner when AUTH_REQUIRED=true, except the explicitly public health
and auth endpoints.
"""

import re
from typing import Any

import pytest
from starlette.testclient import TestClient

from app.api.main import app
from app.api.v1.auth import generate_auth_token


def _get_api_v1_endpoints() -> list[tuple[str, str]]:
    """Extract all HTTP method and path combinations under /api/v1 from OpenAPI schema."""
    schema = app.openapi()
    endpoints: list[tuple[str, str]] = []
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/api/v1"):
            continue
        for method in methods:
            endpoints.append((method.upper(), path))
    return sorted(endpoints)


API_V1_ENDPOINTS = _get_api_v1_endpoints()


def _is_exempt(path: str) -> bool:
    """Return True if the endpoint is intentionally public."""
    return path.startswith("/api/v1/health") or path.startswith("/api/v1/auth")


def _fill_path_params(path: str) -> str:
    """Replace path parameters with placeholder values."""
    param_replacements = {
        "{staff_id}": "staff_test_id",
        "{absence_id}": "absence_test_id",
        "{preassigned_id}": "preassigned_test_id",
        "{quarter_key}": "2026-Q4",
    }
    result = path
    for placeholder, val in param_replacements.items():
        result = result.replace(placeholder, val)
    # Generic fallback for any remaining {param}
    return re.sub(r"\{[^}]+\}", "placeholder", result)


@pytest.mark.parametrize(("method", "raw_path"), API_V1_ENDPOINTS)
def test_all_api_v1_routes_require_auth_when_enforced(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    raw_path: str,
) -> None:
    """Every endpoint under /api/v1 (except /health and /auth/*) returns 401 without credentials."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("APP_PASSWORD", "test-clinic-secret-123")

    request_path = _fill_path_params(raw_path)

    # Empty payload to prevent 422 where possible, but 401 must precede validation
    kwargs: dict[str, Any] = {}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}

    response = client.request(method, request_path, **kwargs)

    if _is_exempt(raw_path):
        assert response.status_code != 401, (
            f"Exempt route {method} {raw_path} unexpectedly returned 401."
        )
    else:
        assert response.status_code == 401, (
            f"Protected route {method} {raw_path} was accessible without auth (status: {response.status_code})."
        )
        assert response.json().get("detail") == "Authentifizierung als Planer erforderlich."


@pytest.mark.parametrize(
    ("method", "raw_path"), [ep for ep in API_V1_ENDPOINTS if not _is_exempt(ep[1])]
)
def test_protected_routes_accept_valid_bearer_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    raw_path: str,
) -> None:
    """Protected endpoints accept valid planner Bearer token (no 401)."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("APP_PASSWORD", "test-clinic-secret-123")

    token = generate_auth_token()
    headers = {"Authorization": f"Bearer {token}"}
    request_path = _fill_path_params(raw_path)

    kwargs: dict[str, Any] = {"headers": headers}
    if method in ("POST", "PUT", "PATCH"):
        kwargs["json"] = {}

    response = client.request(method, request_path, **kwargs)
    assert response.status_code != 401, (
        f"Protected route {method} {raw_path} rejected a valid session token with 401."
    )
