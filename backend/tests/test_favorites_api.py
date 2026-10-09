import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import delete, func, select

from app.bot.handlers.user import catalog as bot_catalog
from app.bot.handlers.user import favorites as bot_favorites
from app.bot.handlers.user.favorites import render_favorites
from app.bot.keyboards.callback_data import FavoriteRemoveCallback, FavoriteToggleCallback
from app.db.models.category import Category
from app.db.models.enums import ProductUnit
from app.db.models.favorite import Favorite
from app.db.models.product import Product
from app.services.after_commit import commit_with_after_commit

from .api_helpers import IMAGE_URL, make_api_case


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _relax_api_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.api.rate_limit.GENERAL_LIMIT", 500)


async def _favorite_count(session_maker, *, user_id: int, product_id: int) -> int:
    async with session_maker() as session:
        return (
            await session.scalar(
                select(func.count()).where(
                    Favorite.user_id == user_id,
                    Favorite.product_id == product_id,
                )
            )
            or 0
        )


async def test_favorite_api_is_owner_scoped_and_idempotent(
    test_engine,
) -> None:
    async with make_api_case(test_engine) as case:
        path = f"/api/v1/favorites/{case.product_id}"
        anonymous = await case.client.get("/api/v1/favorites")
        assert anonymous.status_code == 401

        concurrent_puts = await asyncio.gather(
            *(case.client.put(path, headers=_auth(case.token)) for _ in range(5))
        )
        repeated_put = await case.client.put(path, headers=_auth(case.token))

        assert all(response.status_code in (200, 204) for response in concurrent_puts)
        assert repeated_put.status_code in (200, 204)
        assert (
            await _favorite_count(
                case.session_maker, user_id=case.user_id, product_id=case.product_id
            )
            == 1
        )

        other_user_list = await case.client.get(
            "/api/v1/favorites", headers=_auth(case.other_token)
        )
        other_user_state = await case.client.get(path, headers=_auth(case.other_token))
        other_user_put = await case.client.put(path, headers=_auth(case.other_token))
        other_user_delete = await case.client.delete(path, headers=_auth(case.other_token))
        assert other_user_list.status_code == 200
        assert other_user_list.json()["items"] == []
        assert other_user_state.status_code == 200
        assert other_user_state.json() == {"is_favorite": False}
        assert other_user_put.status_code in (200, 204)
        assert other_user_delete.status_code == 204
        assert (
            await _favorite_count(
                case.session_maker, user_id=case.user_id, product_id=case.product_id
            )
            == 1
        )

        concurrent_deletes = await asyncio.gather(
            *(case.client.delete(path, headers=_auth(case.token)) for _ in range(5))
        )
        assert all(response.status_code == 204 for response in concurrent_deletes)
        first_delete = await case.client.delete(path, headers=_auth(case.token))
        repeated_delete = await case.client.delete(path, headers=_auth(case.token))
        assert first_delete.status_code == 204
        assert repeated_delete.status_code == 204
        assert (
            await _favorite_count(
                case.session_maker, user_id=case.user_id, product_id=case.product_id
            )
            == 0
        )

        inactive_put = await case.client.put(path, headers=_auth(case.token))
        assert inactive_put.status_code in (200, 204)
        async with case.session_maker() as session:
            product = await session.get(Product, case.product_id)
            assert product is not None
            product.is_active = False
            await session.commit()
        rejected = await case.client.put(path, headers=_auth(case.token))
        assert rejected.status_code == 404
        assert "items" not in rejected.json()

        async with case.session_maker() as session:
            product = await session.get(Product, case.product_id)
            assert product is not None
            category = await session.get(Category, product.category_id)
            assert category is not None
            product.is_active = True
            category.is_active = False
            await session.commit()
        rejected_for_inactive_ancestor = await case.client.put(path, headers=_auth(case.token))
        assert rejected_for_inactive_ancestor.status_code == 404
        hidden_from_list = await case.client.get(
            "/api/v1/favorites", headers=_auth(case.token)
        )
        assert hidden_from_list.status_code == 200
        assert hidden_from_list.json()["items"] == []
        assert hidden_from_list.json()["total"] == 0


