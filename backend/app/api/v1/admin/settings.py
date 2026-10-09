from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import MANAGEMENT_ROLES, get_db, require_admin_roles
from app.api.schemas.admin import StoreSettingsPatch, StoreSettingsSnapshot
from app.db.models.admin import Admin
from app.services import store_settings_service

router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])
_require_management_admin = require_admin_roles(*MANAGEMENT_ROLES)


@router.get("", response_model=StoreSettingsSnapshot)
async def get_settings(
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> StoreSettingsSnapshot:
    return await store_settings_service.get_store_settings(session, admin_id=admin.id)


@router.patch("", response_model=StoreSettingsSnapshot)
async def patch_settings(
    payload: StoreSettingsPatch,
    session: AsyncSession = Depends(get_db, scope="function"),
    admin: Admin = Depends(_require_management_admin),
) -> StoreSettingsSnapshot:
    return await store_settings_service.patch_store_settings(
        session,
        admin_id=admin.id,
        expected_version=payload.expected_version,
        changes=payload,
    )
