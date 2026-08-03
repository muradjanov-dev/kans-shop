from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.rate_limit import RateLimitMiddleware
from app.api.v1 import router as api_v1_router
from app.bot.loader import create_bot, create_dispatcher
from app.bot.services.system_notifications import notify_admins_deploy
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import verify_webhook_secret
from app.db.session import async_session_maker

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    bot = create_bot()
    app.state.bot = bot
    app.state.dispatcher = None

    if settings.webhook_url:
        dispatcher = create_dispatcher()
        app.state.dispatcher = dispatcher
        await bot.set_webhook(
            url=f"{settings.webhook_url}/webhook",
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
        )
        log.info("webhook_set", url=settings.webhook_url)
        async with async_session_maker() as session:
            await notify_admins_deploy(bot, session)
    else:
        log.info("webhook_disabled_use_bot_polling_py")

    yield

    await bot.session.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Kans Shop API", lifespan=lifespan)

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list({settings.webapp_url, "http://localhost:5173"}),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_v1_router)
    app.mount("/media", StaticFiles(directory=settings.media_root_path), name="media")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhook")
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if not verify_webhook_secret(x_telegram_bot_api_secret_token):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        dispatcher: Dispatcher | None = request.app.state.dispatcher
        if dispatcher is None:
            raise HTTPException(status_code=503, detail="Webhook mode is not enabled")

        update = Update.model_validate(await request.json())
        await dispatcher.feed_webhook_update(request.app.state.bot, update)
        return {"ok": True}

    return app


app = create_app()
