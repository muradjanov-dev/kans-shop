import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import MenuButtonWebApp

from app.bot.keyboards.inline.admin_menu import admin_menu_keyboard
from app.bot.keyboards.inline.main_menu import main_menu_inline_keyboard
from app.bot.utils import commands
from app.core.config import Settings, build_webapp_entry_url


def test_webapp_entry_url_replaces_version_and_preserves_other_url_parts() -> None:
    assert (
        build_webapp_entry_url(
            "https://shop.example/mini?tgWebAppStartParam=src_abc&startapp=abc&v=old#home",
            "2",
        )
        == "https://shop.example/mini?tgWebAppStartParam=src_abc&startapp=abc&v=2#home"
    )


def test_settings_webapp_entry_url_is_separate_from_base_url() -> None:
    settings = Settings.model_construct(
        webapp_url="https://shop.example/mini?source=telegram",
        webapp_entry_version="2",
    )

    assert settings.webapp_url == "https://shop.example/mini?source=telegram"
    assert settings.webapp_entry_url == "https://shop.example/mini?source=telegram&v=2"


def test_admin_entry_url_adds_admin_path_and_preserves_query() -> None:
    settings = Settings.model_construct(
        webapp_url="https://shop.example/mini/?source=telegram&v=old#home",
        webapp_entry_version="2",
    )

    assert settings.webapp_admin_entry_url == (
        "https://shop.example/mini/admin?source=telegram&v=2#home"
    )


def test_inline_main_menu_uses_versioned_webapp_entry(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "webapp_url", "https://shop.example/mini")
    monkeypatch.setattr(settings, "webapp_entry_version", "2")
    keyboard = main_menu_inline_keyboard(lambda key: key)

    web_app_button = next(
        button
        for row in keyboard.inline_keyboard
        for button in row
        if button.web_app is not None
    )
    assert web_app_button.web_app is not None
    assert web_app_button.web_app.url == "https://shop.example/mini?v=2"


def test_admin_menu_link_uses_versioned_admin_entry(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(
        settings,
        "webapp_url",
        "https://shop.example/mini?source=telegram&v=old#home",
    )
    monkeypatch.setattr(settings, "webapp_entry_version", "2")
    keyboard = admin_menu_keyboard(lambda key: key, new_orders_count=0)

    admin_button = next(
        button for row in keyboard.inline_keyboard for button in row if button.url is not None
    )
    assert admin_button.url == "https://shop.example/mini/admin?source=telegram&v=2#home"


async def test_webhook_startup_sets_versioned_global_webapp_menu(monkeypatch) -> None:
    import app.main as main

    class FakeBotSession:
        async def close(self) -> None:
            return None

    class FakeBot:
        def __init__(self) -> None:
            self.session = FakeBotSession()
            self.menu_button = None
            self.set_chat_menu_button = AsyncMock(side_effect=self._set_menu_button)
            self.set_webhook = AsyncMock()

        async def _set_menu_button(self, *, menu_button):
            self.menu_button = menu_button

    class FakeSessionContext:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self) -> None:
            return None

    class FakeSessionMaker:
        def __call__(self):
            return FakeSessionContext()

    async def wait_for_stop(_bot, _session_maker, _redis, stop: asyncio.Event) -> None:
        await stop.wait()

    async def no_setup(_bot) -> None:
        return None

    async def no_notification(_session) -> None:
        return None

    bot = FakeBot()
    monkeypatch.setattr(main, "create_bot", lambda: bot)
    monkeypatch.setattr(main, "create_dispatcher", lambda: object())
    monkeypatch.setattr(main, "setup_bot_commands", no_setup)
    monkeypatch.setattr(main, "get_redis", lambda: object())
    monkeypatch.setattr(main, "run_outbox_worker", wait_for_stop)
    monkeypatch.setattr(main, "run_broadcast_worker", wait_for_stop)
    monkeypatch.setattr(main, "notify_admins_deploy", no_notification)
    monkeypatch.setattr(main.settings, "webhook_url", "https://api.example")
    monkeypatch.setattr(main.settings, "webapp_url", "https://shop.example/mini?from=telegram")
    monkeypatch.setattr(main.settings, "webapp_entry_version", "2")

    app = main.create_app()
    app.state.session_maker = FakeSessionMaker()
    async with app.router.lifespan_context(app):
        assert isinstance(bot.menu_button, MenuButtonWebApp)
        assert bot.menu_button.web_app.url == "https://shop.example/mini?from=telegram&v=2"
        bot.set_chat_menu_button.assert_awaited_once_with(menu_button=bot.menu_button)


@pytest.mark.parametrize(
    "error",
    [
        TelegramBadRequest(method=SimpleNamespace(), message="bad menu button"),
        TelegramNetworkError(method=SimpleNamespace(), message="connection lost"),
    ],
)
async def test_menu_button_telegram_failures_do_not_abort_startup(monkeypatch, error) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "webapp_url", "https://shop.example/mini")
    monkeypatch.setattr(settings, "webapp_entry_version", "2")
    bot = SimpleNamespace(set_chat_menu_button=AsyncMock(side_effect=error))
    logger = SimpleNamespace(error=Mock(), info=Mock())
    monkeypatch.setattr(commands, "log", logger)

    await commands.setup_webapp_menu_button(bot)

    bot.set_chat_menu_button.assert_awaited_once()
    logger.error.assert_called_once_with(
        "set_webapp_menu_button_failed", error_type=type(error).__name__
    )


async def test_menu_button_success_log_contains_entry_version(monkeypatch) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "webapp_url", "https://shop.example/mini")
    monkeypatch.setattr(settings, "webapp_entry_version", "2")
    bot = SimpleNamespace(set_chat_menu_button=AsyncMock())
    logger = SimpleNamespace(error=Mock(), info=Mock())
    monkeypatch.setattr(commands, "log", logger)

    await commands.setup_webapp_menu_button(bot)

    logger.info.assert_called_once_with("webapp_menu_button_configured", entry_version="2")


def test_nginx_spa_html_is_uncacheable_and_assets_are_immutable() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for config_path in (repo_root / "frontend/nginx.conf", repo_root / "nginx/nginx.conf"):
        config = config_path.read_text(encoding="utf-8")
        assert "location = /index.html" in config
        assert "no-store, no-cache, must-revalidate" in config
        assert "location /" in config
        assert "location ^~ /assets/" in config
        assert "try_files $uri =404;" in config
        assert "public, max-age=31536000, immutable" in config

    compose_nginx = (repo_root / "nginx/nginx.conf").read_text(encoding="utf-8")
    assert "location ^~ /media/" in compose_nginx
    assert "location ^~ /api/" in compose_nginx
