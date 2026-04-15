"""
Input validation tests for the HR App backend.

Covers two layers:
  1. Schema tests – Pydantic ValidationErrors raised directly, no HTTP round-trip.
    2. API tests    – FastAPI TestClient sends HTTP requests through the route
                                        layer with database helpers stubbed so validation,
                                        auth, and endpoint wiring are exercised without a live DB.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admin_headers() -> dict[str, str]:
    """Return an Authorization header accepted by require_admin.
    When no env vars are set the security module whitelists 'dev-token'."""
    return {"Authorization": "Bearer dev-token"}


# ===========================================================================
# 1. SCHEMA VALIDATION (pure Pydantic – no DB, no HTTP)
# ===========================================================================

class TestNominationCreateSchema:
    """NominationCreate must reject empty / whitespace-only / too-long inputs."""

    from app.schemas import NominationCreate  # noqa: PLC0415 – class-level OK

    _VALID = dict(
        nominatorName="Alex Johnson",
        nominatorTeam="Engineering",
        nomineeEmployeeId="emp-001",
        nominationText="Always goes above and beyond for the whole team.",
    )

    def _make(self, **overrides):
        from app.schemas import NominationCreate
        return NominationCreate(**{**self._VALID, **overrides})

    def test_valid_data_is_accepted(self):
        nom = self._make()
        assert nom.nominator_name == "Alex Johnson"
        assert nom.nomination_text == "Always goes above and beyond for the whole team."

    def test_whitespace_is_stripped_from_text_fields(self):
        nom = self._make(nominatorName="  Alice  ", nominatorTeam="  Design  ")
        assert nom.nominator_name == "Alice"
        assert nom.nominator_team == "Design"

    def test_empty_nominator_name_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominatorName="")

    def test_whitespace_only_nominator_name_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominatorName="   ")

    def test_nominator_name_exceeding_max_length_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominatorName="A" * 201)

    def test_empty_nominator_team_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominatorTeam="")

    def test_whitespace_only_nominator_team_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominatorTeam="   ")

    def test_empty_nominee_employee_id_raises(self):
        with pytest.raises(ValidationError):
            self._make(nomineeEmployeeId="")

    def test_nomination_text_below_minimum_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominationText="Too short")  # 9 chars

    def test_nomination_text_exactly_9_chars_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominationText="123456789")

    def test_nomination_text_exactly_10_chars_is_accepted(self):
        nom = self._make(nominationText="1234567890")
        assert len(nom.nomination_text) == 10

    def test_whitespace_only_nomination_text_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominationText="          ")

    def test_nomination_text_exceeding_max_length_raises(self):
        with pytest.raises(ValidationError):
            self._make(nominationText="A" * 5001)


class TestEmployeeCreateSchema:
    """EmployeeCreate must reject blank required fields and invalid status values."""

    _VALID = dict(
        fullName="Jane Doe",
        team="engineering",
        location="north",
        status="active",
    )

    def _make(self, **overrides):
        from app.schemas import EmployeeCreate
        return EmployeeCreate(**{**self._VALID, **overrides})

    def test_valid_data_is_accepted(self):
        emp = self._make()
        assert emp.full_name == "Jane Doe"
        assert emp.status == "active"

    def test_whitespace_full_name_is_stripped_then_rejected(self):
        with pytest.raises(ValidationError):
            self._make(fullName="   ")

    def test_empty_full_name_raises(self):
        with pytest.raises(ValidationError):
            self._make(fullName="")

    def test_full_name_exceeding_max_length_raises(self):
        with pytest.raises(ValidationError):
            self._make(fullName="A" * 201)

    def test_whitespace_team_is_stripped_then_rejected(self):
        with pytest.raises(ValidationError):
            self._make(team="   ")

    def test_empty_location_raises(self):
        with pytest.raises(ValidationError):
            self._make(location="")

    def test_invalid_status_raises(self):
        with pytest.raises(ValidationError):
            self._make(status="invalid-status")

    def test_all_valid_statuses_are_accepted(self):
        for s in ("active", "pipeline", "away", "offline"):
            emp = self._make(status=s)
            assert emp.status == s


class TestEmployeeUpdateSchema:
    """EmployeeUpdate must reject empty strings for fields that are provided."""

    def test_all_none_is_accepted(self):
        from app.schemas import EmployeeUpdate
        upd = EmployeeUpdate()
        assert upd.full_name is None

    def test_valid_partial_update_is_accepted(self):
        from app.schemas import EmployeeUpdate
        upd = EmployeeUpdate(fullName="Updated Name", status="away")
        assert upd.full_name == "Updated Name"
        assert upd.status == "away"

    def test_empty_string_full_name_raises(self):
        from app.schemas import EmployeeUpdate
        with pytest.raises(ValidationError):
            EmployeeUpdate(fullName="")

    def test_empty_string_team_raises(self):
        from app.schemas import EmployeeUpdate
        with pytest.raises(ValidationError):
            EmployeeUpdate(team="")

    def test_invalid_status_raises(self):
        from app.schemas import EmployeeUpdate
        with pytest.raises(ValidationError):
            EmployeeUpdate(status="unknown")


class TestUserCreateSchema:
    """UserCreate must enforce email format and minimum password length."""

    _VALID = dict(
        email="user@example.com",
        password="securepassword",
        fullName="New User",
    )

    def _make(self, **overrides):
        from app.schemas import UserCreate
        return UserCreate(**{**self._VALID, **overrides})

    def test_valid_data_is_accepted(self):
        user = self._make()
        assert user.email == "user@example.com"

    def test_missing_at_symbol_raises(self):
        with pytest.raises(ValidationError):
            self._make(email="notanemail")

    def test_missing_domain_raises(self):
        with pytest.raises(ValidationError):
            self._make(email="user@")

    def test_email_with_spaces_raises(self):
        with pytest.raises(ValidationError):
            self._make(email="user @example.com")

    def test_password_shorter_than_8_chars_raises(self):
        with pytest.raises(ValidationError):
            self._make(password="short")

    def test_password_exactly_8_chars_is_accepted(self):
        user = self._make(password="exactly8")
        assert len(user.password) == 8

    def test_empty_full_name_raises(self):
        with pytest.raises(ValidationError):
            self._make(fullName="")


class TestJobCreateSchema:
    """JobCreate must enforce non-empty job_number and job_title."""

    def test_valid_data_is_accepted(self):
        from app.schemas import JobCreate
        job = JobCreate(job_number="J001", job_title="Software Engineer")
        assert job.job_number == "J001"

    def test_empty_job_number_raises(self):
        from app.schemas import JobCreate
        with pytest.raises(ValidationError):
            JobCreate(job_number="", job_title="Software Engineer")

    def test_empty_job_title_raises(self):
        from app.schemas import JobCreate
        with pytest.raises(ValidationError):
            JobCreate(job_number="J001", job_title="")

    def test_job_number_exceeding_max_length_raises(self):
        from app.schemas import JobCreate
        with pytest.raises(ValidationError):
            JobCreate(job_number="J" * 51, job_title="Title")

    def test_job_title_exceeding_max_length_raises(self):
        from app.schemas import JobCreate
        with pytest.raises(ValidationError):
            JobCreate(job_number="J001", job_title="T" * 201)


class TestLoginRequestSchema:
    """LoginRequest must reject empty username or password."""

    def test_valid_credentials_are_accepted(self):
        from app.schemas import LoginRequest
        req = LoginRequest(username="admin@test.com", password="s3cr3t!")
        assert req.username == "admin@test.com"

    def test_empty_username_raises(self):
        from app.schemas import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="password")

    def test_empty_password_raises(self):
        from app.schemas import LoginRequest
        with pytest.raises(ValidationError):
            LoginRequest(username="admin@test.com", password="")


# ===========================================================================
# 2. API ENDPOINT VALIDATION (TestClient + route-level stubs)
# ===========================================================================

@pytest.fixture()
def api_client(monkeypatch):
    """Yield a TestClient with route dependencies stubbed for deterministic tests."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import auth, employees, jobs, nominations, routes, users

    monkeypatch.setattr(employees, "fetch_employees", lambda *args, **kwargs: [])
    monkeypatch.setattr(auth, "fetch_user_auth_by_email", lambda email: None)
    monkeypatch.setattr(nominations, "fetch_employee_by_id", lambda employee_id: None)
    monkeypatch.setattr(nominations, "fetch_nominations", lambda: [])

    fastapi_app = FastAPI()
    fastapi_app.include_router(routes.router, prefix="/api")
    fastapi_app.include_router(auth.router, prefix="/api")
    fastapi_app.include_router(employees.router, prefix="/api")
    fastapi_app.include_router(jobs.router, prefix="/api")
    fastapi_app.include_router(users.router, prefix="/api")
    fastapi_app.include_router(nominations.router, prefix="/api")

    with TestClient(fastapi_app) as client:
        yield client


