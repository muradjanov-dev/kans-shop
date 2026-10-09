from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from PIL import Image
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import settings
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.broadcast import Broadcast
from app.db.models.broadcast_recipient import BroadcastRecipient
from app.db.models.enums import (
    AdminRole,
    BroadcastRecipientStatus,
    BroadcastStatus,
    BroadcastTarget,
)
from app.db.models.user import User
from app.main import create_app

from .api_helpers import ApiCase, make_api_case


def _admin_headers(cookie: str, csrf: str | None = None) -> dict[str, str]:
    headers = {"Cookie": f"__Host-kans-admin={cookie}"}
    if csrf is not None:
        headers.update({"Origin": settings.webapp_origin, "X-CSRF-Token": csrf})
    return headers


async def _make_admin_session(
    session: AsyncSession, *, role: AdminRole = AdminRole.MANAGER
) -> tuple[Admin, str, str]:
    actor = Admin(
        telegram_id=9_300_000_000_000_000 + int(token_urlsafe(5).encode().hex(), 16),
        full_name="Synthetic Broadcast Admin",
        role=role,
    )
    session.add(actor)
    await session.flush()
    cookie = token_urlsafe(32)
    csrf = token_urlsafe(48)
    now = datetime.now(UTC)
    session.add(
        AdminSession(
            admin_id=actor.id,
            token_hash=sha256(cookie.encode("ascii")).hexdigest(),
            csrf_token=csrf,
            auth_epoch=actor.auth_epoch,
            idle_expires_at=now + timedelta(hours=12),
            absolute_expires_at=now + timedelta(days=7),
        )
    )
    await session.flush()
    return actor, cookie, csrf


class CountingBot:
    id = 770001

    def __init__(self) -> None:
        self.sent: list[tuple[str, tuple, dict]] = []
        self.failure: Exception | None = None

    async def send_message(self, *args, **kwargs):
        self.sent.append(("message", args, kwargs))
        if self.failure is not None:
            raise self.failure

    async def send_photo(self, *args, **kwargs):
        self.sent.append(("photo", args, kwargs))
        if self.failure is not None:
            raise self.failure


class FakeRedis:
    async def eval(self, *_args):
        return 0


@asynccontextmanager
async def _broadcast_case(
    test_engine: AsyncEngine,
) -> AsyncIterator[tuple[ApiCase, Admin, str, str]]:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        async with case.session_maker() as session:
            admin, cookie, csrf = await _make_admin_session(session)
            await session.commit()
        case.client.cookies.set("__Host-kans-admin", cookie, path="/")
        try:
            yield case, admin, cookie, csrf
        finally:
            async with case.session_maker() as session:
                await session.execute(
                    delete(BroadcastRecipient).where(
                        BroadcastRecipient.broadcast_id.in_(
                            select(Broadcast.id).where(Broadcast.admin_id == admin.id)
                        )
                    )
                )
                await session.execute(delete(Broadcast).where(Broadcast.admin_id == admin.id))
                await session.execute(delete(Admin).where(Admin.id == admin.id))
                await session.commit()


def _content(*, target: str = "all", text: str = "Synthetic restock announcement") -> dict:
    return {
        "target": target,
        "text": text,
        "photo_storage_key": None,
        "photo_file_id": None,
        "button_text": None,
        "button_url": None,
    }


async def _preview_and_draft(
    session: AsyncSession,
    *,
    admin_id: int,
    text: str = "Synthetic restock announcement",
    target: BroadcastTarget = BroadcastTarget.ALL,
):
    from app.services.admin_broadcast_service import (
        create_broadcast_draft,
        preview_broadcast,
    )

    preview = await preview_broadcast(
        session,
        admin_id=admin_id,
        target=target,
        text=text,
        photo_storage_key=None,
        photo_file_id=None,
        button_text=None,
        button_url=None,
    )
    draft = await create_broadcast_draft(session, admin_id=admin_id, preview=preview)
    return preview, draft


