from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

DB_PATH = Path(os.getenv("HR_APP_DB_PATH", "mydatabase.db")).resolve()
VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE_TABLES = {"refresh_tokens"}


def _dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = _dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def get_table_names() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [r["name"] for r in rows]


def get_public_table_names() -> list[str]:
    return [t for t in get_table_names() if t not in SENSITIVE_TABLES]


def ensure_valid_table_name(table_name: str, *, allow_sensitive: bool = False) -> None:
    if not VALID_IDENTIFIER.match(table_name):
        raise ValueError("Invalid table name format")
    tables = set(get_table_names() if allow_sensitive else get_public_table_names())
    if table_name not in tables:
        raise ValueError(f"Unknown table: {table_name}")


def initialize_database() -> None:
    """Create required tables when the app starts if they do not exist."""
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_number TEXT PRIMARY KEY,
                job_title TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS employees (
                id TEXT PRIMARY KEY,
                job_number TEXT,
                full_name TEXT NOT NULL,
                team TEXT NOT NULL,
                location TEXT NOT NULL,
                avatar_url TEXT,
                status TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_number)
                    REFERENCES jobs(job_number)
                    ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                employee_id TEXT UNIQUE,
                email TEXT NOT NULL UNIQUE,
                passwordHash TEXT NOT NULL,
                fullName TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                jobTitle TEXT,
                team TEXT,
                avatarUrl TEXT,
                status TEXT DEFAULT 'active',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            );

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                revoked_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_employees_job_number ON employees(job_number);
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_employee_id ON users(employee_id);
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token);
            CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
            """
        )
        conn.commit()


def _has_team_enum_check(create_sql: str | None) -> bool:
    if not create_sql:
        return False
    normalized = re.sub(r"\s+", " ", create_sql).lower()
    return "check (team in" in normalized


def migrate_team_constraints_if_needed() -> None:
    """Relax team columns to allow any string values in users and employees."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name, sql
            FROM sqlite_master
            WHERE type = 'table' AND name IN ('employees', 'users')
            """
        ).fetchall()
        table_sql = {str(row["name"]): row.get("sql") for row in rows}
        needs_migration = any(
            _has_team_enum_check(table_sql.get(table_name))
            for table_name in ("employees", "users")
        )
        if not needs_migration:
            return

        conn.executescript(
            """
            PRAGMA foreign_keys = OFF;
            BEGIN TRANSACTION;

            CREATE TABLE employees_new (
                id TEXT PRIMARY KEY,
                job_number TEXT,
                full_name TEXT NOT NULL,
                team TEXT NOT NULL,
                location TEXT NOT NULL CHECK (location IN ('north', 'south')),
                avatar_url TEXT,
                status TEXT NOT NULL CHECK (status IN ('active', 'away', 'offline')),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_number)
                    REFERENCES jobs(job_number)
                    ON DELETE SET NULL
            );

            INSERT INTO employees_new (
                id, job_number, full_name, team, location, avatar_url, status, created_at, updated_at
            )
            SELECT
                id, job_number, full_name, team, location, avatar_url, status, created_at, updated_at
            FROM employees;

            CREATE TABLE users_new (
                id TEXT PRIMARY KEY,
                employee_id TEXT UNIQUE,
                email TEXT NOT NULL UNIQUE,
                passwordHash TEXT NOT NULL,
                fullName TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
                jobTitle TEXT,
                team TEXT,
                avatarUrl TEXT,
                status TEXT DEFAULT 'active' CHECK (status IN ('active', 'away', 'offline')),
                is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            );

            INSERT INTO users_new (
                id, employee_id, email, passwordHash, fullName, role,
                jobTitle, team, avatarUrl, status, is_active,
                created_at, updated_at, last_login_at
            )
            SELECT
                id, employee_id, email, passwordHash, fullName, role,
                jobTitle, team, avatarUrl, status, is_active,
                created_at, updated_at, last_login_at
            FROM users;

            DROP TABLE users;
            DROP TABLE employees;

            ALTER TABLE employees_new RENAME TO employees;
            ALTER TABLE users_new RENAME TO users;

            COMMIT;
            PRAGMA foreign_keys = ON;
            """
        )


def _users_linked_to_employees(create_sql: str | None) -> bool:
    if not create_sql:
        return False
    normalized = re.sub(r"\s+", " ", create_sql).lower()
    return (
        "foreign key (employee_id) references employees(id)" in normalized
        or "employee_id text not null" in normalized
    )


def migrate_users_employee_link_if_needed() -> None:
    """Make users.employee_id optional and remove dependency on employees."""
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = 'users'
            LIMIT 1
            """
        ).fetchone()
        create_sql = None if row is None else row.get("sql")
        if not _users_linked_to_employees(create_sql):
            return

        conn.executescript(
            """
            PRAGMA foreign_keys = OFF;
            BEGIN TRANSACTION;

            CREATE TABLE users_new (
                id TEXT PRIMARY KEY,
                employee_id TEXT UNIQUE,
                email TEXT NOT NULL UNIQUE,
                passwordHash TEXT NOT NULL,
                fullName TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'employee',
                jobTitle TEXT,
                team TEXT,
                avatarUrl TEXT,
                status TEXT DEFAULT 'active',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            );

            INSERT INTO users_new (
                id, employee_id, email, passwordHash, fullName, role,
                jobTitle, team, avatarUrl, status, is_active,
                created_at, updated_at, last_login_at
            )
            SELECT
                id, employee_id, email, passwordHash, fullName, role,
                jobTitle, team, avatarUrl, status, is_active,
                created_at, updated_at, last_login_at
            FROM users;

            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_employee_id ON users(employee_id);

            COMMIT;
            PRAGMA foreign_keys = ON;
            """
        )


