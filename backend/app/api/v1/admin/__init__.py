from fastapi import APIRouter

from app.api.v1.admin import (
    audit,
    broadcasts,
    categories,
    orders,
    payments,
    products,
    settings,
    stats,
    team,
    users,
)

router = APIRouter()
router.include_router(categories.router)
router.include_router(products.router)
router.include_router(orders.router)
router.include_router(payments.router)
router.include_router(users.router)
router.include_router(settings.router)
router.include_router(stats.router)
router.include_router(broadcasts.router)
router.include_router(audit.router)
router.include_router(team.router)