@pytest.mark.asyncio
async def test_preview_and_draft_never_send(test_engine: AsyncEngine) -> None:
    async with _broadcast_case(test_engine) as (case, _admin, cookie, csrf):
        bot = CountingBot()
        case.app.state.bot = bot
        headers = _admin_headers(cookie, csrf)

        preview = await case.client.post(
            "/api/v1/admin/broadcasts/preview", headers=headers, json=_content()
        )
        assert preview.status_code == 200, preview.text
        assert preview.headers["cache-control"] == "private, no-store"
        assert preview.json()["preview_count"] == 2

        draft = await case.client.post(
            "/api/v1/admin/broadcasts",
            headers=headers,
            json={**_content(), **preview.json()},
        )
        assert draft.status_code == 201, draft.text
        assert draft.json()["status"] == "draft"
        assert bot.sent == []
        async with case.session_maker() as session:
            checkpoint_count = await session.scalar(
                select(func.count()).select_from(BroadcastRecipient)
            )
            assert checkpoint_count == 0
            stored = await session.get(Broadcast, draft.json()["id"])
            assert stored is not None and stored.status == BroadcastStatus.DRAFT


@pytest.mark.asyncio
async def test_broadcast_photo_upload_is_private_and_csrf_guarded(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    monkeypatch.setattr(settings, "media_root", str(public_root))
    monkeypatch.setattr(settings, "private_media_root", str(private_root))
    image = BytesIO()
    Image.new("RGB", (2, 2), color="navy").save(image, format="PNG")

    async with _broadcast_case(test_engine) as (case, _admin, cookie, csrf):
        endpoint = "/api/v1/admin/broadcasts/media"
        denied = await case.client.post(
            endpoint,
            headers={
                "Cookie": f"__Host-kans-admin={cookie}",
                "Origin": settings.webapp_origin,
            },
            files={"file": ("synthetic.png", image.getvalue(), "image/png")},
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "CSRF_FAILED"

        unsupported = await case.client.post(
            endpoint,
            headers=_admin_headers(cookie, csrf),
            files={"file": ("synthetic.txt", image.getvalue(), "text/plain")},
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

        uploaded = await case.client.post(
            endpoint,
            headers=_admin_headers(cookie, csrf),
            files={"file": ("synthetic.png", image.getvalue(), "image/png")},
        )
        assert uploaded.status_code == 201, uploaded.text
        key = uploaded.json()["photo_storage_key"]
        assert len(key) == 36
        saved = private_root / "broadcasts" / key
        assert saved.is_file()
        assert saved.read_bytes() == image.getvalue()
        assert saved.stat().st_mode & 0o777 == 0o600
        assert not (public_root / "broadcasts" / key).exists()
        public_response = await case.client.get(f"/media/broadcasts/{key}")
        assert public_response.status_code == 404
        photo_only_preview = await case.client.post(
            "/api/v1/admin/broadcasts/preview",
            headers=_admin_headers(cookie, csrf),
            json={
                "target": "all",
                "text": "",
                "photo_storage_key": key,
                "photo_file_id": None,
                "button_text": None,
                "button_url": None,
            },
        )
        assert photo_only_preview.status_code == 200, photo_only_preview.text


@pytest.mark.asyncio
async def test_launch_snapshot_idempotency_and_preview_conflicts(
    test_engine: AsyncEngine,
) -> None:

    async with _broadcast_case(test_engine) as (case, admin, cookie, csrf):
        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            stale_preview, stale_draft = await _preview_and_draft(
                session, admin_id=admin.id, text="Synthetic preview before audience growth"
            )
            await session.commit()
            broadcast_id = draft.id
            stale_broadcast_id = stale_draft.id
            launch_key = uuid4()

        headers = _admin_headers(cookie, csrf)
        launch_body = {
            "preview_fingerprint": preview.preview_fingerprint,
            "preview_count": preview.preview_count,
            "idempotency_key": str(launch_key),
        }
        first = await case.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/launch",
            headers=headers,
            json=launch_body,
        )
        assert first.status_code == 202, first.text
        replay = await case.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/launch",
            headers=headers,
            json=launch_body,
        )
        assert replay.status_code == 202, replay.text
        assert replay.json()["id"] == first.json()["id"] == broadcast_id

        async with case.session_maker() as session:
            stored = await session.get(Broadcast, broadcast_id)
            assert stored is not None
            assert stored.admin_id == admin.id
            assert stored.launch_idempotency_key == launch_key
            assert stored.launch_fingerprint == preview.preview_fingerprint
            assert stored.launch_count == preview.preview_count == 2
            assert stored.launcher_auth_epoch == admin.auth_epoch
            assert stored.launched_at is not None and stored.launched_at.tzinfo is not None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(BroadcastRecipient)
                    .where(BroadcastRecipient.broadcast_id == broadcast_id)
                )
                == 2
            )

            new_user = User(telegram_id=7_700_100_003, first_name="Synthetic new audience")
            session.add(new_user)
            await session.flush()
            new_user_id = new_user.id
            await session.commit()

        response = await case.client.post(
            f"/api/v1/admin/broadcasts/{stale_broadcast_id}/launch",
            headers=headers,
            json={
                "preview_fingerprint": stale_preview.preview_fingerprint,
                "preview_count": stale_preview.preview_count,
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BROADCAST_AUDIENCE_CHANGED"

        async with case.session_maker() as session:
            _fresh_preview, changed_content = await _preview_and_draft(
                session, admin_id=admin.id, text="Original preview content"
            )
            content_id = changed_content.id
            await session.commit()
            async with case.session_maker() as update_session:
                row = await update_session.get(Broadcast, content_id)
                assert row is not None
                row.text = "Different content after preview"
                await update_session.commit()
            response = await case.client.post(
                f"/api/v1/admin/broadcasts/{content_id}/launch",
                headers=headers,
                json={
                    "preview_fingerprint": _fresh_preview.preview_fingerprint,
                    "preview_count": _fresh_preview.preview_count,
                    "idempotency_key": str(uuid4()),
                },
            )
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "BROADCAST_PREVIEW_CHANGED"

        async with case.session_maker() as session:
            await session.execute(delete(User).where(User.id == new_user_id))
            await session.commit()


def test_preview_fingerprint_sorts_audience_and_binds_campaign_content() -> None:
    from app.services.admin_broadcast_service import fingerprint_broadcast_preview

    fields = {
        "target": BroadcastTarget.ALL,
        "text": "Synthetic notice",
        "photo_storage_key": "2ce45495-d870-4bd3-a2d0-3c9fd6c25ddc",
        "photo_file_id": None,
        "button_text": "Shop",
        "button_url": "https://shop.example.test",
    }
    forward = fingerprint_broadcast_preview([7, 2], **fields)
    reverse = fingerprint_broadcast_preview([2, 7], **fields)
    assert forward == reverse
    assert fingerprint_broadcast_preview([2, 7, 8], **fields) != forward
    assert (
        fingerprint_broadcast_preview([2, 7], **{**fields, "target": BroadcastTarget.ACTIVE})
        != forward
    )
    assert (
        fingerprint_broadcast_preview([2, 7], **{**fields, "text": "Changed text"}) != forward
    )
    assert (
        fingerprint_broadcast_preview(
            [2, 7], **{**fields, "photo_storage_key": "e2f39776-d037-42eb-b6af-7d75451b6d1c"}
        )
        != forward
    )
    assert (
        fingerprint_broadcast_preview([2, 7], **{**fields, "button_text": "Other"}) != forward
    )
    assert (
        fingerprint_broadcast_preview(
            [2, 7], **{**fields, "button_url": "https://other.example.test"}
        )
        != forward
    )


def test_broadcast_confirmation_is_an_explicit_launch_action() -> None:
    from app.bot.keyboards.callback_data import BroadcastConfirmCallback
    from app.bot.keyboards.inline.admin_broadcast import broadcast_confirm_keyboard

    keyboard = broadcast_confirm_keyboard(lambda key: key)
    callback_data = keyboard.inline_keyboard[0][0].callback_data
    assert callback_data is not None
    assert BroadcastConfirmCallback.unpack(callback_data).action == "launch"


@pytest.mark.asyncio
async def test_same_count_recipient_change_is_an_audience_conflict(
    test_engine: AsyncEngine,
) -> None:
    async with _broadcast_case(test_engine) as (case, admin, cookie, csrf):
        async with case.session_maker() as session:
            original_user = await session.get(User, case.user_id)
            replacement_user = await session.get(User, case.other_user_id)
            assert original_user is not None and replacement_user is not None
            replacement_user.is_blocked = True
            await session.commit()

        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            assert preview.preview_count == 1
            await session.commit()
            broadcast_id = draft.id

        async with case.session_maker() as session:
            original_user = await session.get(User, case.user_id)
            replacement_user = await session.get(User, case.other_user_id)
            assert original_user is not None and replacement_user is not None
            original_user.is_blocked = True
            replacement_user.is_blocked = False
            await session.commit()

        response = await case.client.post(
            f"/api/v1/admin/broadcasts/{broadcast_id}/launch",
            headers=_admin_headers(cookie, csrf),
            json={
                "preview_fingerprint": preview.preview_fingerprint,
                "preview_count": preview.preview_count,
                "idempotency_key": str(uuid4()),
            },
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "BROADCAST_AUDIENCE_CHANGED"


@pytest.mark.asyncio
async def test_empty_audience_launch_finishes_without_stuck_sending(
    test_engine: AsyncEngine,
) -> None:
    from app.services.admin_broadcast_service import launch_broadcast

    async with (
        _broadcast_case(test_engine) as (_case, admin, _cookie, _csrf),
        _case.session_maker() as session,
    ):
        preview, draft = await _preview_and_draft(
            session, admin_id=admin.id, target=BroadcastTarget.ACTIVE
        )
        assert preview.preview_count == 0
        launched = await launch_broadcast(
            session,
            admin_id=admin.id,
            broadcast_id=draft.id,
            preview_fingerprint=preview.preview_fingerprint,
            preview_count=preview.preview_count,
            idempotency_key=uuid4(),
        )
        assert launched.status == BroadcastStatus.COMPLETED
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(BroadcastRecipient.broadcast_id == launched.id)
            )
            == 0
        )


@pytest.mark.asyncio
async def test_broadcast_recipient_restart_and_checkpoint(test_engine: AsyncEngine) -> None:
    from app.services.admin_broadcast_service import launch_broadcast
    from app.services.broadcast_worker import claim_broadcast_batch, process_broadcast_claim

    async with _broadcast_case(test_engine) as (case, admin, _cookie, _csrf):
        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            broadcast = await launch_broadcast(
                session,
                admin_id=admin.id,
                broadcast_id=draft.id,
                preview_fingerprint=preview.preview_fingerprint,
                preview_count=preview.preview_count,
                idempotency_key=uuid4(),
            )
            broadcast_id = broadcast.id
            await session.commit()

        async with case.session_maker() as session:
            recipients = list(
                (
                    await session.scalars(
                        select(BroadcastRecipient)
                        .where(BroadcastRecipient.broadcast_id == broadcast_id)
                        .order_by(BroadcastRecipient.user_id)
                    )
                ).all()
            )
            recipients[0].status = BroadcastRecipientStatus.SENT
            recipients[0].sent_at = datetime.now(UTC)
            recipients[1].status = BroadcastRecipientStatus.SENDING
            recipients[1].lease_token = str(uuid4())
            recipients[1].lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            await session.commit()

        async with case.session_maker() as session:
            claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-restart-worker",
                now=datetime.now(UTC),
                limit=10,
                lease_seconds=30,
            )
            assert [claim.user_id for claim in claims] == [recipients[1].user_id]
            await session.commit()
        assert claims[0].lease_token

        bot = CountingBot()
        await process_broadcast_claim(bot, case.session_maker, FakeRedis(), claims[0])
        assert len(bot.sent) == 1
        async with case.session_maker() as session:
            sent = await session.scalar(
                select(BroadcastRecipient.status).where(
                    BroadcastRecipient.id == recipients[1].id
                )
            )
            assert sent == BroadcastRecipientStatus.SENT
            sent_count = await session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(
                    BroadcastRecipient.broadcast_id == broadcast_id,
                    BroadcastRecipient.status == BroadcastRecipientStatus.SENT,
                )
            )
            assert sent_count == 2


