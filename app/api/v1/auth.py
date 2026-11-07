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


# Default precomputed hash fallback if neither PASSWORD_HASH nor APP_PASSWORD is set in env
# Default clinic planner password: "Trillig2026!"
_DEFAULT_PASSWORD_HASH = hashlib.sha256(b"Trillig2026!").hexdigest()


def is_auth_required() -> bool:
    """Return whether authentication is strictly enforced on API routes."""
    val = os.environ.get("AUTH_REQUIRED", "false").strip().lower()
    return val in ("true", "1", "yes")


def get_expected_password_hash() -> str | None:
    """Retrieve expected password hash from environment."""
    stored_hash = os.environ.get("PASSWORD_HASH")
    if stored_hash:
        return stored_hash.lower()
    plain_pw = os.environ.get("APP_PASSWORD")
    if plain_pw:
        return hashlib.sha256(plain_pw.encode("utf-8")).hexdigest()
    return _DEFAULT_PASSWORD_HASH


def generate_auth_token() -> str:
    """Generate a stable HMAC token verifying authenticated session."""
    expected = get_expected_password_hash() or "unprotected"
    return hmac.new(_SESSION_SECRET.encode("utf-8"), expected.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_token(token: str | None) -> bool:
    """Check if token matches current expected session token."""
    if not token:
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
    input_hash = hashlib.sha256(req.password.encode("utf-8")).hexdigest()

    if expected_hash and hmac.compare_digest(input_hash, expected_hash):
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
