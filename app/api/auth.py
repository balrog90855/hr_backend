from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from app.schemas import AuthTokenResponse, LoginRequest, LogoutRequest, MessageResponse, RefreshTokenRequest
from app.security import (
    build_refresh_token,
    create_access_token,
    refresh_token_expiry,
    user_role_from_db,
    verify_password,
)
from app.database import (
    create_refresh_token,
    fetch_refresh_token,
    fetch_user_auth_by_email,
    fetch_user_auth_by_id,
    revoke_refresh_token,
)

BLOCKED_AUTH_STATUSES = {"inactive", "disabled", "locked", "suspended"}

router = APIRouter(prefix="/auth", tags=["auth"])


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: LoginRequest) -> AuthTokenResponse:
    user = fetch_user_auth_by_email(payload.username)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_status = str(user.get("status") or "").strip().lower()
    if int(user.get("is_active") or 0) != 1 or user_status in BLOCKED_AUTH_STATUSES:
        raise HTTPException(status_code=403, detail="User account is inactive")

    if not verify_password(payload.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    role = user_role_from_db(user.get("role"))
    access_token, expires_in = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=role,
    )

    refresh_token = build_refresh_token()
    create_refresh_token(user_id=user["id"], token=refresh_token, expires_at=refresh_token_expiry())

    return AuthTokenResponse(
        access_token=access_token,
        access_token_expires_in=expires_in,
        refresh_token=refresh_token,
    )


@router.post("/token")
def login_for_oauth2(form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, str | int]:
    user = fetch_user_auth_by_email(form_data.username)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    user_status = str(user.get("status") or "").strip().lower()
    if int(user.get("is_active") or 0) != 1 or user_status in BLOCKED_AUTH_STATUSES:
        raise HTTPException(status_code=403, detail="User account is inactive")

    if not verify_password(form_data.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    role = user_role_from_db(user.get("role"))
    access_token, expires_in = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=role,
    )

    refresh_token = build_refresh_token()
    create_refresh_token(user_id=user["id"], token=refresh_token, expires_at=refresh_token_expiry())

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expires_in,
        "refresh_token": refresh_token,
    }


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh_access_token(payload: RefreshTokenRequest) -> AuthTokenResponse:
    token_row = fetch_refresh_token(payload.refresh_token)
    if token_row is None:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if token_row.get("revoked_at") is not None:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    expires_at = datetime.fromisoformat(str(token_row["expires_at"]))
    if expires_at <= _utc_now_naive():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = fetch_user_auth_by_id(token_row["user_id"])
    user_status = str((user or {}).get("status") or "").strip().lower()
    if user is None or int(user.get("is_active") or 0) != 1 or user_status in BLOCKED_AUTH_STATUSES:
        raise HTTPException(status_code=403, detail="User account is inactive")

    role = user_role_from_db(user.get("role"))
    access_token, expires_in = create_access_token(
        user_id=user["id"],
        email=user["email"],
        role=role,
    )

    # Rotate refresh token on every refresh request.
    revoke_refresh_token(payload.refresh_token)
    new_refresh_token = build_refresh_token()
    create_refresh_token(user_id=user["id"], token=new_refresh_token, expires_at=refresh_token_expiry())

    return AuthTokenResponse(
        access_token=access_token,
        access_token_expires_in=expires_in,
        refresh_token=new_refresh_token,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest) -> MessageResponse:
    # Idempotent logout: token is considered logged out whether or not it exists.
    revoke_refresh_token(payload.refresh_token)
    return MessageResponse(detail="Logged out")
