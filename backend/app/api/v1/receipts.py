from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_admin_session_principal,
    get_current_admin,
    get_current_user,
    get_db,
)
from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.db.models.admin import Admin
from app.db.models.user import User
from app.services.receipt_service import open_order_receipt
from app.services.receipt_storage import PrivateReceiptStorage

router = APIRouter(prefix="/orders", tags=["order-receipts"])


@dataclass(frozen=True)
class ReceiptActor:
    user: User | None = None
    admin: Admin | None = None


async def _receipt_actor(
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db),
) -> ReceiptActor:
    # An explicit bearer identity always wins. In particular, an owner token cannot use an
    # unrelated admin cookie to bypass order ownership.
    if authorization is not None:
        user = await get_current_user(authorization=authorization, session=session)
        return ReceiptActor(user=user)

    if request.cookies.get("__Host-kans-admin") is None:
        raise UnauthorizedError("Receipt access requires a buyer or admin session")
    principal = await get_admin_session_principal(request, response, session)
    admin = await get_current_admin(principal=principal, session=session)
    response.headers["Cache-Control"] = "private, no-store"
    return ReceiptActor(admin=admin)


@router.get("/{order_id}/receipt", response_class=FileResponse)
async def get_order_receipt(
    order_id: int,
    response: Response,
    actor: ReceiptActor = Depends(_receipt_actor),
    session: AsyncSession = Depends(get_db),
) -> FileResponse:
    receipt = await open_order_receipt(
        session,
        PrivateReceiptStorage(settings.private_media_root_path),
        order_id=order_id,
        user_id=actor.user.id if actor.user is not None else 0,
        admin_id=actor.admin.id if actor.admin is not None else None,
    )
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return FileResponse(
        receipt.path,
        media_type=receipt.content_type,
        filename=f"order-{order_id}-receipt.{_extension(receipt.path)}",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _extension(path: Path) -> str:
    return path.suffix.lstrip(".")
