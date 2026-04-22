from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator
from uuid import uuid4

import pymysql

DB_PATH = f"mysql://{os.getenv('DB_USER', 'root')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 3306)}/{os.getenv('DB_NAME', 'mydb')}"

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE_TABLES = {"refresh_tokens"}
USER_MUTABLE_COLUMNS = {
    "employee_id",
    "email",
    "passwordHash",
    "fullName",
    "role",
    "jobTitle",
    "team",
    "avatarUrl",
    "status",
    "is_active",
    "last_login_at",
}


def _normalize_nomination_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    created_at = row.get("created_at")
    if isinstance(created_at, datetime):
        row["created_at"] = created_at.isoformat(sep=" ")
    return row


def _normalize_job_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None

    if row.get("is_vacant") is None:
        row["is_vacant"] = 0

    if row.get("is_retained") is None:
        row["is_retained"] = 0

    return row


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_job_numbers(job_numbers: Iterable[str | None]) -> list[str]:
    unique_job_numbers: list[str] = []
    seen: set[str] = set()

    for job_number in job_numbers:
        if not job_number or job_number in seen:
            continue
        seen.add(job_number)
        unique_job_numbers.append(job_number)

    return unique_job_numbers


def sync_job_vacancy_states(job_numbers: Iterable[str | None] | None = None) -> None:
    normalized_job_numbers = None if job_numbers is None else _normalize_job_numbers(job_numbers)
    if normalized_job_numbers == []:
        return

    where_clause = ""
    params: list[Any] = [_utc_now_naive()]

    if normalized_job_numbers is not None:
        placeholders = ", ".join(["%s"] * len(normalized_job_numbers))
        where_clause = f"WHERE j.job_number IN ({placeholders})"
        params.extend(normalized_job_numbers)

    query = f"""
        UPDATE jobs j
        SET
            is_vacant = CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM employees e
                    WHERE e.job_number = j.job_number
                ) THEN 0
                ELSE 1
            END,
            updated_at = %s
        {where_clause}
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
        conn.commit()


# 🔹 DB CONNECTION
@contextmanager
def get_connection() -> Iterator[pymysql.connections.Connection]:
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "mydb"),
        port=int(os.getenv("DB_PORT", 3306)),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    try:
        yield conn
    finally:
        conn.close()


# 🔹 TABLE INIT
def initialize_database() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_number VARCHAR(255) PRIMARY KEY,
                job_title VARCHAR(255) NOT NULL,
                is_vacant INT DEFAULT 0,
                is_retained INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """)

            cur.execute("SHOW COLUMNS FROM jobs LIKE 'is_retained'")
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE jobs ADD COLUMN is_retained INT DEFAULT 0")

            cur.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id VARCHAR(36) PRIMARY KEY,
                job_number VARCHAR(255),
                full_name VARCHAR(255) NOT NULL,
                team VARCHAR(255) NOT NULL,
                location VARCHAR(50) NOT NULL,
                avatar_url TEXT,
                status VARCHAR(50) NOT NULL,
                service VARCHAR(255),
                grade VARCHAR(255),
                appraisal_due_date DATETIME,
                expected_start DATE,
                fad DATE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (job_number) REFERENCES jobs(job_number) ON DELETE SET NULL
            )
            """)

            cur.execute("SHOW COLUMNS FROM employees LIKE 'expected_start'")
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE employees ADD COLUMN expected_start DATE")

            cur.execute("SHOW COLUMNS FROM employees LIKE 'fad'")
            if cur.fetchone() is None:
                cur.execute("ALTER TABLE employees ADD COLUMN fad DATE")

            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(36) PRIMARY KEY,
                employee_id VARCHAR(36) UNIQUE,
                email VARCHAR(255) NOT NULL UNIQUE,
                passwordHash TEXT NOT NULL,
                fullName VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL DEFAULT 'employee',
                jobTitle VARCHAR(255),
                team VARCHAR(255),
                avatarUrl TEXT,
                status VARCHAR(50) DEFAULT 'active',
                is_active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                last_login_at DATETIME
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                token TEXT NOT NULL,
                expires_at DATETIME NOT NULL,
                revoked_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS nominations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nominator_name VARCHAR(255) NOT NULL,
                nominator_team VARCHAR(255) NOT NULL,
                nominee_employee_id VARCHAR(36) NOT NULL,
                nominee_name VARCHAR(255) NOT NULL,
                nomination_text TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """)

        conn.commit()


