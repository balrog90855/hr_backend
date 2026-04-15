from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas import NominationCreate, NominationOut
from app.security import require_admin
from app.database import create_nomination, fetch_employee_by_id, fetch_nominations

router = APIRouter(tags=["nominations"])


@router.post("/nominations", response_model=NominationOut, status_code=status.HTTP_201_CREATED)
def submit_nomination(body: NominationCreate) -> NominationOut:
    employee = fetch_employee_by_id(body.nominee_employee_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found")

    row = create_nomination({
        "nominator_name": body.nominator_name,
        "nominator_team": body.nominator_team,
        "nominee_employee_id": body.nominee_employee_id,
        "nominee_name": str(employee["full_name"]),
        "nomination_text": body.nomination_text,
    })
    return NominationOut.model_validate(row)


@router.get("/nominations", response_model=list[NominationOut], dependencies=[Depends(require_admin)])
def list_nominations() -> list[NominationOut]:
    rows = fetch_nominations()
    return [NominationOut.model_validate(r) for r in rows]
