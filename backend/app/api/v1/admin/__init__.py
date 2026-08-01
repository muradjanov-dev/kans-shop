from fastapi import APIRouter

from app.api.v1.admin import broadcasts, categories, orders, products, stats, users

router = APIRouter()
router.include_router(categories.router)
router.include_router(products.router)
router.include_router(orders.router)
router.include_router(users.router)
router.include_router(stats.router)
router.include_router(broadcasts.router)