class TestNominationsEndpoint:
    """POST /api/nominations validation via the HTTP layer."""

    def test_missing_required_fields_returns_422(self, api_client):
        resp = api_client.post("/api/nominations", json={})
        assert resp.status_code == 422

    def test_empty_nominator_name_returns_422(self, api_client):
        resp = api_client.post("/api/nominations", json={
            "nominatorName": "",
            "nominatorTeam": "Engineering",
            "nomineeEmployeeId": "emp-1",
            "nominationText": "A brilliant colleague who always helps others.",
        })
        assert resp.status_code == 422

    def test_short_nomination_text_returns_422(self, api_client):
        resp = api_client.post("/api/nominations", json={
            "nominatorName": "Alex",
            "nominatorTeam": "Engineering",
            "nomineeEmployeeId": "emp-1",
            "nominationText": "Too short",
        })
        assert resp.status_code == 422

    def test_nonexistent_employee_returns_404(self, api_client):
        resp = api_client.post("/api/nominations", json={
            "nominatorName": "Alex",
            "nominatorTeam": "Engineering",
            "nomineeEmployeeId": "does-not-exist",
            "nominationText": "A brilliant colleague who always helps others.",
        })
        assert resp.status_code == 404

    def test_get_nominations_without_auth_returns_401_or_403(self, api_client):
        resp = api_client.get("/api/nominations")
        assert resp.status_code in (401, 403)