def fetch_rows(table_name: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    ensure_valid_table_name(table_name, allow_sensitive=False)
    query = f"SELECT * FROM {table_name} LIMIT ? OFFSET ?"
    with get_connection() as conn:
        return conn.execute(query, (limit, offset)).fetchall()


def fetch_row_by_id(table_name: str, row_id: str) -> dict[str, Any] | None:
    ensure_valid_table_name(table_name, allow_sensitive=False)
    query = f"SELECT * FROM {table_name} WHERE id = ? LIMIT 1"
    with get_connection() as conn:
        return conn.execute(query, (row_id,)).fetchone()


def _build_filters(base_query: str, where_clauses: list[str], order_clause: str) -> str:
    where_sql = ""
    if where_clauses:
        where_sql = " WHERE " + " AND ".join(where_clauses)
    return f"{base_query}{where_sql} {order_clause} LIMIT ? OFFSET ?"


def migrate_employee_appraisal_fields_if_needed() -> None:
    """Add service, grade, and appraisal_due_date columns to employees if absent."""
    with get_connection() as conn:
        existing_cols = {col["name"] for col in conn.execute("PRAGMA table_info(employees)").fetchall()}
        if all(col in existing_cols for col in ("service", "grade", "appraisal_due_date")):
            return
        if "service" not in existing_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN service TEXT")
        if "grade" not in existing_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN grade TEXT")
        if "appraisal_due_date" not in existing_cols:
            conn.execute("ALTER TABLE employees ADD COLUMN appraisal_due_date TEXT")
        conn.commit()


def fetch_employees(
    limit: int = 50,
    offset: int = 0,
    *,
    status: str | None = None,
    team: str | None = None,
    location: str | None = None,
    service: str | None = None,
    grade: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where: list[str] = []

    if status:
        where.append("e.status = ?")
        params.append(status)
    if team:
        where.append("e.team = ?")
        params.append(team)
    if location:
        where.append("e.location = ?")
        params.append(location)
    if service:
        where.append("e.service = ?")
        params.append(service)
    if grade:
        where.append("e.grade = ?")
        params.append(grade)
    if search:
        where.append("(e.full_name LIKE ? OR COALESCE(j.job_title, '') LIKE ? OR COALESCE(e.job_number, '') LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    query = _build_filters(
        """
        SELECT e.id, e.job_number, e.full_name, j.job_title, e.team,
               e.location, e.avatar_url, e.status,
               e.service, e.grade, e.appraisal_due_date,
               e.created_at, e.updated_at
        FROM employees e
        LEFT JOIN jobs j ON j.job_number = e.job_number
        """,
        where,
        "ORDER BY e.created_at DESC",
    )
    params.extend([limit, offset])
    with get_connection() as conn:
        return conn.execute(query, tuple(params)).fetchall()


def fetch_job_by_number(job_number: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT job_number, job_title, created_at, updated_at
            FROM jobs
            WHERE job_number = ?
            LIMIT 1
            """,
            (job_number,),
        ).fetchone()


def create_job(data: dict[str, Any]) -> dict[str, Any]:
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    job_number = data["job_number"]
    if fetch_job_by_number(job_number) is not None:
        raise ValueError(f"job_number already exists: {job_number}")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_number, job_title, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (job_number, data["job_title"], now, now),
        )
        conn.commit()
    row = fetch_job_by_number(job_number)
    if row is None:
        raise RuntimeError("Failed to create job")
    row.setdefault("is_vacant", 1)
    return row


def bulk_create_jobs(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, data in enumerate(items):
        try:
            row = create_job(data)
            created.append(row)
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "input": data, "detail": str(exc)})
    return created, errors


def _jobs_has_is_vacant_column(conn: sqlite3.Connection) -> bool:
    columns = conn.execute("PRAGMA table_info(jobs)").fetchall()
    return any(col["name"] == "is_vacant" for col in columns)


def _sync_job_vacancy(conn: sqlite3.Connection, job_number: str, now: str) -> None:
    if not _jobs_has_is_vacant_column(conn):
        return

    assigned_count = conn.execute(
        "SELECT COUNT(1) AS cnt FROM employees WHERE job_number = ?",
        (job_number,),
    ).fetchone()
    is_vacant = 0 if int((assigned_count or {}).get("cnt", 0)) > 0 else 1
    conn.execute(
        """
        UPDATE jobs
        SET is_vacant = ?,
            updated_at = ?
        WHERE job_number = ?
        """,
        (is_vacant, now, job_number),
    )


def fetch_jobs(
    limit: int = 50,
    offset: int = 0,
    *,
    vacant_only: bool = False,
    search: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where: list[str] = []

    if search:
        where.append("(j.job_number LIKE ? OR j.job_title LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like])

    if vacant_only:
        where.append(
            "NOT EXISTS (SELECT 1 FROM employees e WHERE e.job_number = j.job_number)"
        )

    where_sql = ""
    if where:
        where_sql = " WHERE " + " AND ".join(where)

    query = (
        """
        SELECT j.job_number, j.job_title, j.created_at, j.updated_at,
               CASE
                   WHEN EXISTS (SELECT 1 FROM employees e WHERE e.job_number = j.job_number)
                   THEN 0
                   ELSE 1
               END AS is_vacant
        FROM jobs j
        """
        + where_sql
        + " ORDER BY j.job_number ASC LIMIT ? OFFSET ?"
    )
    params.extend([limit, offset])

    with get_connection() as conn:
        return conn.execute(query, tuple(params)).fetchall()


def fetch_employee_by_id(employee_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT e.id, e.job_number, e.full_name, j.job_title, e.team,
                   e.location, e.avatar_url, e.status,
                   e.service, e.grade, e.appraisal_due_date,
                   e.created_at, e.updated_at
            FROM employees e
            LEFT JOIN jobs j ON j.job_number = e.job_number
            WHERE e.id = ?
            LIMIT 1
            """,
            (employee_id,),
        ).fetchone()


def create_employee(data: dict[str, Any]) -> dict[str, Any]:
    employee_id = data.get("id") or str(uuid4())
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    job_number = data.get("job_number")
    
    if job_number and fetch_job_by_number(job_number) is None:
        raise ValueError(f"Unknown job_number: {job_number}")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO employees (
                id, job_number, full_name, team, location, avatar_url, status,
                service, grade, appraisal_due_date,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                data.get("created_at") or now,
                data.get("updated_at") or now,
            ),
        )
        if job_number:
            _sync_job_vacancy(conn, job_number, now)
        conn.commit()
    row = fetch_employee_by_id(employee_id)
    if row is None:
        raise RuntimeError("Failed to create employee")
    return row


def update_employee(employee_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    allowed_fields = {
        "job_number",
        "full_name",
        "team",
        "location",
        "avatar_url",
        "status",
        "service",
        "grade",
        "appraisal_due_date",
    }
    clean_updates = {k: v for k, v in updates.items() if k in allowed_fields}
    job_title = updates.get("job_title")
    if not clean_updates and job_title is None:
        return fetch_employee_by_id(employee_id)

    if "job_number" in clean_updates and clean_updates["job_number"] is not None:
        if fetch_job_by_number(clean_updates["job_number"]) is None:
            raise ValueError(f"Unknown job_number: {clean_updates['job_number']}")

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT job_number FROM employees WHERE id = ? LIMIT 1",
            (employee_id,),
        ).fetchone()
    if existing is None:
        return None

    old_job_number = str(existing["job_number"]) if existing["job_number"] else None
    target_job_number = clean_updates.get("job_number", old_job_number)
    if job_title is not None and not target_job_number:
        raise ValueError("Cannot update job_title for an employee without a job_number")

    clean_updates["updated_at"] = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    now = str(clean_updates["updated_at"])
    set_clause = ", ".join(f"{field} = ?" for field in clean_updates)
    params = list(clean_updates.values()) + [employee_id]

    with get_connection() as conn:
        if clean_updates:
            result = conn.execute(
                f"UPDATE employees SET {set_clause} WHERE id = ?",
                tuple(params),
            )
        else:
            result = conn.execute("SELECT 1 FROM employees WHERE id = ?", (employee_id,))

        if job_title is not None:
            conn.execute(
                """
                UPDATE jobs
                SET job_title = ?,
                    updated_at = ?
                WHERE job_number = ?
                """,
                (job_title, now, target_job_number),
            )

        new_job_number = target_job_number
        if new_job_number:
            _sync_job_vacancy(conn, new_job_number, now)
        if old_job_number and new_job_number != old_job_number:
            _sync_job_vacancy(conn, old_job_number, now)
        conn.commit()
        if clean_updates and result.rowcount == 0:
            return None
    return fetch_employee_by_id(employee_id)


def delete_employee(employee_id: str) -> bool:
    with get_connection() as conn:
        existing = conn.execute(
            "SELECT job_number FROM employees WHERE id = ? LIMIT 1",
            (employee_id,),
        ).fetchone()
        if existing is None:
            return False

        now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
        result = conn.execute("DELETE FROM employees WHERE id = ?", (employee_id,))
        _sync_job_vacancy(conn, str(existing["job_number"]), now)
        conn.commit()
        return result.rowcount > 0


def fetch_users(limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    return fetch_users_filtered(limit=limit, offset=offset)


def fetch_users_filtered(
    limit: int = 50,
    offset: int = 0,
    *,
    status: str | None = None,
    team: str | None = None,
    email: str | None = None,
    job_title: str | None = None,
    search: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = []
    where: list[str] = []

    if status:
        where.append("status = ?")
        params.append(status)
    if team:
        where.append("team = ?")
        params.append(team)
    if email:
        where.append("email LIKE ?")
        params.append(f"%{email}%")
    if job_title:
        where.append("jobTitle LIKE ?")
        params.append(f"%{job_title}%")
    if search:
        where.append("(email LIKE ? OR fullName LIKE ? OR jobTitle LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])

    query = _build_filters(
        """
         SELECT id, employee_id, email, fullName, role, jobTitle, team,
               avatarUrl, status, is_active, created_at, updated_at, last_login_at
        FROM users
        """,
        where,
        "ORDER BY created_at DESC",
    )
    params.extend([limit, offset])

    with get_connection() as conn:
        return conn.execute(query, tuple(params)).fetchall()


def fetch_user_by_id(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, employee_id, email, fullName, role, jobTitle, team,
                   avatarUrl, status, is_active, created_at, updated_at, last_login_at
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()


def create_user(data: dict[str, Any]) -> dict[str, Any]:
    user_id = data.get("id") or str(uuid4())
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO users (
                id, employee_id, email, passwordHash, fullName, role, jobTitle, team,
                avatarUrl, status, is_active, created_at, updated_at, last_login_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
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
                data.get("is_active", 1),
                data.get("created_at") or now,
                data.get("updated_at") or now,
                data.get("last_login_at"),
            ),
        )
        conn.commit()

    row = fetch_user_by_id(user_id)
    if row is None:
        raise RuntimeError("Failed to create user")
    return row


def update_user(user_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    allowed_fields = {
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
    clean_updates = {
        k: v
        for k, v in updates.items()
        if k in allowed_fields and (v is not None or k == "employee_id")
    }
    if not clean_updates:
        return fetch_user_by_id(user_id)

    clean_updates["updated_at"] = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    set_clause = ", ".join(f"{field} = ?" for field in clean_updates)
    params = list(clean_updates.values()) + [user_id]

    with get_connection() as conn:
        result = conn.execute(
            f"UPDATE users SET {set_clause} WHERE id = ?",
            tuple(params),
        )
        conn.commit()
        if result.rowcount == 0:
            return None
    return fetch_user_by_id(user_id)


def delete_user(user_id: str) -> bool:
    with get_connection() as conn:
        result = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return result.rowcount > 0


def bulk_create_employees(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Insert multiple employees, collecting per-item errors instead of aborting.

    Returns (created_rows, errors) where each error is
    {"index": int, "input": dict, "detail": str}.
    """
    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for idx, data in enumerate(items):
        try:
            row = create_employee(data)
            created.append(row)
        except Exception as exc:  # noqa: BLE001
            errors.append({"index": idx, "input": data, "detail": str(exc)})
    return created, errors


def delete_all_employees() -> int:
    with get_connection() as conn:
        result = conn.execute("DELETE FROM employees")
        conn.commit()
        return result.rowcount


def delete_all_users() -> int:
    with get_connection() as conn:
        result = conn.execute("DELETE FROM users")
        conn.commit()
        return result.rowcount


def delete_all_jobs() -> int:
    with get_connection() as conn:
        result = conn.execute("DELETE FROM jobs")
        conn.commit()
        return result.rowcount


def fetch_user_auth_by_email(email: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, email, passwordHash, role, status, is_active
            FROM users
            WHERE email = ?
            LIMIT 1
            """,
            (email,),
        ).fetchone()


def fetch_user_auth_by_id(user_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, email, passwordHash, role, status, is_active
            FROM users
            WHERE id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()


def create_refresh_token(user_id: str, token: str, expires_at: datetime) -> dict[str, Any]:
    token_id = str(uuid4())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO refresh_tokens (id, user_id, token, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_id, user_id, token, expires_at.isoformat(sep=" ", timespec="seconds")),
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, user_id, token, expires_at, revoked_at, created_at
            FROM refresh_tokens
            WHERE id = ?
            LIMIT 1
            """,
            (token_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError("Failed to create refresh token")
    return row


def fetch_refresh_token(token: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT id, user_id, token, expires_at, revoked_at, created_at
            FROM refresh_tokens
            WHERE token = ?
            LIMIT 1
            """,
            (token,),
        ).fetchone()


def revoke_refresh_token(token: str) -> bool:
    now = datetime.utcnow().isoformat(sep=" ", timespec="seconds")
    with get_connection() as conn:
        result = conn.execute(
            """
            UPDATE refresh_tokens
            SET revoked_at = ?
            WHERE token = ? AND revoked_at IS NULL
            """,
            (now, token),
        )
        conn.commit()
        return result.rowcount > 0
