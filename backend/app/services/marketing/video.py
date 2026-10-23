"""Animated channel advert: a 720x900 MP4 drawn with Pillow and encoded by ffmpeg.

Scenes: an intro with the brand and a hook line, one scene per product (photo on a white
card, name, price badge) and an outro with the ways to order. Frames are produced one at a
time and piped straight into ffmpeg, so memory stays flat however long the advert is. The
ffmpeg binary ships inside the imageio-ffmpeg wheel; no system package is needed.

Every advert gets its own look (`advert_style`): colour theme, product layout, how the photo
enters, scene transitions, intro and outro variants, price badge and doodles. The main
choices rotate with the day number, so two consecutive days never share them.
"""

from __future__ import annotations

import contextlib
import math
import random
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

WIDTH, HEIGHT = 720, 900
FPS = 30
INTRO_SECONDS = 2.8
PRODUCT_SECONDS = 3.8
OUTRO_SECONDS = 4.4
FADE_SECONDS = 0.35
TRANSITION_SECONDS = 0.45

FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Manrope.ttf"

WHITE = (255, 255, 255)

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class AdProduct:
    name: str
    price: str
    old_price: str | None
    image: Image.Image


@dataclass(frozen=True)
class AdBrand:
    hook: str
    bot_username: str
    phone: str | None
    channel_username: str | None
    currency: str = "so'm"
    order_title: str = "Buyurtma bering"
    order_button: str = "Botda buyurtma qilish"
    tagline: str = "Kanselyariya · Ofis · Maktab"
    footer: str = "Kans Shop — ish, o'qish va ijod uchun"


@dataclass(frozen=True)
class RenderedVideo:
    data: bytes
    width: int
    height: int
    seconds: float


# --------------------------------------------------------------------------- styles


# The brand: the KANSSHOP logo is black on white, its "A" a pencil with a yellow top.
BRAND_YELLOW = (253, 237, 4)
BRAND_BLACK = (22, 22, 22)
GRAPHITE = (52, 52, 50)
MID_GREY = (112, 112, 108)
GOLD = (214, 186, 0)


@dataclass(frozen=True)
class Theme:
    """One arrangement of the brand colours: intro/outro ("stage"), product scenes and accents."""

    name: str
    dark_top: RGB  # stage gradient
    dark_bottom: RGB
    glow: RGB
    light: tuple[tuple[RGB, RGB], ...]  # product scene gradients
    accent: RGB  # price badge
    on_accent: RGB
    accent_edge: RGB | None  # outline when the badge would melt into a light scene
    cta: RGB  # outro button
    on_cta: RGB
    soft: RGB  # hook line, footer, icon discs
    chip: RGB  # tagline pill
    on_chip: RGB
    ink: RGB  # text on product scenes
    muted: RGB
    paper: RGB  # titles and contact rows on the stage
    doodles_dark: tuple[RGB, ...]
    doodles_light: tuple[RGB, ...]
    mark_bg: RGB  # app-icon square behind the pencil
    mark_ink: RGB


THEMES: tuple[Theme, ...] = (
    # Black stage, white product scenes, yellow badges: the logo on a dark wall.
    Theme(
        name="noir",
        dark_top=(30, 30, 29),
        dark_bottom=(8, 8, 8),
        glow=(120, 108, 0),
        light=(
            (WHITE, (240, 240, 237)),
            ((240, 240, 237), (255, 250, 214)),
            ((255, 250, 214), WHITE),
        ),
        accent=BRAND_YELLOW,
        on_accent=BRAND_BLACK,
        accent_edge=BRAND_BLACK,
        cta=BRAND_YELLOW,
        on_cta=BRAND_BLACK,
        soft=BRAND_YELLOW,
        chip=GRAPHITE,
        on_chip=WHITE,
        ink=BRAND_BLACK,
        muted=MID_GREY,
        paper=WHITE,
        doodles_dark=(BRAND_YELLOW, WHITE, MID_GREY),
        doodles_light=(BRAND_BLACK, GOLD, (160, 160, 156)),
        mark_bg=WHITE,
        mark_ink=BRAND_BLACK,
    ),
    # Yellow stage with black type, black price badges.
    Theme(
        name="lemon",
        dark_top=BRAND_YELLOW,
        dark_bottom=(240, 212, 0),
        glow=WHITE,
        light=(
            (WHITE, (244, 244, 241)),
            ((244, 244, 241), WHITE),
            (WHITE, (255, 251, 220)),
        ),
        accent=BRAND_BLACK,
        on_accent=BRAND_YELLOW,
        accent_edge=None,
        cta=BRAND_BLACK,
        on_cta=BRAND_YELLOW,
        soft=GRAPHITE,
        chip=BRAND_BLACK,
        on_chip=BRAND_YELLOW,
        ink=BRAND_BLACK,
        muted=MID_GREY,
        paper=BRAND_BLACK,
        doodles_dark=(BRAND_BLACK, WHITE, (150, 136, 0)),
        doodles_light=(BRAND_BLACK, GOLD, (160, 160, 156)),
        mark_bg=BRAND_BLACK,
        mark_ink=WHITE,
    ),
    # White stage with a yellow haze, like the logo itself.
    Theme(
        name="paper",
        dark_top=WHITE,
        dark_bottom=(236, 236, 232),
        glow=BRAND_YELLOW,
        light=(
            ((255, 249, 196), WHITE),
            (WHITE, (242, 242, 238)),
            ((242, 242, 238), (255, 249, 196)),
        ),
        accent=BRAND_YELLOW,
        on_accent=BRAND_BLACK,
        accent_edge=BRAND_BLACK,
        cta=BRAND_BLACK,
        on_cta=BRAND_YELLOW,
        soft=GRAPHITE,
        chip=BRAND_BLACK,
        on_chip=BRAND_YELLOW,
        ink=BRAND_BLACK,
        muted=MID_GREY,
        paper=BRAND_BLACK,
        doodles_dark=(BRAND_BLACK, GOLD, (170, 170, 166)),
        doodles_light=(BRAND_BLACK, GOLD, (170, 170, 166)),
        mark_bg=BRAND_BLACK,
        mark_ink=WHITE,
    ),
    # Graphite stage, light grey scenes, yellow accents.
    Theme(
        name="graphite",
        dark_top=(70, 70, 67),
        dark_bottom=(30, 30, 29),
        glow=(150, 138, 20),
        light=(
            ((246, 246, 244), (228, 228, 224)),
            ((228, 228, 224), (255, 248, 190)),
            ((255, 248, 190), (246, 246, 244)),
        ),
        accent=BRAND_YELLOW,
        on_accent=BRAND_BLACK,
        accent_edge=BRAND_BLACK,
        cta=BRAND_YELLOW,
        on_cta=BRAND_BLACK,
        soft=BRAND_YELLOW,
        chip=(92, 92, 88),
        on_chip=WHITE,
        ink=BRAND_BLACK,
        muted=MID_GREY,
        paper=WHITE,
        doodles_dark=(BRAND_YELLOW, (210, 210, 205), WHITE),
        doodles_light=(GRAPHITE, GOLD, (150, 150, 146)),
        mark_bg=BRAND_YELLOW,
        mark_ink=BRAND_BLACK,
    ),
    # Black stage, bright yellow product scenes, black price badges.
    Theme(
        name="bold",
        dark_top=(24, 24, 23),
        dark_bottom=(6, 6, 6),
        glow=(90, 84, 0),
        light=(
            (BRAND_YELLOW, (255, 245, 120)),
            ((255, 245, 120), BRAND_YELLOW),
            ((250, 228, 0), (255, 247, 150)),
        ),
        accent=BRAND_BLACK,
        on_accent=BRAND_YELLOW,
        accent_edge=None,
        cta=BRAND_YELLOW,
        on_cta=BRAND_BLACK,
        soft=BRAND_YELLOW,
        chip=GRAPHITE,
        on_chip=BRAND_YELLOW,
        ink=BRAND_BLACK,
        muted=(80, 74, 20),
        paper=WHITE,
        doodles_dark=(BRAND_YELLOW, WHITE, MID_GREY),
        doodles_light=(BRAND_BLACK, WHITE, (110, 100, 10)),
        mark_bg=BRAND_YELLOW,
        mark_ink=BRAND_BLACK,
    ),
)

