"""The channel advert names products in Uzbek Latin, never with the catalog's Russian names."""

import json
import re
from pathlib import Path

from app.services.marketing import uz_names
from app.services.marketing.captions import CaptionProduct, benefit_for
from app.services.marketing.uz_names import transliterate, uzbek_product_name

CYRILLIC = re.compile("[А-Яа-яЁё]")
DATA = Path(uz_names.__file__).with_name("uz_product_names.json")


def test_every_curated_translation_is_uzbek_latin() -> None:
    curated = json.loads(DATA.read_text(encoding="utf-8"))
    assert len(curated) >= 200
    for source, uzbek in curated.items():
        assert CYRILLIC.search(source), source
        assert uzbek.strip() and not CYRILLIC.search(uzbek), uzbek


def test_catalog_names_use_the_curated_translation_whatever_the_spacing() -> None:
    expected = "Luxor Premier Touch Pen sharikli ruchkalar to'plami"
    assert (
        uzbek_product_name("Ручка шариковая в блистере Premier Touch Pen Luxor (наб)")
        == expected
    )
    assert (
        uzbek_product_name("  ручка шариковая в блистере   Premier Touch Pen Luxor (наб) ")
        == expected
    )
    assert (
        uzbek_product_name('Ручка шариковая " Ecowrite" Luxor син.')
        == "Luxor Ecowrite sharikli ruchka, ko'k"
    )


def test_latin_names_are_kept() -> None:
    assert (
        uzbek_product_name("Registr papka (ko'k)  7.5 sm Genius")
        == "Registr papka (ko'k) 7.5 sm Genius"
    )


def test_new_products_get_a_glossary_translation_without_cyrillic() -> None:
    assert (
        uzbek_product_name("Тетрадь 96л А4ф клетка на скобе")
        == "Daftar 96 varaq A4 katak skrepkali"
    )
    gel = uzbek_product_name("Ручка гелевая синяя 0,5мм")
    assert gel.startswith("Gelli ruchka") and "ko'k" in gel and "0,5 mm" in gel
    for name in ["Дырокол Deli 0102 на 20 листов", "Набор маркеров 12 цв.", "Ёлочные игрушки"]:
        translated = uzbek_product_name(name)
        assert translated and not CYRILLIC.search(translated), translated


def test_transliteration_keeps_letter_case() -> None:
    assert transliterate("Щётка Шарик") == "Shyotka Sharik"


def test_two_products_of_one_kind_are_not_praised_with_the_same_words() -> None:
    import random

    from app.services.marketing.captions import CaptionContext, template_caption

    pens = ["Luxor Spark sharikli ruchka, qora", "Luxor Ecowrite sharikli ruchka, ko'k"]
    context = CaptionContext(
        products=[
            CaptionProduct(name=name, price="1", old_price=None, category="") for name in pens
        ],
        bot_username="kansshopbot",
        phone=None,
        channel_username="kansshop_uzb",
        free_delivery_from=None,
        weekday_date="21-oktabr, seshanba",
    )
    for seed in range(20):
        text = template_caption(context, rng=random.Random(seed)).text
        assert text.count("yozganda qo'l charchamaydi") <= 1, text


def test_benefits_understand_uzbek_names() -> None:
    def benefit(name: str) -> str:
        return benefit_for(CaptionProduct(name=name, price="1", old_price=None, category=""))

    assert "yopishtiradi" in benefit("Hatber X-Mate qalam yelim, 8 g")
    assert "o'tkir" in benefit("Vivo Pastel qalamtaroshi")
    assert "ijodga" in benefit("«ZOO» plastilini, 12 rang")
    assert "varag'i" in benefit("METALLIC bloknoti, A6, 40 varaq")
    assert "yozganda" in benefit("Luxor Spark sharikli ruchka, qora")
