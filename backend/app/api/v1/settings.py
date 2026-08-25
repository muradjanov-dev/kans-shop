from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.settings import PublicSettingsOut
from app.db.models.enums import PaymentProvider
from app.db.repositories import setting_repository
from app.services import payment_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/public", response_model=PublicSettingsOut)
async def get_public_settings(session: AsyncSession = Depends(get_db)) -> PublicSettingsOut:
    settings_map = await setting_repository.get_all(session)
    enabled_providers = [
        provider.value
        for provider in PaymentProvider
        if payment_service.is_provider_configured(provider)
    ]
    return PublicSettingsOut(
        **{k: v for k, v in settings_map.items() if k in PublicSettingsOut.model_fields},
        enabled_payment_providers=enabled_providers,
    )