LAYOUTS = ("classic", "flipped", "spotlight")
MOTIONS = ("slide_right", "rise", "zoom", "slide_left", "spin", "drop")
TRANSITIONS = ("fade", "wipe", "slide", "circle")
INTROS = ("pop", "typewriter", "split")
OUTROS = ("rows", "panel")
PRICE_SHAPES = ("pill", "sticker", "tag")
DOODLE_SETS: tuple[tuple[str, ...], ...] = (
    ("ring", "plus", "spark", "dots", "wave", "clip"),
    ("confetti", "dots", "ring", "confetti", "star"),
    ("star", "spark", "plus", "ring"),
    ("wave", "clip", "dots", "confetti"),
    ("pencil", "ring", "star", "dots", "pencil"),
)


@dataclass(frozen=True)
class AdStyle:
    theme: Theme
    layout: str
    motion: str
    transition: str
    intro: str
    outro: str
    price_shape: str
    doodles: tuple[str, ...]
    seed: int

    @property
    def key(self) -> str:
        return "/".join(
            (
                self.theme.name,
                self.layout,
                self.motion,
                self.transition,
                self.intro,
                self.outro,
                self.price_shape,
            )
        )


def advert_style(day: int) -> AdStyle:
    """The look of the advert for a day number (`date.toordinal()`).

    Theme, layout, entrance motion, transition and doodles rotate with the day, each with
    its own step, so consecutive days differ in all of them and a full combination only
    returns after many months. The smaller details are shuffled by the day as seed.
    """

    def rotate(options: tuple[Any, ...], step: int, offset: int) -> Any:
        return options[(day * step + offset) % len(options)]

    rng = random.Random(day * 7919 + 17)
    return AdStyle(
        theme=THEMES[day % len(THEMES)],
        layout=rotate(LAYOUTS, 2, 1),
        motion=rotate(MOTIONS, 5, 2),
        transition=rotate(TRANSITIONS, 3, 1),
        intro=rng.choice(INTROS),
        outro=rng.choice(OUTROS),
        price_shape=rng.choice(PRICE_SHAPES),
        doodles=rotate(DOODLE_SETS, 2, 3),
        seed=day,
    )


# --------------------------------------------------------------------------- helpers


def _clamp(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def ease_out_cubic(t: float) -> float:
    t = _clamp(t)
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    t = _clamp(t)
    return t * t * (3 - 2 * t)


def ease_out_back(t: float, overshoot: float = 1.70158) -> float:
    t = _clamp(t) - 1
    return t * t * ((overshoot + 1) * t + overshoot) + 1


def ease_out_bounce(t: float) -> float:
    t = _clamp(t)
    if t < 1 / 2.75:
        return 7.5625 * t * t
    if t < 2 / 2.75:
        t -= 1.5 / 2.75
        return 7.5625 * t * t + 0.75
    if t < 2.5 / 2.75:
        t -= 2.25 / 2.75
        return 7.5625 * t * t + 0.9375
    t -= 2.625 / 2.75
    return 7.5625 * t * t + 0.984375


def _progress(t: float, start: float, duration: float) -> float:
    return _clamp((t - start) / duration)


@lru_cache(maxsize=64)
def _font(size: int, weight: int = 800) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(FONT_PATH), size)
    # A static (non-variable) font file has no weight axis; it then renders at its own weight.
    with contextlib.suppress(OSError, AttributeError):
        font.set_variation_by_axes([weight])
    return font


def _wrap(
    text: str, font: ImageFont.FreeTypeFont, max_width: int, max_lines: int
) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
        while font.getlength(current) > max_width and len(current) > 2:
            current = current[:-2] + "…"
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while font.getlength(last + "…") > max_width and len(last) > 1:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,.;:-") + "…"
    return lines


