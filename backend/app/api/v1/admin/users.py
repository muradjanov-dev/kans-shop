from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import UserBlockIn, UserOut
from app.api.schemas.common import PageOut
from app.core.exceptions import NotFoundError
from app.db.repositories import user_repository
from app.services.common import Page

router = APIRouter(
    prefix="/admin/users",
    tags=["admin-users"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


class UserNotFoundError(NotFoundError):
    code = "USER_NOT_FOUND"


@router.get("", response_model=PageOut[UserOut])
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
) -> PageOut[UserOut]:
    items, total = await user_repository.list_all(session, page=page, limit=limit)
    return PageOut[UserOut].from_page(Page(items=items, total=total, page=page, limit=limit))


@router.patch("/{user_id}/block", response_model=UserOut)
async def set_user_blocked(
    user_id: int, payload: UserBlockIn, session: AsyncSession = Depends(get_db)
) -> UserOut:
    user = await user_repository.get_by_id(session, user_id)
    if user is None:
        raise UserNotFoundError(f"User {user_id} not found")
    await user_repository.set_blocked(session, user, payload.blocked)
    return UserOut.model_validate(user)
