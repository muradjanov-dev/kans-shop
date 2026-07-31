from aiogram import Router

from app.bot.handlers.user import user_router

root_router = Router(name="root")
root_router.include_router(user_router)

__all__ = ["root_router"]
