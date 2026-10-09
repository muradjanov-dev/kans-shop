from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.schemas.catalog import ProductOut
from app.api.schemas.common import PageOut
from app.api.schemas.favorites import FavoriteStateOut
from app.db.models.user import User
from app.services import favorite_service

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=PageOut[ProductOut])
async def list_favorites(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=24, ge=1, le=50),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> PageOut[ProductOut]:
    result = await favorite_service.list_favorites(session, user.id, page=page, limit=limit)
    return PageOut[ProductOut].from_page(result)


@router.get("/{product_id}", response_model=FavoriteStateOut)
async def get_favorite_state(
    product_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> FavoriteStateOut:
    is_favorite = await favorite_service.is_favorite(session, user.id, product_id)
    return FavoriteStateOut(is_favorite=is_favorite)


@router.put("/{product_id}", status_code=204)
async def add_favorite(
    product_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Response:
    await favorite_service.add_favorite(session, user.id, product_id)
    return Response(status_code=204)


@router.delete("/{product_id}", status_code=204)
async def remove_favorite(
    product_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> Response:
    await favorite_service.remove_favorite(session, user.id, product_id)
    return Response(status_code=204)
