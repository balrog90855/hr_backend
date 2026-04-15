from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status


from app.schemas import MessageResponse, UserCreate, UserOut, UserUpdate
from app.security import hash_password, require_admin, require_auth
from app.database import (
    create_user,
    delete_all_users,
    delete_user,
    fetch_user_by_id,
    fetch_users_filtered,
    update_user,
)

router = APIRouter(tags=["users"])


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user_route(payload: UserCreate) -> UserOut:
    db_payload = payload.model_dump(by_alias=True)
    db_payload["passwordHash"] = hash_password(db_payload.pop("password"))
    try:
        row = create_user(db_payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to create user: {exc}") from exc
    return UserOut.model_validate(row)


@router.get("/users", response_model=list[UserOut], dependencies=[Depends(require_auth)])
def list_users(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    team: str | None = None,
    email: str | None = None,
    job_title: Annotated[str | None, Query(alias="job_title")] = None,
    search: str | None = None,
) -> list[UserOut]:
    rows = fetch_users_filtered(
        limit=limit,
        offset=offset,
        status=status_filter,
        team=team,
        email=email,
        job_title=job_title,
        search=search,
    )
    return [UserOut.model_validate(r) for r in rows]


@router.get("/users/{user_id}", response_model=UserOut, dependencies=[Depends(require_auth)])
def get_user(user_id: str) -> UserOut:
    row = fetch_user_by_id(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(row)


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user_route(
    user_id: str,
    payload: UserUpdate,
    _authorized: None = Depends(require_admin),
) -> UserOut:
    db_payload = payload.model_dump(by_alias=True, exclude_unset=True)
    row = update_user(user_id, db_payload)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut.model_validate(row)


@router.delete("/users", response_model=MessageResponse)
def delete_all_users_route(
    _authorized: None = Depends(require_admin),
) -> MessageResponse:
    count = delete_all_users()
    return MessageResponse(detail=f"Deleted {count} user(s)")


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_route(
    user_id: str,
    _authorized: None = Depends(require_admin),
) -> Response:
    deleted = delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
