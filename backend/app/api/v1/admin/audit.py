from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_db
from app.api.schemas.admin import AdminAuditEventOut
from app.api.schemas.common import PageOut
from app.db.models.admin import Admin
from app.db.models.admin_audit_event import AdminAuditEvent
from app.db.models.enums import AdminRole
from app.services.common import Page

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])

# These are the operational, catalog, settings, customer, source, and broadcast records that a
# manager can review. Team membership and authentication/session changes remain superadmin-only.
_MANAGER_RESOURCE_TYPES = frozenset(
    {
        "admin_order_message",
        "admin_order_messages",
        "broadcast",
        "broadcast_recipient",
        "broadcast_recipients",
        "broadcasts",
        "categories",
        "category",
        "customer",
        "customers",
        "order",
        "orders",
        "payment",
        "payments",
        "product",
        "products",
        "setting",
        "settings",
        "source",
        "store_setting",
        "store_settings",
        "traffic_source",
        "traffic_sources",
        "user",
        "users",
    }
)
_OPERATOR_RESOURCE_TYPES = frozenset(
    {
        "admin_order_message",
        "admin_order_messages",
        "order",
        "orders",
        "payment",
        "payments",
    }
)


@router.get("", response_model=PageOut[AdminAuditEventOut])
async def list_admin_audit_events(
    response: Response,
    action: str | None = Query(default=None, max_length=64),
    resource_type: str | None = Query(default=None, max_length=64),
    actor_admin_id: int | None = Query(default=None, ge=1),
    request_id: str | None = Query(default=None, max_length=64),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
) -> PageOut[AdminAuditEventOut]:
    response.headers["Cache-Control"] = "private, no-store"
    filters = []
    if action is not None:
        filters.append(AdminAuditEvent.action == action)
    if resource_type is not None:
        filters.append(AdminAuditEvent.resource_type == resource_type)
    if request_id is not None:
        filters.append(AdminAuditEvent.request_id == request_id)

    if admin.role == AdminRole.MANAGER:
        filters.append(AdminAuditEvent.resource_type.in_(_MANAGER_RESOURCE_TYPES))
    elif admin.role == AdminRole.OPERATOR:
        filters.append(AdminAuditEvent.actor_admin_id == admin.id)
        filters.append(AdminAuditEvent.resource_type.in_(_OPERATOR_RESOURCE_TYPES))

    if actor_admin_id is not None:
        filters.append(AdminAuditEvent.actor_admin_id == actor_admin_id)

    total = await session.scalar(
        select(func.count()).select_from(AdminAuditEvent).where(*filters)
    )
    events = list(
        (
            await session.scalars(
                select(AdminAuditEvent)
                .where(*filters)
                .order_by(AdminAuditEvent.created_at.desc(), AdminAuditEvent.id.desc())
                .offset((page - 1) * limit)
                .limit(limit)
            )
        ).all()
    )
    return PageOut[AdminAuditEventOut].from_page(
        Page(
            items=[AdminAuditEventOut.model_validate(event) for event in events],
            total=total or 0,
            page=page,
            limit=limit,
        )
    )
