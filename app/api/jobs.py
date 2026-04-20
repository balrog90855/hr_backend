from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas import BulkJobCreateResponse, JobCreate, JobOut, JobVacancySyncRequest, MessageResponse
from app.security import require_admin
from app.database import bulk_create_jobs, delete_all_jobs, fetch_jobs, sync_job_vacancy_states

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_model=list[JobOut])
def list_jobs(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    vacant_only: bool = False,
    search: str | None = None,
) -> list[JobOut]:
    rows = fetch_jobs(
        limit=limit,
        offset=offset,
        vacant_only=vacant_only,
        search=search,
    )
    return [JobOut.model_validate(r) for r in rows]


@router.post("/jobs/bulk", response_model=BulkJobCreateResponse, status_code=status.HTTP_207_MULTI_STATUS)
def bulk_create_jobs_route(
    payload: list[JobCreate],
    _authorized: None = Depends(require_admin),
) -> BulkJobCreateResponse:
    items = [j.model_dump() for j in payload]
    created_rows, errors = bulk_create_jobs(items)
    return BulkJobCreateResponse(
        created=[JobOut.model_validate(r) for r in created_rows],
        errors=errors,
    )


@router.post("/jobs/sync-vacancy", response_model=MessageResponse)
def sync_job_vacancy_route(
    payload: JobVacancySyncRequest | None = None,
    _authorized: None = Depends(require_admin),
) -> MessageResponse:
    job_numbers = None if payload is None or not payload.job_numbers else payload.job_numbers
    sync_job_vacancy_states(job_numbers)

    if job_numbers is None:
        return MessageResponse(detail="Synchronized vacancy flags for all jobs")

    return MessageResponse(detail=f"Synchronized vacancy flags for {len(job_numbers)} job(s)")


@router.delete("/jobs", response_model=MessageResponse)
def delete_all_jobs_route(
    _authorized: None = Depends(require_admin),
) -> MessageResponse:
    count = delete_all_jobs()
    return MessageResponse(detail=f"Deleted {count} job(s)")
