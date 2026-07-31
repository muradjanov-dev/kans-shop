from aiogram import Router

from app.bot.handlers.admin import orders

admin_router = Router(name="admin")
admin_router.include_router(orders.router)

__all__ = ["admin_router"]
