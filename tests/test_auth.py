"""Unit and integration tests for authentication, tokens, and path security (Findings A3, A4, A5)."""

from pathlib import Path

import pytest
from itsdangerous import SignatureExpired
from starlette.testclient import TestClient

from app.api.main import create_app
from app.api.v1.auth import (
    generate_auth_token,
    get_auth_status,
    get_serializer,
    hash_password,
    is_auth_required,
    validate_auth_config,
    verify_password,
    verify_token,
)
from app.persistence.repository import FileJsonRepository, _safe_path

# -----------------------------------------------------------------------------
# A3: Fail-Closed Auth Default & Cloud Run Bypass Prevention
# -----------------------------------------------------------------------------


def test_auth_status_defaults_to_enforced_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authentication defaults to enforced (fail-closed) when environment is unconfigured."""
    monkeypatch.delenv("ALLOW_INSECURE_DEV", raising=False)
    monkeypatch.delenv("AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert is_auth_required() is True
    status_resp = get_auth_status()
    assert status_resp["required"] is True


def test_auth_status_allows_insecure_dev_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    """Outside Cloud Run, ALLOW_INSECURE_DEV=1 or AUTH_REQUIRED=false enables dev bypass."""
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "1")
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert is_auth_required() is False
    status_resp = get_auth_status()
    assert status_resp["required"] is False


def test_auth_status_ignores_insecure_dev_on_cloud_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """In Cloud Run (K_SERVICE set), auth is strictly enforced and dev bypass is ignored (A3)."""
    monkeypatch.setenv("K_SERVICE", "dienstplan-dev")
    monkeypatch.setenv("ALLOW_INSECURE_DEV", "1")
    monkeypatch.setenv("AUTH_REQUIRED", "false")
    assert is_auth_required() is True
    status_resp = get_auth_status()
    assert status_resp["required"] is True


# -----------------------------------------------------------------------------
# A4: Timed Tokens, Password Rotation Stamp & Scrypt Hashes
# -----------------------------------------------------------------------------


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


def test_timed_token_expiration_and_tampering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Session tokens enforce max_age expiration and reject tampering (A4)."""
    monkeypatch.setenv("APP_PASSWORD", "clinic-secret")
    token = generate_auth_token()
    assert verify_token(token) is True

    # Tampered token
    tampered = token[:-4] + "xxxx"
    assert verify_token(tampered) is False

    # Expired token: simulate by loading with negative max_age via serializer
    serializer = get_serializer()
    expired_token = serializer.dumps({"role": "planner", "stamp": "dev"})
    # Verify expired check logic
    with pytest.raises(SignatureExpired):
        serializer.loads(expired_token, max_age=-1)


def test_token_revocation_on_password_change(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tokens minted under password A become invalid when the password rotates to B (A4)."""
    monkeypatch.setenv("APP_PASSWORD", "first-password")
    token = generate_auth_token()
    assert verify_token(token) is True

    # Rotate password
    monkeypatch.setenv("APP_PASSWORD", "rotated-password-2026")
    assert verify_token(token) is False


def test_scrypt_and_legacy_sha256_verification() -> None:
    """verify_password handles both scrypt hashes and legacy sha256 hashes (A4)."""
    scrypt_hash = hash_password("secret-pw")
    assert ":" in scrypt_hash
    assert verify_password("secret-pw", scrypt_hash) is True
    assert verify_password("wrong-pw", scrypt_hash) is False

    # Legacy SHA-256 fallback
    import hashlib

    legacy_sha = hashlib.sha256(b"legacy-pw").hexdigest()
    assert verify_password("legacy-pw", legacy_sha) is True
    assert verify_password("wrong-pw", legacy_sha) is False


def test_require_planner_enforcement_when_auth_required(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When AUTH_REQUIRED=true, protected endpoints reject unauthenticated requests."""
    monkeypatch.delenv("ALLOW_INSECURE_DEV", raising=False)
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("APP_PASSWORD", "secure-clinic-pw-42")

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

    bad_token_res = client.post(
        "/api/v1/staff",
        json=payload,
        headers={"Authorization": "Bearer bad-token-123"},
    )
    assert bad_token_res.status_code == 401

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
    monkeypatch.delenv("ALLOW_INSECURE_DEV", raising=False)
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


# -----------------------------------------------------------------------------
# A5: Path Traversal Prevention
# -----------------------------------------------------------------------------


def test_safe_path_helper_guards_against_traversal(tmp_path: Path) -> None:
    """_safe_path rejects directory traversal attempts and malformed IDs (A5)."""
    base_dir = tmp_path / "records"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Valid IDs
    assert _safe_path(base_dir, "staff-01") == (base_dir / "staff-01.json").resolve()
    assert _safe_path(base_dir, "STAFF_2026") == (base_dir / "STAFF_2026.json").resolve()

    # Traversal attempts
    with pytest.raises(ValueError, match="Invalid record identifier format"):
        _safe_path(base_dir, "../../etc/passwd")

    with pytest.raises(ValueError, match="Invalid record identifier format"):
        _safe_path(base_dir, "../escape")

    with pytest.raises(ValueError, match="Invalid record identifier format"):
        _safe_path(base_dir, "id/with/slash")

    with pytest.raises(ValueError, match="Invalid record identifier format"):
        _safe_path(base_dir, "")


def test_file_json_repository_safe_path_integration(tmp_path: Path) -> None:
    """FileJsonRepository methods reject path traversal IDs (A5)."""
    repo = FileJsonRepository(base_dir=tmp_path / "test_repo")

    with pytest.raises(ValueError, match="Invalid record identifier format"):
        repo.get_staff("../../outside")

    with pytest.raises(ValueError, match="Invalid record identifier format"):
        repo.get_absence("../evil_absence")

    with pytest.raises(ValueError, match="Invalid record identifier format"):
        repo.delete_staff("../delete_outside")


def test_api_rejects_path_traversal_on_id_parameters(client: TestClient) -> None:
    """FastAPI rejects path traversal attempts on ID parameters with 404 or 422 (A5)."""
    # URL encoded traversal or slash in path parameter
    res = client.get("/api/v1/staff/..%2F..%2Fetc%2Fpasswd")
    assert res.status_code in (404, 422)

    res_post = client.post(
        "/api/v1/staff",
        json={
            "id": "../../traversal_id",
            "identifier": "TRV",
            "name": "Traversal Test",
            "hours": 40,
        },
    )
    # Model regex validation catches traversal in payload
    assert res_post.status_code == 422
