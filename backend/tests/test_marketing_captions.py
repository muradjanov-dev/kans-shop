"""Channel advert captions and the video renderer (no database, no network)."""

import random

import pytest
from PIL import Image

from app.services.marketing import captions
from app.services.marketing.captions import (
    TELEGRAM_CAPTION_LIMIT,
    CaptionContext,
    CaptionProduct,
    benefit_for,
    build_caption,
    template_caption,
)
from app.services.marketing.video import AdBrand, AdProduct, advert_seconds, render_advert
from app.services.marketing.worker import money, pretty_phone, uzbek_date, video_hook


def _context(names: list[str] | None = None) -> CaptionContext:
    names = names or ["Registr papka 7.5 sm Genius", "Ish jurnali 80 varaq", "Ruchka Luxor"]
    return CaptionContext(
        products=[
            CaptionProduct(name=name, price="12 000", old_price=None, category="Ofis")
            for name in names
        ],
        bot_username="kansshopbot",
        phone="+998 55 513 33 30",
        channel_username="kansshop_uzb",
        free_delivery_from="300 000",
        weekday_date="20-oktabr, seshanba",
    )


def test_template_caption_ends_with_the_channel_and_carries_every_order_route() -> None:
    caption = template_caption(_context(), rng=random.Random(4))

    assert caption.source == "template"
    assert caption.key and ":" in caption.key
    assert caption.text.rstrip().endswith("📣 @kansshop_uzb")
    assert "🤖 Buyurtma: @kansshopbot" in caption.text
    assert "📞 Telefon: +998 55 513 33 30" in caption.text
    assert "<b>12 000 so'm</b>" in caption.text
    assert "300 000 so'mdan ortiq buyurtmalarga yetkazib berish bepul" in caption.text
    assert len(caption.text) <= TELEGRAM_CAPTION_LIMIT


def test_template_caption_escapes_product_names_and_stays_within_telegram_limit() -> None:
    long_names = [f"Daftar <A5> & qalam to'plami {index} " + "x" * 120 for index in range(6)]
    caption = template_caption(_context(long_names), rng=random.Random(1))

    assert "<A5>" not in caption.text
    assert "&lt;A5&gt; &amp;" in caption.text
    assert len(caption.text) <= TELEGRAM_CAPTION_LIMIT
    assert caption.text.rstrip().endswith("📣 @kansshop_uzb")


def test_recent_hooks_are_not_repeated() -> None:
    recent = [f"{key}:spotlight" for key, _hook in captions.HOOKS[:-1]]
    for seed in range(10):
        caption = template_caption(_context(), recent_keys=recent, rng=random.Random(seed))
        assert caption.key is not None and caption.key.startswith(captions.HOOKS[-1][0])


def test_benefits_follow_the_product_kind() -> None:
    folder = CaptionProduct(name="Registr papka", price="1", old_price=None, category="")
    pen = CaptionProduct(name="Ручка шариковая", price="1", old_price=None, category="")
    other = CaptionProduct(name="Something", price="1", old_price=None, category="")
    assert "hujjatlar" in benefit_for(folder)
    assert "yozganda" in benefit_for(pen)
    assert benefit_for(other) == captions._DEFAULT_BENEFIT


async def test_build_caption_uses_templates_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def must_not_call(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("Claude must not be called without an API key")

    monkeypatch.setattr(captions, "claude_story", must_not_call)
    caption = await build_caption(_context(), api_key="")
    assert caption.source == "template"


async def test_build_caption_uses_claude_story_and_keeps_facts_in_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = "Kuz keldi, rejalar ko'paydi. Shunday paytda tartibli stol — eng yaxshi yordamchi."

    async def fake_story(*_args: object, **_kwargs: object) -> str:
        return story

    monkeypatch.setattr(captions, "claude_story", fake_story)
    caption = await build_caption(_context(), api_key="sk-test", rng=random.Random(2))

    assert caption.source == "llm"
    assert caption.text.startswith(story)
    assert "🤖 Buyurtma: @kansshopbot" in caption.text
    assert caption.text.rstrip().endswith("📣 @kansshop_uzb")


async def test_build_caption_falls_back_when_claude_has_no_usable_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_story(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(captions, "claude_story", no_story)
    caption = await build_caption(_context(), api_key="sk-test")
    assert caption.source == "template"


def test_formatting_helpers() -> None:
    from datetime import date
    from decimal import Decimal

    assert money(Decimal("12000.50")) == "12 001"
    assert pretty_phone("+998555133330") == "+998 55 513 33 30"
    assert pretty_phone(None) is None
    assert uzbek_date(date(2026, 10, 20)) == "20-oktabr, seshanba"
    assert (
        video_hook("Ish stolingizga bir qarang. Unga nima kerak? 🤔")
        == "Ish stolingizga bir qarang."
    )
    assert "☕" not in video_hook("Ertalabki choy ☕️ va reja")


def test_render_advert_produces_an_mp4_of_the_expected_length() -> None:
    photo = Image.new("RGB", (400, 300), (240, 120, 60))
    brand = AdBrand(
        hook="Ish stolingizga yangi kayfiyat",
        bot_username="kansshopbot",
        phone="+998 55 513 33 30",
        channel_username="kansshop_uzb",
    )
    product = AdProduct(
        name="Тетрадь A5 48 листов", price="9 500", old_price="11 000", image=photo
    )

    rendered = render_advert([product], brand, fps=4)

    assert rendered.data[4:8] == b"ftyp"
    assert (rendered.width, rendered.height) == (720, 900)
    assert rendered.seconds == pytest.approx(advert_seconds(1), abs=0.5)
    assert all(10 <= advert_seconds(count) <= 50 for count in range(0, 30))
