from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, employees, jobs, routes, users
from app.database import (
    DB_PATH,
    get_table_names,
    initialize_database,
    migrate_team_constraints_if_needed,
    migrate_users_employee_link_if_needed,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="HR App API",
    version="0.1.0",
    description="Protected FastAPI layer over existing SQLite HR database",
)


@app.on_event("startup")
def startup_initialize_database() -> None:
    initialize_database()
    migrate_team_constraints_if_needed()
    migrate_users_employee_link_if_needed()
    logger.info("Database ready at %s with tables: %s", DB_PATH, ", ".join(get_table_names()))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(employees.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(users.router, prefix="/api")
