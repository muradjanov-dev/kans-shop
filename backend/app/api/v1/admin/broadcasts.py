from aiogram import Bot
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    MANAGEMENT_ROLES,
    get_bot,
    get_current_admin,
    get_db,
    require_admin_roles,
)
from app.api.schemas.admin import BroadcastCreateIn, BroadcastOut
from app.bot.keyboards.inline.admin_broadcast import broadcast_content_button
from app.core.exceptions import NotFoundError
from app.db.models.admin import Admin
from app.db.models.enums import BroadcastStatus
from app.db.repositories import broadcast_repository, user_repository
from app.db.session import async_session_maker
from app.services.broadcast_service import run_broadcast

router = APIRouter(
    prefix="/admin/broadcasts",
    tags=["admin-broadcasts"],
    dependencies=[Depends(require_admin_roles(*MANAGEMENT_ROLES))],
)


class BroadcastNotFoundError(NotFoundError):
    code = "BROADCAST_NOT_FOUND"


async def _send_and_finish(broadcast_id: int, bot: Bot) -> None:
    """Runs as a FastAPI BackgroundTask, after the response is already sent — opens its own
    DB session since the request-scoped one is closed by then (see docs/ASSUMPTIONS.md)."""
    async with async_session_maker() as session:
        broadcast = await broadcast_repository.get_by_id(session, broadcast_id)
        if broadcast is None:
            return
        await broadcast_repository.mark_sending(session, broadcast)

        audience = await user_repository.list_for_broadcast(session, broadcast.target.value)
        button_markup = broadcast_content_button(broadcast.button_text, broadcast.button_url)
        sent, failed = await run_broadcast(
            bot,
            session,
            audience,
            text=broadcast.text,
            photo_file_id=broadcast.photo_file_id,
            button_markup=button_markup,
        )
        status = (
            BroadcastStatus.COMPLETED if failed < len(audience) else BroadcastStatus.FAILED
        )
        await broadcast_repository.finish(
            session, broadcast, sent=sent, failed=failed, status=status
        )
        await session.commit()


@router.post("", response_model=BroadcastOut, status_code=202)
async def create_broadcast(
    payload: BroadcastCreateIn,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    bot: Bot = Depends(get_bot),
) -> BroadcastOut:
    broadcast = await broadcast_repository.create(
        session,
        admin_id=admin.id,
        text=payload.text,
        photo_file_id=payload.photo_file_id,
        button_text=payload.button_text,
        button_url=payload.button_url,
        target=payload.target,
    )
    background_tasks.add_task(_send_and_finish, broadcast.id, bot)
    return BroadcastOut.model_validate(broadcast)


@router.get("/{broadcast_id}", response_model=BroadcastOut)
async def get_broadcast(
    broadcast_id: int, session: AsyncSession = Depends(get_db)
) -> BroadcastOut:
    broadcast = await broadcast_repository.get_by_id(session, broadcast_id)
    if broadcast is None:
        raise BroadcastNotFoundError(f"Broadcast {broadcast_id} not found")
    return BroadcastOut.model_validate(broadcast)
