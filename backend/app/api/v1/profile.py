from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas.customer import ProfileOut, ProfilePatch
from app.db.models.user import User
from app.services import profile_service

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
async def get_profile(
    user: User = Depends(get_current_user),
) -> ProfileOut:
    return ProfileOut.model_validate(user)


@router.patch("", response_model=ProfileOut)
async def patch_profile(
    payload: ProfilePatch,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> ProfileOut:
    updated = await profile_service.update_profile(
        session, user, payload.model_dump(exclude_unset=True)
    )
    return ProfileOut.model_validate(updated)