async def test_favorites_page_eager_loads_product_images(test_engine) -> None:
    async with make_api_case(test_engine) as case:
        extra_ids: list[int] = []
        try:
            async with case.session_maker() as session:
                base_product = await session.get(Product, case.product_id)
                assert base_product is not None
                extras = [
                    Product(
                        category_id=base_product.category_id,
                        name_uz=f"Test product {index}",
                        name_ru=f"Test product {index}",
                        sku=f"FAV-PAGE-{case.product_id}-{index}",
                        price=Decimal("5000"),
                        stock_qty=10,
                        unit=ProductUnit.DONA,
                    )
                    for index in range(24)
                ]
                session.add_all(extras)
                await session.flush()
                extra_ids = [product.id for product in extras]
                session.add_all(
                    Favorite(user_id=case.user_id, product_id=product_id)
                    for product_id in extra_ids
                )
                session.add(Favorite(user_id=case.user_id, product_id=case.product_id))
                await session.commit()

            page = await case.client.get("/api/v1/favorites", headers=_auth(case.token))

            assert page.status_code == 200
            payload = page.json()
            assert payload["total"] == 25
            assert payload["page"] == 1
            assert payload["limit"] == 24
            assert len(payload["items"]) == 24
            product = next(item for item in payload["items"] if item["id"] == case.product_id)
            assert product["images"][0]["url"] == IMAGE_URL

            second_page = await case.client.get(
                "/api/v1/favorites?page=2&limit=24", headers=_auth(case.token)
            )
            assert second_page.status_code == 200
            assert second_page.json()["total"] == 25
            assert len(second_page.json()["items"]) == 1
        finally:
            if extra_ids:
                async with case.session_maker() as session:
                    await session.execute(
                        delete(Favorite).where(Favorite.product_id.in_(extra_ids))
                    )
                    await session.execute(delete(Product).where(Product.id.in_(extra_ids)))
                    await session.commit()


async def test_favorite_state_is_separate_from_public_catalog(test_engine) -> None:
    async with make_api_case(test_engine) as case:
        product = await case.client.get(f"/api/v1/catalog/products/{case.product_id}")
        state_before = await case.client.get(
            f"/api/v1/favorites/{case.product_id}", headers=_auth(case.token)
        )
        assert product.status_code == 200
        assert "is_favorite" not in product.json()
        assert state_before.status_code == 200
        assert state_before.json() == {"is_favorite": False}

        added = await case.client.put(
            f"/api/v1/favorites/{case.product_id}", headers=_auth(case.token)
        )
        state_after = await case.client.get(
            f"/api/v1/favorites/{case.product_id}", headers=_auth(case.token)
        )
        public_again = await case.client.get(f"/api/v1/catalog/products/{case.product_id}")
        assert added.status_code in (200, 204)
        assert state_after.status_code == 200
        assert state_after.json() == {"is_favorite": True}
        assert public_again.status_code == 200
        assert "is_favorite" not in public_again.json()


async def test_bot_and_web_use_same_favorite_service(
    test_engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with make_api_case(test_engine) as case:
        path = f"/api/v1/favorites/{case.product_id}"
        web_add = await case.client.put(path, headers=_auth(case.token))
        assert web_add.status_code in (200, 204)

        bot_messages: list[str] = []

        async def send(text: str, reply_markup=None) -> object:
            bot_messages.append(text)
            return object()

        async with case.session_maker() as session:
            await render_favorites(
                send,
                session,
                case.user_id,
                lang="uz",
                translator=lambda key, **_: key,
            )
        assert any("Test pen" in message for message in bot_messages)

        async def editable_message(callback, translator):
            return SimpleNamespace(edit_text=AsyncMock())

        monkeypatch.setattr(bot_catalog, "require_message", editable_message)
        monkeypatch.setattr(bot_catalog, "send_product_detail", AsyncMock())
        callback = SimpleNamespace(answer=AsyncMock())
        callback_data = FavoriteToggleCallback(
            product_id=case.product_id, origin="category", ref_id=1, page=1
        )
        bot_user = SimpleNamespace(id=case.user_id)

        async with case.session_maker() as session:
            await bot_catalog.on_favorite_toggle(
                callback,
                callback_data,
                session,
                bot_user,
                "uz",
                lambda key, **_: key,
            )
            await commit_with_after_commit(session)
        web_list_after_bot_remove = await case.client.get(
            "/api/v1/favorites", headers=_auth(case.token)
        )
        assert web_list_after_bot_remove.status_code == 200
        assert web_list_after_bot_remove.json()["items"] == []

        async with case.session_maker() as session:
            await bot_catalog.on_favorite_toggle(
                callback,
                callback_data,
                session,
                bot_user,
                "uz",
                lambda key, **_: key,
            )
            await commit_with_after_commit(session)
        web_list_after_bot_add = await case.client.get(
            "/api/v1/favorites", headers=_auth(case.token)
        )
        assert web_list_after_bot_add.status_code == 200
        assert [item["id"] for item in web_list_after_bot_add.json()["items"]] == [
            case.product_id
        ]

        monkeypatch.setattr(bot_favorites, "require_message", editable_message)
        remove_callback = SimpleNamespace(answer=AsyncMock())
        async with case.session_maker() as session:
            await bot_favorites.on_favorite_remove(
                remove_callback,
                FavoriteRemoveCallback(product_id=case.product_id),
                session,
                bot_user,
                "uz",
                lambda key, **_: key,
            )
            await commit_with_after_commit(session)
        web_list_after_favorite_remove = await case.client.get(
            "/api/v1/favorites", headers=_auth(case.token)
        )
        assert web_list_after_favorite_remove.status_code == 200
        assert web_list_after_favorite_remove.json()["items"] == []
