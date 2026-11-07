"""Unit and integration tests for authentication and planner access control."""

from starlette.testclient import TestClient

from app.api.v1.auth import (
    generate_auth_token,
    get_auth_status,
    is_auth_required,
    verify_token,
)


def test_auth_status_default_is_not_enforced(monkeypatch) -> None:
    """In default development / test environments, authentication is optional."""
    monkeypatch.delenv("AUTH_REQUIRED", raising=False)
    assert not is_auth_required()
    status_resp = get_auth_status()
    assert status_resp["required"] is False


def test_auth_status_enforced_when_configured(monkeypatch) -> None:
    """When AUTH_REQUIRED is set to true, status returns required."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    assert is_auth_required()
    status_resp = get_auth_status()
    assert status_resp["required"] is True


def test_login_flow_with_valid_and_invalid_passwords(client: TestClient) -> None:
    """Login succeeds with default clinic password and fails with invalid input."""
    # Valid login
    res = client.post("/api/v1/auth/login", json={"password": "Trillig2026!"})
    assert res.status_code == 200
    data = res.json()
    assert data["authenticated"] is True
    assert data["token"]
    assert verify_token(data["token"])

    # Invalid login
    res_bad = client.post("/api/v1/auth/login", json={"password": "wrong-password"})
    assert res_bad.status_code == 401
    assert "Ungültiges Passwort" in res_bad.json()["detail"]


def test_verify_session_endpoint(client: TestClient) -> None:
    """GET /api/v1/auth/verify checks session token validity."""
    valid_token = generate_auth_token()
    res = client.get("/api/v1/auth/verify", headers={"Authorization": f"Bearer {valid_token}"})
    assert res.status_code == 200
    assert res.json()["valid"] is True


def test_require_planner_enforcement_when_auth_required(client: TestClient, monkeypatch) -> None:
    """When AUTH_REQUIRED=true, protected endpoints reject unauthenticated requests."""
    monkeypatch.setenv("AUTH_REQUIRED", "true")

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
