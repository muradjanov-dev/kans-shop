from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import AdminUserDetail, UserBlockIn, UserOut
from app.api.schemas.common import PageOut
from app.db.models.admin import Admin
from app.db.models.user import User
from app.services import customer_admin_service
from app.services.common import Page

router = APIRouter(prefix="/admin/users", tags=["admin-users"])
_require_management_admin = require_admin_roles(*MANAGEMENT_ROLES)


@router.get("", response_model=PageOut[UserOut])
async def list_users(
    query: str | None = Query(default=None, max_length=128),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> PageOut[UserOut]:
    result = await customer_admin_service.list_admin_users(
        session,
        admin_id=admin.id,
        query=query,
        page=page,
        limit=limit,
    )
    items = [
        UserOut.model_validate(user).model_copy(
            update={"phone": customer_admin_service.mask_phone(user.phone)}
        )
        for user in result.items
    ]
    return PageOut[UserOut].from_page(
        Page(items=items, total=result.total, page=result.page, limit=result.limit)
    )


@router.get("/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> AdminUserDetail:
    return await customer_admin_service.get_admin_user(
        session, admin_id=admin.id, user_id=user_id
    )


@router.patch("/{user_id}/block", response_model=UserOut)
async def set_user_blocked(
    user_id: int,
    payload: UserBlockIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> UserOut:
    user: User = await customer_admin_service.set_user_blocked(
        session,
        admin_id=admin.id,
        user_id=user_id,
        blocked=payload.blocked,
    )
    return UserOut.model_validate(user)
