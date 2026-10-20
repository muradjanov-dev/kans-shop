"""Captions for the daily channel advert.

The caption sells without selling: a relatable opening, the products with one honest
benefit each, a gentle invitation, then the facts people act on (prices, the bot, the
phone) and the channel username last. The story part comes from Claude when
ANTHROPIC_API_KEY is set and from the built-in Uzbek templates otherwise; the facts are
always assembled here, so a model can never get a price or a contact wrong.
"""

from __future__ import annotations

import html
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

import anthropic

from app.core.logging import get_logger

log = get_logger(__name__)

TELEGRAM_CAPTION_LIMIT = 1024
MAX_STORY_CHARS = 620
HASHTAGS = "#kanselyariya #ofis #maktab #KansShop"


@dataclass(frozen=True)
class CaptionProduct:
    name: str
    price: str
    old_price: str | None
    category: str


@dataclass(frozen=True)
class CaptionContext:
    products: Sequence[CaptionProduct]
    bot_username: str
    phone: str | None
    channel_username: str | None
    free_delivery_from: str | None
    weekday_date: str


@dataclass(frozen=True)
class Caption:
    text: str
    source: str
    key: str | None
    hook: str


HOOKS: list[tuple[str, str]] = [
    ("desk", "Ish stolingizga bir qarang. Unga nima yetishmayapti? 🤔"),
    (
        "morning",
        "Ertalabki choy, yangi reja va toza varaq — kun shunday boshlansa, yaxshi o'tadi ☕️",
    ),
    ("small", "Ba'zan bitta kichik buyum butun kunning kayfiyatini o'zgartiradi ✨"),
    (
        "colleague",
        "Hamkasbingiz yana ruchkangizni olib ketdimi? Bunga chek qo'yish vaqti keldi 😄",
    ),
    ("order", "Tartib — bu kayfiyat. Kayfiyat esa — natija 📈"),
    ("idea", "Eng zo'r g'oyalar odatda qo'lda qalam bo'lmagan payt keladi 💡"),
    (
        "school",
        "Darsga tayyorgarlik kechki shoshilinchlikdan emas, to'g'ri jihozlardan boshlanadi 🎒",
    ),
    ("search", "Ofisda eng ko'p vaqt nimaga ketadi? Kerakli narsani qidirishga 🔍"),
    (
        "gift",
        "Kichik sovg'a — katta e'tibor. Yaxshi kanselyariya hech qachon ortiqcha bo'lmaydi 🎁",
    ),
    ("week", "Yangi hafta — yangi rejalar. Ularni yozib qo'yish uchun hammasi tayyor 🗓"),
    ("quality", "Arzon narsa ikki marta olinadi, sifatlisi — bir marta 🌿"),
    (
        "five",
        "Ish boshlanishidan oldin 5 daqiqa ajrating: stolni tartibga keltiring, qolgani oson 🗂",
    ),
    ("habit", "Muvaffaqiyat katta qadamlardan emas, har kungi kichik odatlardan yig'iladi ✍️"),
    ("coffee", "Qahva tayyor, kayfiyat joyida. Endi faqat yaxshi ruchka kerak 😉"),
]

STORIES: list[tuple[str, str]] = [
    (
        "spotlight",
        "Bugun e'tiborimizda — {p1}. {B1}. Yoniga {p2} ham qo'shsangiz, to'plam to'liq bo'ladi.",
    ),
    (
        "simple",
        "{p1} ko'rinishidan oddiy, lekin ishda o'zini ko'rsatadi: {b1}. {P2} esa kundalik ishlarni yanada yengillashtiradi.",
    ),
    (
        "trust",
        "Biz tanlagan narsalarni o'zimiz ham ishlatamiz. Masalan, {p1} — {b1}. {P2} ham shunday: {b2}.",
    ),
    ("details", "Katta ishlar mayda detallardan boshlanadi. {P1} — {b1}, {p2} esa {b2}."),
    (
        "pair",
        "Ba'zi narsalar bir-biri bilan yaxshi chiqishadi: {p1} va {p2}. Birinchisi — {b1}, ikkinchisi — {b2}.",
    ),
]

SOFT_CTAS: list[str] = [
    "Shoshilmang: avval ko'rib chiqing, yoqsa — botda bir necha bosishda buyurtma berasiz 🙂",
    "Savolingiz bormi? Bemalol yozing — maslahat beramiz, hech qanday majburiyat yo'q 🤝",
    "Ofis, maktab va uy uchun kerakli hammasi bir joyda — botda 🛒",
    "Narx va mavjudligini botda bir zumda ko'rasiz 👀",
    "Bugun buyurtma qiling — ertangi ishlaringiz tayyor turadi ✅",
]