@pytest.mark.asyncio
async def test_legacy_or_incomplete_broadcast_checkpoints_never_rebuild_audience(
    test_engine: AsyncEngine,
) -> None:
    from app.services.broadcast_worker import claim_broadcast_batch

    async with (
        _broadcast_case(test_engine) as (case, admin, _cookie, _csrf),
        case.session_maker() as session,
    ):
        legacy = Broadcast(
            admin_id=admin.id,
            text="Synthetic legacy sending row",
            target=BroadcastTarget.ALL,
            status=BroadcastStatus.SENDING,
        )
        incomplete = Broadcast(
            admin_id=admin.id,
            text="Synthetic incomplete checkpoint",
            target=BroadcastTarget.ALL,
            status=BroadcastStatus.SENDING,
            preview_content_fingerprint="1" * 64,
            launch_idempotency_key=uuid4(),
            launch_fingerprint="2" * 64,
            launch_count=2,
            launcher_auth_epoch=admin.auth_epoch,
            launched_at=datetime.now(UTC),
        )
        session.add_all([legacy, incomplete])
        await session.flush()
        legacy_id, incomplete_id = legacy.id, incomplete.id
        claims = await claim_broadcast_batch(
            session,
            worker_id="synthetic-no-rebuild-worker",
            now=datetime.now(UTC),
            limit=10,
            lease_seconds=30,
        )
        assert claims == []
        await session.refresh(legacy)
        await session.refresh(incomplete)
        assert legacy.status == BroadcastStatus.FAILED
        assert incomplete.status == BroadcastStatus.FAILED
        assert (
            await session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(BroadcastRecipient.broadcast_id.in_([legacy_id, incomplete_id]))
            )
            == 0
        )


