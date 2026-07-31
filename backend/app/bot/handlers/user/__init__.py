from aiogram import Router

from app.bot.handlers.user import catalog, menu, start

user_router = Router(name="user")
# Order matters: specific button-text handlers (start, menu) must be tried before catalog's
# catch-all free-text search handler, or the catch-all would swallow every other text message.
user_router.include_router(start.router)
user_router.include_router(menu.router)
user_router.include_router(catalog.router)

__all__ = ["user_router"]
