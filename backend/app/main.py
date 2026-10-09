import asyncio
import os
import posixpath
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

from aiogram import Dispatcher
from aiogram.types import Update
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_exception_handlers
from app.api.payments_webhooks import router as payments_webhooks_router
from app.api.rate_limit import RateLimitMiddleware
from app.api.v1 import router as api_v1_router
from app.bot.loader import create_bot, create_dispatcher
from app.bot.services.system_notifications import notify_admins_deploy
from app.bot.utils.commands import setup_bot_commands
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.redis import get_redis
from app.core.security import verify_webhook_secret
from app.db.session import async_session_maker
from app.services.broadcast_worker import run_broadcast_worker
from app.services.notification_outbox_worker import run_outbox_worker

log = get_logger(__name__)


class PublicMediaFiles(StaticFiles):
    """Serve public media while refusing receipt paths at static-file lookup time."""

    def lookup_path(self, path: str) -> tuple[str, os.stat_result | None]:
        if self._is_private_receipt_path(path):
            return "", None
        return super().lookup_path(path)

    def _is_private_receipt_path(self, path: str) -> bool:
        decoded = path
        for _ in range(16):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                break
            decoded = next_decoded
        decoded = decoded.replace("\\", "/")
        normalized = posixpath.normpath(decoded.lstrip("/"))
        if normalized.split("/", maxsplit=1)[0].casefold() == "receipts":
            return True
        if self.directory is None:
            return False
        root = Path(self.directory).resolve()
        candidate = (root / decoded.lstrip("/")).resolve()
        try:
            relative = candidate.relative_to(root)
        except ValueError:
            return False
        parts = relative.parts
        return bool(parts and parts[0].casefold() == "receipts")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    bot = create_bot()
    app.state.bot = bot
    app.state.dispatcher = None
    stop_outbox_worker = asyncio.Event()
    stop_broadcast_worker = asyncio.Event()
    session_maker = getattr(app.state, "session_maker", async_session_maker)
    redis = get_redis()
    worker_task = asyncio.create_task(
        run_outbox_worker(bot, session_maker, redis, stop_outbox_worker),
        name="notification-outbox-worker",
    )
    broadcast_worker_task = asyncio.create_task(
        run_broadcast_worker(bot, session_maker, redis, stop_broadcast_worker),
        name="broadcast-worker",
    )
    app.state.notification_outbox_stop = stop_outbox_worker
    app.state.notification_outbox_task = worker_task
    app.state.broadcast_worker_stop = stop_broadcast_worker
    app.state.broadcast_worker_task = broadcast_worker_task

    try:
        await setup_bot_commands(bot)

        if settings.webhook_url:
            dispatcher = create_dispatcher()
            app.state.dispatcher = dispatcher
            await bot.set_webhook(
                url=f"{settings.webhook_url}/webhook",
                secret_token=settings.webhook_secret,
                drop_pending_updates=True,
            )
            log.info("webhook_set", url=settings.webhook_url)
            async with session_maker() as session:
                await notify_admins_deploy(session)
                await session.commit()
        else:
            log.info("webhook_disabled_use_bot_polling_py")

        yield
    finally:
        stop_outbox_worker.set()
        stop_broadcast_worker.set()
        await asyncio.gather(worker_task, broadcast_worker_task)
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
    app.include_router(payments_webhooks_router)
    app.mount("/media", PublicMediaFiles(directory=settings.media_root_path), name="media")

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