_BENEFITS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"штемп|печат|shtamp|muhr", re.I),
        "hujjatlaringizga rasmiy va ishonchli ko'rinish beradi",
    ),
    (
        re.compile(
            r"творч|ijod|рисов|rasm|albom|rangli|guash|bo['‘ʻ]?yoq|bo['‘ʻ]?yama|akvarel"
            r"|plastilin|mo['‘ʻ]?yqalam|pazl|kraska",
            re.I,
        ),
        "ijodga ilhom beradi va ranglarni jonlantiradi",
    ),
    (
        re.compile(r"папк|архив|papka|arxiv|fayl|registr|skorosshivatel", re.I),
        "hujjatlar doim joyida va tartibli turadi",
    ),
    (re.compile(r"книг|kitob|book", re.I), "o'qishni yoqimli odatga aylantiradi"),
    (
        re.compile(
            r"бумаж|бумаг|qog['‘ʻ]?oz|paper|daftar|тетрад|блокнот|bloknot|jurnal|журнал"
            r"|stiker|xatcho['‘ʻ]?p",
            re.I,
        ),
        "har bir varag'i silliq va ishonchli",
    ),
    # Before the writing tools: "qalam yelim" is glue and "qalamtarosh" a sharpener.
    (re.compile(r"yelim|клей", re.I), "qog'ozni toza va mustahkam yopishtiradi"),
    (re.compile(r"qalamtarosh|точилк", re.I), "qalamni bir zumda o'tkir qiladi"),
    (
        re.compile(r"письм|ручк|yozuv|ruchka|pen|qalam|маркер|marker|карандаш", re.I),
        "yozganda qo'l charchamaydi, chiziq esa bir tekis chiqadi",
    ),
    (re.compile(r"школ|maktab|school", re.I), "darsga tayyorgarlikni ancha yengillashtiradi"),
    (
        re.compile(r"быт|maishiy|xo['‘ʻ]?jalik|batarey|батарей|салфет|salfetka", re.I),
        "uyda ham, ofisda ham doim asqotadi",
    ),
    (
        re.compile(r"строит|qurilish|build", re.I),
        "ishni tez va puxta bitirishga yordam beradi",
    ),
    (
        re.compile(
            r"офис|ofis|office|калькулятор|kalkulyator|степлер|stepler|скотч|skotch|нож"
            r"|pichoq|qaychi|lotok|kanselyariya",
            re.I,
        ),
        "ish stolini tartibli va qulay qiladi",
    ),
]
_DEFAULT_BENEFIT = "kundalik ishlaringizni yengillashtiradi"


def _escape(text: str) -> str:
    """Escape for Telegram's HTML mode, keeping apostrophes (o'tkazma) readable."""
    return html.escape(text, quote=False)


def benefit_for(product: CaptionProduct) -> str:
    text = f"{product.name} {product.category}"
    return next(
        (benefit for pattern, benefit in _BENEFITS if pattern.search(text)), _DEFAULT_BENEFIT
    )


def _short_name(name: str, limit: int = 60) -> str:
    name = " ".join(name.split())
    return name if len(name) <= limit else name[: limit - 1].rstrip() + "…"


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


# Two products of the same kind would otherwise praise the second one with the first's words.
_SECOND_BENEFIT = "kundalik ishda doim asqotadi"


def _story_from_template(products: Sequence[CaptionProduct], template: str) -> str:
    first = products[0]
    second = products[1] if len(products) > 1 else products[0]
    first_benefit = benefit_for(first)
    second_benefit = benefit_for(second)
    if second is not first and second_benefit == first_benefit:
        second_benefit = _SECOND_BENEFIT
    values = {
        "p1": _short_name(first.name),
        "p2": _short_name(second.name),
        "b1": first_benefit,
        "b2": second_benefit,
    }
    values |= {key.upper(): _capitalize(value) for key, value in values.items()}
    return template.format(**values)


def _facts(context: CaptionContext) -> str:
    lines = []
    for product in context.products:
        line = f"🛍 {_escape(_short_name(product.name))} — <b>{_escape(product.price)} so'm</b>"
        if product.old_price:
            line += f" <s>{_escape(product.old_price)}</s>"
        lines.append(line)
    return "\n".join(lines)


def _contacts(context: CaptionContext, soft_cta: str) -> str:
    parts = [_escape(soft_cta)]
    if context.free_delivery_from:
        parts.append(
            f"🚚 {_escape(context.free_delivery_from)} so'mdan ortiq buyurtmalarga "
            "yetkazib berish bepul."
        )
    order = [f"🤖 Buyurtma: @{context.bot_username}"]
    if context.phone:
        order.append(f"📞 Telefon: {_escape(context.phone)}")
    tail = [HASHTAGS]
    if context.channel_username:
        tail.append(f"📣 @{context.channel_username}")
    return "\n".join(parts) + "\n\n" + "\n".join(order) + "\n\n" + "\n".join(tail)


