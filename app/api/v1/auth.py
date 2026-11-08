"""Simple authentication endpoint for clinic password protection."""

import hashlib
import hmac
import os
import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Auth"])

# Static active session token generated at runtime or secret
_SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))


class LoginRequest(BaseModel):
    """Payload containing clinic access password."""

    password: str


class AuthResponse(BaseModel):
    """Authentication result with session token."""

    authenticated: bool
    token: str | None = None
    detail: str | None = None


def is_auth_required() -> bool:
    """Return whether authentication is strictly enforced on API routes."""
    val = os.environ.get("AUTH_REQUIRED", "false").strip().lower()
    return val in ("true", "1", "yes")


def get_expected_password_hash() -> str | None:
    """Retrieve expected password hash from environment."""
    stored_hash = os.environ.get("PASSWORD_HASH")
    if stored_hash:
        return stored_hash.strip().lower()
    plain_pw = os.environ.get("APP_PASSWORD")
    if plain_pw:
        return hashlib.sha256(plain_pw.encode("utf-8")).hexdigest()
    return None


def validate_auth_config() -> None:
    """Verify authentication configuration.

    Fails closed if authentication is enforced but credentials are missing.

    Raises:
        RuntimeError: If authentication is required (AUTH_REQUIRED=true) but neither
            PASSWORD_HASH nor APP_PASSWORD is configured in the environment.
    """
    if is_auth_required() and not get_expected_password_hash():
        raise RuntimeError(
            "Authentication is required (AUTH_REQUIRED=true) but neither PASSWORD_HASH "
            "nor APP_PASSWORD is configured in the environment. Refusing to start."
        )


def generate_auth_token() -> str:
    """Generate a stable HMAC token verifying authenticated session."""
    expected = get_expected_password_hash()
    if is_auth_required() and not expected:
        raise RuntimeError(
            "Cannot generate auth token: authentication is required but no password is configured."
        )
    expected_str = expected or "unprotected"
    return hmac.new(
        _SESSION_SECRET.encode("utf-8"), expected_str.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_token(token: str | None) -> bool:
    """Check if token matches current expected session token."""
    if not token:
        return False
    expected_hash = get_expected_password_hash()
    if is_auth_required() and not expected_hash:
        return False
    expected = generate_auth_token()
    return hmac.compare_digest(token, expected)


@router.get("/status")
def get_auth_status() -> dict[str, bool]:
    """Check if password authentication is required."""
    return {"required": is_auth_required()}


@router.get("/verify")
def verify_session(authorization: Annotated[str | None, Header()] = None) -> dict[str, bool]:
    """Verify if the provided session token is valid."""
    if not is_auth_required():
        return {"valid": True, "required": False}
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    return {"valid": verify_token(token), "required": True}


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest) -> AuthResponse:
    """Validate clinic password and return session token."""
    expected_hash = get_expected_password_hash()
    if not expected_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Passwort. Bitte versuchen Sie es erneut.",
        )
    input_hash = hashlib.sha256(req.password.encode("utf-8")).hexdigest()

    if hmac.compare_digest(input_hash, expected_hash):
        return AuthResponse(authenticated=True, token=generate_auth_token())

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Ungültiges Passwort. Bitte versuchen Sie es erneut.",
    )


def require_planner(authorization: Annotated[str | None, Header()] = None) -> bool:
    """Dependency verifying planner authorization.

    In local/test environments (AUTH_REQUIRED=false), permits requests without a token.
    In protected/production environments (AUTH_REQUIRED=true), enforces valid session bearer token.
    """
    if not is_auth_required():
        return True

    if not get_expected_password_hash():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung als Planer erforderlich.",
        )

    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if not verify_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentifizierung als Planer erforderlich.",
        )
    return True


require_auth = require_planner
