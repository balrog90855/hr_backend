from __future__ import annotations

from importlib.resources import files
import logging
import os
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.staticfiles import StaticFiles

from app.api import auth, employees, jobs, nominations, routes, users
from app.database import initialize_database

logger = logging.getLogger(__name__)


def resolve_swagger_ui_path() -> Path:
  vendor_path = Path(str(files("swagger_ui_bundle").joinpath("vendor")))
  required_files = {"swagger-ui.css", "swagger-ui-bundle.js"}

  if not vendor_path.exists():
    raise FileNotFoundError(f"Swagger UI vendor directory not found: {vendor_path}")

  for root, _, filenames in os.walk(vendor_path):
    if required_files.issubset(set(filenames)):
      return Path(root)

  raise FileNotFoundError(
    f"Could not locate Swagger UI assets under vendor directory: {vendor_path}"
  )


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    openapi_schema["openapi"] = "3.0.3"
    openapi_schema.pop("jsonSchemaDialect", None)
    app.openapi_schema = openapi_schema
    return app.openapi_schema

# Configure Swagger UI to use local assets (offline-friendly)
swagger_js_url = "/static/swagger-ui-bundle.js"
swagger_css_url = "/static/swagger-ui.css"
swagger_favicon_url = "/static/favicon-32x32.png"

app = FastAPI(
    title="HR App API",
    version="0.1.0",
    description="FastAPI backend using MySQL",
    docs_url=None,
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.openapi = custom_openapi

# Mount Swagger UI static files from swagger-ui-py package
try:
    swagger_ui_path = resolve_swagger_ui_path()
    app.mount("/static", StaticFiles(directory=str(swagger_ui_path)), name="static")
    logger.info("Swagger UI mounted from local assets at %s", swagger_ui_path)
except Exception as e:
    logger.warning("Could not mount local Swagger UI assets: %s", e)



@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html(request: Request):
    root_path = request.scope.get("root_path", "")
    openapi_url = f"{root_path}{app.openapi_url}"
    return get_swagger_ui_html(
        openapi_url=openapi_url,
        title="HR App API Docs",
        swagger_js_url=swagger_js_url,
        swagger_css_url=swagger_css_url,
        swagger_favicon_url=swagger_favicon_url,
    )



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