def assemble(context: CaptionContext, *, story_html: str, soft_cta: str) -> str:
    """Join the story with the facts block; trims the product list if Telegram's limit hits."""
    products = list(context.products)
    while True:
        trimmed = CaptionContext(
            products=products,
            bot_username=context.bot_username,
            phone=context.phone,
            channel_username=context.channel_username,
            free_delivery_from=context.free_delivery_from,
            weekday_date=context.weekday_date,
        )
        text = f"{story_html}\n\n{_facts(trimmed)}\n\n{_contacts(trimmed, soft_cta)}"
        if len(text) <= TELEGRAM_CAPTION_LIMIT or len(products) <= 1:
            return text[:TELEGRAM_CAPTION_LIMIT]
        products = products[:-1]


def template_caption(
    context: CaptionContext,
    *,
    recent_keys: Sequence[str] = (),
    rng: random.Random | None = None,
) -> Caption:
    rng = rng or random.Random()
    recent_hooks = {key.split(":", 1)[0] for key in recent_keys}
    hooks = [hook for hook in HOOKS if hook[0] not in recent_hooks] or HOOKS
    hook_key, hook = rng.choice(hooks)
    story_key, story_template = rng.choice(STORIES)
    story = _story_from_template(context.products, story_template)
    soft_cta = rng.choice(SOFT_CTAS)
    story_html = f"{_escape(hook)}\n\n{_escape(story)}"
    return Caption(
        text=assemble(context, story_html=story_html, soft_cta=soft_cta),
        source="template",
        key=f"{hook_key}:{story_key}",
        hook=hook,
    )


# --------------------------------------------------------------------------- Claude

_SYSTEM_PROMPT = (
    "You write daily Telegram channel posts for Kans Shop, a stationery and office-supplies "
    "shop in Tashkent. Write in Uzbek (Latin script) in a warm, witty, human voice — like a "
    "shop owner who genuinely loves good stationery, never like an advert. Sell without "
    "selling: open with a relatable everyday moment or a tiny story, let the products appear "
    "naturally with one concrete benefit each, and close with a gentle, pressure-free "
    "invitation. Use at most three emoji. Prices, phone numbers, usernames, links and "
    "hashtags are added after your text, so leave them out. Reply with the post text only: "
    "two or three short paragraphs, under 600 characters in total."
)

_FORBIDDEN = re.compile(r"@|https?://|t\.me/|\+?998|#\w")


async def claude_story(
    context: CaptionContext, *, api_key: str, model: str, timeout: float = 90.0
) -> str | None:
    """A Claude-written story for the advert, or None if it cannot be used."""
    product_lines = "\n".join(
        f"- {product.name} (kategoriya: {product.category}; narx: {product.price} so'm)"
        for product in context.products
    )
    prompt = (
        f"Bugun: {context.weekday_date}.\n"
        f"Bugungi postdagi mahsulotlar:\n{product_lines}\n\n"
        "Kanal uchun post matnini yozing."
    )
    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=2)
    try:
        response = await client.beta.messages.create(
            model=model,
            max_tokens=8000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": "medium"},
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIConnectionError:
        log.warning("marketing_caption_claude_unreachable")
        return None
    except anthropic.RateLimitError:
        log.warning("marketing_caption_claude_rate_limited")
        return None
    except anthropic.APIStatusError as exc:
        log.warning("marketing_caption_claude_error", status=exc.status_code)
        return None
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        log.warning("marketing_caption_claude_refused")
        return None
    text = "\n".join(
        block.text.strip() for block in response.content if block.type == "text" and block.text
    ).strip()
    if not 80 <= len(text) <= MAX_STORY_CHARS or _FORBIDDEN.search(text):
        log.warning("marketing_caption_claude_unusable", length=len(text))
        return None
    return text


async def build_caption(
    context: CaptionContext,
    *,
    api_key: str = "",
    model: str = "claude-opus-5-5",
    recent_keys: Sequence[str] = (),
    rng: random.Random | None = None,
) -> Caption:
    """Claude's story when a key is configured and the answer is usable, templates otherwise."""
    fallback = template_caption(context, recent_keys=recent_keys, rng=rng)
    if not api_key:
        return fallback
    story = await claude_story(context, api_key=api_key, model=model)
    if story is None:
        return fallback
    soft_cta = (rng or random.Random()).choice(SOFT_CTAS)
    first_line = story.splitlines()[0][:120]
    return Caption(
        text=assemble(context, story_html=_escape(story), soft_cta=soft_cta),
        source="llm",
        key=None,
        hook=first_line,
    )
