"""Uzbek product names for the channel advert.

The catalog's `name_uz` mostly holds the Russian name from 1C, which made an Uzbek advert
read in two languages. The advert therefore names products in Uzbek Latin:

1. a curated translation for every current catalog product (uz_product_names.json, keyed by
   the catalog name, so a renamed product falls through to step 2 instead of showing a
   stale translation);
2. otherwise a stationery glossary for the common words, with every remaining Cyrillic word
   transliterated, so no Cyrillic ever reaches the advert.

Names already written in Latin are used as they are.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).with_name("uz_product_names.json")
_CYRILLIC = re.compile("[А-Яа-яЁё]")


def _key(name: str) -> str:
    return " ".join(name.lower().split())


@lru_cache(maxsize=1)
def _curated() -> dict[str, str]:
    raw: dict[str, str] = json.loads(_DATA.read_text(encoding="utf-8"))
    return {_key(source): uzbek for source, uzbek in raw.items()}


# Phrases first (longest meaning wins), then single words. Lower-case Russian on the left.
_PHRASES: tuple[tuple[str, str], ...] = (
    (r"ручк\w* шариков\w*", "sharikli ruchka"),
    (r"ручк\w* гелев\w*", "gelli ruchka"),
    (r"ручк\w* ролев\w*", "rolikli ruchka"),
    (r"карандаш\w* цветн\w*", "rangli qalamlar"),
    (r"маркер\w* текстов\w*", "matn markeri"),
    (r"маркер\w* перманентн\w*", "permanent marker"),
    (r"для бел\w* доск\w*", "oq doska uchun"),
    (r"для рисования", "rasm uchun"),
    (r"для лепки", "plastilin uchun"),
    (r"для заметок", "yozuvlar uchun"),
    (r"на гребне", "spiralli"),
    (r"на скобе", "skrepkali"),
    (r"на молнии", "zamokli"),
    (r"без кисти", "mo'yqalamsiz"),
    (r"с кистью", "mo'yqalam bilan"),
    (r"штемпельн\w* краск\w*", "muhr bo'yog'i"),
    (r"штемпельн\w* подушк\w*", "muhr yostiqchasi"),
    (r"оснастк\w* для печат\w*", "muhr korpusi"),
    (r"клей[- ]карандаш", "qalam yelim"),
    (r"папка[- ]уголок", "burchakli papka"),
)

_WORDS: dict[str, str] = {
    "ручка": "ruchka",
    "ручки": "ruchkalar",
    "ручек": "ruchkalar",
    "карандаш": "qalam",
    "карандаши": "qalamlar",
    "карандашей": "qalamlar",
    "тетрадь": "daftar",
    "тетради": "daftarlar",
    "блокнот": "bloknot",
    "альбом": "albom",
    "папка": "papka",
    "папки": "papkalar",
    "маркер": "marker",
    "маркеры": "markerlar",
    "пластилин": "plastilin",
    "акварель": "akvarel",
    "гуашь": "guash",
    "краска": "bo'yoq",
    "краски": "bo'yoqlar",
    "кисть": "mo'yqalam",
    "кисти": "mo'yqalamlar",
    "набор": "to'plam",
    "клей": "yelim",
    "ножницы": "qaychi",
    "точилка": "qalamtarosh",
    "ластик": "o'chirg'ich",
    "линейка": "chizg'ich",
    "калькулятор": "kalkulyator",
    "бумага": "qog'oz",
    "бумаги": "qog'oz",
    "картон": "karton",
    "картона": "karton",
    "игра": "o'yin",
    "пазлы": "pazl",
    "раскраска": "bo'yama",
    "доска": "doska",
    "пенал": "penal",
    "стикеры": "stikerlar",
    "закладки": "xatcho'plar",
    "скотч": "skotch",
    "лента": "lenta",
    "журнал": "jurnal",
    "книга": "kitob",
    "файл": "fayl",
    "файлы": "fayllar",
    "степлер": "stepler",
    "скобы": "skobalar",
    "скрепки": "skrepkalar",
    "корректор": "korrektor",
    "салфетки": "salfetkalar",
    "батарейка": "batareyka",
    "палитра": "palitra",
    "цветные": "rangli",
    "цветная": "rangli",
    "цветной": "rangli",
    "пластиковая": "plastik",
    "пластиковый": "plastik",
    "пластиковые": "plastik",
    "пластик": "plastik",
    "металлический": "metall",
    "деревянные": "yog'och",
    "акриловые": "akril",
    "клетка": "katak",
    "цвет": "rang",
    "цвета": "rang",
    "цветов": "rang",
    "цв": "rang",
    "лист": "varaq",
    "листов": "varaq",
    "л": "varaq",
    "шт": "dona",
    "штук": "dona",
    "мм": "mm",
    "см": "sm",
    "м": "m",
    "гр": "g",
    "г": "g",
    "мл": "ml",
    "мкм": "mkm",
    "синий": "ko'k",
    "синяя": "ko'k",
    "синее": "ko'k",
    "син": "ko'k",
    "черный": "qora",
    "черная": "qora",
    "чер": "qora",
    "черн": "qora",
    "красный": "qizil",
    "красная": "qizil",
    "крас": "qizil",
    "зеленый": "yashil",
    "зеленая": "yashil",
    "зел": "yashil",
    "желтый": "sariq",
    "желтая": "sariq",
    "белый": "oq",
    "белая": "oq",
    "розовый": "pushti",
    "розовая": "pushti",
    "роз": "pushti",
    "серый": "kulrang",
    "серая": "kulrang",
    "оранжевый": "to'q sariq",
    "оранж": "to'q sariq",
    "фиолетовый": "binafsha",
    "голубой": "havorang",
    "голубая": "havorang",
    "коричневый": "jigarrang",
    "коричневая": "jigarrang",
    "золото": "tillarang",
    "серебро": "kumushrang",
    "ассорти": "turli",
    "ассорт": "turli",
    "и": "va",
    "серия": "seriya",
    "формат": "format",
    "наб": "to'plam",
    "уп": "qadoq",
}
# Prepositions and packing notes that only add noise in an advert.
_DROP = frozenset(
    {
        "в",
        "на",
        "с",
        "для",
        "по",
        "из",
        "к",
        "от",
        "до",
        "обл",
        "инд",
        "индив",
        "упак",
        "европодвесом",
        "европодвес",
        "блистере",
        "коробке",
        "пакете",
        "ф",
    }
)

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh",
    "щ": "sh", "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip


def transliterate(text: str) -> str:
    """Russian Cyrillic to Uzbek Latin letters, keeping the case of each letter."""
    out = []
    for char in text:
        latin = _TRANSLIT.get(char.lower())
        if latin is None:
            out.append(char)
        elif char.isupper() and latin:
            out.append(latin[0].upper() + latin[1:])
        else:
            out.append(latin)
    return "".join(out)


_WORD = re.compile(r"[А-Яа-яЁё]+")


def _approximate(name: str) -> str:
    text = name
    for pattern, replacement in _PHRASES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    def word(match: re.Match[str]) -> str:
        lower = match.group(0).lower()
        if lower in _DROP:
            return ""
        if lower in _WORDS:
            return _WORDS[lower]
        return transliterate(match.group(0))

    text = _WORD.sub(word, text)
    text = re.sub(r"(\d)\s*(varaq|rang|dona|mm|sm|ml|mkm|g)\b", r"\1 \2", text)
    text = re.sub(r"\s+([,.;)])", r"\1", text)
    text = re.sub(r"[\s.]+$", "", " ".join(text.split()))
    return text[:1].upper() + text[1:] if text else name


def uzbek_product_name(name: str) -> str:
    """The product's name for an Uzbek advert, never containing Cyrillic letters."""
    clean = " ".join(name.split())
    if not _CYRILLIC.search(clean):
        return clean
    curated = _curated().get(_key(clean))
    if curated:
        return curated
    return _approximate(clean)
