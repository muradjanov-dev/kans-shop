"""Reverse geocoding of shared delivery locations (no real network: httpx MockTransport)."""

from decimal import Decimal
from functools import partial
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bot.handlers.user.checkout import on_address_location
from app.bot.states.checkout import CheckoutStates
from app.bot.utils.i18n import translate
from app.core.config import settings
from app.services import geocoding

from .api_helpers import make_api_case

TASHKENT_REPLY = {
    "name": "",
    "display_name": "12, Yuqori Darxon ko'chasi, Darxon mahallasi, Chilonzor tumani, "
    "Toshkent, 100115, O'zbekiston",
    "address": {
        "house_number": "12",
        "road": "Yuqori Darxon ko'chasi",
        "neighbourhood": "Darxon mahallasi",
        "city_district": "Chilonzor tumani",
        "city": "Toshkent",
        "postcode": "100115",
        "country": "O'zbekiston",
        "country_code": "uz",
    },
}


@pytest.fixture(autouse=True)
def _geocoder_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "geocoder_enabled", True)
    monkeypatch.setattr(geocoding, "_MIN_INTERVAL_SECONDS", 0.0)
    geocoding.clear_cache()


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_format_address_keeps_street_area_and_city_but_not_postcode_or_country() -> None:
    assert geocoding.format_address(TASHKENT_REPLY) == (
        "Yuqori Darxon ko'chasi 12, Darxon mahallasi, Chilonzor tumani, Toshkent"
    )


def test_format_address_puts_a_named_place_first() -> None:
    reply = {"name": "Mega Planet", "address": {"road": "Ahmad Donish", "city": "Toshkent"}}
    assert geocoding.format_address(reply) == "Mega Planet, Ahmad Donish, Toshkent"


def test_format_address_falls_back_to_display_name_without_postcode_and_country() -> None:
    reply = {
        "display_name": "Qibray tumani, Toshkent viloyati, 111200, O'zbekiston",
        "address": {"county": "Qibray tumani", "postcode": "111200", "country": "O'zbekiston"},
    }
    assert geocoding.format_address(reply) == "Qibray tumani, Toshkent viloyati"


async def test_reverse_geocode_asks_nominatim_politely_and_caches() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=TASHKENT_REPLY)

    async with _client(handler) as client:
        first = await geocoding.reverse_geocode(
            Decimal("41.2856"), Decimal("69.2034"), language="uz", client=client
        )
        again = await geocoding.reverse_geocode(
            Decimal("41.285600"), Decimal("69.203400"), language="uz", client=client
        )

    assert (
        first
        == again
        == "Yuqori Darxon ko'chasi 12, Darxon mahallasi, Chilonzor tumani, Toshkent"
    )
    assert len(requests) == 1
    request = requests[0]
    assert request.url.path == "/reverse"
    assert request.url.params["lat"] == "41.285600"
    assert request.url.params["lon"] == "69.203400"
    assert request.url.params["format"] == "jsonv2"
    assert request.headers["user-agent"] == settings.geocoder_user_agent
    assert request.headers["accept-language"].startswith("uz")


async def test_reverse_geocode_returns_none_when_the_service_fails() -> None:
    async with _client(lambda request: httpx.Response(503)) as client:
        assert (
            await geocoding.reverse_geocode(Decimal("41"), Decimal("69"), client=client)
            is None
        )


async def test_reverse_geocode_is_off_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "geocoder_enabled", False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("the geocoder must not be called when disabled")

    async with _client(handler) as client:
        assert (
            await geocoding.reverse_geocode(Decimal("41"), Decimal("69"), client=client)
            is None
        )


def test_map_links_point_at_the_exact_coordinates() -> None:
    google, yandex = geocoding.map_links(Decimal("41.2856"), Decimal("69.2034"))
    assert google == "https://maps.google.com/?q=41.285600,69.203400"
    assert yandex == "https://yandex.uz/maps/?pt=69.203400,41.285600&z=17&l=map"


async def test_reverse_geocode_api_is_for_signed_in_customers(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_reverse(latitude: Decimal, longitude: Decimal, *, language: str) -> str:
        return f"{latitude} {longitude} {language}"

    monkeypatch.setattr(geocoding, "reverse_geocode", fake_reverse)
    params = {"lat": "41.2856", "lon": "69.2034", "lang": "ru"}
    async with make_api_case(test_engine) as case:
        anonymous = await case.client.get("/api/v1/geocode/reverse", params=params)
        signed_in = await case.client.get(
            "/api/v1/geocode/reverse",
            params=params,
            headers={"Authorization": f"Bearer {case.token}"},
        )
        out_of_range = await case.client.get(
            "/api/v1/geocode/reverse",
            params={"lat": "95", "lon": "69"},
            headers={"Authorization": f"Bearer {case.token}"},
        )

    assert anonymous.status_code == 401
    assert signed_in.status_code == 200
    assert signed_in.json() == {
        "address": "41.285600 69.203400 ru",
        "latitude": "41.285600",
        "longitude": "69.203400",
    }
    assert signed_in.headers["cache-control"] == "private, no-store"
    assert out_of_range.status_code == 422


class _FakeState:
    def __init__(self) -> None:
        self.data: dict[str, object] = {}
        self.state: object = None

    async def update_data(self, **values: object) -> None:
        self.data.update(values)

    async def set_state(self, value: object) -> None:
        self.state = value


class _FakeMessage:
    def __init__(self, latitude: float, longitude: float) -> None:
        self.location = SimpleNamespace(latitude=latitude, longitude=longitude)
        self.answers: list[str] = []

    async def answer(self, text: str, **_kwargs: object) -> None:
        self.answers.append(text)


async def test_bot_location_step_stores_the_written_address_and_shows_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_reverse(latitude: Decimal, longitude: Decimal, *, language: str) -> str:
        assert (latitude, longitude, language) == (
            Decimal("41.2856"),
            Decimal("69.2034"),
            "ru",
        )
        return "Yuqori Darxon ko'chasi 12 <B>"

    monkeypatch.setattr(geocoding, "reverse_geocode", fake_reverse)
    message = _FakeMessage(41.2856, 69.2034)
    state = _FakeState()

    await on_address_location(message, state, partial(translate, "ru"), "ru")  # type: ignore[arg-type]

    assert state.data == {
        "address": "Yuqori Darxon ko'chasi 12 <B>",
        "latitude": 41.2856,
        "longitude": 69.2034,
    }
    assert state.state == CheckoutStates.entering_address_comment
    assert "Yuqori Darxon ko'chasi 12 &lt;B&gt;" in message.answers[0]


async def test_bot_location_step_still_works_without_an_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_address(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(geocoding, "reverse_geocode", no_address)
    message = _FakeMessage(41.0, 69.0)
    state = _FakeState()

    await on_address_location(message, state, partial(translate, "uz"), "uz")  # type: ignore[arg-type]

    assert state.data["address"] is None
    assert state.data["latitude"] == 41.0
    assert message.answers[0] == translate("uz", "checkout.location_saved")
