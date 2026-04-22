from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_job_number(value: Any, *, blank_to_none: bool) -> Any:
    if not isinstance(value, str):
        return value

    normalized = value.strip()
    if normalized == "" and blank_to_none:
        return None
    return normalized


class HealthResponse(BaseModel):
    status: str
    database: str


class TableListResponse(BaseModel):
    tables: list[str]


class GenericRowsResponse(BaseModel):
    table: str
    count: int
    rows: list[dict[str, Any]]


class EmployeeOut(BaseModel):
    id: str
    job_number: str | None = None
    job_title: str | None = None
    full_name: str
    team: str
    location: str
    avatar_url: str | None = None
    status: str
    service: str | None = None
    grade: str | None = None
    appraisal_due_date: str | None = None
    expected_start: str | None = None
    fad: str | None = None


class JobOut(BaseModel):
    job_number: str
    job_title: str
    is_vacant: int
    is_retained: int = 0


class JobCreate(BaseModel):
    job_number: str = Field(min_length=1, max_length=50)
    job_title: str = Field(min_length=1, max_length=200)
    is_retained: int = Field(default=0, ge=0, le=1)

    @field_validator("job_number", mode="before")
    @classmethod
    def _normalize_job_number(cls, v: Any) -> Any:
        return _normalize_job_number(v, blank_to_none=False)


class BulkJobCreateResponse(BaseModel):
    created: list[JobOut]
    errors: list[dict[str, Any]]


class JobUpdate(BaseModel):
    job_title: str | None = Field(default=None, min_length=1, max_length=200)
    is_retained: int | None = Field(default=None, ge=0, le=1)


class JobVacancySyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_numbers: list[str] | None = Field(default=None, alias="jobNumbers")

    @field_validator("job_numbers", mode="before")
    @classmethod
    def _normalize_job_numbers(cls, v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, list):
            return v
        return [_normalize_job_number(item, blank_to_none=False) for item in v]


class UserOut(BaseModel):
    id: str
    employee_id: str | None = None
    email: str
    full_name: str = Field(alias="fullName")
    role: str
    job_title: str | None = Field(default=None, alias="jobTitle")
    team: str | None = None
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: str | None = None
    is_active: int
    last_login_at: datetime | None = None


class EmployeeCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    job_number: str | None = Field(default=None, alias="jobNumber")
    full_name: str = Field(alias="fullName", min_length=1, max_length=200)
    team: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=100)
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: Literal["active", "pipeline", "away", "offline"]
    service: str | None = None
    grade: str | None = None
    appraisal_due_date: str | None = Field(default=None, alias="appraisalDueDate")
    expected_start: str | None = Field(default=None, alias="expectedStart")
    fad: str | None = Field(default=None, alias="fad")

    @field_validator("full_name", "team", "location", mode="before")
    @classmethod
    def _strip_required_text(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("job_number", mode="before")
    @classmethod
    def _normalize_job_number(cls, v: Any) -> Any:
        return _normalize_job_number(v, blank_to_none=True)


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_number: str | None = Field(default=None, alias="jobNumber")
    full_name: str | None = Field(default=None, alias="fullName", min_length=1, max_length=200)
    team: str | None = Field(default=None, min_length=1, max_length=100)
    location: str | None = Field(default=None, min_length=1, max_length=100)
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: Literal["active", "pipeline", "away", "offline"] | None = None
    service: str | None = None
    grade: str | None = None
    appraisal_due_date: str | None = Field(default=None, alias="appraisalDueDate")
    expected_start: str | None = Field(default=None, alias="expectedStart")
    fad: str | None = Field(default=None, alias="fad")

    @field_validator("job_number", mode="before")
    @classmethod
    def _normalize_job_number(cls, v: Any) -> Any:
        return _normalize_job_number(v, blank_to_none=True)


class UserCreate(BaseModel):
    id: str | None = None
    employee_id: str | None = None
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(min_length=8)
    full_name: str = Field(alias="fullName", min_length=1, max_length=200)
    role: str | None = None
    job_title: str | None = Field(default=None, alias="jobTitle")
    team: str | None = None
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: str | None = None
    is_active: int = 1
    last_login_at: datetime | None = None


class UserUpdate(BaseModel):
    employee_id: str | None = None
    email: str | None = None
    password_hash: str | None = Field(default=None, alias="passwordHash")
    full_name: str | None = Field(default=None, alias="fullName")
    role: str | None = None
    job_title: str | None = Field(default=None, alias="jobTitle")
    team: str | None = None
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: str | None = None
    is_active: int | None = None
    last_login_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class BulkEmployeeCreateResponse(BaseModel):
    created: list[EmployeeOut]
    errors: list[dict[str, Any]]


class MessageResponse(BaseModel):
    detail: str


class AuthTokenResponse(BaseModel):
    token_type: str = "bearer"
    access_token: str
    access_token_expires_in: int
    refresh_token: str


class NominationCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nominator_name: str = Field(alias="nominatorName", min_length=1, max_length=200)
    nominator_team: str = Field(alias="nominatorTeam", min_length=1, max_length=100)
    nominee_employee_id: str = Field(alias="nomineeEmployeeId", min_length=1, max_length=100)
    nomination_text: str = Field(alias="nominationText", min_length=10, max_length=5000)

    @field_validator("nominator_name", "nominator_team", "nomination_text", mode="before")
    @classmethod
    def _strip_text_fields(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v


class NominationOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    nominator_name: str = Field(serialization_alias="nominatorName")
    nominator_team: str = Field(serialization_alias="nominatorTeam")
    nominee_employee_id: str = Field(serialization_alias="nomineeEmployeeId")
    nominee_name: str = Field(serialization_alias="nomineeName")
    nomination_text: str = Field(serialization_alias="nominationText")
    created_at: str = Field(serialization_alias="createdAt")
