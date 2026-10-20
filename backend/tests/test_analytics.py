"""Storefront behaviour analytics: collection, attribution, retention and admin reports."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from secrets import token_hex, token_urlsafe
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api import rate_limit
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.analytics import AnalyticsEvent, AnalyticsSession
from app.db.models.enums import AdminRole, OrderType, PaymentMethod
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.user import User
from app.services import analytics_service

from .api_helpers import ApiCase, make_api_case

EVENTS_URL = "/api/v1/analytics/events"


def _now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def _batch(
    *,
    visitor: uuid.UUID,
    session: uuid.UUID,
    events: list[dict[str, Any]],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "visitor_id": str(visitor),
        "session_id": str(session),
        "sent_at": _now_ms(),
        "platform": "telegram",
        "device": "mobile",
        "language": "uz",
        "entry_path": "/",
        "events": events,
        **extra,
    }


@asynccontextmanager
async def _analytics_case(test_engine: AsyncEngine) -> AsyncIterator[ApiCase]:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        before = datetime.now(UTC) - timedelta(seconds=1)
        try:
            yield case
        finally:
            async with case.session_maker() as session:
                await session.execute(
                    delete(AnalyticsSession).where(AnalyticsSession.created_at >= before)
                )
                await session.commit()


async def _sessions(case: ApiCase, *keys: uuid.UUID) -> list[AnalyticsSession]:
    async with case.session_maker() as session:
        rows = await session.scalars(
            select(AnalyticsSession)
            .where(AnalyticsSession.session_key.in_(keys))
            .order_by(AnalyticsSession.id)
        )
        return list(rows)


async def _events(case: ApiCase, key: uuid.UUID) -> list[AnalyticsEvent]:
    async with case.session_maker() as session:
        rows = await session.scalars(
            select(AnalyticsEvent)
            .join(AnalyticsSession, AnalyticsSession.id == AnalyticsEvent.session_id)
            .where(AnalyticsSession.session_key == key)
            .order_by(AnalyticsEvent.id)
        )
        return list(rows)


async def test_a_guest_batch_opens_a_session_and_keeps_only_clean_events(
    test_engine: AsyncEngine,
) -> None:
    visitor, key = uuid.uuid4(), uuid.uuid4()
    now = _now_ms()
    async with _analytics_case(test_engine) as case:
        response = await case.client.post(
            EVENTS_URL,
            json=_batch(
                visitor=visitor,
                session=key,
                referrer="https://t.me/kansshop_uzb?start=1",
                source="channel<script>",
                events=[
                    {"type": "page_view", "path": "/product/42?from=hero", "at": now - 9000},
                    {
                        "type": "section_view",
                        "path": "/",
                        "section": "Hero Carousel!",
                        "value": 0,
                    },
                    {"type": "section_time", "path": "/", "section": "hero", "value": 4000},
                    {"type": "page_time", "path": "/", "value": 999_999},
                    {"type": "page_time", "path": "/", "value": 0},
                    {
                        "type": "product_view",
                        "product_id": case.product_id,
                        "path": "/product/7",
                    },
                    {"type": "add_to_cart", "product_id": 987_654_321, "value": 2},
                    {"type": "teleport", "path": "/"},
                    {"type": "search", "label": "  qora   ruchka  ", "value": 0},
                ],
            ),
        )
        assert response.status_code == 202
        assert response.json() == {"accepted": 7}

        [row] = await _sessions(case, key)
        assert (row.platform, row.device, row.language) == ("telegram", "mobile", "uz")
        assert row.user_id is None and row.is_staff is False
        assert row.referrer == "t.me"
        assert row.source == "channelscript"
        assert row.page_views == 1
        assert row.engaged_ms == analytics_service.MAX_TIMING_MS
        assert row.events_count == 7

        events = await _events(case, key)
        by_type = {event.type: event for event in events}
        assert "teleport" not in by_type
        assert by_type["page_view"].path == "/product/:id"
        assert by_type["section_view"].section == "herocarousel"
        assert by_type["product_view"].product_id == case.product_id
        assert by_type["product_view"].path == "/product/:id"
        assert by_type["add_to_cart"].product_id is None
        assert by_type["search"].label == "qora ruchka"
        assert [event.value for event in events if event.type == "page_time"] == [
            analytics_service.MAX_TIMING_MS
        ]


async def test_signing_in_attributes_the_browser_s_earlier_guest_sessions(
    test_engine: AsyncEngine,
) -> None:
    visitor, guest_key, signed_key = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with _analytics_case(test_engine) as case:
        guest = await case.client.post(
            EVENTS_URL,
            json=_batch(
                visitor=visitor, session=guest_key, events=[{"type": "page_view", "path": "/"}]
            ),
        )
        signed = await case.client.post(
            EVENTS_URL,
            headers={"Authorization": f"Bearer {case.token}"},
            json=_batch(
                visitor=visitor,
                session=signed_key,
                events=[{"type": "page_view", "path": "/cart"}],
            ),
        )
        broken_token = await case.client.post(
            EVENTS_URL,
            headers={"Authorization": "Bearer not-a-token"},
            json=_batch(
                visitor=uuid.uuid4(),
                session=uuid.uuid4(),
                events=[{"type": "page_view", "path": "/"}],
            ),
        )

        assert guest.status_code == signed.status_code == broken_token.status_code == 202
        sessions = await _sessions(case, guest_key, signed_key)
        assert [row.user_id for row in sessions] == [case.user_id, case.user_id]
        assert all(row.is_staff is False for row in sessions)


async def test_staff_browsing_is_flagged(test_engine: AsyncEngine) -> None:
    key = uuid.uuid4()
    async with _analytics_case(test_engine) as case:
        async with case.session_maker() as session:
            user = await session.get(User, case.user_id)
            assert user is not None
            staff = Admin(
                telegram_id=user.telegram_id, full_name="Shop owner", role=AdminRole.MANAGER
            )
            session.add(staff)
            await session.commit()
            staff_id = staff.id
        try:
            response = await case.client.post(
                EVENTS_URL,
                headers={"Authorization": f"Bearer {case.token}"},
                json=_batch(
                    visitor=uuid.uuid4(),
                    session=key,
                    events=[{"type": "page_view", "path": "/"}],
                ),
            )
            assert response.status_code == 202
            [row] = await _sessions(case, key)
            assert row.is_staff is True
        finally:
            async with case.session_maker() as session:
                await session.execute(delete(Admin).where(Admin.id == staff_id))
                await session.commit()


async def test_another_visitor_cannot_write_into_a_session(test_engine: AsyncEngine) -> None:
    key = uuid.uuid4()
    async with _analytics_case(test_engine) as case:
        first = await case.client.post(
            EVENTS_URL,
            json=_batch(
                visitor=uuid.uuid4(), session=key, events=[{"type": "page_view", "path": "/"}]
            ),
        )
        intruder = await case.client.post(
            EVENTS_URL,
            json=_batch(
                visitor=uuid.uuid4(),
                session=key,
                events=[{"type": "page_view", "path": "/"}, {"type": "click", "target": "x"}],
            ),
        )
        assert first.json() == {"accepted": 1}
        assert intruder.json() == {"accepted": 0}
        assert len(await _events(case, key)) == 1


async def test_event_times_follow_the_server_clock(test_engine: AsyncEngine) -> None:
    key = uuid.uuid4()
    client_now = _now_ms() - 3_600_000  # the phone's clock is an hour behind
    async with _analytics_case(test_engine) as case:
        response = await case.client.post(
            EVENTS_URL,
            json={
                **_batch(
                    visitor=uuid.uuid4(),
                    session=key,
                    events=[
                        {"type": "page_view", "path": "/", "at": client_now - 5000},
                        {"type": "click", "target": "old", "at": client_now - 3 * 86_400_000},
                    ],
                ),
                "sent_at": client_now,
            },
        )
        assert response.status_code == 202
        now = datetime.now(UTC)
        page_view, click = await _events(case, key)
        assert timedelta(seconds=3) < now - page_view.occurred_at < timedelta(seconds=30)
        assert abs((now - click.occurred_at) - analytics_service.MAX_EVENT_AGE) < timedelta(
            seconds=30
        )


async def test_crawlers_are_not_counted(test_engine: AsyncEngine) -> None:
    key = uuid.uuid4()
    async with _analytics_case(test_engine) as case:
        response = await case.client.post(
            EVENTS_URL,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1)"},
            json=_batch(
                visitor=uuid.uuid4(), session=key, events=[{"type": "page_view", "path": "/"}]
            ),
        )
        assert response.json() == {"accepted": 0}
        assert await _sessions(case, key) == []


async def test_analytics_has_its_own_rate_budget(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(rate_limit, "ANALYTICS_LIMIT", 1)
    async with _analytics_case(test_engine) as case:
        payload = _batch(
            visitor=uuid.uuid4(),
            session=uuid.uuid4(),
            events=[{"type": "page_view", "path": "/"}],
        )
        with patch("app.api.rate_limit.get_redis") as get_redis:
            counts: dict[str, int] = {}

            async def incr(key: str) -> int:
                counts[key] = counts.get(key, 0) + 1
                return counts[key]

            async def expire(_key: str, _seconds: int) -> bool:
                return True

            get_redis.return_value.incr = incr
            get_redis.return_value.expire = expire
            first = await case.client.post(EVENTS_URL, json=payload)
            second = await case.client.post(EVENTS_URL, json=payload)

        assert first.status_code == 202
        assert second.status_code == 429
        assert all(key.startswith("ratelimit:analytics:") for key in counts)


async def test_old_analytics_are_pruned(test_engine: AsyncEngine) -> None:
    async with _analytics_case(test_engine) as case:
        now = datetime.now(UTC)
        async with case.session_maker() as session:
            ancient = AnalyticsSession(
                session_key=uuid.uuid4(),
                visitor_key=uuid.uuid4(),
                platform="web",
                device="desktop",
                started_at=now - timedelta(days=500),
                last_seen_at=now - timedelta(days=500),
            )
            recent = AnalyticsSession(
                session_key=uuid.uuid4(),
                visitor_key=uuid.uuid4(),
                platform="web",
                device="desktop",
                started_at=now - timedelta(days=200),
                last_seen_at=now - timedelta(days=1),
            )
            session.add_all([ancient, recent])
            await session.flush()
            session.add_all(
                [
                    AnalyticsEvent(
                        session_id=recent.id,
                        type="page_view",
                        occurred_at=now - timedelta(days=190),
                    ),
                    AnalyticsEvent(
                        session_id=recent.id,
                        type="page_view",
                        occurred_at=now - timedelta(days=2),
                    ),
                ]
            )
            await session.commit()
            recent_key, ancient_key = recent.session_key, ancient.session_key

        async with case.session_maker() as session, session.begin():
            events, sessions = await analytics_service.prune_analytics(session, now=now)

        assert events >= 1 and sessions >= 1
        assert [row.session_key for row in await _sessions(case, recent_key, ancient_key)] == [
            recent_key
        ]
        assert len(await _events(case, recent_key)) == 1


# --------------------------------------------------------------------------- reports


async def _admin_cookie(session: AsyncSession, role: AdminRole) -> tuple[int, str]:
    admin = Admin(
        telegram_id=9_400_000_000_000_000 + int(token_hex(4), 16),
        full_name="Synthetic Analytics Admin",
        role=role,
    )
    session.add(admin)
    await session.flush()
    cookie = token_urlsafe(32)
    now = datetime.now(UTC)
    session.add(
        AdminSession(
            admin_id=admin.id,
            token_hash=sha256(cookie.encode("ascii")).hexdigest(),
            csrf_token=token_urlsafe(48),
            auth_epoch=admin.auth_epoch,
            idle_expires_at=now + timedelta(hours=12),
            absolute_expires_at=now + timedelta(days=7),
        )
    )
    await session.flush()
    return admin.id, cookie


async def test_reports_need_a_manager(test_engine: AsyncEngine) -> None:
    async with _analytics_case(test_engine) as case:
        async with case.session_maker() as session:
            admin_id, cookie = await _admin_cookie(session, AdminRole.OPERATOR)
            await session.commit()
        try:
            response = await case.client.get(
                "/api/v1/admin/analytics/summary",
                headers={"Cookie": f"__Host-kans-admin={cookie}"},
            )
            anonymous = await case.client.get("/api/v1/admin/analytics/summary")
            assert response.status_code == 403
            assert anonymous.status_code == 401
        finally:
            async with case.session_maker() as session:
                await session.execute(
                    delete(AdminSession).where(AdminSession.admin_id == admin_id)
                )
                await session.execute(delete(Admin).where(Admin.id == admin_id))
                await session.commit()


async def test_reports_show_behaviour_interest_customers_and_sales(
    test_engine: AsyncEngine,
) -> None:
    async with _analytics_case(test_engine) as case:
        async with case.session_maker() as session:
            admin_id, cookie = await _admin_cookie(session, AdminRole.MANAGER)
            await session.commit()
        headers = {"Cookie": f"__Host-kans-admin={cookie}"}

        async def report(name: str, **params: Any) -> dict[str, Any]:
            response = await case.client.get(
                f"/api/v1/admin/analytics/{name}",
                headers=headers,
                params={"period": "week", **params},
            )
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "private, no-store"
            return response.json()

        order_id: int | None = None
        try:
            before_summary = await report("summary")
            before_sales = await report("sales")

            signed_key, guest_key = uuid.uuid4(), uuid.uuid4()
            shopper_events = [
                {"type": "page_view", "path": "/"},
                {"type": "section_view", "path": "/", "section": "hero", "value": 0},
                {"type": "section_view", "path": "/", "section": "products", "value": 3},
                {"type": "section_time", "path": "/", "section": "products", "value": 8000},
                {"type": "scroll_depth", "path": "/", "target": "pv1", "value": 60},
                {"type": "scroll_depth", "path": "/", "target": "pv1", "value": 80},
                {
                    "type": "click",
                    "path": "/",
                    "section": "hero",
                    "target": "hero_cta",
                    "label": "Mahsulot tanlash",
                },
                {"type": "search", "path": "/", "label": "Ruchka", "value": 3},
                {"type": "filter", "path": "/", "target": "sort", "label": "price_asc"},
                {"type": "product_impression", "path": "/", "product_id": case.product_id},
                {
                    "type": "page_view",
                    "path": f"/product/{case.product_id}",
                    "product_id": case.product_id,
                },
                {
                    "type": "product_view",
                    "path": f"/product/{case.product_id}",
                    "product_id": case.product_id,
                },
                {
                    "type": "page_time",
                    "path": f"/product/{case.product_id}",
                    "product_id": case.product_id,
                    "value": 30_000,
                },
                {"type": "add_to_cart", "product_id": case.product_id, "value": 2},
                {"type": "favorite_add", "product_id": case.product_id},
                {"type": "checkout_start", "path": "/checkout"},
                {"type": "order_placed", "path": "/orders/:id"},
            ]
            signed = await case.client.post(
                EVENTS_URL,
                headers={"Authorization": f"Bearer {case.token}"},
                json=_batch(visitor=uuid.uuid4(), session=signed_key, events=shopper_events),
            )
            guest = await case.client.post(
                EVENTS_URL,
                json=_batch(
                    visitor=uuid.uuid4(),
                    session=guest_key,
                    platform="web",
                    device="desktop",
                    events=[
                        {"type": "page_view", "path": "/"},
                        {"type": "section_view", "path": "/", "section": "hero", "value": 0},
                        {"type": "scroll_depth", "path": "/", "value": 20},
                        {
                            "type": "page_view",
                            "path": f"/product/{case.product_id}",
                            "product_id": case.product_id,
                        },
                        {
                            "type": "product_view",
                            "path": f"/product/{case.product_id}",
                            "product_id": case.product_id,
                        },
                    ],
                ),
            )
            assert signed.status_code == guest.status_code == 202

            async with case.session_maker() as session:
                shopper = await session.get(User, case.user_id)
                assert shopper is not None
                shopper.phone = "+998901112233"
                order = Order(
                    order_number=f"AN-{token_hex(4)}",
                    user_id=case.user_id,
                    order_type=OrderType.DELIVERY,
                    customer_name="Analytics buyer",
                    customer_phone="+998901112233",
                    subtotal=Decimal("10000"),
                    total=Decimal("10000"),
                    payment_method=PaymentMethod.CASH,
                )
                session.add(order)
                await session.flush()
                session.add(
                    OrderItem(
                        order_id=order.id,
                        product_id=case.product_id,
                        product_name_snapshot="Test pen",
                        product_sku_snapshot="SKU",
                        price=Decimal("5000"),
                        quantity=2,
                        total=Decimal("10000"),
                    )
                )
                await session.commit()
                order_id = order.id

            summary = await report("summary")
            assert summary["sessions"] - before_summary["sessions"] == 2
            assert summary["visitors"] - before_summary["visitors"] == 2
            assert summary["signed_in_visitors"] - before_summary["signed_in_visitors"] == 1
            assert summary["product_views"] - before_summary["product_views"] == 2
            assert summary["cart_adds"] - before_summary["cart_adds"] == 1
            assert summary["sales"]["orders"] - before_summary["sales"]["orders"] == 1
            assert len(summary["timeline"]) >= 7
            assert {item["key"] for item in summary["platforms"]} >= {"telegram", "web"}

            behavior = await report("behavior")
            home_sections = {
                item["section"]: item for item in behavior["sections"] if item["path"] == "/"
            }
            assert home_sections["hero"]["sessions"] >= 2
            assert home_sections["products"]["total_seconds"] >= 8
            assert home_sections["products"]["position"] == 3
            assert any(click["target"] == "hero_cta" for click in behavior["clicks"])
            assert any(search["term"] == "ruchka" for search in behavior["searches"])
            assert [step["key"] for step in behavior["funnel"]] == [
                "sessions",
                "product_view",
                "add_to_cart",
                "checkout_start",
                "order_placed",
            ]
            assert len(behavior["hours"]) == 24
            # Two reports of the same page view count once, at their deepest.
            home_scroll = next(item for item in behavior["scroll"] if item["path"] == "/")
            assert home_scroll["page_views"] == 2
            assert home_scroll["reached_75"] == 0.5

            products = await report("products")
            pen = next(
                item for item in products["products"] if item["product_id"] == case.product_id
            )
            assert pen["views"] >= 2 and pen["viewers"] >= 2
            assert pen["cart_adds"] >= 1 and pen["favorites"] >= 1
            assert pen["ordered_qty"] >= 2 and pen["view_seconds"] >= 30
            assert pen["name"] == "Test pen"

            customers = await report("customers", query="Cart API")
            mine = next(item for item in customers["items"] if item["user_id"] == case.user_id)
            assert mine["sessions"] == 1 and mine["orders"] == 1
            assert mine["phone"] == "+998*****2233"  # masked like the admin customer list
            assert mine["interests"] == ["Test pen"]
            assert mine["platform"] == "telegram"
            assert customers["guest_sessions"] >= 1

            detail = await report(f"customers/{case.user_id}")
            assert detail["customer"]["user_id"] == case.user_id
            assert detail["products"][0]["product_id"] == case.product_id
            assert detail["products"][0]["ordered_qty"] == 2
            assert detail["searches"] == ["Ruchka"]
            assert {event["type"] for event in detail["events"]} >= {
                "product_view",
                "add_to_cart",
            }
            assert not any(event["type"] == "page_time" for event in detail["events"])

            missing = await case.client.get(
                "/api/v1/admin/analytics/customers/999999999", headers=headers
            )
            assert missing.status_code == 404

            sales = await report("sales")
            assert sales["summary"]["orders"] - before_sales["summary"]["orders"] == 1
            assert Decimal(sales["summary"]["revenue"]) - Decimal(
                before_sales["summary"]["revenue"]
            ) == Decimal("10000")
            assert any(item["name"] == "Test pen" for item in sales["top_products"])
            assert any(item["key"] == "cash" for item in sales["payment_methods"])
            assert sum(cell["orders"] for cell in sales["heatmap"]) >= 1
        finally:
            async with case.session_maker() as session:
                if order_id is not None:
                    await session.execute(
                        delete(OrderItem).where(OrderItem.order_id == order_id)
                    )
                    await session.execute(delete(Order).where(Order.id == order_id))
                await session.execute(
                    delete(AdminSession).where(AdminSession.admin_id == admin_id)
                )
                await session.execute(delete(Admin).where(Admin.id == admin_id))
                await session.commit()