# 🔹 BASIC HELPERS
def fetch_user_by_id(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM users WHERE id = %s LIMIT 1
            """, (user_id,))
            return cur.fetchone()


def create_user(data: dict[str, Any]) -> dict[str, Any]:
    user_id = data.get("id") or str(uuid4())
    now = _utc_now_naive()
    is_active = int(data.get("is_active", True))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (
                    id, employee_id, email, passwordHash, fullName,
                    role, jobTitle, team, avatarUrl, status,
                    is_active, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id,
                data.get("employee_id"),
                data["email"],
                data["passwordHash"],
                data["fullName"],
                data.get("role", "employee"),
                data.get("jobTitle"),
                data.get("team"),
                data.get("avatarUrl"),
                data.get("status", "active"),
                is_active,
                now,
                now,
            ))
        conn.commit()

    return fetch_user_by_id(user_id)


def fetch_users(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM users
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            return cur.fetchall()


def fetch_users_filtered(limit: int = 50, offset: int = 0, status: str | None = None, team: str | None = None, email: str | None = None, job_title: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
    conditions = []
    params = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if team:
        conditions.append("team = %s")
        params.append(team)
    if email:
        conditions.append("email LIKE %s")
        params.append(f"%{email}%")
    if job_title:
        conditions.append("jobTitle = %s")
        params.append(job_title)
    if search:
        conditions.append("(fullName LIKE %s OR email LIKE %s OR team LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT * FROM users
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()


def fetch_user_auth_by_email(email: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM users WHERE email = %s LIMIT 1
            """, (email,))
            return cur.fetchone()