@pytest.mark.asyncio
async def test_worker_preserves_uploaded_and_legacy_photo_content_and_buttons(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from aiogram.types import BufferedInputFile

    from app.services.admin_broadcast_service import (
        create_broadcast_draft,
        launch_broadcast,
        preview_broadcast,
    )
    from app.services.broadcast_media_service import store_broadcast_photo
    from app.services.broadcast_worker import claim_broadcast_batch, process_broadcast_claim

    monkeypatch.setattr(settings, "media_root", str(tmp_path / "public"))
    monkeypatch.setattr(settings, "private_media_root", str(tmp_path / "private"))
    image = BytesIO()
    Image.new("RGB", (3, 2), color="purple").save(image, format="PNG")
    image_bytes = image.getvalue()
    storage_key = store_broadcast_photo(content=image_bytes, content_type="image/png")

    async with _broadcast_case(test_engine) as (case, admin, _cookie, _csrf):
        bot = CountingBot()
        for photo_storage_key, photo_file_id in (
            (storage_key, None),
            (None, "synthetic-legacy-telegram-photo-id"),
        ):
            async with case.session_maker() as session:
                preview = await preview_broadcast(
                    session,
                    admin_id=admin.id,
                    target=BroadcastTarget.ALL,
                    text="Synthetic photo campaign",
                    photo_storage_key=photo_storage_key,
                    photo_file_id=photo_file_id,
                    button_text="Open shop",
                    button_url="https://shop.example.test",
                )
                draft = await create_broadcast_draft(
                    session, admin_id=admin.id, preview=preview
                )
                await launch_broadcast(
                    session,
                    admin_id=admin.id,
                    broadcast_id=draft.id,
                    preview_fingerprint=preview.preview_fingerprint,
                    preview_count=preview.preview_count,
                    idempotency_key=uuid4(),
                )
                await session.commit()

            async with case.session_maker() as session:
                claims = await claim_broadcast_batch(
                    session,
                    worker_id="synthetic-photo-worker",
                    now=datetime.now(UTC),
                    limit=10,
                    lease_seconds=30,
                )
                await session.commit()
            assert len(claims) == 2
            for claim in claims:
                await process_broadcast_claim(bot, case.session_maker, FakeRedis(), claim)

        assert len(bot.sent) == 4
        uploaded_photo = bot.sent[0][2]["photo"]
        assert isinstance(uploaded_photo, BufferedInputFile)
        assert uploaded_photo.data == image_bytes
        assert bot.sent[0][2]["caption"] == "Synthetic photo campaign"
        assert bot.sent[0][2]["reply_markup"].inline_keyboard[0][0].url == (
            "https://shop.example.test"
        )
        assert bot.sent[2][2]["photo"] == "synthetic-legacy-telegram-photo-id"
        assert bot.sent[2][2]["reply_markup"].inline_keyboard[0][0].text == "Open shop"


@pytest.mark.asyncio
async def test_cancel_and_revoked_actor_stop_pending(test_engine: AsyncEngine) -> None:
    from app.services.admin_broadcast_service import cancel_broadcast, launch_broadcast
    from app.services.broadcast_worker import claim_broadcast_batch, process_broadcast_claim

    async with _broadcast_case(test_engine) as (case, admin, _cookie, _csrf):
        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            cancelled = await launch_broadcast(
                session,
                admin_id=admin.id,
                broadcast_id=draft.id,
                preview_fingerprint=preview.preview_fingerprint,
                preview_count=preview.preview_count,
                idempotency_key=uuid4(),
            )
            cancelled_id = cancelled.id
            await session.commit()
        async with case.session_maker() as session:
            in_flight_claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-cancel-inflight-worker",
                now=datetime.now(UTC),
                limit=1,
                lease_seconds=30,
            )
            assert in_flight_claims
            await session.commit()
        async with case.session_maker() as session:
            result = await cancel_broadcast(
                session, admin_id=admin.id, broadcast_id=cancelled_id
            )
            assert result.status == BroadcastStatus.CANCELLED
            still_sending = await session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(
                    BroadcastRecipient.broadcast_id == cancelled_id,
                    BroadcastRecipient.status == BroadcastRecipientStatus.SENDING,
                )
            )
            assert still_sending == 1
            await session.commit()
        cancelled_bot = CountingBot()
        await process_broadcast_claim(
            cancelled_bot, case.session_maker, FakeRedis(), in_flight_claims[0]
        )
        assert cancelled_bot.sent == []
        async with case.session_maker() as session:
            remaining_sending = await session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(
                    BroadcastRecipient.broadcast_id == cancelled_id,
                    BroadcastRecipient.status == BroadcastRecipientStatus.SENDING,
                )
            )
            assert remaining_sending == 0
        async with case.session_maker() as session:
            claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-cancel-worker",
                now=datetime.now(UTC),
                limit=10,
                lease_seconds=30,
            )
            await session.commit()
        assert claims == []

        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            revoked = await launch_broadcast(
                session,
                admin_id=admin.id,
                broadcast_id=draft.id,
                preview_fingerprint=preview.preview_fingerprint,
                preview_count=preview.preview_count,
                idempotency_key=uuid4(),
            )
            revoked_id = revoked.id
            await session.commit()
        async with case.session_maker() as session:
            claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-revoked-worker",
                now=datetime.now(UTC),
                limit=1,
                lease_seconds=30,
            )
            assert claims
            actor = await session.get(Admin, admin.id)
            assert actor is not None
            actor.auth_epoch += 1
            await session.commit()
        bot = CountingBot()
        await process_broadcast_claim(bot, case.session_maker, FakeRedis(), claims[0])
        assert bot.sent == []
        async with case.session_maker() as session:
            row = await session.get(Broadcast, revoked_id)
            assert row is not None and row.status == BroadcastStatus.CANCELLED
            pending = await session.scalar(
                select(func.count())
                .select_from(BroadcastRecipient)
                .where(
                    BroadcastRecipient.broadcast_id == revoked_id,
                    BroadcastRecipient.status == BroadcastRecipientStatus.PENDING,
                )
            )
            assert pending == 0


