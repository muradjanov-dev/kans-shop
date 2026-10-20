"""Reverse geocoding: turn delivery coordinates into a written street address.

Customers can share a location instead of typing an address (bot location button or the
Mini App "send my location" button). Couriers and admins still need words, so the shop asks
OpenStreetMap Nominatim for the nearest address.

Nominatim's usage policy asks for an identifying User-Agent and at most one request per
second, so calls are serialized per process and results are cached by rounded coordinates.
Every failure returns ``None``: checkout and the bot keep working with the raw coordinates,
which admins always receive as a map link anyway.
"""

import asyncio
import time
from collections import OrderedDict
from decimal import Decimal
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_TIMEOUT_SECONDS = 6.0
_MIN_INTERVAL_SECONDS = 1.0
_CACHE_SIZE = 512
_MAX_ADDRESS_LENGTH = 300
_ACCEPT_LANGUAGE = {"uz": "uz,ru;q=0.8,en;q=0.5", "ru": "ru,uz;q=0.8,en;q=0.5"}

# Most specific first. Postcode and country are left out on purpose: a courier in Tashkent
# needs the street, the neighbourhood and the district, not "100115, O'zbekiston".
_STREET_KEYS = ("road", "pedestrian", "footway", "path", "square")
_AREA_KEYS = (
    ("neighbourhood", "quarter", "residential", "hamlet"),
    ("suburb", "city_district", "district", "borough", "county"),
    ("city", "town", "village", "municipality"),
)
_PLACE_KEYS = ("amenity", "shop", "building", "office", "tourism", "leisure")

_cache: OrderedDict[tuple[str, str, str], str] = OrderedDict()
_lock = asyncio.Lock()
_last_request_at = 0.0


def _first(address: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = address.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def format_address(payload: dict[str, Any]) -> str | None:
    """Build "Place, Street 12, Neighbourhood, District, City" from a Nominatim reply."""
    address = payload.get("address")
    if not isinstance(address, dict):
        return None

    parts: list[str] = []
    place = _first(address, _PLACE_KEYS)
    name = payload.get("name")
    if isinstance(name, str) and name.strip():
        place = name.strip()
    street = _first(address, _STREET_KEYS)
    house = address.get("house_number")
    if place and place != street:
        parts.append(place)
    if street:
        parts.append(
            f"{street} {house.strip()}" if isinstance(house, str) and house else street
        )
    for keys in _AREA_KEYS:
        value = _first(address, keys)
        if value:
            parts.append(value)

    unique: list[str] = []
    for part in parts:
        if part.casefold() not in {existing.casefold() for existing in unique}:
            unique.append(part)
    if len(unique) < 2:
        # Too little structure (open field, unmapped area): fall back to Nominatim's own label.
        display = payload.get("display_name")
        if isinstance(display, str) and display.strip():
            country = address.get("country")
            postcode = address.get("postcode")
            unique = [
                piece.strip()
                for piece in display.split(",")
                if piece.strip() and piece.strip() not in {country, postcode}
            ]
    text = ", ".join(unique)
    return text[:_MAX_ADDRESS_LENGTH] or None


def _cache_key(latitude: Decimal, longitude: Decimal, language: str) -> tuple[str, str, str]:
    # Five decimals is about one metre: the same doorstep shared twice is answered from memory.
    return (f"{latitude:.5f}", f"{longitude:.5f}", language)


async def reverse_geocode(
    latitude: Decimal,
    longitude: Decimal,
    *,
    language: str = "uz",
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Return a written address for the coordinates, or None if it cannot be determined."""
    global _last_request_at
    if not settings.geocoder_enabled:
        return None
    if not (Decimal("-90") <= latitude <= Decimal("90")) or not (
        Decimal("-180") <= longitude <= Decimal("180")
    ):
        return None
    language = language if language in _ACCEPT_LANGUAGE else "uz"
    key = _cache_key(latitude, longitude, language)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return cached

    async with _lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            await asyncio.sleep(wait)
        _last_request_at = time.monotonic()
        try:
            payload = await _fetch(latitude, longitude, language, client)
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("reverse_geocode_failed", error=type(exc).__name__)
            return None

    address = format_address(payload) if isinstance(payload, dict) else None
    if address:
        _cache[key] = address
        if len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return address


async def _fetch(
    latitude: Decimal, longitude: Decimal, language: str, client: httpx.AsyncClient | None
) -> Any:
    params = {
        "format": "jsonv2",
        "lat": f"{latitude:.6f}",
        "lon": f"{longitude:.6f}",
        "zoom": "18",
        "addressdetails": "1",
    }
    headers = {
        "User-Agent": settings.geocoder_user_agent,
        "Accept-Language": _ACCEPT_LANGUAGE[language],
    }
    url = f"{settings.geocoder_url.rstrip('/')}/reverse"
    if client is not None:
        response = await client.get(
            url, params=params, headers=headers, timeout=_TIMEOUT_SECONDS
        )
    else:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as own_client:
            response = await own_client.get(url, params=params, headers=headers)
    response.raise_for_status()
    return response.json()


def map_links(latitude: Decimal, longitude: Decimal) -> tuple[str, str]:
    """Google Maps and Yandex Maps links that open the exact point on a phone."""
    lat = f"{latitude:.6f}"
    lon = f"{longitude:.6f}"
    return (
        f"https://maps.google.com/?q={lat},{lon}",
        f"https://yandex.uz/maps/?pt={lon},{lat}&z=17&l=map",
    )


def clear_cache() -> None:
    _cache.clear()