def fetch_user_auth_by_id(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM users WHERE id = %s LIMIT 1
            """, (user_id,))
            return cur.fetchone()


def update_user(user_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if not data:
        return fetch_user_by_id(user_id)

    unknown_columns = set(data).difference(USER_MUTABLE_COLUMNS)
    if unknown_columns:
        raise ValueError(f"Unsupported user fields: {', '.join(sorted(unknown_columns))}")

    set_parts = []
    params = []
    for key, value in data.items():
        if key == "is_active" and value is not None:
            value = int(value)
        set_parts.append(f"{key} = %s")
        params.append(value)

    set_parts.append("updated_at = %s")
    params.append(_utc_now_naive())
    params.append(user_id)

    query = f"""
        UPDATE users
        SET {', '.join(set_parts)}
        WHERE id = %s
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.rowcount == 0:
                return None
        conn.commit()
    return fetch_user_by_id(user_id)


def delete_user(user_id: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def delete_all_users() -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM users")
            count = cur.rowcount
        conn.commit()
        return count


def create_refresh_token(user_id: str, token: str, expires_at: datetime) -> None:
    refresh_id = str(uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO refresh_tokens (id, user_id, token, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (refresh_id, user_id, token, expires_at, _utc_now_naive()))
        conn.commit()


def fetch_refresh_token(token: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM refresh_tokens WHERE token = %s LIMIT 1
            """, (token,))
            return cur.fetchone()


def revoke_refresh_token(token: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE refresh_tokens
                SET revoked_at = %s
                WHERE token = %s AND revoked_at IS NULL
            """, (_utc_now_naive(), token))
            revoked = cur.rowcount > 0
        conn.commit()
        return revoked


def get_public_table_names() -> list[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SHOW TABLES
            """)
            tables = cur.fetchall()
            return [list(row.values())[0] for row in tables if list(row.values())[0] not in SENSITIVE_TABLES]


def fetch_rows(table_name: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    if not VALID_IDENTIFIER.match(table_name):
        raise ValueError(f"Invalid table name: {table_name}")
    if table_name in SENSITIVE_TABLES:
        raise ValueError(f"Access denied to table: {table_name}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT * FROM {table_name}
                LIMIT %s OFFSET %s
            """, (limit, offset))
            return cur.fetchall()


# 🔹 EMPLOYEE HELPERS
def fetch_employees(limit: int = 50, offset: int = 0, status: str | None = None, team: str | None = None, location: str | None = None, service: str | None = None, grade: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
    conditions = []
    params = []
    if status:
        conditions.append("status = %s")
        params.append(status)
    if team:
        conditions.append("team = %s")
        params.append(team)
    if location:
        conditions.append("location = %s")
        params.append(location)
    if service:
        conditions.append("service = %s")
        params.append(service)
    if grade:
        conditions.append("grade = %s")
        params.append(grade)
    if search:
        conditions.append("(full_name LIKE %s OR team LIKE %s OR location LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT e.*, j.job_title
        FROM employees e
        LEFT JOIN jobs j ON e.job_number = j.job_number
        WHERE {where_clause}
        ORDER BY e.full_name
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            for row in rows:
                if row.get('appraisal_due_date'):
                    row['appraisal_due_date'] = row['appraisal_due_date'].strftime('%Y-%m-%d')
                if row.get('expected_start'):
                    row['expected_start'] = row['expected_start'].strftime('%Y-%m-%d')
                if row.get('fad'):
                    row['fad'] = row['fad'].strftime('%Y-%m-%d')
            return rows


def fetch_employee_by_id(employee_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT e.*, j.job_title
                FROM employees e
                LEFT JOIN jobs j ON e.job_number = j.job_number
                WHERE e.id = %s LIMIT 1
            """, (employee_id,))
            row = cur.fetchone()
            if row:
                if row.get('appraisal_due_date'):
                    row['appraisal_due_date'] = row['appraisal_due_date'].strftime('%Y-%m-%d')
                if row.get('expected_start'):
                    row['expected_start'] = row['expected_start'].strftime('%Y-%m-%d')
                if row.get('fad'):
                    row['fad'] = row['fad'].strftime('%Y-%m-%d')
            return row


def _create_employee_record(data: dict[str, Any], sync_vacancy: bool) -> dict[str, Any]:
    employee_id = data.get("id") or str(uuid4())
    now = _utc_now_naive()
    job_number = data.get("job_number")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO employees (
                    id, job_number, full_name, team, location,
                    avatar_url, status, service, grade, appraisal_due_date,
                    expected_start, fad,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                employee_id,
                job_number,
                data["full_name"],
                data["team"],
                data["location"],
                data.get("avatar_url"),
                data["status"],
                data.get("service"),
                data.get("grade"),
                data.get("appraisal_due_date"),
                data.get("expected_start"),
                data.get("fad"),
                now,
                now,
            ))
        conn.commit()

    if sync_vacancy:
        sync_job_vacancy_states([job_number])

    row = fetch_employee_by_id(employee_id)
    if row is None:
        raise RuntimeError(f"Failed to load employee after creation: {employee_id}")
    return row


def create_employee(data: dict[str, Any]) -> dict[str, Any]:
    return _create_employee_record(data, sync_vacancy=True)


def bulk_create_employees(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    created = []
    errors = []
    affected_job_numbers: list[str | None] = []
    for item in items:
        try:
            created.append(_create_employee_record(item, sync_vacancy=False))
            affected_job_numbers.append(item.get("job_number"))
        except Exception as e:
            errors.append({"detail": f"Failed to create employee {item.get('full_name', 'unknown')}: {e}"})

    sync_job_vacancy_states(affected_job_numbers)
    return created, errors


def update_employee(employee_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    current_employee = fetch_employee_by_id(employee_id)
    if current_employee is None:
        return None
    if not data:
        return current_employee

    set_parts = []
    params = []
    for key, value in data.items():
        if key == "job_title":
            continue  # Skip job_title
        set_parts.append(f"{key} = %s")
        params.append(value)

    if not set_parts:
        return current_employee

    previous_job_number = current_employee.get("job_number")
    next_job_number = data.get("job_number", previous_job_number)
    params.append(employee_id)
    query = f"""
        UPDATE employees
        SET {', '.join(set_parts)}, updated_at = %s
        WHERE id = %s
    """
    params.insert(-1, _utc_now_naive())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.rowcount == 0:
                return None
        conn.commit()

    sync_job_vacancy_states([previous_job_number, next_job_number])
    return fetch_employee_by_id(employee_id)


def delete_employee(employee_id: str) -> bool:
    current_employee = fetch_employee_by_id(employee_id)
    if current_employee is None:
        return False

    job_number = current_employee.get("job_number")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE id = %s", (employee_id,))
            deleted = cur.rowcount > 0
        conn.commit()

    if deleted:
        sync_job_vacancy_states([job_number])
    return deleted


def delete_all_employees() -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employees")
            count = cur.rowcount
        conn.commit()

    sync_job_vacancy_states()
    return count


# 🔹 JOB HELPERS
def fetch_job_by_number(job_number: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM jobs WHERE job_number = %s LIMIT 1
            """, (job_number,))
            return _normalize_job_row(cur.fetchone())


def fetch_jobs(limit: int = 50, offset: int = 0, vacant_only: bool = False, search: str | None = None) -> list[dict[str, Any]]:
    conditions = []
    params = []
    if vacant_only:
        conditions.append("is_vacant = 1")
    if search:
        conditions.append("(job_number LIKE %s OR job_title LIKE %s)")
        params.extend([f"%{search}%", f"%{search}%"])
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query = f"""
        SELECT * FROM jobs
        WHERE {where_clause}
        ORDER BY job_number
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
            return [_normalize_job_row(row) for row in rows]


def bulk_create_jobs(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    created = []
    errors = []
    for item in items:
        try:
            created.append(create_job(item))
        except Exception as e:
            errors.append({"detail": f"Failed to create job {item.get('job_number', 'unknown')}: {e}"})
    return created, errors


def create_job(data: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now_naive()
    is_retained = int(data.get("is_retained", 0))

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jobs (job_number, job_title, is_vacant, is_retained, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                data["job_number"],
                data["job_title"],
                1,
                is_retained,
                now,
                now,
            ))
        conn.commit()

    sync_job_vacancy_states([data["job_number"]])
    row = fetch_job_by_number(data["job_number"])
    if row is None:
        return {
            "job_number": data["job_number"],
            "job_title": data["job_title"],
            "is_vacant": 1,
            "is_retained": is_retained,
        }
    return row


def update_job(job_number: str, data: dict[str, Any]) -> dict[str, Any] | None:
    mutable_fields = ["job_title", "is_retained"]
    updates: list[str] = []
    params: list[Any] = []

    for field in mutable_fields:
        if field in data:
            updates.append(f"{field} = %s")
            value = int(data[field]) if field == "is_retained" else data[field]
            params.append(value)

    if not updates:
        return fetch_job_by_number(job_number)

    updates.append("updated_at = %s")
    params.append(_utc_now_naive())
    params.append(job_number)

    query = f"""
        UPDATE jobs
        SET {', '.join(updates)}
        WHERE job_number = %s
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            affected = cur.rowcount
        conn.commit()

    if affected == 0:
        return None

    return fetch_job_by_number(job_number)


def delete_job(job_number: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jobs WHERE job_number = %s", (job_number,))
            deleted = cur.rowcount > 0
        conn.commit()

    return deleted


def delete_all_jobs() -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM jobs")
            count = cur.rowcount
        conn.commit()
        return count


# 🔹 NOMINATION HELPERS
def fetch_nominations(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM nominations
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            return [_normalize_nomination_row(row) for row in cur.fetchall()]


def create_nomination(data: dict[str, Any]) -> dict[str, Any]:
    created_at = _utc_now_naive()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO nominations (
                    nominator_name, nominator_team, nominee_employee_id,
                    nominee_name, nomination_text, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                data["nominator_name"],
                data["nominator_team"],
                data["nominee_employee_id"],
                data["nominee_name"],
                data["nomination_text"],
                created_at,
            ))
            nomination_id = cur.lastrowid
        conn.commit()
        return _normalize_nomination_row({**data, "id": nomination_id, "created_at": created_at})