@pytest.mark.asyncio
async def test_forbidden_user_is_blocked(test_engine: AsyncEngine) -> None:
    from app.services.admin_broadcast_service import launch_broadcast
    from app.services.broadcast_worker import claim_broadcast_batch, process_broadcast_claim

    async with _broadcast_case(test_engine) as (case, admin, _cookie, _csrf):
        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            await launch_broadcast(
                session,
                admin_id=admin.id,
                broadcast_id=draft.id,
                preview_fingerprint=preview.preview_fingerprint,
                preview_count=preview.preview_count,
                idempotency_key=uuid4(),
            )
            await session.commit()
        async with case.session_maker() as session:
            claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-forbidden-worker",
                now=datetime.now(UTC),
                limit=1,
                lease_seconds=30,
            )
            claim = claims[0]
            await session.commit()
        bot = CountingBot()
        bot.failure = TelegramForbiddenError(method=None, message="Synthetic forbidden")
        await process_broadcast_claim(bot, case.session_maker, FakeRedis(), claim)
        async with case.session_maker() as session:
            user = await session.get(User, claim.user_id)
            recipient = await session.scalar(
                select(BroadcastRecipient).where(BroadcastRecipient.id == claim.recipient_id)
            )
            assert user is not None and user.is_blocked
            assert (
                recipient is not None and recipient.status == BroadcastRecipientStatus.FAILED
            )
            assert recipient.last_error == "telegram_forbidden"