def _text_block(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    fill: RGB,
    *,
    gap: int = 6,
    align: str = "left",
) -> Image.Image:
    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    widths = [math.ceil(font.getlength(line)) for line in lines] or [1]
    width = max(widths) + 4
    height = line_height * max(len(lines), 1) + gap * max(len(lines) - 1, 0)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for index, line in enumerate(lines):
        x = (width - widths[index]) // 2 if align == "center" else 0
        draw.text((x, index * (line_height + gap)), line, font=font, fill=(*fill, 255))
    return layer


def _faded(layer: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return layer
    faded = layer.copy()
    alpha = faded.getchannel("A").point(lambda value: int(value * _clamp(opacity)))
    faded.putalpha(alpha)
    return faded


def _composite(frame: Image.Image, layer: Image.Image, x: float, y: float) -> None:
    """Alpha-composite `layer` with its top-left at (x, y), clipped to the frame."""
    left, top = round(x), round(y)
    crop_left, crop_top = max(0, -left), max(0, -top)
    crop_right = min(layer.width, WIDTH - left)
    crop_bottom = min(layer.height, HEIGHT - top)
    if crop_right <= crop_left or crop_bottom <= crop_top:
        return
    if (crop_left, crop_top, crop_right, crop_bottom) != (0, 0, layer.width, layer.height):
        layer = layer.crop((crop_left, crop_top, crop_right, crop_bottom))
    frame.alpha_composite(layer, (left + crop_left, top + crop_top))


def _centered(frame: Image.Image, layer: Image.Image, cx: float, cy: float) -> None:
    _composite(frame, layer, cx - layer.width / 2, cy - layer.height / 2)


def _scaled(layer: Image.Image, scale: float) -> Image.Image:
    if abs(scale - 1) < 0.003:
        return layer
    size = (max(1, round(layer.width * scale)), max(1, round(layer.height * scale)))
    return layer.resize(size, Image.Resampling.BILINEAR)


def _gradient(top: RGB, bottom: RGB, glow: RGB | None = None, seed: int = 0) -> Image.Image:
    mask = Image.linear_gradient("L").resize((WIDTH, HEIGHT))
    base = Image.composite(
        Image.new("RGB", (WIDTH, HEIGHT), bottom), Image.new("RGB", (WIDTH, HEIGHT), top), mask
    )
    frame = base.convert("RGBA")
    if glow is not None:
        # The glow wanders from advert to advert, so even one theme never looks identical.
        rng = random.Random(seed)
        cx, cy = rng.uniform(0.15, 0.85) * WIDTH, rng.uniform(0.0, 0.35) * HEIGHT
        rx, ry = rng.uniform(0.35, 0.55) * WIDTH, rng.uniform(0.2, 0.3) * HEIGHT
        halo = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(*glow, 120))
        frame.alpha_composite(halo.filter(ImageFilter.GaussianBlur(90)))
    return frame


def _pill(
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: RGB,
    color: RGB,
    *,
    pad_x: int = 28,
    pad_y: int = 14,
    edge: RGB | None = None,
) -> Image.Image:
    left, top, right, bottom = font.getbbox(text)
    width = math.ceil(right - left) + pad_x * 2
    height = math.ceil(bottom - top) + pad_y * 2
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=height // 2,
        fill=(*fill, 255),
        outline=(*edge, 255) if edge else None,
        width=4 if edge else 0,
    )
    draw.text((pad_x - left, pad_y - top), text, font=font, fill=(*color, 255))
    return layer


