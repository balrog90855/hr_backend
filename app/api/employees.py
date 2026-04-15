from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status


from app.schemas import BulkEmployeeCreateResponse, EmployeeCreate, EmployeeOut, EmployeeUpdate, MessageResponse
from app.security import require_admin, require_auth
from app.database import (
    bulk_create_employees,
    create_employee,
    delete_all_employees,
    delete_employee,
    fetch_employee_by_id,
    fetch_employees,
    update_employee,
)

router = APIRouter(tags=["employees"])


@router.get("/employees", response_model=list[EmployeeOut])
def list_employees(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    team: str | None = None,
    location: str | None = None,
    service: str | None = None,
    grade: str | None = None,
    search: str | None = None,
) -> list[EmployeeOut]:
    rows = fetch_employees(
        limit=limit,
        offset=offset,
        status=status_filter,
        team=team,
        location=location,
        service=service,
        grade=grade,
        search=search,
    )
    return [EmployeeOut.model_validate(r) for r in rows]


@router.get("/employees/{employee_id}", response_model=EmployeeOut, dependencies=[Depends(require_auth)])
def get_employee(employee_id: str) -> EmployeeOut:
    row = fetch_employee_by_id(employee_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return EmployeeOut.model_validate(row)


@router.post("/employees", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee_route(
    payload: EmployeeCreate,
    _authorized: None = Depends(require_admin),
) -> EmployeeOut:
    try:
        row = create_employee(payload.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create employee: {exc}") from exc
    return EmployeeOut.model_validate(row)


@router.post(
    "/employees/bulk",
    response_model=BulkEmployeeCreateResponse,
    status_code=status.HTTP_207_MULTI_STATUS,
)
def bulk_create_employees_route(
    payload: list[EmployeeCreate],
    _authorized: None = Depends(require_admin),
) -> BulkEmployeeCreateResponse:
    items = [e.model_dump() for e in payload]
    created_rows, errors = bulk_create_employees(items)
    return BulkEmployeeCreateResponse(
        created=[EmployeeOut.model_validate(r) for r in created_rows],
        errors=errors,
    )


@router.patch("/employees/{employee_id}", response_model=EmployeeOut)
def update_employee_route(
    employee_id: str,
    payload: EmployeeUpdate,
    _authorized: None = Depends(require_admin),
) -> EmployeeOut:
    try:
        row = update_employee(employee_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    return EmployeeOut.model_validate(row)


@router.delete("/employees", response_model=MessageResponse)
def delete_all_employees_route(
    _authorized: None = Depends(require_admin),
) -> MessageResponse:
    count = delete_all_employees()
    return MessageResponse(detail=f"Deleted {count} employee(s)")


@router.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee_route(
    employee_id: str,
    _authorized: None = Depends(require_admin),
) -> Response:
    deleted = delete_employee(employee_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Employee not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