@pytest.mark.asyncio
async def test_shared_pacing_and_retry_after(test_engine: AsyncEngine, monkeypatch) -> None:
    from app.services import broadcast_worker
    from app.services.admin_broadcast_service import launch_broadcast

    async with _broadcast_case(test_engine) as (case, admin, _cookie, _csrf):
        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            await launch_broadcast(
                session,
                admin_id=admin.id,
                broadcast_id=draft.id,
                preview_fingerprint=preview.preview_fingerprint,
                preview_count=preview.preview_count,
                idempotency_key=uuid4(),
            )
            await session.commit()
        async with case.session_maker() as session:
            claims = await broadcast_worker.claim_broadcast_batch(
                session,
                worker_id="synthetic-rate-worker",
                now=datetime.now(UTC),
                limit=1,
                lease_seconds=30,
            )
            await session.commit()
        pacing_calls: list[tuple[int, datetime]] = []

        async def acquire(redis, *, bot_id: int, now: datetime) -> None:
            pacing_calls.append((bot_id, now))

        monkeypatch.setattr(broadcast_worker, "acquire_telegram_slot", acquire)
        bot = CountingBot()
        bot.failure = TelegramRetryAfter(
            method=None, message="Too Many Requests", retry_after=3
        )
        before = datetime.now(UTC)
        await broadcast_worker.process_broadcast_claim(
            bot, case.session_maker, FakeRedis(), claims[0]
        )
        assert len(pacing_calls) == 1
        assert pacing_calls[0][0] == bot.id
        async with case.session_maker() as session:
            recipient = await session.scalar(
                select(BroadcastRecipient).where(
                    BroadcastRecipient.id == claims[0].recipient_id
                )
            )
            assert recipient is not None
            assert recipient.status == BroadcastRecipientStatus.PENDING
            assert recipient.last_error == "telegram_retry_after"
            assert recipient.next_available_at >= before + timedelta(seconds=2.9)


