from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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
    full_name: str
    job_title: str | None = None
    team: str
    location: str
    avatar_url: str | None = None
    status: str


class JobOut(BaseModel):
    job_number: str
    job_title: str
    is_vacant: int


class JobCreate(BaseModel):
    job_number: str
    job_title: str


class BulkJobCreateResponse(BaseModel):
    created: list[JobOut]
    errors: list[dict[str, Any]]


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
    full_name: str = Field(alias="fullName")
    team: str
    location: str
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: str


class EmployeeUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    job_number: str | None = Field(default=None, alias="jobNumber")
    job_title: str | None = Field(default=None, alias="jobTitle")
    full_name: str | None = Field(default=None, alias="fullName")
    team: str | None = None
    location: str | None = None
    avatar_url: str | None = Field(default=None, alias="avatarUrl")
    status: str | None = None


class UserCreate(BaseModel):
    id: str | None = None
    employee_id: str | None = None
    email: str
    password: str
    full_name: str = Field(alias="fullName")
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
    username: str
    password: str


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