class TestEmployeesEndpoint:
    """GET /api/employees query-parameter validation."""

    def test_limit_zero_returns_422(self, api_client):
        resp = api_client.get("/api/employees?limit=0")
        assert resp.status_code == 422

    def test_limit_above_maximum_returns_422(self, api_client):
        resp = api_client.get("/api/employees?limit=501")
        assert resp.status_code == 422

    def test_negative_offset_returns_422(self, api_client):
        resp = api_client.get("/api/employees?offset=-1")
        assert resp.status_code == 422

    def test_valid_query_params_returns_200(self, api_client):
        resp = api_client.get("/api/employees?limit=10&offset=0")
        assert resp.status_code == 200

    def test_create_employee_with_missing_fields_returns_422(self, api_client):
        resp = api_client.post(
            "/api/employees",
            json={"fullName": ""},
            headers=_admin_headers(),
        )
        assert resp.status_code == 422

    def test_create_employee_with_invalid_status_returns_422(self, api_client):
        resp = api_client.post(
            "/api/employees",
            json={
                "fullName": "John Smith",
                "team": "engineering",
                "location": "north",
                "status": "not-a-real-status",
            },
            headers=_admin_headers(),
        )
        assert resp.status_code == 422


class TestAuthEndpoint:
    """POST /api/auth/login validation."""

    def test_empty_username_returns_422(self, api_client):
        resp = api_client.post("/api/auth/login", json={"username": "", "password": "password"})
        assert resp.status_code == 422

    def test_empty_password_returns_422(self, api_client):
        resp = api_client.post("/api/auth/login", json={"username": "user@test.com", "password": ""})
        assert resp.status_code == 422

    def test_wrong_credentials_return_401(self, api_client):
        resp = api_client.post(
            "/api/auth/login",
            json={"username": "nobody@example.com", "password": "wrongpassword"},
        )
        assert resp.status_code == 401


class TestJobsEndpoint:
    """POST /api/jobs/bulk validation."""

    def test_empty_job_number_returns_422(self, api_client):
        resp = api_client.post(
            "/api/jobs/bulk",
            json=[{"job_number": "", "job_title": "Engineer"}],
            headers=_admin_headers(),
        )
        assert resp.status_code == 422

    def test_empty_job_title_returns_422(self, api_client):
        resp = api_client.post(
            "/api/jobs/bulk",
            json=[{"job_number": "J001", "job_title": ""}],
            headers=_admin_headers(),
        )
        assert resp.status_code == 422


