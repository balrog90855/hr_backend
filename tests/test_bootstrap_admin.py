from __future__ import annotations

import pytest


def test_bootstrap_admin_creates_missing_admin(monkeypatch):
    from app import bootstrap_admin

    created_payloads = []

    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_PASSWORD", "super-secret-password")
    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_FULL_NAME", "Initial Admin")
    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_TEAM", "Leadership")
    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_JOB_TITLE", "HR Director")
    monkeypatch.setattr(bootstrap_admin, "fetch_user_auth_by_email", lambda email: None)
    monkeypatch.setattr(bootstrap_admin, "hash_password", lambda password: f"hashed::{password}")
    monkeypatch.setattr(bootstrap_admin, "create_user", lambda payload: created_payloads.append(payload) or payload)

    message = bootstrap_admin.bootstrap_admin_user()

    assert message == "Created bootstrap admin user for admin@example.com."
    assert created_payloads == [{
        "email": "admin@example.com",
        "passwordHash": "hashed::super-secret-password",
        "fullName": "Initial Admin",
        "role": "admin",
        "jobTitle": "HR Director",
        "team": "Leadership",
        "status": "active",
        "is_active": True,
    }]


def test_bootstrap_admin_rejects_existing_non_admin(monkeypatch):
    from app import bootstrap_admin

    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_PASSWORD", "super-secret-password")
    monkeypatch.setenv("HR_APP_BOOTSTRAP_ADMIN_FULL_NAME", "Initial Admin")
    monkeypatch.setattr(bootstrap_admin, "fetch_user_auth_by_email", lambda email: {
        "email": email,
        "role": "employee",
        "is_active": 1,
    })

    with pytest.raises(RuntimeError, match="not an active admin"):
        bootstrap_admin.bootstrap_admin_user()