from fastapi import APIRouter

from app.api.v1 import auth, cart, catalog, orders, settings
from app.api.v1.admin import router as admin_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(catalog.router)
router.include_router(cart.router)
router.include_router(orders.router)
router.include_router(settings.router)
router.include_router(admin_router)
