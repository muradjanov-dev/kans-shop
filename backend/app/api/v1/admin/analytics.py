"""Admin dashboard: visitor behaviour, product interest, customers and sales."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin_roles
from app.api.schemas.analytics import (
    AnalyticsBehaviorOut,
    AnalyticsCustomerDetailOut,
    AnalyticsCustomersOut,
    AnalyticsPeriod,
    AnalyticsProductsOut,
    AnalyticsSalesOut,
    AnalyticsSummaryOut,
)
from app.db.models.admin import Admin
from app.db.models.enums import AdminRole
from app.services import analytics_report_service as reports

router = APIRouter(prefix="/admin/analytics", tags=["admin-analytics"])
# Per-customer browsing history is personal data: managers and the owner only.
_require_analytics_admin = require_admin_roles(AdminRole.SUPERADMIN, AdminRole.MANAGER)

PeriodQuery = Query(default="week")
StaffQuery = Query(default=False, description="Count the shop team's own visits too")


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


@router.get("/summary", response_model=AnalyticsSummaryOut)
async def get_summary(
    response: Response,
    period: AnalyticsPeriod = PeriodQuery,
    include_staff: bool = StaffQuery,
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(_require_analytics_admin),
) -> AnalyticsSummaryOut:
    _private(response)
    return await reports.summary_report(
        session, period=period, now=datetime.now(UTC), include_staff=include_staff
    )


@router.get("/behavior", response_model=AnalyticsBehaviorOut)
async def get_behavior(
    response: Response,
    period: AnalyticsPeriod = PeriodQuery,
    include_staff: bool = StaffQuery,
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(_require_analytics_admin),
) -> AnalyticsBehaviorOut:
    _private(response)
    return await reports.behavior_report(
        session, period=period, now=datetime.now(UTC), include_staff=include_staff
    )


@router.get("/products", response_model=AnalyticsProductsOut)
async def get_products(
    response: Response,
    period: AnalyticsPeriod = PeriodQuery,
    include_staff: bool = StaffQuery,
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(_require_analytics_admin),
) -> AnalyticsProductsOut:
    _private(response)
    return await reports.products_report(
        session, period=period, now=datetime.now(UTC), include_staff=include_staff
    )


@router.get("/customers", response_model=AnalyticsCustomersOut)
async def get_customers(
    response: Response,
    period: AnalyticsPeriod = PeriodQuery,
    include_staff: bool = StaffQuery,
    page: int = Query(default=1, ge=1, le=10_000),
    limit: int = Query(default=20, ge=1, le=100),
    query: str | None = Query(default=None, max_length=64),
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(_require_analytics_admin),
) -> AnalyticsCustomersOut:
    _private(response)
    return await reports.customers_report(
        session,
        period=period,
        now=datetime.now(UTC),
        page=page,
        limit=limit,
        query=query,
        include_staff=include_staff,
    )


@router.get("/customers/{user_id}", response_model=AnalyticsCustomerDetailOut)
async def get_customer(
    user_id: int,
    response: Response,
    period: AnalyticsPeriod = PeriodQuery,
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(_require_analytics_admin),
) -> AnalyticsCustomerDetailOut:
    _private(response)
    return await reports.customer_detail_report(
        session, user_id=user_id, period=period, now=datetime.now(UTC)
    )


@router.get("/sales", response_model=AnalyticsSalesOut)
async def get_sales(
    response: Response,
    period: AnalyticsPeriod = PeriodQuery,
    session: AsyncSession = Depends(get_db, scope="function"),
    _admin: Admin = Depends(_require_analytics_admin),
) -> AnalyticsSalesOut:
    _private(response)
    return await reports.sales_report(session, period=period, now=datetime.now(UTC))
