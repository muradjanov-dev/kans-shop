from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from unittest.mock import patch

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import resolve_admin_session
from app.bot.utils.admin_guard import require_admin
from app.core.exceptions import ForbiddenError
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.enums import AdminRole

from .api_helpers import ApiCase


async def test_live_actor_is_reloaded_for_every_mutation(
    db_session: AsyncSession, admin: Admin
) -> None:
    stale_actor = await db_session.get(Admin, admin.id)
    assert stale_actor is not None
    assert stale_actor.role == AdminRole.SUPERADMIN

    await db_session.execute(
        update(Admin)
        .where(Admin.id == admin.id)
        .values(role=AdminRole.MANAGER)
        .execution_options(synchronize_session=False)
    )
    try:
        from app.services.admin_actor_service import load_live_admin
    except ImportError:
        pytest.fail("admin_actor_service.load_live_admin is missing")

    current_actor = await load_live_admin(
        db_session,
        admin_id=admin.id,
        allowed_roles=frozenset({AdminRole.MANAGER}),
    )
    assert current_actor.role == AdminRole.MANAGER

    await db_session.execute(
        update(Admin)
        .where(Admin.id == admin.id)
        .values(role=AdminRole.OPERATOR)
        .execution_options(synchronize_session=False)
    )
    with pytest.raises(ForbiddenError):
        await load_live_admin(
            db_session,
            admin_id=admin.id,
            allowed_roles=frozenset({AdminRole.MANAGER}),
            lock=True,
        )

    class FakeEvent:
        answers: list[str]

        def __init__(self) -> None:
            self.answers = []

        async def answer(self, text: str) -> None:
            self.answers.append(text)

    event = FakeEvent()
    allowed = await require_admin(
        event,
        stale_actor,
        lambda key: key,
        roles=(AdminRole.MANAGER,),
        session=db_session,
    )
    assert allowed is False
    assert event.answers == ["admin.not_admin_alert"]


@asynccontextmanager
async def _admin_cookie(case: ApiCase, *, admin: Admin) -> AsyncIterator[None]:
    raw_token = token_urlsafe(32)
    now = datetime.now(UTC)
    async with case.session_maker() as session:
        session.add(
            AdminSession(
                admin_id=admin.id,
                token_hash=sha256(raw_token.encode("ascii")).hexdigest(),
                csrf_token=token_urlsafe(96),
                auth_epoch=admin.auth_epoch,
                idle_expires_at=now + timedelta(hours=12),
                absolute_expires_at=now + timedelta(days=7),
            )
        )
        await session.commit()
    case.client.cookies.set("__Host-kans-admin", raw_token, path="/")
    try:
        yield
    finally:
        async with case.session_maker() as session:
            await session.delete(await session.get(Admin, admin.id))
            await session.commit()


async def test_stale_manager_cookie_request_is_rejected(test_engine: AsyncEngine) -> None:
    """The session resolver's cached Admin must not survive a concurrent demotion."""
    from .api_helpers import make_api_case

    async with make_api_case(test_engine, base_url="https://testserver") as case:
        async with case.session_maker() as session:
            actor = Admin(
                telegram_id=9_876_543_210_123_456,
                full_name="Live actor test",
                role=AdminRole.MANAGER,
            )
            session.add(actor)
            await session.commit()
            await session.refresh(actor)

        original_resolver = resolve_admin_session

        async def resolve_then_demote(session, *, raw_token: str, now: datetime):
            principal = await original_resolver(session, raw_token=raw_token, now=now)
            async with case.session_maker() as writer:
                current = await writer.get(Admin, actor.id)
                assert current is not None
                current.role = AdminRole.OPERATOR
                await writer.commit()
            return principal

        with patch("app.api.deps.resolve_admin_session", side_effect=resolve_then_demote):
            async with _admin_cookie(case, admin=actor):
                response = await case.client.get("/api/v1/admin/users")

        assert response.status_code == 403
