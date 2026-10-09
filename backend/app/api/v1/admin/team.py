from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_roles
from app.api.schemas.admin import (
    AdminChanges,
    AdminCreateIn,
    AdminOut,
    AdminSessionsRevokedOut,
)
from app.api.schemas.common import PageOut
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.services import admin_team_service
from app.services.common import Page

router = APIRouter(prefix="/admin/team", tags=["admin-team"])
_require_superadmin = require_admin_roles(AdminRole.SUPERADMIN)


@router.get("", response_model=PageOut[AdminOut])
async def list_team(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_superadmin),
) -> PageOut[AdminOut]:
    result = await admin_team_service.list_admins(
        session, admin_id=admin.id, page=page, limit=limit
    )
    return PageOut[AdminOut].from_page(
        Page(
            items=[AdminOut.model_validate(item) for item in result.items],
            total=result.total,
            page=result.page,
            limit=result.limit,
        )
    )


@router.post("", response_model=AdminOut, status_code=status.HTTP_201_CREATED)
async def create_team_member(
    payload: AdminCreateIn,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_superadmin),
) -> AdminOut:
    created = await admin_team_service.add_admin(
        session,
        actor_admin_id=admin.id,
        telegram_id=payload.telegram_id,
        full_name=payload.full_name,
        role=payload.role,
    )
    return AdminOut.model_validate(created)


@router.patch("/{admin_id}", response_model=AdminOut)
async def patch_team_member(
    admin_id: int,
    payload: AdminChanges,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_superadmin),
) -> AdminOut:
    updated = await admin_team_service.update_admin(
        session,
        actor_admin_id=admin.id,
        admin_id=admin_id,
        changes=payload,
    )
    return AdminOut.model_validate(updated)


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_member(
    admin_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_superadmin),
) -> Response:
    await admin_team_service.remove_admin(session, actor_admin_id=admin.id, admin_id=admin_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{admin_id}/sessions/revoke", response_model=AdminSessionsRevokedOut)
async def revoke_team_member_sessions(
    admin_id: int,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_superadmin),
) -> AdminSessionsRevokedOut:
    revoked_count = await admin_team_service.revoke_admin_sessions(
        session, actor_admin_id=admin.id, admin_id=admin_id
    )
    return AdminSessionsRevokedOut(revoked_sessions=revoked_count)
