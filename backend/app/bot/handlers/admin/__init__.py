from aiogram import Router

from app.bot.handlers.admin import (
    broadcast,
    categories,
    menu,
    orders,
    orders_list,
    products,
    products_edit,
    products_form,
    settings,
    stats,
    users,
)

admin_router = Router(name="admin")
# menu.py's /admin command + AdminMenuCallback dispatcher must be tried first; then each
# section's own callbacks/FSM message handlers.
admin_router.include_router(menu.router)
admin_router.include_router(orders.router)
admin_router.include_router(orders_list.router)
admin_router.include_router(categories.router)
admin_router.include_router(products.router)
admin_router.include_router(products_form.router)
admin_router.include_router(products_edit.router)
admin_router.include_router(stats.router)
admin_router.include_router(users.router)
admin_router.include_router(settings.router)
admin_router.include_router(broadcast.router)

__all__ = ["admin_router"]
