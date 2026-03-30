from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import DB_PATH, fetch_rows, get_public_table_names
from app.schemas import GenericRowsResponse, HealthResponse, TableListResponse
from app.security import require_auth

router = APIRouter(tags=["general"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", database=str(DB_PATH))


@router.get("/tables", response_model=TableListResponse, dependencies=[Depends(require_auth)])
def list_tables() -> TableListResponse:
    return TableListResponse(tables=get_public_table_names())


@router.get("/tables/{table_name}", response_model=GenericRowsResponse, dependencies=[Depends(require_auth)])
def list_table_rows(
    table_name: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GenericRowsResponse:
    try:
        rows = fetch_rows(table_name=table_name, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GenericRowsResponse(table=table_name, count=len(rows), rows=rows)
