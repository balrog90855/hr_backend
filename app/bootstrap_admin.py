from __future__ import annotations

import os
import sys
from typing import Any

from app.database import create_user, fetch_user_auth_by_email, initialize_database
from app.security import hash_password


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional_env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _bootstrap_payload() -> dict[str, Any]:
    password = _required_env("HR_APP_BOOTSTRAP_ADMIN_PASSWORD")

    return {
        "email": _required_env("HR_APP_BOOTSTRAP_ADMIN_EMAIL"),
        "passwordHash": hash_password(password),
        "fullName": _required_env("HR_APP_BOOTSTRAP_ADMIN_FULL_NAME"),
        "role": "admin",
        "jobTitle": _optional_env("HR_APP_BOOTSTRAP_ADMIN_JOB_TITLE"),
        "team": _optional_env("HR_APP_BOOTSTRAP_ADMIN_TEAM"),
        "status": "active",
        "is_active": True,
    }


def bootstrap_admin_user() -> str:
    payload = _bootstrap_payload()
    existing_user = fetch_user_auth_by_email(payload["email"])

    if existing_user is not None:
        existing_role = str(existing_user.get("role") or "").strip().lower()
        is_active = int(existing_user.get("is_active") or 0) == 1

        if existing_role == "admin" and is_active:
            return f"Bootstrap admin already exists for {payload['email']}."

        raise RuntimeError(
            "A user with the bootstrap admin email already exists but is not an active admin. "
            "Resolve that record manually before retrying."
        )

    create_user(payload)
    return f"Created bootstrap admin user for {payload['email']}."


def main() -> int:
    try:
        initialize_database()
        message = bootstrap_admin_user()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())