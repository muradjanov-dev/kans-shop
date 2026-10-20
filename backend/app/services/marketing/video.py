"""Animated channel advert: a 720x900 MP4 drawn with Pillow and encoded by ffmpeg.

Scenes: an intro with the brand and a hook line, one scene per product (photo on a tilted
white card, name, price badge) and an outro with the ways to order. Frames are produced one
at a time and piped straight into ffmpeg, so memory stays flat however long the advert is.
The ffmpeg binary ships inside the imageio-ffmpeg wheel; no system package is needed.
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

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

WIDTH, HEIGHT = 720, 900
FPS = 30
INTRO_SECONDS = 2.8
PRODUCT_SECONDS = 3.8
OUTRO_SECONDS = 4.4
FADE_SECONDS = 0.35

FONT_PATH = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "Manrope.ttf"

GREEN = (21, 63, 50)
DEEP = (12, 40, 31)
CREAM = (247, 248, 242)
SAGE = (228, 237, 229)
PEACH = (251, 230, 214)
ORANGE = (238, 121, 56)
INK = (35, 54, 44)
MUTED = (105, 117, 108)
MINT = (152, 207, 173)
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


def _gradient(top: RGB, bottom: RGB, glow: RGB | None = None) -> Image.Image:
    mask = Image.linear_gradient("L").resize((WIDTH, HEIGHT))
    base = Image.composite(
        Image.new("RGB", (WIDTH, HEIGHT), bottom), Image.new("RGB", (WIDTH, HEIGHT), top), mask
    )
    frame = base.convert("RGBA")
    if glow is not None:
        halo = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse(
            (WIDTH * 0.35, -HEIGHT * 0.12, WIDTH * 1.25, HEIGHT * 0.45), fill=(*glow, 120)
        )
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
) -> Image.Image:
    left, top, right, bottom = font.getbbox(text)
    width = math.ceil(right - left) + pad_x * 2
    height = math.ceil(bottom - top) + pad_y * 2
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=height // 2, fill=(*fill, 255)
    )
    draw.text((pad_x - left, pad_y - top), text, font=font, fill=(*color, 255))
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
    def make(cls, seed: int, colors: list[RGB], alpha: int, count: int = 9) -> _DoodleField:
        rng = random.Random(seed)
        kinds = ["ring", "plus", "spark", "dots", "wave", "clip"]
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
                        kinds[index % len(kinds)], size, colors[index % len(colors)], alpha
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


def _icon(kind: str, size: int = 64) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse((0, 0, size - 1, size - 1), fill=(*MINT, 255))
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
            fill=(*GREEN, 255),
        )
    elif kind == "phone":
        draw.rounded_rectangle(
            (22 * s, 13 * s, 42 * s, 51 * s),
            radius=int(5 * s),
            outline=(*GREEN, 255),
            width=max(3, int(4 * s)),
        )
        draw.line(
            (29 * s, 45 * s, 35 * s, 45 * s), fill=(*GREEN, 255), width=max(2, int(3 * s))
        )
    else:  # channel / megaphone
        draw.polygon(
            [(17 * s, 27 * s), (36 * s, 18 * s), (36 * s, 46 * s), (17 * s, 37 * s)],
            fill=(*GREEN, 255),
        )
        draw.rectangle((38 * s, 26 * s, 44 * s, 38 * s), fill=(*GREEN, 255))
        draw.line(
            (22 * s, 38 * s, 25 * s, 48 * s), fill=(*GREEN, 255), width=max(3, int(4 * s))
        )
    return layer


def _brand_mark(size: int = 132) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * 0.24), fill=(*CREAM, 255)
    )
    font = _font(int(size * 0.62), 800)
    left, top, right, bottom = font.getbbox("K")
    draw.text(
        ((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
        "K",
        font=font,
        fill=(*GREEN, 255),
    )
    dot = size * 0.1
    draw.ellipse(
        (size * 0.7 - dot, size * 0.22 - dot, size * 0.7 + dot, size * 0.22 + dot),
        fill=(*ORANGE, 255),
    )
    return layer


# --------------------------------------------------------------------------- scenes


class _Scene:
    duration: float

    def render(self, t: float) -> Image.Image:  # pragma: no cover - interface
        raise NotImplementedError


class _IntroScene(_Scene):
    duration = INTRO_SECONDS

    def __init__(self, brand: AdBrand) -> None:
        self.background = _gradient(GREEN, DEEP, glow=(46, 110, 84))
        self.doodles = _DoodleField.make(7, [MINT, ORANGE, CREAM], 70)
        self.mark = _brand_mark()
        self.title = _text_block(["Kans Shop"], _font(70, 800), CREAM)
        self.hook = _text_block(
            _wrap(brand.hook, _font(38, 700), 560, 3),
            _font(38, 700),
            MINT,
            gap=10,
            align="center",
        )
        self.tagline = _pill(brand.tagline, _font(24, 700), (35, 84, 67), CREAM)

    def render(self, t: float) -> Image.Image:
        frame = self.background.copy()
        self.doodles.draw(frame, t)
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


_PRODUCT_BACKGROUNDS: list[tuple[RGB, RGB]] = [
    (CREAM, SAGE),
    (SAGE, PEACH),
    (PEACH, CREAM),
    (SAGE, CREAM),
]


class _ProductScene(_Scene):
    duration = PRODUCT_SECONDS

    def __init__(self, product: AdProduct, index: int, total: int, brand: AdBrand) -> None:
        top, bottom = _PRODUCT_BACKGROUNDS[index % len(_PRODUCT_BACKGROUNDS)]
        self.background = _gradient(top, bottom, glow=WHITE)
        self.doodles = _DoodleField.make(100 + index, [GREEN, ORANGE, MUTED], 46)
        self.card = self._card(product.image)
        name_font = _font(44, 800)
        self.name = _text_block(_wrap(product.name, name_font, 620, 3), name_font, INK, gap=4)
        self.price = _pill(
            f"{product.price} {brand.currency}",
            _font(46, 800),
            ORANGE,
            WHITE,
            pad_x=30,
            pad_y=16,
        )
        self.old_price = None
        if product.old_price:
            old = _text_block([f"{product.old_price} {brand.currency}"], _font(30, 600), MUTED)
            ImageDraw.Draw(old).line(
                (0, old.height * 0.55, old.width, old.height * 0.55),
                fill=(*MUTED, 255),
                width=3,
            )
            self.old_price = old
        self.counter = _text_block([f"{index + 1:02d} / {total:02d}"], _font(24, 700), MUTED)
        self.badge = _text_block(["Kans Shop"], _font(24, 800), GREEN)

    @staticmethod
    def _card(photo: Image.Image, size: int = 470) -> Image.Image:
        pad, margin = 26, 46
        canvas = Image.new("RGBA", (size + margin * 2, size + margin * 2), (0, 0, 0, 0))
        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            (margin, margin + 16, margin + size, margin + size + 16),
            radius=40,
            fill=(*GREEN, 70),
        )
        canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18)))
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

    def render(self, t: float) -> Image.Image:
        frame = self.background.copy()
        self.doodles.draw(frame, t)
        _composite(frame, self.counter, 40, 34)
        _composite(frame, self.badge, WIDTH - 40 - self.badge.width, 34)
        enter = ease_out_cubic(_progress(t, 0.0, 0.75))
        scale = (
            0.86
            + 0.14 * ease_out_back(_progress(t, 0.0, 0.85))
            + 0.035 * _progress(t, 0.85, self.duration)
        )
        angle = -7 + 4 * enter + 1.1 * math.sin(t * 1.6)
        card = _scaled(self.card, scale).rotate(
            angle, resample=Image.Resampling.BICUBIC, expand=True
        )
        _centered(frame, card, WIDTH / 2 + (1 - enter) * WIDTH * 0.7, 330)
        rise = ease_out_cubic(_progress(t, 0.45, 0.55))
        _composite(frame, _faded(self.name, rise), 50, 612 + 30 * (1 - rise))
        price_y = 612 + self.name.height + 26
        pop = _progress(t, 0.95, 0.5)
        if pop > 0:
            price = _scaled(self.price, 0.5 + 0.5 * ease_out_back(pop))
            _composite(
                frame,
                price,
                50 + (self.price.width - price.width) / 2,
                price_y + (self.price.height - price.height) / 2,
            )
        if self.old_price is not None:
            fade = ease_out_cubic(_progress(t, 1.2, 0.4))
            _composite(
                frame,
                _faded(self.old_price, fade),
                50 + self.price.width + 22,
                price_y + (self.price.height - self.old_price.height) / 2,
            )
        return frame


class _OutroScene(_Scene):
    duration = OUTRO_SECONDS

    def __init__(self, brand: AdBrand) -> None:
        self.background = _gradient(GREEN, DEEP, glow=(46, 110, 84))
        self.doodles = _DoodleField.make(77, [MINT, ORANGE, CREAM], 64)
        self.title = _text_block([brand.order_title], _font(58, 800), CREAM, align="center")
        rows: list[tuple[str, str]] = [("telegram", f"@{brand.bot_username}")]
        if brand.phone:
            rows.append(("phone", brand.phone))
        if brand.channel_username:
            rows.append(("channel", f"@{brand.channel_username}"))
        self.rows = [
            (_icon(kind), _text_block([text], _font(40, 800), CREAM)) for kind, text in rows
        ]
        self.button = _pill(
            brand.order_button, _font(34, 800), ORANGE, WHITE, pad_x=36, pad_y=20
        )
        self.footer = _text_block([brand.footer], _font(22, 600), MINT, align="center")

    def render(self, t: float) -> Image.Image:
        frame = self.background.copy()
        self.doodles.draw(frame, t)
        rise = ease_out_cubic(_progress(t, 0.0, 0.55))
        _centered(frame, _faded(self.title, rise), WIDTH / 2, 190 + 30 * (1 - rise))
        row_width = max(icon.width + 22 + text.width for icon, text in self.rows)
        left = (WIDTH - row_width) / 2
        for index, (icon, text) in enumerate(self.rows):
            appear = ease_out_cubic(_progress(t, 0.35 + index * 0.22, 0.45))
            y = 300 + index * 100 + 24 * (1 - appear)
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
            _centered(frame, button, WIDTH / 2, 300 + len(self.rows) * 100 + 80)
        _centered(frame, _faded(self.footer, _progress(t, 1.4, 0.6)), WIDTH / 2, HEIGHT - 70)
        return frame


# --------------------------------------------------------------------------- render


# Keeps every advert within the channel's 10-50 second format (1 product: 11 s, 10: 45.2 s).
MAX_PRODUCTS = 10


def advert_seconds(product_count: int) -> float:
    count = min(max(product_count, 1), MAX_PRODUCTS)
    return INTRO_SECONDS + PRODUCT_SECONDS * count + OUTRO_SECONDS


def _frames(products: list[AdProduct], brand: AdBrand, fps: int) -> Iterator[Image.Image]:
    scenes: list[_Scene] = [_IntroScene(brand)]
    scenes += [
        _ProductScene(product, index, len(products), brand)
        for index, product in enumerate(products)
    ]
    scenes.append(_OutroScene(brand))
    previous: Image.Image | None = None
    for scene in scenes:
        count = round(scene.duration * fps)
        last: Image.Image | None = None
        for step in range(count):
            t = step / fps
            frame = scene.render(t).convert("RGB")
            if previous is not None and t < FADE_SECONDS:
                frame = Image.blend(previous, frame, ease_in_out(t / FADE_SECONDS))
            last = frame
            yield frame
        previous = last


def render_advert(
    products: list[AdProduct], brand: AdBrand, *, fps: int = FPS
) -> RenderedVideo:
    """Render the advert to H.264 MP4 bytes (blocking; run it in a worker thread)."""
    if not products:
        raise ValueError("An advert needs at least one product")
    products = products[:MAX_PRODUCTS]
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
                for frame in _frames(products, brand, fps):
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
