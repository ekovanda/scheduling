"""Unit and integration tests for authentication and planner access control."""

import pytest
from starlette.testclient import TestClient

from app.api.main import create_app
from app.api.v1.auth import (
    generate_auth_token,
    get_auth_status,
    is_auth_required,
    validate_auth_config,
    verify_token,
)


def test_auth_status_default_is_not_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """In default development / test environments, authentication is optional."""
    monkeypatch.delenv("AUTH_REQUIRED", raising=False)
    assert not is_auth_required()
    status_resp = get_auth_status()
    assert status_resp["required"] is False


def test_auth_status_enforced_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """When AUTH_REQUIRED is set to true, status returns required."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    assert is_auth_required()
    status_resp = get_auth_status()
    assert status_resp["required"] is True


def test_login_flow_with_valid_and_invalid_passwords(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Login succeeds with configured password and fails with invalid input."""
    monkeypatch.setenv("APP_PASSWORD", "secure-clinic-pw-42")

    # Valid login
    res = client.post("/api/v1/auth/login", json={"password": "secure-clinic-pw-42"})
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["token"]
    assert verify_token(data["token"])

    # Invalid login
    res_bad = client.post("/api/v1/auth/login", json={"password": "wrong-password"})
    assert res_bad.status_code == 401
    assert "Ungültiges Passwort" in res_bad.json()["detail"]


def test_verify_session_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /api/v1/auth/verify checks session token validity."""
    monkeypatch.setenv("APP_PASSWORD", "secure-clinic-pw-42")
    valid_token = generate_auth_token()
    res = client.get("/api/v1/auth/verify", headers={"Authorization": f"Bearer {valid_token}"})
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_require_planner_enforcement_when_auth_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AUTH_REQUIRED=true, protected endpoints reject unauthenticated requests."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("APP_PASSWORD", "secure-clinic-pw-42")

    # 1. Unauthenticated request to protected POST /api/v1/staff
    payload = {
        "id": "tfa_auth_test",
        "identifier": "TAT",
        "name": "Auth Test TFA",
        "beruf": "TFA",
        "abteilung": "station",
        "hours": 40,
    }
    unauth_res = client.post("/api/v1/staff", json=payload)
    assert unauth_res.status_code == 401
    assert "Authentifizierung als Planer erforderlich" in unauth_res.json()["detail"]

    # 2. Request with invalid token
    bad_token_res = client.post(
        "/api/v1/staff",
        json=payload,
        headers={"Authorization": "Bearer bad-token-123"},
    )
    assert bad_token_res.status_code == 401

    # 3. Authenticated request with valid token
    valid_token = generate_auth_token()
    auth_res = client.post(
        "/api/v1/staff",
        json=payload,
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert auth_res.status_code == 201
    assert auth_res.json()["identifier"] == "TAT"


def test_auth_fails_closed_when_auth_required_without_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When AUTH_REQUIRED=true and no password or hash is configured, startup fails closed."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.delenv("PASSWORD_HASH", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)

    with pytest.raises(
        RuntimeError, match="Authentication is required.*neither PASSWORD_HASH nor APP_PASSWORD"
    ):
        validate_auth_config()

    with pytest.raises(
        RuntimeError, match="Authentication is required.*neither PASSWORD_HASH nor APP_PASSWORD"
    ):
        create_app()


def test_login_rejected_when_no_password_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When no password or hash is configured in environment, login attempts fail closed."""
    monkeypatch.delenv("PASSWORD_HASH", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)

    res = client.post("/api/v1/auth/login", json={"password": "any-password"})
    assert res.status_code == 401
    assert "Ungültiges Passwort" in res.json()["detail"]
