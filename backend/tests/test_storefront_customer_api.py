import asyncio
from decimal import Decimal
from secrets import token_hex

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bot.handlers.user.checkout import _default_name
from app.bot.keyboards.reply.checkout import phone_request_keyboard
from app.db.models.enums import OrderStatus, OrderType, PaymentMethod
from app.db.models.order import Order
from app.db.models.user import User
from app.db.repositories import user_repository

from .api_helpers import make_api_case


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _address(label: str = "Home", *, text: str = "12 Amir Temur ko'chasi") -> dict[str, str]:
    return {"label": label, "address_text": text, "address_comment": "Door 4"}


def test_checkout_prefills_profile_name_and_phone() -> None:
    user = User(telegram_id=9_200_000_000_000_001, first_name="Telegram Name")
    user.display_name = "Profile Name"
    user.phone = "+998901234567"

    assert _default_name(user) == "Profile Name"
    keyboard = phone_request_keyboard(lambda key, **kwargs: key, default_phone=user.phone)
    assert user.phone in [button.text for row in keyboard.keyboard for button in row]


async def test_profile_allowlist_phone_and_language(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        response = await case.client.get("/api/v1/profile", headers=_auth(case.token))
        assert response.status_code == 200
        assert set(response.json()) == {"display_name", "phone", "language"}

        updated = await case.client.patch(
            "/api/v1/profile",
            headers=_auth(case.token),
            json={
                "display_name": "  Kamola Aliyeva  ",
                "phone": "90 123 45 67",
                "language": "ru",
            },
        )
        assert updated.status_code == 200
        assert updated.json() == {
            "display_name": "Kamola Aliyeva",
            "phone": "+998901234567",
            "language": "ru",
        }

        extra_field = await case.client.patch(
            "/api/v1/profile",
            headers=_auth(case.token),
            json={"is_admin": True},
        )
        invalid_phone = await case.client.patch(
            "/api/v1/profile",
            headers=_auth(case.token),
            json={"phone": "+998001234567"},
        )
        invalid_language = await case.client.patch(
            "/api/v1/profile",
            headers=_auth(case.token),
            json={"language": "en"},
        )
        assert extra_field.status_code == 422
        assert invalid_phone.status_code == 422
        assert invalid_language.status_code == 422


async def test_profile_old_user_name_backfill(db_session) -> None:
    user = await user_repository.create(
        db_session,
        telegram_id=9_100_000_000_000_001,
        first_name="  Kamola ",
        last_name=" Aliyeva  ",
        username="kamola",
    )
    username_fallback = await user_repository.create(
        db_session,
        telegram_id=9_100_000_000_000_002,
        first_name="  ",
        last_name=None,
        username="  stationery_user  ",
    )
    generic_fallback = await user_repository.create(
        db_session,
        telegram_id=9_100_000_000_000_003,
        first_name="  ",
        last_name=" ",
        username=" ",
    )

    assert getattr(user, "display_name", None) == "Kamola Aliyeva"
    assert getattr(username_fallback, "display_name", None) == "stationery_user"
    assert getattr(generic_fallback, "display_name", None) == "Foydalanuvchi"


async def test_addresses_owner_limit_and_default(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.rate_limit.GENERAL_LIMIT", 100)
    async with make_api_case(test_engine) as case:
        created_ids: list[int] = []
        for index in range(20):
            response = await case.client.post(
                "/api/v1/addresses",
                headers=_auth(case.token),
                json=_address(f"Address {index + 1}"),
            )
            assert response.status_code == 201
            created_ids.append(response.json()["id"])
            assert response.json()["is_default"] is (index == 0)

        listed = await case.client.get("/api/v1/addresses", headers=_auth(case.token))
        assert listed.status_code == 200
        assert len(listed.json()) == 20
        assert sum(address["is_default"] for address in listed.json()) == 1

        twenty_first = await case.client.post(
            "/api/v1/addresses",
            headers=_auth(case.token),
            json=_address("Overflow"),
        )
        assert twenty_first.status_code == 409

        made_default = await case.client.put(
            f"/api/v1/addresses/{created_ids[2]}/default", headers=_auth(case.token)
        )
        assert made_default.status_code == 200
        assert made_default.json()["is_default"] is True

        deleted = await case.client.delete(
            f"/api/v1/addresses/{created_ids[2]}", headers=_auth(case.token)
        )
        assert deleted.status_code == 204
        after_delete = await case.client.get("/api/v1/addresses", headers=_auth(case.token))
        assert after_delete.status_code == 200
        assert len(after_delete.json()) == 19
        assert all(address["is_default"] is False for address in after_delete.json())

        extra_field = await case.client.post(
            "/api/v1/addresses",
            headers=_auth(case.token),
            json={**_address("No default override"), "is_default": True},
        )
        blank_label = await case.client.post(
            "/api/v1/addresses",
            headers=_auth(case.token),
            json=_address("   "),
        )
        assert extra_field.status_code == 422
        assert blank_label.status_code == 422


async def test_address_concurrency_limit_and_order_snapshot(
    test_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.rate_limit.GENERAL_LIMIT", 100)
    async with make_api_case(test_engine) as case:
        first_address_id: int | None = None
        for index in range(19):
            response = await case.client.post(
                "/api/v1/addresses",
                headers=_auth(case.token),
                json=_address(f"Concurrent {index + 1}"),
            )
            assert response.status_code == 201
            if index == 0:
                first_address_id = response.json()["id"]

        concurrent_results = await asyncio.gather(
            case.client.post(
                "/api/v1/addresses",
                headers=_auth(case.token),
                json=_address("Concurrent 20A"),
            ),
            case.client.post(
                "/api/v1/addresses",
                headers=_auth(case.token),
                json=_address("Concurrent 20B"),
            ),
        )
        assert sorted(response.status_code for response in concurrent_results) == [201, 409]
        listed = await case.client.get("/api/v1/addresses", headers=_auth(case.token))
        assert listed.status_code == 200
        assert len(listed.json()) == 20

        async with case.session_maker() as session:
            order = Order(
                order_number=f"KANS-{token_hex(6)}",
                user_id=case.user_id,
                order_type=OrderType.DELIVERY,
                status=OrderStatus.CONFIRMED,
                customer_name="Snapshot Customer",
                customer_phone="+998901234567",
                address="12 Amir Temur ko'chasi",
                address_comment="Door 4",
                subtotal=Decimal("5000"),
                total=Decimal("5000"),
                payment_method=PaymentMethod.CASH,
            )
            session.add(order)
            await session.commit()
            order_id = order.id

        assert first_address_id is not None
        edited = await case.client.patch(
            f"/api/v1/addresses/{first_address_id}",
            headers=_auth(case.token),
            json={"address_text": "New street 22", "address_comment": "Blue gate"},
        )
        assert edited.status_code == 200
        deleted = await case.client.delete(
            f"/api/v1/addresses/{first_address_id}", headers=_auth(case.token)
        )
        assert deleted.status_code == 204

        async with case.session_maker() as session:
            historical_order = await session.get(Order, order_id)
            assert historical_order is not None
            assert historical_order.address == "12 Amir Temur ko'chasi"
            assert historical_order.address_comment == "Door 4"
            await session.delete(historical_order)
            await session.commit()


async def test_foreign_address_is_not_found(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        response = await case.client.post(
            "/api/v1/addresses",
            headers=_auth(case.token),
            json=_address(),
        )
        assert response.status_code == 201
        address_id = response.json()["id"]

        for method in ("patch", "delete", "put"):
            if method == "patch":
                result = await case.client.patch(
                    f"/api/v1/addresses/{address_id}",
                    headers=_auth(case.other_token),
                    json={"label": "Stolen"},
                )
            elif method == "delete":
                result = await case.client.delete(
                    f"/api/v1/addresses/{address_id}",
                    headers=_auth(case.other_token),
                )
            else:
                result = await case.client.put(
                    f"/api/v1/addresses/{address_id}/default",
                    headers=_auth(case.other_token),
                )
            assert result.status_code == 404

        owner_list = await case.client.get("/api/v1/addresses", headers=_auth(case.token))
        assert owner_list.status_code == 200
        assert len(owner_list.json()) == 1
