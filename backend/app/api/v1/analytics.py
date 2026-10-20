"""Behaviour analytics collection for the storefront (guests and signed-in customers)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.schemas.analytics import AnalyticsAcceptedOut, AnalyticsBatchIn
from app.core.security import decode_token
from app.db.models.user import User
from app.db.repositories import user_repository
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _optional_user(session: AsyncSession, authorization: str | None) -> User | None:
    """The signed-in customer, if the batch carries a valid token. An expired or broken
    token only makes the batch anonymous; analytics never asks the browser to sign in."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        payload = decode_token(
            authorization.removeprefix("Bearer ").strip(), expected_type="access"
        )
        user_id = int(payload["sub"])
    except Exception:
        return None
    return await user_repository.get_by_id(session, user_id)


@router.post("/events", status_code=202, response_model=AnalyticsAcceptedOut)
async def collect_events(
    batch: AnalyticsBatchIn,
    request: Request,
    response: Response,
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_db, scope="function"),
) -> AnalyticsAcceptedOut:
    response.headers["Cache-Control"] = "no-store"
    if analytics_service.looks_like_bot(request.headers.get("user-agent", "")):
        return AnalyticsAcceptedOut(accepted=0)
    user = await _optional_user(session, authorization)
    accepted = await analytics_service.ingest_batch(
        session, batch, user=user, now=datetime.now(UTC)
    )
    return AnalyticsAcceptedOut(accepted=accepted)