@pytest.mark.asyncio
async def test_broadcast_rechecks_preview_and_actor_before_each_claim(
    test_engine: AsyncEngine,
) -> None:
    from app.services.admin_broadcast_service import launch_broadcast
    from app.services.broadcast_worker import claim_broadcast_batch, process_broadcast_claim

    async with _broadcast_case(test_engine) as (case, admin, _cookie, _csrf):
        async with case.session_maker() as session:
            preview, draft = await _preview_and_draft(session, admin_id=admin.id)
            broadcast = await launch_broadcast(
                session,
                admin_id=admin.id,
                broadcast_id=draft.id,
                preview_fingerprint=preview.preview_fingerprint,
                preview_count=preview.preview_count,
                idempotency_key=uuid4(),
            )
            broadcast_id = broadcast.id
            await session.commit()

        async with case.session_maker() as session:
            claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-live-check-worker",
                now=datetime.now(UTC),
                limit=1,
                lease_seconds=30,
            )
            assert claims
            customer = await session.get(User, claims[0].user_id)
            assert customer is not None
            customer.is_blocked = True
            await session.commit()
        bot = CountingBot()
        await process_broadcast_claim(bot, case.session_maker, FakeRedis(), claims[0])
        assert bot.sent == []

        async with case.session_maker() as session:
            claims = await claim_broadcast_batch(
                session,
                worker_id="synthetic-preview-check-worker",
                now=datetime.now(UTC) + timedelta(minutes=1),
                limit=1,
                lease_seconds=30,
            )
            assert claims
            row = await session.get(Broadcast, broadcast_id)
            assert row is not None
            row.text = "Changed after launch and preview"
            await session.commit()
        await process_broadcast_claim(bot, case.session_maker, FakeRedis(), claims[0])
        assert bot.sent == []


