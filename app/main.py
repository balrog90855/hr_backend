from __future__ import annotations

import logging
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import pkg_resources

from app.api import auth, employees, jobs, nominations, routes, users
from app.database import initialize_database

logger = logging.getLogger(__name__)

# Configure Swagger UI to use local assets (offline-friendly)
swagger_ui_bundle_url = "/static/swagger-ui-bundle.js"
swagger_ui_css_url = "/static/swagger-ui.css"

app = FastAPI(
    title="HR App API",
    version="0.1.0",
    description="FastAPI backend using MySQL",
    swagger_ui_bundle_url=swagger_ui_bundle_url,
    swagger_ui_css_url=swagger_ui_css_url,
    swagger_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# Mount Swagger UI static files from swagger-ui-py package
try:
    swagger_ui_path = pkg_resources.resource_filename("swagger_ui", "static")
    app.mount("/static", StaticFiles(directory=swagger_ui_path), name="static")
    logger.info("Swagger UI mounted from local assets at %s", swagger_ui_path)
except Exception as e:
    logger.warning("Could not mount local Swagger UI assets: %s", e)



@app.on_event("startup")
def startup_initialize_database() -> None:
    for i in range(10):
        try:
            initialize_database()
            logger.info("Database initialized")
            return
        except Exception as e:
            logger.warning("DB not ready yet, retrying... (%s)", e)
            time.sleep(3)

    raise RuntimeError("Database failed to initialize after retries")


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
app.include_router(nominations.router, prefix="/api")