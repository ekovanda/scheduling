"""Simple authentication endpoint for clinic password protection."""

import functools
import hashlib
import hmac
import os
import secrets
import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["Auth"])

# Static active session secret from env or per-process random fallback
_SESSION_SECRET = os.environ.get("SESSION_SECRET", secrets.token_hex(32))
TOKEN_MAX_AGE_SECONDS = 12 * 3600  # 12-hour session lifetime
AUTH_SALT = "planner-auth-session"


class LoginRequest(BaseModel):
    """Payload containing clinic access password."""

    password: str


class AuthResponse(BaseModel):
    """Authentication result with session token."""

    authenticated: bool
    token: str | None = None
    detail: str | None = None


def get_serializer() -> URLSafeTimedSerializer:
    """Return timed token serializer using active SESSION_SECRET."""
    secret = os.environ.get("SESSION_SECRET") or _SESSION_SECRET
    return URLSafeTimedSerializer(secret_key=secret, salt=AUTH_SALT)


def is_auth_required() -> bool:
    """Return whether authentication is strictly enforced on API routes.

    Defaults to True (fail-closed).
    In local development / testing outside Cloud Run (K_SERVICE is unset), an explicit
    opt-out is allowed via ALLOW_INSECURE_DEV=1 (or AUTH_REQUIRED=false).
    When running in Cloud Run (K_SERVICE is set), authentication is ALWAYS enforced
    and insecure bypass attempts are ignored.
    """
    is_cloud_run = bool(os.environ.get("K_SERVICE"))
    if not is_cloud_run:
        if os.environ.get("ALLOW_INSECURE_DEV", "").strip().lower() in ("1", "true", "yes"):
            return False
        auth_req = os.environ.get("AUTH_REQUIRED")
        if auth_req is not None and auth_req.strip().lower() in ("false", "0", "no"):
            return False
    return True


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Derive scrypt hash (N=16384, r=8, p=1) returning salt:derived_key."""
    if salt is None:
        salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, expected_hash: str) -> bool:
    """Verify password against scrypt hash or backward-compatible SHA-256."""
    if not password or not expected_hash:
        return False
    if ":" in expected_hash:
        try:
            salt_hex, key_hex = expected_hash.split(":", 1)
            salt = bytes.fromhex(salt_hex)
            expected_key = bytes.fromhex(key_hex)
            derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1)
            return secrets.compare_digest(derived, expected_key)
        except Exception:
            return False

    # Legacy SHA-256 fallback
    legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy, expected_hash.strip().lower())


@functools.lru_cache(maxsize=1)
def _memoized_app_password_hash(plain: str) -> str:
    return hash_password(plain)


def get_expected_password_hash() -> str | None:
    """Retrieve expected password hash from environment."""
    stored_hash = os.environ.get("PASSWORD_HASH")
    if stored_hash:
        return stored_hash.strip().lower()
    plain_pw = os.environ.get("APP_PASSWORD")
    if plain_pw:
        return _memoized_app_password_hash(plain_pw)
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
    """Generate a signed, timed HMAC session token valid for 12 hours."""
    expected = get_expected_password_hash()
    if is_auth_required() and not expected:
        raise RuntimeError(
            "Cannot generate auth token: authentication is required but no password is configured."
        )
    serializer = get_serializer()
    stamp = expected[:16] if expected else "dev"
    return serializer.dumps({"role": "planner", "stamp": stamp})


def verify_token(token: str | None) -> bool:
    """Check if token matches serializer signature, is unexpired, and matches current password stamp."""
    if not token:
        return False
    expected_hash = get_expected_password_hash()
    if is_auth_required() and not expected_hash:
        return False

    serializer = get_serializer()
    try:
        data = serializer.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False

    if not isinstance(data, dict) or data.get("role") != "planner":
        return False

    expected_stamp = expected_hash[:16] if expected_hash else "dev"
    if data.get("stamp") != expected_stamp:
        return False

    return True


def _throttle_failed_login() -> None:
    """Introduce short delay on failed login attempts to mitigate brute-force attacks."""
    time.sleep(0.25)


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
    """Validate clinic password and return session token with brute-force throttling."""
    expected_hash = get_expected_password_hash()
    if not expected_hash:
        _throttle_failed_login()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Passwort. Bitte versuchen Sie es erneut.",
        )

    if not verify_password(req.password, expected_hash):
        _throttle_failed_login()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiges Passwort. Bitte versuchen Sie es erneut.",
        )

    return AuthResponse(authenticated=True, token=generate_auth_token())


def require_planner(authorization: Annotated[str | None, Header()] = None) -> bool:
    """Dependency verifying planner authorization.

    In local/test environments (AUTH_REQUIRED=false or ALLOW_INSECURE_DEV=1), permits requests without a token.
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
