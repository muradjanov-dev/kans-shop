from fastapi import APIRouter

from app.api import admin_security
from app.api.v1 import (
    addresses,
    auth,
    cart,
    catalog,
    favorites,
    orders,
    profile,
    receipts,
    settings,
)
from app.api.v1.admin import router as admin_router

router = APIRouter(prefix="/api/v1")
router.include_router(admin_security.router)
router.include_router(auth.router)
router.include_router(profile.router)
router.include_router(addresses.router)
router.include_router(catalog.router)
router.include_router(favorites.router)
router.include_router(cart.router)
router.include_router(orders.router)
router.include_router(receipts.router)
router.include_router(settings.router)
router.include_router(admin_router)
