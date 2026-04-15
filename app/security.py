from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from secrets import compare_digest
from typing import Any

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {token.strip() for token in value.split(",") if token.strip()}


def _token_config() -> tuple[set[str], set[str]]:
    legacy_token = os.getenv("HR_APP_API_TOKEN", "").strip()
    admin_tokens = _parse_tokens(os.getenv("HR_APP_ADMIN_TOKENS"))
    readonly_tokens = _parse_tokens(os.getenv("HR_APP_READONLY_TOKENS"))

    # Backward compatibility: existing single-token setups continue to work.
    if legacy_token:
        admin_tokens.add(legacy_token)

    if not admin_tokens and not readonly_tokens:
        admin_tokens.add("dev-token")

    return admin_tokens, readonly_tokens


def _jwt_secret() -> str:
    return os.getenv("HR_APP_JWT_SECRET", "change-me-dev-secret")


def _access_minutes() -> int:
    return int(os.getenv("HR_APP_ACCESS_TOKEN_MINUTES", "30"))


def _refresh_days() -> int:
    return int(os.getenv("HR_APP_REFRESH_TOKEN_DAYS", "7"))


def _extract_bearer_token(token: str | None) -> str:
    if token is None or not token.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return token


def _token_in_set(token: str, candidates: set[str]) -> bool:
    return any(compare_digest(token, candidate) for candidate in candidates)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), stored_hash.encode("utf-8"))
        except Exception:
            return False
    return compare_digest(plain_password, stored_hash)


def _normalize_role(role: str | None) -> str:
    value = (role or "").strip().lower()
    if not value:
        return "employee"
    return value


def create_access_token(user_id: str, email: str, role: str) -> tuple[str, int]:
    expires_in = _access_minutes() * 60
    now = datetime.now(timezone.utc)
    normalized_role = _normalize_role(role)
    payload = {
        "sub": user_id,
        "email": email,
        "role": normalized_role,
        "typ": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")
    return token, expires_in


def refresh_token_expiry() -> datetime:
    return _utc_now_naive() + timedelta(days=_refresh_days())


def build_refresh_token() -> str:
    random_token = os.urandom(32).hex()
    return f"rt_{random_token}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None
    return payload


def token_role(token: str) -> str | None:
    payload = decode_access_token(token)
    if payload is None:
        return None
    role = payload.get("role")
    if isinstance(role, str):
        return _normalize_role(role)
    # Backward compatibility for already issued tokens.
    roles = payload.get("roles")
    if isinstance(roles, list) and roles:
        return _normalize_role(str(roles[0]))
    return None


def require_auth(
    token: str | None = Depends(oauth2_scheme),
) -> None:
    access_token = _extract_bearer_token(token)
    admin_tokens, readonly_tokens = _token_config()
    if (
        _token_in_set(access_token, admin_tokens)
        or _token_in_set(access_token, readonly_tokens)
        or decode_access_token(access_token) is not None
    ):
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def require_admin(
    token: str | None = Depends(oauth2_scheme),
) -> None:
    access_token = _extract_bearer_token(token)
    admin_tokens, readonly_tokens = _token_config()
    if _token_in_set(access_token, admin_tokens):
        return
    role = token_role(access_token)
    if role == "admin":
        return
    if _token_in_set(access_token, readonly_tokens):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")
    if role is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


def user_role_from_db(role_value: str | None) -> str:
    return _normalize_role(role_value)