def _price_badge(text: str, theme: Theme, shape: str) -> Image.Image:
    font = _font(46, 800)
    edge = (*theme.accent_edge, 255) if theme.accent_edge else None
    if shape == "sticker":
        left, top, right, bottom = font.getbbox(text)
        pad_x, pad_y = 30, 22
        width, height = (
            math.ceil(right - left) + pad_x * 2,
            math.ceil(bottom - top) + pad_y * 2,
        )
        layer = Image.new("RGBA", (width + 12, height + 12), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.rounded_rectangle(
            (6, 6, width + 5, height + 5),
            radius=22,
            fill=(*theme.accent, 255),
            outline=edge or (*WHITE, 255),
            width=5,
        )
        draw.text(
            (6 + pad_x - left, 6 + pad_y - top), text, font=font, fill=(*theme.on_accent, 255)
        )
        return layer.rotate(-5, resample=Image.Resampling.BICUBIC, expand=True)
    if shape == "tag":
        left, top, right, bottom = font.getbbox(text)
        notch, pad_x, pad_y = 30, 24, 16
        width = notch + math.ceil(right - left) + pad_x * 2
        height = math.ceil(bottom - top) + pad_y * 2
        layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        shape_points = [
            (notch, 0),
            (width - 1, 0),
            (width - 1, height - 1),
            (notch, height - 1),
            (0, height / 2),
        ]
        draw.polygon(
            shape_points, fill=(*theme.accent, 255), outline=edge, width=4 if edge else 1
        )
        hole = 7
        draw.ellipse(
            (notch * 0.7 - hole, height / 2 - hole, notch * 0.7 + hole, height / 2 + hole),
            fill=(*WHITE, 255),
            outline=edge,
            width=2 if edge else 0,
        )
        draw.text(
            (notch + pad_x - left, pad_y - top), text, font=font, fill=(*theme.on_accent, 255)
        )
        return layer
    return _pill(
        text, font, theme.accent, theme.on_accent, pad_x=30, pad_y=16, edge=theme.accent_edge
    )


# --------------------------------------------------------------------------- logo


def _pencil(width: float, height: float, ink: RGB) -> Image.Image:
    """The logo's "A": a pencil pointing down, yellow wood on top, `ink` lead and outline."""
    w, h = math.ceil(width), math.ceil(height)
    stroke = max(2, round(h / 11))
    layer = Image.new("RGBA", (w + stroke * 2, h + stroke * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    ox = oy = stroke
    shoulder = 0.52
    left_x = ox + w * shoulder * 0.5
    right_x = ox + w * (1 - shoulder * 0.5)
    draw.polygon(
        [(ox, oy), (ox + w, oy), (right_x, oy + h * shoulder), (left_x, oy + h * shoulder)],
        fill=(*BRAND_YELLOW, 255),
    )
    draw.polygon(
        [(left_x, oy + h * shoulder), (right_x, oy + h * shoulder), (ox + w / 2, oy + h)],
        fill=(*ink, 255),
    )
    tip = (ox + w / 2, oy + h)
    draw.line((ox, oy, *tip), fill=(*ink, 255), width=stroke)
    draw.line((ox + w, oy, *tip), fill=(*ink, 255), width=stroke)
    draw.line((ox + w / 2, oy + h * 0.12, *tip), fill=(*ink, 255), width=max(2, stroke - 1))
    return layer


def _wordmark(color: RGB, cap: int, part: str = "all") -> Image.Image:
    """KANSSHOP as on the logo: pencil "A", underlined SHOP, small ®. `part`: all|kans|shop."""
    font = _font(round(cap / 0.71), 800)
    _left, top, _right, bottom = font.getbbox("K")
    cap_px = bottom - top
    tracking = max(1, round(cap * 0.04))
    pencil_w = cap_px * 0.86
    pieces: list[str] = []
    if part in ("all", "kans"):
        pieces += ["K", "|pencil|", "NS"]
    if part in ("all", "shop"):
        pieces += ["SHOP"]
    widths = [pencil_w if piece == "|pencil|" else font.getlength(piece) for piece in pieces]
    reg_font = _font(max(10, round(cap * 0.42)), 600)
    reg_w = reg_font.getlength("®") if part in ("all", "shop") else 0
    total = sum(widths) + tracking * (len(pieces) - 1) + reg_w + 6
    line_gap = round(cap * 0.16)
    underline = max(2, round(cap / 16))
    height = cap_px + line_gap + underline + 6
    layer = Image.new("RGBA", (math.ceil(total) + 4, math.ceil(height)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    x = 2.0
    shop_start = None
    for piece, width in zip(pieces, widths, strict=True):
        if piece == "|pencil|":
            pencil = _pencil(width, cap_px, color)
            stroke = (pencil.width - math.ceil(width)) // 2
            layer.alpha_composite(pencil, (max(0, round(x) - stroke), 0))
        else:
            if piece == "SHOP":
                shop_start = x
            draw.text((x, 2 - top), piece, font=font, fill=(*color, 255))
        x += width + tracking
    if part in ("all", "shop"):
        draw.text(
            (x - tracking + 2, -top - cap * 0.08), "®", font=reg_font, fill=(*color, 255)
        )
        if shop_start is not None:
            y = cap_px + line_gap + 2
            draw.line(
                (shop_start - cap * 0.05, y, x - tracking + reg_w * 0.6, y),
                fill=(*color, 255),
                width=underline,
            )
    return layer


# --------------------------------------------------------------------------- doodles


def _doodle(kind: str, size: int, color: RGB, alpha: int) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    ink = (*color, alpha)
    stroke = max(3, size // 12)
    middle = size / 2
    if kind == "ring":
        draw.ellipse((stroke, stroke, size - stroke, size - stroke), outline=ink, width=stroke)
    elif kind == "plus":
        draw.line((middle, stroke, middle, size - stroke), fill=ink, width=stroke)
        draw.line((stroke, middle, size - stroke, middle), fill=ink, width=stroke)
    elif kind == "spark":
        for angle in range(0, 360, 45):
            reach = size * (0.46 if angle % 90 == 0 else 0.28)
            x = middle + math.cos(math.radians(angle)) * reach
            y = middle + math.sin(math.radians(angle)) * reach
            draw.line((middle, middle, x, y), fill=ink, width=stroke)
    elif kind == "dots":
        step = size / 3
        for row in range(3):
            for col in range(3):
                cx, cy = step * (col + 0.5), step * (row + 0.5)
                draw.ellipse((cx - stroke, cy - stroke, cx + stroke, cy + stroke), fill=ink)
    elif kind == "wave":
        points = [
            (x, middle + math.sin(x / size * math.tau * 1.5) * size * 0.18)
            for x in range(stroke, size - stroke, 3)
        ]
        draw.line(points, fill=ink, width=stroke, joint="curve")
    elif kind == "confetti":
        for index in range(4):
            theta = math.radians(25 + index * 70)
            cx = middle + math.cos(theta) * size * 0.26
            cy = middle + math.sin(theta) * size * 0.26
            dx, dy = math.cos(theta + 1.1) * size * 0.12, math.sin(theta + 1.1) * size * 0.12
            draw.line((cx - dx, cy - dy, cx + dx, cy + dy), fill=ink, width=stroke + 1)
    elif kind == "star":
        star: list[tuple[float, float]] = []
        for index in range(10):
            reach = size * (0.46 if index % 2 == 0 else 0.2)
            theta = math.radians(-90 + index * 36)
            star.append((middle + math.cos(theta) * reach, middle + math.sin(theta) * reach))
        draw.polygon(star, fill=ink)
    elif kind == "pencil":
        body = [
            (size * 0.2, size * 0.7),
            (size * 0.62, size * 0.28),
            (size * 0.76, size * 0.42),
            (size * 0.34, size * 0.84),
        ]
        draw.polygon(body, outline=ink, width=stroke)
        draw.line((size * 0.2, size * 0.7, size * 0.12, size * 0.92), fill=ink, width=stroke)
        draw.line((size * 0.12, size * 0.92, size * 0.34, size * 0.84), fill=ink, width=stroke)
    else:  # paperclip
        draw.rounded_rectangle(
            (size * 0.3, stroke, size * 0.7, size - stroke),
            radius=int(size * 0.2),
            outline=ink,
            width=stroke,
        )
        draw.rounded_rectangle(
            (size * 0.4, size * 0.22, size * 0.6, size * 0.75),
            radius=int(size * 0.1),
            outline=ink,
            width=stroke,
        )
    return layer


@dataclass
class _Floater:
    sprite: Image.Image
    x: float
    y: float
    amp_x: float
    amp_y: float
    speed: float
    phase: float
    spin: float


@dataclass
class _DoodleField:
    floaters: list[_Floater] = field(default_factory=list)

    @classmethod
    def make(
        cls,
        seed: int,
        colors: list[RGB],
        alpha: int,
        kinds: tuple[str, ...] = DOODLE_SETS[0],
        count: int = 9,
    ) -> _DoodleField:
        rng = random.Random(seed)
        floaters = []
        for index in range(count):
            size = rng.randint(34, 70)
            # Keep doodles in the margins so they frame the text instead of crossing it.
            side = index % 4
            if side == 0:
                x, y = rng.uniform(-14, 30), rng.uniform(90, HEIGHT - 160)
            elif side == 1:
                x, y = rng.uniform(WIDTH - 70, WIDTH - 20), rng.uniform(90, HEIGHT - 160)
            elif side == 2:
                x, y = rng.uniform(120, WIDTH - 180), rng.uniform(-10, 24)
            else:
                x, y = (
                    rng.uniform(-10, 80) if index % 2 else rng.uniform(WIDTH - 110, WIDTH - 30)
                ), rng.uniform(HEIGHT - 70, HEIGHT - 30)
            floaters.append(
                _Floater(
                    sprite=_doodle(
                        kinds[(index + seed) % len(kinds)],
                        size,
                        colors[index % len(colors)],
                        alpha,
                    ),
                    x=x,
                    y=y,
                    amp_x=rng.uniform(6, 16),
                    amp_y=rng.uniform(8, 22),
                    speed=rng.uniform(0.5, 1.1),
                    phase=rng.uniform(0, math.tau),
                    spin=rng.uniform(-24, 24),
                )
            )
        return cls(floaters)

    def draw(self, frame: Image.Image, t: float) -> None:
        for item in self.floaters:
            sprite = item.sprite.rotate(
                item.spin * math.sin(t * 0.6 + item.phase), resample=Image.Resampling.BICUBIC
            )
            x = item.x + math.sin(t * item.speed + item.phase) * item.amp_x
            y = item.y + math.cos(t * item.speed * 0.8 + item.phase) * item.amp_y
            _composite(frame, sprite, x, y)


# --------------------------------------------------------------------------- icons


def _icon(
    kind: str,
    theme: Theme,
    size: int = 64,
    *,
    disc: RGB | None = None,
    glyph: RGB | None = None,
) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(*(disc or theme.soft), 255))
    ink = (*(glyph or theme.dark_top), 255)
    s = size / 64
    if kind == "telegram":
        draw.polygon(
            [
                (16 * s, 31 * s),
                (48 * s, 18 * s),
                (42 * s, 47 * s),
                (32 * s, 39 * s),
                (27 * s, 45 * s),
                (27 * s, 36 * s),
            ],
            fill=ink,
        )
    elif kind == "phone":
        draw.rounded_rectangle(
            (22 * s, 13 * s, 42 * s, 51 * s),
            radius=int(5 * s),
            outline=ink,
            width=max(3, int(4 * s)),
        )
        draw.line((29 * s, 45 * s, 35 * s, 45 * s), fill=ink, width=max(2, int(3 * s)))
    else:  # channel / megaphone
        draw.polygon(
            [(17 * s, 27 * s), (36 * s, 18 * s), (36 * s, 46 * s), (17 * s, 37 * s)], fill=ink
        )
        draw.rectangle((38 * s, 26 * s, 44 * s, 38 * s), fill=ink)
        draw.line((22 * s, 38 * s, 25 * s, 48 * s), fill=ink, width=max(3, int(4 * s)))
    return layer


def _brand_mark(theme: Theme, size: int = 132) -> Image.Image:
    """An app-icon square with the logo's pencil."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * 0.24), fill=(*theme.mark_bg, 255)
    )
    pencil = _pencil(size * 0.5, size * 0.58, theme.mark_ink)
    layer.alpha_composite(pencil, ((size - pencil.width) // 2, (size - pencil.height) // 2))
    return layer


# --------------------------------------------------------------------------- scenes


class _Scene:
    duration: float

    def render(self, t: float) -> Image.Image:  # pragma: no cover - interface
        raise NotImplementedError


class _IntroScene(_Scene):
    duration = INTRO_SECONDS

    def __init__(self, brand: AdBrand, style: AdStyle) -> None:
        theme = style.theme
        self.variant = style.intro
        self.theme = theme
        self.background = _gradient(theme.dark_top, theme.dark_bottom, theme.glow, style.seed)
        self.doodles = _DoodleField.make(
            style.seed * 7 + 1, list(theme.doodles_dark), 70, style.doodles
        )
        self.mark = _brand_mark(theme)
        self.title = _wordmark(theme.paper, 62)
        self.kans = _wordmark(theme.paper, 74, "kans")
        self.shop = _wordmark(theme.paper, 74, "shop")
        self.hook_font = _font(38, 700)
        self.hook_lines = _wrap(brand.hook, self.hook_font, 560, 3)
        self.hook = _text_block(
            self.hook_lines, self.hook_font, theme.soft, gap=10, align="center"
        )
        self.tagline = _pill(brand.tagline, _font(24, 700), theme.chip, theme.on_chip)

    def _typed_hook(self, share: float) -> Image.Image:
        total = sum(len(line) for line in self.hook_lines)
        remaining = round(total * _clamp(share))
        lines: list[str] = []
        for line in self.hook_lines:
            lines.append(line[:remaining])
            remaining -= len(line)
            if remaining <= 0:
                break
        if share < 1:
            lines[-1] += "|"
        return _text_block(lines, self.hook_font, self.theme.soft, gap=10, align="center")

    def render(self, t: float) -> Image.Image:
        frame = self.background.copy()
        self.doodles.draw(frame, t)
        if self.variant == "typewriter":
            drop = ease_out_bounce(_progress(t, 0.0, 0.8))
            _centered(frame, self.mark, WIDTH / 2, -120 + 370 * drop)
            rise = ease_out_cubic(_progress(t, 0.35, 0.5))
            _centered(frame, _faded(self.title, rise), WIDTH / 2, 390 + 20 * (1 - rise))
            share = _progress(t, 0.7, 1.2)
            if share > 0:
                typed = self._typed_hook(share)
                _composite(
                    frame, typed, (WIDTH - self.hook.width) / 2, 530 - self.hook.height / 2
                )
        elif self.variant == "split":
            slide = ease_out_back(_progress(t, 0.0, 0.75))
            gap = -10  # the halves meet as one word, like the logo
            total = self.kans.width + gap + self.shop.width
            left = (WIDTH - total) / 2
            _composite(frame, self.kans, left - (1 - slide) * WIDTH, 330)
            _composite(
                frame, self.shop, left + self.kans.width + gap + (1 - slide) * WIDTH, 330
            )
            spin = ease_out_back(_progress(t, 0.4, 0.6))
            if spin > 0:
                mark = _scaled(self.mark, 0.62 * max(spin, 0.05)).rotate(
                    (1 - spin) * 180, resample=Image.Resampling.BICUBIC, expand=True
                )
                _centered(frame, mark, WIDTH / 2, 190)
            hook = ease_out_cubic(_progress(t, 0.8, 0.6))
            _centered(frame, _faded(self.hook, hook), WIDTH / 2, 540 + 24 * (1 - hook))
        else:  # pop
            pop = ease_out_back(_progress(t, 0.0, 0.7))
            mark = _scaled(self.mark, 0.4 + 0.6 * pop).rotate(
                -10 + 6 * pop, resample=Image.Resampling.BICUBIC, expand=True
            )
            _centered(frame, _faded(mark, _progress(t, 0, 0.25)), WIDTH / 2, 250)
            rise = ease_out_cubic(_progress(t, 0.3, 0.6))
            _centered(frame, _faded(self.title, rise), WIDTH / 2, 390 + 30 * (1 - rise))
            hook = ease_out_cubic(_progress(t, 0.75, 0.6))
            _centered(frame, _faded(self.hook, hook), WIDTH / 2, 530 + 24 * (1 - hook))
        tag = ease_out_cubic(_progress(t, 1.2, 0.5))
        _centered(frame, _faded(self.tagline, tag), WIDTH / 2, 745 + 16 * (1 - tag))
        return frame


class _ProductScene(_Scene):
    duration = PRODUCT_SECONDS

    def __init__(
        self, product: AdProduct, index: int, total: int, brand: AdBrand, style: AdStyle
    ) -> None:
        theme = style.theme
        self.theme = theme
        self.layout = style.layout
        # Each product of the same advert enters differently too.
        self.motion = MOTIONS[(MOTIONS.index(style.motion) + index) % len(MOTIONS)]
        top, bottom = theme.light[index % len(theme.light)]
        self.background = _gradient(top, bottom, WHITE, style.seed * 13 + index)
        self.doodles = _DoodleField.make(
            style.seed * 31 + index, list(theme.doodles_light), 46, style.doodles
        )
        name_font = _font(44 if self.layout != "spotlight" else 40, 800)
        name_width = 620 if self.layout != "spotlight" else 560
        name_lines = _wrap(product.name, name_font, name_width, 3)
        self.name = _text_block(
            name_lines,
            name_font,
            theme.ink,
            gap=4,
            align="center" if self.layout == "spotlight" else "left",
        )
        card_size = {"classic": 470, "flipped": 420, "spotlight": 400}[self.layout]
        if len(name_lines) > 2 and self.layout != "spotlight":
            card_size -= 30  # leave the long name room to breathe
        self.card = self._card(product.image, BRAND_BLACK, card_size)
        self.card_margin = 46
        self.price = _price_badge(
            f"{product.price} {brand.currency}", theme, style.price_shape
        )
        self.old_price = None
        if product.old_price:
            old = _text_block(
                [f"{product.old_price} {brand.currency}"], _font(30, 600), theme.muted
            )
            ImageDraw.Draw(old).line(
                (0, old.height * 0.55, old.width, old.height * 0.55),
                fill=(*theme.muted, 255),
                width=3,
            )
            self.old_price = old
        self.counter = _text_block(
            [f"{index + 1:02d} / {total:02d}"], _font(24, 700), theme.muted
        )
        self.badge = _wordmark(theme.ink, 20)
        self.blob: Image.Image | None = None
        self.panel: Image.Image | None = None
        if self.layout == "spotlight":
            # A yellow sun behind the photo on light scenes, a white one on yellow scenes.
            self.blob = self._blob(BRAND_YELLOW if top[2] > 150 else WHITE)
            panel_height = self.name.height + self.price.height + 70
            panel = Image.new("RGBA", (WIDTH - 80, panel_height), (0, 0, 0, 0))
            ImageDraw.Draw(panel).rounded_rectangle(
                (0, 0, panel.width - 1, panel_height - 1), radius=34, fill=(*WHITE, 235)
            )
            self.panel = panel

    @staticmethod
    def _blob(fill: RGB, radius: int = 250) -> Image.Image:
        layer = Image.new("RGBA", (radius * 2 + 40, radius * 2 + 40), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.ellipse((20, 20, radius * 2 + 20, radius * 2 + 20), fill=(*fill, 230))
        draw.ellipse(
            (0, 0, radius * 2 + 39, radius * 2 + 39), outline=(*BRAND_BLACK, 150), width=5
        )
        return layer

    @staticmethod
    def _card(photo: Image.Image, shadow: RGB, size: int) -> Image.Image:
        pad, margin = 26, 46
        canvas = Image.new("RGBA", (size + margin * 2, size + margin * 2), (0, 0, 0, 0))
        shade = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(shade).rounded_rectangle(
            (margin, margin + 16, margin + size, margin + size + 16),
            radius=40,
            fill=(*shadow, 70),
        )
        canvas.alpha_composite(shade.filter(ImageFilter.GaussianBlur(18)))
        body = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(body).rounded_rectangle(
            (0, 0, size - 1, size - 1), radius=40, fill=(*WHITE, 255)
        )
        fitted = ImageOps.contain(
            photo.convert("RGBA"), (size - pad * 2, size - pad * 2), Image.Resampling.LANCZOS
        )
        body.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
        canvas.alpha_composite(body, (margin, margin))
        return canvas

    def _card_motion(self, t: float) -> tuple[float, float, float, float]:
        """Offset x, offset y, scale and angle of the photo card as it enters."""
        enter = ease_out_cubic(_progress(t, 0.0, 0.75))
        back = ease_out_back(_progress(t, 0.0, 0.85))
        settle = 0.86 + 0.14 * back
        if self.motion == "slide_left":
            return -(1 - enter) * WIDTH * 0.7, 0.0, settle, 7 - 4 * enter
        if self.motion == "rise":
            return 0.0, (1 - enter) * HEIGHT * 0.6, settle, 4 - 6 * enter
        if self.motion == "zoom":
            return 0.0, 0.0, 0.2 + 0.8 * back, -3.0
        if self.motion == "spin":
            return 0.0, 0.0, 0.45 + 0.55 * enter, -100 * (1 - enter) - 3
        if self.motion == "drop":
            fall = ease_out_bounce(_progress(t, 0.0, 0.95))
            return 0.0, -(1 - fall) * HEIGHT * 0.65, 1.0, 2.0
        return (1 - enter) * WIDTH * 0.7, 0.0, settle, -7 + 4 * enter  # slide_right

    def _draw_card(self, frame: Image.Image, t: float, cx: float, cy: float) -> None:
        dx, dy, scale, angle = self._card_motion(t)
        scale += 0.035 * _progress(t, 0.85, self.duration)
        angle += 1.1 * math.sin(t * 1.6)
        card = _scaled(self.card, scale).rotate(
            angle, resample=Image.Resampling.BICUBIC, expand=True
        )
        _centered(frame, card, cx + dx, cy + dy)

    def _draw_price(self, frame: Image.Image, t: float, x: float, y: float) -> None:
        pop = _progress(t, 0.95, 0.5)
        if pop > 0:
            price = _scaled(self.price, 0.5 + 0.5 * ease_out_back(pop))
            _composite(
                frame,
                price,
                x + (self.price.width - price.width) / 2,
                y + (self.price.height - price.height) / 2,
            )
        if self.old_price is not None:
            fade = ease_out_cubic(_progress(t, 1.2, 0.4))
            _composite(
                frame,
                _faded(self.old_price, fade),
                x + self.price.width + 22,
                y + (self.price.height - self.old_price.height) / 2,
            )

    def render(self, t: float) -> Image.Image:
        frame = self.background.copy()
        self.doodles.draw(frame, t)
        _composite(frame, self.counter, 40, 34)
        _composite(frame, self.badge, WIDTH - 40 - self.badge.width, 34)
        rise = ease_out_cubic(_progress(t, 0.45, 0.55))
        visible_half = (self.card.height - 2 * self.card_margin) / 2
        if self.layout == "flipped":
            name_y = 104
            _composite(frame, _faded(self.name, rise), 50, name_y - 24 * (1 - rise))
            price_y = name_y + self.name.height + 22
            self._draw_price(frame, t, 50, price_y)
            card_y = min(
                HEIGHT - 44 - visible_half, price_y + self.price.height + 34 + visible_half
            )
            self._draw_card(frame, t, WIDTH / 2, card_y)
        elif self.layout == "spotlight" and self.blob is not None and self.panel is not None:
            glow = ease_out_back(_progress(t, 0.0, 0.7))
            pulse = 1 + 0.02 * math.sin(t * 2.4)
            _centered(frame, _scaled(self.blob, max(0.05, glow) * pulse), WIDTH / 2, 350)
            self._draw_card(frame, t, WIDTH / 2, 350)
            panel_y = HEIGHT - 40 - self.panel.height
            _composite(frame, _faded(self.panel, rise), 40, panel_y + 30 * (1 - rise))
            _centered(
                frame, _faded(self.name, rise), WIDTH / 2, panel_y + 26 + self.name.height / 2
            )
            price_x = (WIDTH - self.price.width) / 2
            if self.old_price is not None:
                price_x -= (self.old_price.width + 22) / 2
            self._draw_price(frame, t, price_x, panel_y + 40 + self.name.height)
        else:  # classic
            # A long name pushes the text block, and the photo with it, up to stay on screen.
            text_height = self.name.height + 26 + self.price.height
            text_top = min(612.0, HEIGHT - 44 - text_height)
            card_y = max(70 + visible_half, min(330.0, text_top - 18 - visible_half))
            self._draw_card(frame, t, WIDTH / 2, card_y)
            _composite(frame, _faded(self.name, rise), 50, text_top + 30 * (1 - rise))
            self._draw_price(frame, t, 50, text_top + self.name.height + 26)
        return frame


class _OutroScene(_Scene):
    duration = OUTRO_SECONDS

    def __init__(self, brand: AdBrand, style: AdStyle) -> None:
        theme = style.theme
        self.variant = style.outro
        self.background = _gradient(
            theme.dark_top, theme.dark_bottom, theme.glow, style.seed * 3 + 2
        )
        self.doodles = _DoodleField.make(
            style.seed * 7 + 5, list(theme.doodles_dark), 64, style.doodles
        )
        self.title = _text_block(
            [brand.order_title], _font(58, 800), theme.paper, align="center"
        )
        rows: list[tuple[str, str]] = [("telegram", f"@{brand.bot_username}")]
        if brand.phone:
            rows.append(("phone", brand.phone))
        if brand.channel_username:
            rows.append(("channel", f"@{brand.channel_username}"))
        # The contact card is white on dark and yellow stages, black on the white stage.
        light_stage = min(theme.dark_top) > 200
        panel_fill, panel_text = (BRAND_BLACK, WHITE) if light_stage else (WHITE, BRAND_BLACK)
        on_panel = self.variant == "panel"
        self.rows = [
            (
                (
                    _icon(kind, theme, disc=BRAND_YELLOW, glyph=BRAND_BLACK)
                    if on_panel
                    else _icon(kind, theme)
                ),
                _text_block([text], _font(40, 800), panel_text if on_panel else theme.paper),
            )
            for kind, text in rows
        ]
        self.button = _pill(
            brand.order_button, _font(34, 800), theme.cta, theme.on_cta, pad_x=36, pad_y=20
        )
        self.footer = _text_block([brand.footer], _font(22, 600), theme.soft, align="center")
        self.panel: Image.Image | None = None
        if on_panel:
            height = len(self.rows) * 100 + 40
            panel = Image.new("RGBA", (WIDTH - 100, height), (0, 0, 0, 0))
            ImageDraw.Draw(panel).rounded_rectangle(
                (0, 0, panel.width - 1, height - 1), radius=36, fill=(*panel_fill, 255)
            )
            self.panel = panel

    def render(self, t: float) -> Image.Image:
        frame = self.background.copy()
        self.doodles.draw(frame, t)
        rise = ease_out_cubic(_progress(t, 0.0, 0.55))
        _centered(frame, _faded(self.title, rise), WIDTH / 2, 190 + 30 * (1 - rise))
        rows_top = 300
        if self.panel is not None:
            grow = ease_out_back(_progress(t, 0.15, 0.55))
            panel = _scaled(self.panel, max(0.05, grow))
            _centered(frame, panel, WIDTH / 2, rows_top - 20 + self.panel.height / 2)
        row_width = max(icon.width + 22 + text.width for icon, text in self.rows)
        left = (WIDTH - row_width) / 2
        for index, (icon, text) in enumerate(self.rows):
            appear = ease_out_cubic(_progress(t, 0.35 + index * 0.22, 0.45))
            y = rows_top + index * 100 + 24 * (1 - appear)
            _composite(frame, _faded(icon, appear), left - 30 * (1 - appear), y)
            _composite(
                frame,
                _faded(text, appear),
                left + icon.width + 22,
                y + (icon.height - text.height) / 2,
            )
        button_in = ease_out_back(_progress(t, 1.1, 0.5))
        if button_in > 0:
            pulse = 1 + 0.035 * math.sin(max(0.0, t - 1.6) * 5.2)
            button = _scaled(self.button, (0.6 + 0.4 * button_in) * pulse)
            _centered(frame, button, WIDTH / 2, rows_top + len(self.rows) * 100 + 80)
        _centered(frame, _faded(self.footer, _progress(t, 1.4, 0.6)), WIDTH / 2, HEIGHT - 70)
        return frame


# --------------------------------------------------------------------------- transitions


def _transition(
    previous: Image.Image, current: Image.Image, share: float, kind: str
) -> Image.Image:
    p = ease_in_out(share)
    if kind == "wipe":
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(mask).rectangle((0, 0, round(p * WIDTH), HEIGHT), fill=255)
        return Image.composite(current, previous, mask)
    if kind == "slide":
        offset = round(p * WIDTH)
        frame = Image.new("RGB", (WIDTH, HEIGHT))
        frame.paste(previous.crop((offset, 0, WIDTH, HEIGHT)), (0, 0))
        if offset > 0:
            frame.paste(current.crop((0, 0, offset, HEIGHT)), (WIDTH - offset, 0))
        return frame
    if kind == "circle":
        radius = p * math.hypot(WIDTH, HEIGHT) / 2
        mask = Image.new("L", (WIDTH, HEIGHT), 0)
        ImageDraw.Draw(mask).ellipse(
            (WIDTH / 2 - radius, HEIGHT / 2 - radius, WIDTH / 2 + radius, HEIGHT / 2 + radius),
            fill=255,
        )
        return Image.composite(current, previous, mask)
    return Image.blend(previous, current, p)


# --------------------------------------------------------------------------- render


# Keeps every advert within the channel's 10-50 second format (1 product: 11 s, 10: 45.2 s).
MAX_PRODUCTS = 10


def advert_seconds(product_count: int) -> float:
    count = min(max(product_count, 1), MAX_PRODUCTS)
    return INTRO_SECONDS + PRODUCT_SECONDS * count + OUTRO_SECONDS


def _scenes(products: list[AdProduct], brand: AdBrand, style: AdStyle) -> list[_Scene]:
    scenes: list[_Scene] = [_IntroScene(brand, style)]
    scenes += [
        _ProductScene(product, index, len(products), brand, style)
        for index, product in enumerate(products)
    ]
    scenes.append(_OutroScene(brand, style))
    return scenes


def _frames(
    products: list[AdProduct], brand: AdBrand, fps: int, style: AdStyle
) -> Iterator[Image.Image]:
    span = FADE_SECONDS if style.transition == "fade" else TRANSITION_SECONDS
    previous: Image.Image | None = None
    for scene in _scenes(products, brand, style):
        count = round(scene.duration * fps)
        last: Image.Image | None = None
        for step in range(count):
            t = step / fps
            frame = scene.render(t).convert("RGB")
            if previous is not None and t < span:
                frame = _transition(previous, frame, t / span, style.transition)
            last = frame
            yield frame
        previous = last


def render_advert(
    products: list[AdProduct],
    brand: AdBrand,
    *,
    fps: int = FPS,
    style: AdStyle | None = None,
) -> RenderedVideo:
    """Render the advert to H.264 MP4 bytes (blocking; run it in a worker thread)."""
    if not products:
        raise ValueError("An advert needs at least one product")
    products = products[:MAX_PRODUCTS]
    style = style or advert_style(0)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="kans-advert-") as folder:
        output = Path(folder) / "advert.mp4"
        log_path = Path(folder) / "ffmpeg.log"
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{WIDTH}x{HEIGHT}", "-r", str(fps),
            "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-threads", "2", str(output),
        ]  # fmt: skip
        frames = 0
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log
            )
            try:
                assert process.stdin is not None
                for frame in _frames(products, brand, fps, style):
                    process.stdin.write(frame.tobytes())
                    frames += 1
                process.stdin.close()
                process.wait(timeout=180)
            except BaseException:
                process.kill()
                process.wait()
                raise
        if process.returncode != 0 or not output.exists():
            details = log_path.read_text(errors="replace")[-500:]
            raise RuntimeError(f"ffmpeg exited with {process.returncode}: {details}")
        return RenderedVideo(output.read_bytes(), WIDTH, HEIGHT, frames / fps)
