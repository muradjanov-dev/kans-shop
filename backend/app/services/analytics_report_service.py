"""Read side of the storefront analytics: what the admin dashboard shows.

Periods follow the admin stats: `today` is the Tashkent calendar day, the others are
rolling windows. Sessions belong to a period by their start, events by their own time.
Staff sessions (admins browsing their own shop) are left out unless asked for.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.analytics import (
    AmountOut,
    AnalyticsBehaviorOut,
    AnalyticsCustomerDetailOut,
    AnalyticsCustomersOut,
    AnalyticsProductsOut,
    AnalyticsSalesOut,
    AnalyticsSummaryOut,
    ClickStatOut,
    CountOut,
    CustomerActivityOut,
    CustomerEventOut,
    CustomerProductOut,
    CustomerSessionOut,
    FunnelStepOut,
    HeatCellOut,
    PageStatOut,
    ProductInterestOut,
    SalesSummaryOut,
    ScrollStatOut,
    SearchStatOut,
    SectionStatOut,
    TimelinePointOut,
    TopCustomerOut,
    TopSoldProductOut,
)
from app.core.config import settings
from app.core.exceptions import UserNotFoundError
from app.db.models.analytics import AnalyticsEvent, AnalyticsSession
from app.db.models.category import Category
from app.db.models.enums import OrderStatus, PaymentStatus
from app.db.models.order import Order
from app.db.models.order_item import OrderItem
from app.db.models.product import Product
from app.db.models.product_image import ProductImage
from app.db.models.user import User
from app.services.customer_admin_service import mask_phone

Period = Literal["today", "week", "month", "quarter"]
_ROLLING_DAYS = {"week": 7, "month": 30, "quarter": 90}
BOUNCE_MS = 10_000
_ZERO = Decimal("0")


def _zone() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def period_bounds(period: Period, *, now: datetime) -> tuple[datetime, datetime]:
    end = now.astimezone(UTC)
    if period == "today":
        local = end.astimezone(_zone())
        return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC), end
    if period not in _ROLLING_DAYS:
        raise ValueError("period must be today, week, month or quarter")
    return end - timedelta(days=_ROLLING_DAYS[period]), end


def _local_days(since: datetime, until: datetime) -> list[date]:
    first = since.astimezone(_zone()).date()
    last = until.astimezone(_zone()).date()
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _local(column: Any) -> Any:
    return func.timezone(settings.timezone, column)


def _ratio(part: int | float, whole: int | float) -> float:
    return round(part / whole, 4) if whole else 0.0


def _seconds(milliseconds: int | Decimal | None) -> int:
    return int((milliseconds or 0) // 1000)


@dataclass(frozen=True)
class _Scope:
    since: datetime
    until: datetime
    include_staff: bool

    def sessions(self) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            AnalyticsSession.started_at >= self.since,
            AnalyticsSession.started_at <= self.until,
        ]
        if not self.include_staff:
            conditions.append(AnalyticsSession.is_staff.is_(False))
        return conditions

    def events(self) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [
            AnalyticsEvent.occurred_at >= self.since,
            AnalyticsEvent.occurred_at <= self.until,
        ]
        if not self.include_staff:
            conditions.append(AnalyticsSession.is_staff.is_(False))
        return conditions

    def orders(self) -> list[ColumnElement[bool]]:
        return [Order.created_at >= self.since, Order.created_at <= self.until]


def _scope(period: Period, *, now: datetime, include_staff: bool) -> _Scope:
    since, until = period_bounds(period, now=now)
    return _Scope(since=since, until=until, include_staff=include_staff)


def _events_select(*columns: Any) -> Any:
    return (
        select(*columns)
        .select_from(AnalyticsEvent)
        .join(AnalyticsSession, AnalyticsSession.id == AnalyticsEvent.session_id)
    )


_LIVE_ORDER = Order.status != OrderStatus.CANCELLED


# --------------------------------------------------------------------------- sales


async def _sales_summary(session: AsyncSession, scope: _Scope) -> SalesSummaryOut:
    row = (
        await session.execute(
            select(
                func.count().filter(_LIVE_ORDER).label("orders"),
                func.coalesce(func.sum(Order.total).filter(_LIVE_ORDER), 0).label("revenue"),
                func.coalesce(
                    func.sum(Order.total).filter(
                        _LIVE_ORDER, Order.payment_status == PaymentStatus.PAID
                    ),
                    0,
                ).label("paid"),
                func.count().filter(Order.status == OrderStatus.CANCELLED).label("cancelled"),
                func.count(distinct(Order.user_id)).filter(_LIVE_ORDER).label("customers"),
            ).where(*scope.orders())
        )
    ).one()
    items_sold = await session.scalar(
        select(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(*scope.orders(), _LIVE_ORDER)
    )
    first_orders = (
        select(Order.user_id, func.min(Order.created_at).label("first_at"))
        .where(_LIVE_ORDER)
        .group_by(Order.user_id)
        .subquery()
    )
    new_customers = await session.scalar(
        select(func.count())
        .select_from(first_orders)
        .where(first_orders.c.first_at >= scope.since, first_orders.c.first_at <= scope.until)
    )
    orders = int(row.orders or 0)
    revenue = Decimal(row.revenue or 0)
    customers = int(row.customers or 0)
    new = int(new_customers or 0)
    return SalesSummaryOut(
        orders=orders,
        revenue=revenue,
        paid_amount=Decimal(row.paid or 0),
        avg_check=(revenue / orders).quantize(Decimal("0.01")) if orders else _ZERO,
        items_sold=int(items_sold or 0),
        cancelled=int(row.cancelled or 0),
        customers=customers,
        new_customers=new,
        returning_customers=max(customers - new, 0),
    )


async def sales_report(
    session: AsyncSession, *, period: Period, now: datetime
) -> AnalyticsSalesOut:
    scope = _scope(period, now=now, include_staff=True)
    summary = await _sales_summary(session, scope)

    async def grouped(column: Any, *, live_only: bool) -> list[AmountOut]:
        conditions = [*scope.orders()]
        if live_only:
            conditions.append(_LIVE_ORDER)
        rows = await session.execute(
            select(column, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(*conditions)
            .group_by(column)
            .order_by(func.count().desc())
        )
        return [
            AmountOut(
                key=str(getattr(key, "value", key)), count=int(count), amount=Decimal(amount)
            )
            for key, count, amount in rows
        ]

    category_name = func.coalesce(Category.name_uz, "—")
    category_rows = await session.execute(
        select(
            category_name,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.total), 0),
        )
        .select_from(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .outerjoin(Product, Product.id == OrderItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(*scope.orders(), _LIVE_ORDER)
        .group_by(category_name)
        .order_by(func.coalesce(func.sum(OrderItem.total), 0).desc())
        .limit(15)
    )
    top_product_rows = await session.execute(
        select(
            OrderItem.product_name_snapshot,
            func.sum(OrderItem.quantity),
            func.sum(OrderItem.total),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(*scope.orders(), _LIVE_ORDER)
        .group_by(OrderItem.product_name_snapshot)
        .order_by(func.sum(OrderItem.total).desc())
        .limit(15)
    )
    top_customer_rows = await session.execute(
        select(
            User.id, User.display_name, User.first_name, func.count(), func.sum(Order.total)
        )
        .select_from(Order)
        .join(User, User.id == Order.user_id)
        .where(*scope.orders(), _LIVE_ORDER)
        .group_by(User.id, User.display_name, User.first_name)
        .order_by(func.sum(Order.total).desc())
        .limit(10)
    )
    weekday = func.extract("isodow", _local(Order.created_at))
    hour = func.extract("hour", _local(Order.created_at))
    heat_rows = await session.execute(
        select(weekday, hour, func.count())
        .where(*scope.orders(), _LIVE_ORDER)
        .group_by(weekday, hour)
    )
    return AnalyticsSalesOut(
        period=period,
        summary=summary,
        statuses=await grouped(Order.status, live_only=False),
        payment_methods=await grouped(Order.payment_method, live_only=True),
        order_types=await grouped(Order.order_type, live_only=True),
        categories=[
            AmountOut(key=str(name), count=int(quantity), amount=Decimal(amount))
            for name, quantity, amount in category_rows
        ],
        top_products=[
            TopSoldProductOut(name=name, quantity=int(quantity), revenue=Decimal(revenue))
            for name, quantity, revenue in top_product_rows
        ],
        top_customers=[
            TopCustomerOut(
                user_id=user_id,
                name=_display_name(display_name, first_name),
                orders=int(count),
                revenue=Decimal(revenue),
            )
            for user_id, display_name, first_name, count, revenue in top_customer_rows
        ],
        heatmap=[
            HeatCellOut(weekday=int(day), hour=int(hour_of_day), orders=int(count))
            for day, hour_of_day, count in heat_rows
        ],
        avg_items_per_order=(
            round(summary.items_sold / summary.orders, 2) if summary.orders else 0.0
        ),
    )


def _display_name(display_name: str | None, first_name: str | None) -> str:
    for candidate in (display_name, first_name):
        if candidate and candidate.strip() and candidate != "Foydalanuvchi":
            return candidate.strip()
    return (display_name or first_name or "—").strip() or "—"


# --------------------------------------------------------------------------- summary


async def summary_report(
    session: AsyncSession, *, period: Period, now: datetime, include_staff: bool = False
) -> AnalyticsSummaryOut:
    scope = _scope(period, now=now, include_staff=include_staff)
    totals = (
        await session.execute(
            select(
                func.count().label("sessions"),
                func.count(distinct(AnalyticsSession.visitor_key)).label("visitors"),
                func.count(distinct(AnalyticsSession.user_id)).label("signed_in"),
                func.coalesce(func.sum(AnalyticsSession.page_views), 0).label("page_views"),
                func.coalesce(func.sum(AnalyticsSession.engaged_ms), 0).label("engaged_ms"),
                func.count()
                .filter(
                    AnalyticsSession.page_views <= 1, AnalyticsSession.engaged_ms < BOUNCE_MS
                )
                .label("bounces"),
            ).where(*scope.sessions())
        )
    ).one()
    sessions = int(totals.sessions or 0)
    visitors = int(totals.visitors or 0)

    active_visitors = select(AnalyticsSession.visitor_key).where(*scope.sessions()).distinct()
    first_seen = (
        select(
            AnalyticsSession.visitor_key,
            func.min(AnalyticsSession.started_at).label("first_at"),
        )
        .where(AnalyticsSession.visitor_key.in_(active_visitors))
        .group_by(AnalyticsSession.visitor_key)
        .subquery()
    )
    new_visitors = int(
        await session.scalar(
            select(func.count())
            .select_from(first_seen)
            .where(first_seen.c.first_at >= scope.since)
        )
        or 0
    )

    event_totals = (
        await session.execute(
            _events_select(
                func.count().filter(AnalyticsEvent.type == "product_view").label("views"),
                func.count().filter(AnalyticsEvent.type == "add_to_cart").label("carts"),
                func.count(distinct(AnalyticsEvent.session_id))
                .filter(AnalyticsEvent.type == "order_placed")
                .label("ordering_sessions"),
            ).where(*scope.events())
        )
    ).one()

    async def split(column: Any, limit: int = 10) -> list[CountOut]:
        rows = await session.execute(
            select(column, func.count())
            .where(*scope.sessions())
            .group_by(column)
            .order_by(func.count().desc())
            .limit(limit)
        )
        return [CountOut(key=str(key or "direct"), count=int(count)) for key, count in rows]

    day = func.date(_local(AnalyticsSession.started_at))
    visit_rows = await session.execute(
        select(day, func.count(), func.count(distinct(AnalyticsSession.visitor_key)))
        .where(*scope.sessions())
        .group_by(day)
    )
    visits = {row[0]: (int(row[1]), int(row[2])) for row in visit_rows}
    order_day = func.date(_local(Order.created_at))
    order_rows = await session.execute(
        select(order_day, func.count(), func.coalesce(func.sum(Order.total), 0))
        .where(*scope.orders(), _LIVE_ORDER)
        .group_by(order_day)
    )
    orders_by_day = {row[0]: (int(row[1]), Decimal(row[2])) for row in order_rows}
    timeline = [
        TimelinePointOut(
            day=day_value,
            sessions=visits.get(day_value, (0, 0))[0],
            visitors=visits.get(day_value, (0, 0))[1],
            orders=orders_by_day.get(day_value, (0, _ZERO))[0],
            revenue=orders_by_day.get(day_value, (0, _ZERO))[1],
        )
        for day_value in _local_days(scope.since, scope.until)
    ]

    return AnalyticsSummaryOut(
        period=period,
        since=scope.since,
        until=scope.until,
        visitors=visitors,
        new_visitors=new_visitors,
        returning_visitors=max(visitors - new_visitors, 0),
        signed_in_visitors=int(totals.signed_in or 0),
        sessions=sessions,
        page_views=int(totals.page_views or 0),
        engaged_seconds=_seconds(totals.engaged_ms),
        avg_session_seconds=_seconds(totals.engaged_ms) // sessions if sessions else 0,
        bounce_rate=_ratio(int(totals.bounces or 0), sessions),
        product_views=int(event_totals.views or 0),
        cart_adds=int(event_totals.carts or 0),
        conversion_rate=_ratio(int(event_totals.ordering_sessions or 0), sessions),
        platforms=await split(AnalyticsSession.platform),
        devices=await split(AnalyticsSession.device),
        sources=await split(func.coalesce(AnalyticsSession.source, AnalyticsSession.referrer)),
        timeline=timeline,
        sales=await _sales_summary(session, scope),
    )


# --------------------------------------------------------------------------- behaviour

FUNNEL_STEPS = ("product_view", "add_to_cart", "checkout_start", "order_placed")


async def behavior_report(
    session: AsyncSession, *, period: Period, now: datetime, include_staff: bool = False
) -> AnalyticsBehaviorOut:
    scope = _scope(period, now=now, include_staff=include_staff)
    events = scope.events()
    sessions_total = int(
        await session.scalar(
            select(func.count()).select_from(AnalyticsSession).where(*scope.sessions())
        )
        or 0
    )

    page_rows = await session.execute(
        _events_select(
            AnalyticsEvent.path,
            func.count().filter(AnalyticsEvent.type == "page_view"),
            func.count(distinct(AnalyticsEvent.session_id)).filter(
                AnalyticsEvent.type == "page_view"
            ),
            func.coalesce(
                func.sum(AnalyticsEvent.value).filter(AnalyticsEvent.type == "page_time"), 0
            ),
        )
        .where(
            *events,
            AnalyticsEvent.path.is_not(None),
            AnalyticsEvent.type.in_(("page_view", "page_time")),
        )
        .group_by(AnalyticsEvent.path)
    )
    pages: list[PageStatOut] = []
    sessions_by_path: dict[str, int] = {}
    for path, views, page_sessions, total_ms in page_rows:
        sessions_by_path[path] = int(page_sessions)
        pages.append(
            PageStatOut(
                path=path,
                views=int(views),
                sessions=int(page_sessions),
                total_seconds=_seconds(total_ms),
                avg_seconds=round(int(total_ms) / 1000 / int(views), 1) if views else 0.0,
            )
        )
    pages.sort(key=lambda page: (page.views, page.total_seconds), reverse=True)

    reach_rows = await session.execute(
        _events_select(
            AnalyticsEvent.path,
            AnalyticsEvent.section,
            func.count(distinct(AnalyticsEvent.session_id)),
            func.coalesce(func.min(AnalyticsEvent.value), 0),
        )
        .where(
            *events, AnalyticsEvent.type == "section_view", AnalyticsEvent.section.is_not(None)
        )
        .group_by(AnalyticsEvent.path, AnalyticsEvent.section)
    )
    time_rows = await session.execute(
        _events_select(
            AnalyticsEvent.path,
            AnalyticsEvent.section,
            func.coalesce(func.sum(AnalyticsEvent.value), 0),
        )
        .where(
            *events, AnalyticsEvent.type == "section_time", AnalyticsEvent.section.is_not(None)
        )
        .group_by(AnalyticsEvent.path, AnalyticsEvent.section)
    )
    section_time = {(path, section): int(total) for path, section, total in time_rows}
    sections: list[SectionStatOut] = []
    for path, section, reached, position in reach_rows:
        path_key = path or ""
        total_ms = section_time.pop((path, section), 0)
        page_sessions = sessions_by_path.get(path_key, 0)
        sections.append(
            SectionStatOut(
                path=path_key,
                section=section,
                position=int(position),
                sessions=int(reached),
                reach_rate=(
                    min(_ratio(int(reached), page_sessions), 1.0) if page_sessions else 0.0
                ),
                total_seconds=_seconds(total_ms),
                avg_seconds=round(total_ms / 1000 / int(reached), 1) if reached else 0.0,
            )
        )
    sections.sort(
        key=lambda item: (-sessions_by_path.get(item.path, 0), item.path, item.position)
    )

    # A page view can report its depth more than once (tab hidden, then left); the target
    # carries the page view number, so keep only the deepest report of each view.
    per_view = (
        _events_select(
            AnalyticsEvent.path.label("path"),
            func.max(AnalyticsEvent.value).label("depth"),
        )
        .where(
            *events, AnalyticsEvent.type == "scroll_depth", AnalyticsEvent.path.is_not(None)
        )
        .group_by(AnalyticsEvent.session_id, AnalyticsEvent.path, AnalyticsEvent.target)
        .subquery()
    )
    scroll_rows = await session.execute(
        select(
            per_view.c.path,
            func.count(),
            func.count().filter(per_view.c.depth >= 25),
            func.count().filter(per_view.c.depth >= 50),
            func.count().filter(per_view.c.depth >= 75),
            func.count().filter(per_view.c.depth >= 90),
        )
        .group_by(per_view.c.path)
        .order_by(func.count().desc())
        .limit(12)
    )
    scroll = [
        ScrollStatOut(
            path=path,
            page_views=int(total),
            reached_25=_ratio(int(q25), int(total)),
            reached_50=_ratio(int(q50), int(total)),
            reached_75=_ratio(int(q75), int(total)),
            reached_90=_ratio(int(q90), int(total)),
        )
        for path, total, q25, q50, q75, q90 in scroll_rows
    ]

    click_rows = await session.execute(
        _events_select(
            AnalyticsEvent.section,
            AnalyticsEvent.target,
            AnalyticsEvent.label,
            func.count(),
            func.count(distinct(AnalyticsEvent.session_id)),
        )
        .where(*events, AnalyticsEvent.type == "click")
        .group_by(AnalyticsEvent.section, AnalyticsEvent.target, AnalyticsEvent.label)
        .order_by(func.count().desc())
        .limit(30)
    )
    clicks = [
        ClickStatOut(
            section=section,
            target=target,
            label=label,
            clicks=int(count),
            sessions=int(unique),
        )
        for section, target, label, count, unique in click_rows
    ]

    funnel_row = (
        await session.execute(
            _events_select(
                *(
                    func.count(distinct(AnalyticsEvent.session_id)).filter(
                        AnalyticsEvent.type == step
                    )
                    for step in FUNNEL_STEPS
                )
            ).where(*events, AnalyticsEvent.type.in_(FUNNEL_STEPS))
        )
    ).one()
    funnel = [FunnelStepOut(key="sessions", sessions=sessions_total)] + [
        FunnelStepOut(key=step, sessions=int(count or 0))
        for step, count in zip(FUNNEL_STEPS, funnel_row, strict=True)
    ]

    hour = func.extract("hour", _local(AnalyticsSession.started_at))
    hour_rows = await session.execute(
        select(hour, func.count()).where(*scope.sessions()).group_by(hour)
    )
    hours = [0] * 24
    for hour_value, count in hour_rows:
        hours[int(hour_value) % 24] = int(count)

    term = func.lower(AnalyticsEvent.label)
    search_rows = await session.execute(
        _events_select(
            term,
            func.count(),
            func.count(distinct(AnalyticsEvent.session_id)),
            func.count().filter(AnalyticsEvent.value == 0),
        )
        .where(*events, AnalyticsEvent.type == "search", AnalyticsEvent.label.is_not(None))
        .group_by(term)
        .order_by(func.count().desc())
        .limit(30)
    )
    searches = [
        SearchStatOut(
            term=value, searches=int(count), sessions=int(unique), zero_results=int(zero)
        )
        for value, count, unique, zero in search_rows
    ]

    async def counted(event_type: str) -> list[CountOut]:
        rows = await session.execute(
            _events_select(AnalyticsEvent.target, func.count())
            .where(*events, AnalyticsEvent.type == event_type)
            .group_by(AnalyticsEvent.target)
            .order_by(func.count().desc())
            .limit(20)
        )
        return [CountOut(key=str(key or "—"), count=int(count)) for key, count in rows]

    return AnalyticsBehaviorOut(
        period=period,
        sessions=sessions_total,
        sections=sections,
        pages=pages[:20],
        scroll=scroll,
        clicks=clicks,
        funnel=funnel,
        hours=hours,
        searches=searches,
        filters=await counted("filter"),
        carousel=await counted("carousel"),
    )


# --------------------------------------------------------------------------- products


async def _product_details(
    session: AsyncSession, product_ids: set[int]
) -> dict[int, tuple[str, Decimal | None, str | None]]:
    if not product_ids:
        return {}
    rows = await session.execute(
        select(Product.id, Product.name_uz, Product.price).where(Product.id.in_(product_ids))
    )
    details: dict[int, tuple[str, Decimal | None, str | None]] = {
        product_id: (name, price, None) for product_id, name, price in rows
    }
    image_rows = await session.execute(
        select(ProductImage.product_id, ProductImage.url)
        .where(ProductImage.product_id.in_(product_ids), ProductImage.url.is_not(None))
        .order_by(
            ProductImage.product_id, ProductImage.is_main.desc(), ProductImage.sort_order
        )
    )
    seen: set[int] = set()
    for product_id, url in image_rows:
        if product_id in seen or product_id not in details or not (url or "").strip():
            continue
        seen.add(product_id)
        name, price, _image = details[product_id]
        details[product_id] = (name, price, url.strip())
    return details


async def _ordered_by_product(
    session: AsyncSession, scope: _Scope, *, user_id: int | None = None
) -> dict[int, tuple[int, Decimal]]:
    conditions = [*scope.orders(), _LIVE_ORDER, OrderItem.product_id.is_not(None)]
    if user_id is not None:
        conditions.append(Order.user_id == user_id)
    rows = await session.execute(
        select(OrderItem.product_id, func.sum(OrderItem.quantity), func.sum(OrderItem.total))
        .join(Order, Order.id == OrderItem.order_id)
        .where(*conditions)
        .group_by(OrderItem.product_id)
    )
    return {
        int(product_id): (int(quantity), Decimal(total))
        for product_id, quantity, total in rows
    }


def _interest_columns() -> tuple[Any, ...]:
    return (
        func.count().filter(AnalyticsEvent.type == "product_impression"),
        func.count().filter(AnalyticsEvent.type == "product_view"),
        func.count(distinct(AnalyticsEvent.session_id)).filter(
            AnalyticsEvent.type == "product_view"
        ),
        func.coalesce(
            func.sum(AnalyticsEvent.value).filter(AnalyticsEvent.type == "page_time"), 0
        ),
        func.count().filter(AnalyticsEvent.type == "add_to_cart"),
        func.count().filter(AnalyticsEvent.type == "favorite_add"),
    )


async def products_report(
    session: AsyncSession, *, period: Period, now: datetime, include_staff: bool = False
) -> AnalyticsProductsOut:
    scope = _scope(period, now=now, include_staff=include_staff)
    rows = await session.execute(
        _events_select(AnalyticsEvent.product_id, *_interest_columns())
        .where(*scope.events(), AnalyticsEvent.product_id.is_not(None))
        .group_by(AnalyticsEvent.product_id)
    )
    interest = {
        int(product_id): (
            int(impressions),
            int(views),
            int(viewers),
            int(view_ms),
            int(carts),
            int(favorites),
        )
        for product_id, impressions, views, viewers, view_ms, carts, favorites in rows
    }
    ordered = await _ordered_by_product(session, scope)
    details = await _product_details(session, set(interest) | set(ordered))

    items: list[ProductInterestOut] = []
    for product_id, (name, price, image_url) in details.items():
        impressions, views, viewers, view_ms, carts, favorites = interest.get(
            product_id, (0, 0, 0, 0, 0, 0)
        )
        quantity, revenue = ordered.get(product_id, (0, _ZERO))
        items.append(
            ProductInterestOut(
                product_id=product_id,
                name=name,
                price=price,
                image_url=image_url,
                impressions=impressions,
                views=views,
                viewers=viewers,
                view_seconds=_seconds(view_ms),
                cart_adds=carts,
                favorites=favorites,
                ordered_qty=quantity,
                revenue=revenue,
            )
        )
    items.sort(
        key=lambda item: (item.views, item.cart_adds, item.ordered_qty, item.impressions),
        reverse=True,
    )
    not_bought = [item for item in items if item.viewers >= 2 and item.ordered_qty == 0]
    not_bought.sort(
        key=lambda item: (item.viewers, item.cart_adds, item.view_seconds), reverse=True
    )
    return AnalyticsProductsOut(
        period=period, products=items[:60], interested_not_bought=not_bought[:20]
    )


# --------------------------------------------------------------------------- customers


def _interest_score(views: int, carts: int, favorites: int, view_ms: int) -> float:
    return views + 3 * carts + 2 * favorites + view_ms / 60_000


async def _customer_rows(
    session: AsyncSession,
    scope: _Scope,
    *,
    user_ids: list[int],
) -> list[CustomerActivityOut]:
    if not user_ids:
        return []
    activity = {
        row.user_id: row
        for row in await session.execute(
            select(
                AnalyticsSession.user_id,
                func.count().label("sessions"),
                func.coalesce(func.sum(AnalyticsSession.engaged_ms), 0).label("engaged_ms"),
                func.coalesce(func.sum(AnalyticsSession.page_views), 0).label("page_views"),
                func.min(AnalyticsSession.started_at).label("first_seen"),
                func.max(AnalyticsSession.last_seen_at).label("last_seen"),
            )
            .where(*scope.sessions(), AnalyticsSession.user_id.in_(user_ids))
            .group_by(AnalyticsSession.user_id)
        )
    }
    platforms = {
        user_id: platform
        for user_id, platform in await session.execute(
            select(AnalyticsSession.user_id, AnalyticsSession.platform)
            .where(*scope.sessions(), AnalyticsSession.user_id.in_(user_ids))
            .distinct(AnalyticsSession.user_id)
            .order_by(AnalyticsSession.user_id, AnalyticsSession.last_seen_at.desc())
        )
    }
    per_product: dict[int, list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for user_id, product_id, views, carts, favorites, view_ms in await session.execute(
        _events_select(
            AnalyticsSession.user_id,
            AnalyticsEvent.product_id,
            func.count().filter(AnalyticsEvent.type == "product_view"),
            func.count().filter(AnalyticsEvent.type == "add_to_cart"),
            func.count().filter(AnalyticsEvent.type == "favorite_add"),
            func.coalesce(
                func.sum(AnalyticsEvent.value).filter(AnalyticsEvent.type == "page_time"), 0
            ),
        )
        .where(
            *scope.events(),
            AnalyticsSession.user_id.in_(user_ids),
            AnalyticsEvent.product_id.is_not(None),
            AnalyticsEvent.type.in_(
                ("product_view", "add_to_cart", "favorite_add", "page_time")
            ),
        )
        .group_by(AnalyticsSession.user_id, AnalyticsEvent.product_id)
    ):
        per_product[int(user_id)].append(
            (int(product_id), int(views), int(carts), int(favorites), int(view_ms))
        )
    orders = {
        user_id: (int(count), Decimal(total))
        for user_id, count, total in await session.execute(
            select(Order.user_id, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(*scope.orders(), _LIVE_ORDER, Order.user_id.in_(user_ids))
            .group_by(Order.user_id)
        )
    }
    users = {
        user.id: user
        for user in await session.scalars(select(User).where(User.id.in_(user_ids)))
    }
    names = await _product_details(
        session, {product_id for rows in per_product.values() for product_id, *_ in rows}
    )

    result: list[CustomerActivityOut] = []
    for user_id in user_ids:
        user = users.get(user_id)
        stats = activity.get(user_id)
        if user is None or stats is None:
            continue
        products = per_product.get(user_id, [])
        ranked = sorted(
            products,
            key=lambda item: _interest_score(item[1], item[2], item[3], item[4]),
            reverse=True,
        )
        order_count, revenue = orders.get(user_id, (0, _ZERO))
        result.append(
            CustomerActivityOut(
                user_id=user_id,
                name=_display_name(user.display_name, user.first_name),
                username=user.username,
                # Same privacy as the admin customer list: never the full number.
                phone=mask_phone(user.phone),
                sessions=int(stats.sessions),
                engaged_seconds=_seconds(stats.engaged_ms),
                page_views=int(stats.page_views),
                first_seen=stats.first_seen,
                last_seen=stats.last_seen,
                platform=platforms.get(user_id, "web"),
                products_viewed=sum(1 for item in products if item[1] > 0),
                cart_adds=sum(item[2] for item in products),
                orders=order_count,
                revenue=revenue,
                interests=[names[item[0]][0] for item in ranked[:3] if item[0] in names],
            )
        )
    return result


async def customers_report(
    session: AsyncSession,
    *,
    period: Period,
    now: datetime,
    page: int = 1,
    limit: int = 20,
    query: str | None = None,
    include_staff: bool = False,
) -> AnalyticsCustomersOut:
    scope = _scope(period, now=now, include_staff=include_staff)
    conditions: list[ColumnElement[bool]] = [
        *scope.sessions(),
        AnalyticsSession.user_id.is_not(None),
    ]
    search = (query or "").strip()
    if search:
        pattern = f"%{search.replace('%', '').replace('_', '')}%"
        conditions.append(
            or_(
                User.display_name.ilike(pattern),
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.username.ilike(pattern),
                User.phone.ilike(pattern),
            )
        )
    engaged = func.coalesce(func.sum(AnalyticsSession.engaged_ms), 0)
    ranked = (
        select(AnalyticsSession.user_id)
        .join(User, User.id == AnalyticsSession.user_id)
        .where(*conditions)
        .group_by(AnalyticsSession.user_id)
    )
    total = int(await session.scalar(select(func.count()).select_from(ranked.subquery())) or 0)
    user_ids = [
        int(user_id)
        for user_id in await session.scalars(
            ranked.order_by(engaged.desc(), func.max(AnalyticsSession.last_seen_at).desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        if user_id is not None
    ]
    guests = (
        await session.execute(
            select(func.count(distinct(AnalyticsSession.visitor_key)), func.count()).where(
                *scope.sessions(), AnalyticsSession.user_id.is_(None)
            )
        )
    ).one()
    return AnalyticsCustomersOut(
        period=period,
        items=await _customer_rows(session, scope, user_ids=user_ids),
        total=total,
        page=page,
        limit=limit,
        guest_visitors=int(guests[0] or 0),
        guest_sessions=int(guests[1] or 0),
    )


async def customer_detail_report(
    session: AsyncSession,
    *,
    user_id: int,
    period: Period,
    now: datetime,
    include_staff: bool = True,
) -> AnalyticsCustomerDetailOut:
    user = await session.get(User, user_id)
    if user is None:
        raise UserNotFoundError("Customer not found")
    scope = _scope(period, now=now, include_staff=include_staff)
    rows = await _customer_rows(session, scope, user_ids=[user_id])
    customer = (
        rows[0]
        if rows
        else CustomerActivityOut(
            user_id=user_id,
            name=_display_name(user.display_name, user.first_name),
            username=user.username,
            phone=mask_phone(user.phone),
            sessions=0,
            engaged_seconds=0,
            page_views=0,
            first_seen=user.created_at,
            last_seen=user.last_active_at or user.created_at,
            platform="web",
            products_viewed=0,
            cart_adds=0,
            orders=0,
            revenue=_ZERO,
            interests=[],
        )
    )
    session_rows = await session.scalars(
        select(AnalyticsSession)
        .where(*scope.sessions(), AnalyticsSession.user_id == user_id)
        .order_by(AnalyticsSession.started_at.desc())
        .limit(50)
    )
    sessions = [
        CustomerSessionOut(
            started_at=row.started_at,
            last_seen_at=row.last_seen_at,
            engaged_seconds=_seconds(row.engaged_ms),
            page_views=row.page_views,
            platform=row.platform,
            device=row.device,
            entry_path=row.entry_path,
        )
        for row in session_rows
    ]
    interest_rows = await session.execute(
        _events_select(
            AnalyticsEvent.product_id,
            func.count().filter(AnalyticsEvent.type == "product_view"),
            func.coalesce(
                func.sum(AnalyticsEvent.value).filter(AnalyticsEvent.type == "page_time"), 0
            ),
            func.count().filter(AnalyticsEvent.type == "add_to_cart"),
            func.count().filter(AnalyticsEvent.type == "favorite_add"),
        )
        .where(
            *scope.events(),
            AnalyticsSession.user_id == user_id,
            AnalyticsEvent.product_id.is_not(None),
        )
        .group_by(AnalyticsEvent.product_id)
    )
    interest = {
        int(product_id): (int(views), int(view_ms), int(carts), int(favorites))
        for product_id, views, view_ms, carts, favorites in interest_rows
    }
    ordered = await _ordered_by_product(session, scope, user_id=user_id)
    details = await _product_details(session, set(interest) | set(ordered))
    products = [
        CustomerProductOut(
            product_id=product_id,
            name=details[product_id][0],
            views=interest.get(product_id, (0, 0, 0, 0))[0],
            view_seconds=_seconds(interest.get(product_id, (0, 0, 0, 0))[1]),
            cart_adds=interest.get(product_id, (0, 0, 0, 0))[2],
            favorites=interest.get(product_id, (0, 0, 0, 0))[3],
            ordered_qty=ordered.get(product_id, (0, _ZERO))[0],
        )
        for product_id in details
    ]
    products.sort(
        key=lambda item: _interest_score(
            item.views, item.cart_adds, item.favorites, item.view_seconds * 1000
        )
        + 5 * item.ordered_qty,
        reverse=True,
    )
    search_rows = await session.execute(
        _events_select(AnalyticsEvent.label, func.max(AnalyticsEvent.occurred_at))
        .where(
            *scope.events(),
            AnalyticsSession.user_id == user_id,
            AnalyticsEvent.type == "search",
            AnalyticsEvent.label.is_not(None),
        )
        .group_by(AnalyticsEvent.label)
        .order_by(func.max(AnalyticsEvent.occurred_at).desc())
        .limit(20)
    )
    event_rows = await session.execute(
        _events_select(AnalyticsEvent, Product.name_uz)
        .outerjoin(Product, Product.id == AnalyticsEvent.product_id)
        .where(
            *scope.events(),
            AnalyticsSession.user_id == user_id,
            AnalyticsEvent.type.not_in(("page_time", "section_time", "product_impression")),
        )
        .order_by(AnalyticsEvent.occurred_at.desc(), AnalyticsEvent.id.desc())
        .limit(100)
    )
    events = [
        CustomerEventOut(
            occurred_at=event.occurred_at,
            type=event.type,
            path=event.path,
            section=event.section,
            target=event.target,
            label=event.label,
            product_name=product_name,
            value=event.value,
        )
        for event, product_name in event_rows
    ]
    return AnalyticsCustomerDetailOut(
        period=period,
        customer=customer,
        sessions=sessions,
        products=products[:30],
        searches=[label for label, _last in search_rows],
        events=events,
    )