@pytest.mark.asyncio
async def test_bot_confirmation_queues_durable_broadcast_without_sending(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from aiogram.enums import ChatType
    from aiogram.types import Chat, Message

    from app.bot.handlers.admin.broadcast import on_broadcast_send
    from app.services.admin_broadcast_service import preview_broadcast

    class _State:
        def __init__(self, data: dict) -> None:
            self.data = data

        async def get_data(self) -> dict:
            return self.data

        async def clear(self) -> None:
            self.data = {}

    class _Message:
        async def edit_text(self, *_args, **_kwargs):
            return Message(
                message_id=99,
                date=datetime.now(UTC),
                chat=Chat(id=9_300_000_000_000_000, type=ChatType.PRIVATE),
            )

        async def answer(self, *_args, **_kwargs):
            return None

    class _Callback:
        message = _Message()

        async def answer(self, *_args, **_kwargs):
            return None

    async def edit_message_text(_self, *_args, **_kwargs):
        return None

    monkeypatch.setattr(Message, "edit_text", edit_message_text)
    async with (
        _broadcast_case(test_engine) as (_case, admin, _cookie, _csrf),
        _case.session_maker() as session,
    ):
        preview = await preview_broadcast(
            session,
            admin_id=admin.id,
            target=BroadcastTarget.ALL,
            text="Synthetic bot campaign",
            photo_storage_key=None,
            photo_file_id=None,
            button_text=None,
            button_url=None,
        )
        bot = CountingBot()
        await on_broadcast_send(
            _Callback(),
            session,
            admin,
            bot,
            _State(
                {
                    "content_text": preview.text,
                    "photo_file_id": None,
                    "button_text": None,
                    "button_url": None,
                    "target": preview.target.value,
                    "preview_content_fingerprint": preview.preview_content_fingerprint,
                    "preview_fingerprint": preview.preview_fingerprint,
                    "preview_count": preview.preview_count,
                    "idempotency_key": str(uuid4()),
                }
            ),
            lambda key, **kwargs: key.format(**kwargs),
        )
        assert bot.sent == []
        assert await session.scalar(select(func.count()).select_from(BroadcastRecipient)) == 2
        broadcast = await session.scalar(
            select(Broadcast).where(Broadcast.admin_id == admin.id)
        )
        assert broadcast is not None and broadcast.status == BroadcastStatus.SENDING


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_broadcast_worker(monkeypatch) -> None:
    import app.main as main

    class _BotSession:
        async def close(self) -> None:
            return None

    class _Bot:
        session = _BotSession()

    async def _worker(_bot, _maker, _redis, stop) -> None:
        await stop.wait()

    async def _setup(_bot) -> None:
        return None

    monkeypatch.setattr(main, "create_bot", lambda: _Bot())
    monkeypatch.setattr(main, "setup_bot_commands", _setup)
    monkeypatch.setattr(main, "get_redis", lambda: FakeRedis())
    monkeypatch.setattr(main, "run_outbox_worker", _worker)
    monkeypatch.setattr(main, "run_broadcast_worker", _worker, raising=False)
    app = create_app()
    async with app.router.lifespan_context(app):
        assert app.state.notification_outbox_task.done() is False
        assert app.state.broadcast_worker_task.done() is False
        assert app.state.broadcast_worker_stop.is_set() is False
    assert app.state.notification_outbox_stop.is_set() is True
    assert app.state.broadcast_worker_stop.is_set() is True
    assert app.state.notification_outbox_task.done() is True
    assert app.state.broadcast_worker_task.done() is True