class TestAuthRefreshAndLogout:
    """Refresh and logout routes should remain operational after DB changes."""

    def test_refresh_rotates_refresh_token(self, api_client, monkeypatch):
        from app.api import auth

        revoked_tokens = []
        created_tokens = []

        monkeypatch.setattr(auth, "fetch_refresh_token", lambda token: {
            "token": token,
            "user_id": "user-1",
            "revoked_at": None,
            "expires_at": datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        })
        monkeypatch.setattr(auth, "fetch_user_auth_by_id", lambda user_id: {
            "id": user_id,
            "email": "admin@example.com",
            "role": "admin",
            "status": "active",
            "is_active": 1,
        })
        monkeypatch.setattr(auth, "revoke_refresh_token", lambda token: revoked_tokens.append(token) or True)
        monkeypatch.setattr(auth, "build_refresh_token", lambda: "rt_new_token")
        monkeypatch.setattr(auth, "refresh_token_expiry", lambda: datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7))
        monkeypatch.setattr(auth, "create_access_token", lambda user_id, email, role: ("access-token", 1800))
        monkeypatch.setattr(
            auth,
            "create_refresh_token",
            lambda user_id, token, expires_at: created_tokens.append((user_id, token, expires_at)),
        )

        resp = api_client.post("/api/auth/refresh", json={"refresh_token": "rt_old_token"})

        assert resp.status_code == 200
        assert resp.json()["refresh_token"] == "rt_new_token"
        assert revoked_tokens == ["rt_old_token"]
        assert created_tokens and created_tokens[0][0] == "user-1"
        assert created_tokens[0][1] == "rt_new_token"

    def test_logout_revokes_token_idempotently(self, api_client, monkeypatch):
        from app.api import auth

        revoked_tokens = []
        monkeypatch.setattr(auth, "revoke_refresh_token", lambda token: revoked_tokens.append(token) or False)

        resp = api_client.post("/api/auth/logout", json={"refresh_token": "rt_old_token"})

        assert resp.status_code == 200
        assert resp.json() == {"detail": "Logged out"}
        assert revoked_tokens == ["rt_old_token"]


class TestUsersEndpoint:
    """User mutation routes should remain wired after the database change."""

    def test_update_user_returns_updated_row(self, api_client, monkeypatch):
        from app.api import users

        monkeypatch.setattr(users, "update_user", lambda user_id, payload: {
            "id": user_id,
            "employee_id": payload.get("employee_id"),
            "email": payload.get("email", "user@example.com"),
            "fullName": payload.get("fullName", "Updated User"),
            "role": payload.get("role", "employee"),
            "jobTitle": payload.get("jobTitle"),
            "team": payload.get("team"),
            "avatarUrl": payload.get("avatarUrl"),
            "status": payload.get("status", "active"),
            "is_active": payload.get("is_active", 1),
            "last_login_at": None,
        })

        resp = api_client.patch(
            "/api/users/user-1",
            json={"fullName": "Updated User", "status": "active", "is_active": 1},
            headers=_admin_headers(),
        )

        assert resp.status_code == 200
        assert resp.json()["fullName"] == "Updated User"
        assert resp.json()["status"] == "active"

    def test_delete_user_returns_204_when_deleted(self, api_client, monkeypatch):
        from app.api import users

        monkeypatch.setattr(users, "delete_user", lambda user_id: True)

        resp = api_client.delete("/api/users/user-1", headers=_admin_headers())

        assert resp.status_code == 204
        assert resp.text == ""

    def test_delete_all_users_returns_count_message(self, api_client, monkeypatch):
        from app.api import users

        monkeypatch.setattr(users, "delete_all_users", lambda: 3)

        resp = api_client.delete("/api/users", headers=_admin_headers())

        assert resp.status_code == 200
        assert resp.json() == {"detail": "Deleted 3 user(s)"}


class TestSuccessfulNominationEndpoint:
    """Nomination creation should still work with the current helper signature."""

    def test_create_nomination_returns_created_row(self, api_client, monkeypatch):
        from app.api import nominations

        monkeypatch.setattr(nominations, "fetch_employee_by_id", lambda employee_id: {
            "id": employee_id,
            "full_name": "Jane Doe",
        })
        monkeypatch.setattr(nominations, "create_nomination", lambda payload: {
            "id": 7,
            **payload,
            "created_at": "2026-04-15 12:00:00",
        })

        resp = api_client.post(
            "/api/nominations",
            json={
                "nominatorName": "Alex Johnson",
                "nominatorTeam": "Engineering",
                "nomineeEmployeeId": "emp-1",
                "nominationText": "A brilliant colleague who always helps others.",
            },
        )

        assert resp.status_code == 201
        body = resp.json()
        assert body["nomineeName"] == "Jane Doe"
        assert body["createdAt"] == "2026-04-15 12:00:00"
