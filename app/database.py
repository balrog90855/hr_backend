from __future__ import annotations

import os
import re
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from uuid import uuid4

import pymysql

DB_PATH = f"mysql://{os.getenv('DB_USER', 'root')}@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', 3306)}/{os.getenv('DB_NAME', 'mydb')}"

VALID_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SENSITIVE_TABLES = {"refresh_tokens"}


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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """)

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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (job_number) REFERENCES jobs(job_number) ON DELETE SET NULL
            )
            """)

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
    now = datetime.utcnow()

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
                data.get("is_active", True),
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


def create_refresh_token(user_id: str, token: str, expires_at: datetime) -> None:
    refresh_id = str(uuid4())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO refresh_tokens (id, user_id, token, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (refresh_id, user_id, token, expires_at, datetime.utcnow()))
        conn.commit()


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
            if row and row.get('appraisal_due_date'):
                row['appraisal_due_date'] = row['appraisal_due_date'].strftime('%Y-%m-%d')
            return row


def create_employee(data: dict[str, Any]) -> dict[str, Any]:
    employee_id = data.get("id") or str(uuid4())
    now = datetime.utcnow()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO employees (
                    id, job_number, full_name, team, location,
                    avatar_url, status, service, grade, appraisal_due_date,
                    created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                employee_id,
                data.get("job_number"),
                data["full_name"],
                data["team"],
                data["location"],
                data.get("avatar_url"),
                data["status"],
                data.get("service"),
                data.get("grade"),
                data.get("appraisal_due_date"),
                now,
                now,
            ))
        conn.commit()
        return fetch_employee_by_id(employee_id)


def bulk_create_employees(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    created = []
    errors = []
    for item in items:
        try:
            created.append(create_employee(item))
        except Exception as e:
            errors.append({"detail": f"Failed to create employee {item.get('full_name', 'unknown')}: {e}"})
    return created, errors


def update_employee(employee_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
    if not data:
        return fetch_employee_by_id(employee_id)
    set_parts = []
    params = []
    for key, value in data.items():
        if key == "job_title":
            continue  # Skip job_title
        set_parts.append(f"{key} = %s")
        params.append(value)
    params.append(employee_id)
    query = f"""
        UPDATE employees
        SET {', '.join(set_parts)}, updated_at = %s
        WHERE id = %s
    """
    params.insert(-1, datetime.utcnow())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if cur.rowcount == 0:
                return None
        conn.commit()
        return fetch_employee_by_id(employee_id)


def delete_employee(employee_id: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employees WHERE id = %s", (employee_id,))
            deleted = cur.rowcount > 0
        conn.commit()
        return deleted


def delete_all_employees() -> int:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employees")
            count = cur.rowcount
        conn.commit()
        return count


# 🔹 JOB HELPERS
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
            for row in rows:
                if 'is_vacant' not in row or row['is_vacant'] is None:
                    row['is_vacant'] = 0
            return rows


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
    now = datetime.utcnow()
    is_vacant = data.get("is_vacant", 0)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO jobs (job_number, job_title, is_vacant, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                data["job_number"],
                data["job_title"],
                is_vacant,
                now,
                now,
            ))
        conn.commit()
        return {"job_number": data["job_number"], "job_title": data["job_title"], "is_vacant": is_vacant}


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
            return cur.fetchall()


def create_nomination(data: dict[str, Any]) -> dict[str, Any]:
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
                datetime.utcnow(),
            ))
            nomination_id = cur.lastrowid
        conn.commit()
        return {**data, "id": nomination_id, "created_at": datetime.utcnow()}