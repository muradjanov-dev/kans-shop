"""Every channel advert looks different, always in the brand's yellow, black and white."""

from dataclasses import replace
from datetime import date

from PIL import Image

from app.services.marketing.video import (
    BRAND_BLACK,
    BRAND_YELLOW,
    DOODLE_SETS,
    HEIGHT,
    INTROS,
    LAYOUTS,
    MOTIONS,
    OUTROS,
    PRICE_SHAPES,
    THEMES,
    TRANSITIONS,
    WHITE,
    WIDTH,
    AdBrand,
    AdProduct,
    AdStyle,
    _scenes,
    _transition,
    _wordmark,
    advert_style,
)

START = date(2026, 10, 23).toordinal()


def test_consecutive_days_never_share_the_main_choices() -> None:
    for day in range(START, START + 400):
        today, tomorrow = advert_style(day), advert_style(day + 1)
        assert today.theme != tomorrow.theme
        assert today.layout != tomorrow.layout
        assert today.motion != tomorrow.motion
        assert today.transition != tomorrow.transition
        assert today.doodles != tomorrow.doodles


def test_a_season_of_adverts_has_no_repeated_look() -> None:
    keys = [advert_style(day).key for day in range(START, START + 60)]
    assert len(set(keys)) == len(keys)


def test_every_theme_is_built_on_the_logo_colours() -> None:
    for theme in THEMES:
        stage_and_badges = {
            theme.dark_top,
            theme.accent,
            theme.on_accent,
            theme.cta,
            theme.on_cta,
        }
        assert stage_and_badges & {BRAND_YELLOW, BRAND_BLACK, WHITE}, theme.name
        assert BRAND_YELLOW in {
            theme.accent,
            theme.on_accent,
            theme.cta,
            theme.soft,
            theme.dark_top,
        }


def _variations() -> list[AdStyle]:
    base = advert_style(START)
    styles = [replace(base, theme=theme, seed=index) for index, theme in enumerate(THEMES)]
    styles += [replace(base, layout=value) for value in LAYOUTS]
    styles += [replace(base, motion=value) for value in MOTIONS]
    styles += [replace(base, intro=value) for value in INTROS]
    styles += [replace(base, outro=value) for value in OUTROS]
    styles += [replace(base, price_shape=value) for value in PRICE_SHAPES]
    styles += [replace(base, doodles=value) for value in DOODLE_SETS]
    return styles


def test_every_variant_draws_full_frames() -> None:
    photo = Image.new("RGB", (300, 400), (40, 90, 200))
    products = [
        AdProduct("Luxor Spark sharikli ruchka, qora", "1 700", "2 100", photo),
        AdProduct("METALLIC bloknoti, A5, 80 varaq, katak, spiralli", "38 000", None, photo),
    ]
    brand = AdBrand(
        hook="Ish stolingizga bir qarang. Unga nima yetishmayapti?",
        bot_username="kansshopbot",
        phone="+998 55 513 33 30",
        channel_username="kansshop_uzb",
    )
    for style in _variations():
        scenes = _scenes(products, brand, style)
        frames = [
            scene.render(moment) for scene in scenes for moment in (0.1, scene.duration - 0.1)
        ]
        assert all(frame.size == (WIDTH, HEIGHT) for frame in frames), style.key
    first, second = frames[0].convert("RGB"), frames[2].convert("RGB")
    for kind in TRANSITIONS:
        for share in (0.0, 0.5, 1.0):
            assert _transition(first, second, share, kind).size == (WIDTH, HEIGHT)


def test_the_wordmark_has_the_yellow_pencil() -> None:
    mark = _wordmark(BRAND_BLACK, 60)
    colours = {pixel[:3] for pixel in mark.get_flattened_data() if pixel[3] == 255}
    assert BRAND_YELLOW in colours and BRAND_BLACK in colours
    assert mark.width > mark.height * 4
