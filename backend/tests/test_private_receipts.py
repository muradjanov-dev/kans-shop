from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from secrets import token_hex, token_urlsafe
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.schemas.order import OrderOut
from app.core.config import settings
from app.core.exceptions import (
    AdminSessionRequiredError,
    ForbiddenError,
    InvalidFileError,
    OrderAlreadyProcessedError,
)
from app.core.uploads import MAX_RECEIPT_SIZE_BYTES, validate_receipt_content
from app.db.models.admin import Admin
from app.db.models.admin_session import AdminSession
from app.db.models.enums import (
    AdminRole,
    OrderStatus,
    OrderType,
    PaymentMethod,
    PaymentStatus,
)
from app.db.models.order import Order
from app.db.models.user import User
from app.db.repositories import order_repository, setting_repository
from app.services.receipt_service import attach_card_transfer_receipt, open_order_receipt
from app.services.receipt_storage import PrivateReceiptStorage

from .api_helpers import make_api_case


def _image_bytes(image_format: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(34, 120, 210)).save(buffer, format=image_format)
    return buffer.getvalue()


def _pdf_bytes(size: int | None = None) -> bytes:
    content = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF"
    if size is not None:
        ending = b"\n%%EOF"
        content = b"%PDF-1.7\n" + b" " * (size - len(b"%PDF-1.7\n") - len(ending)) + ending
    return content


async def _new_order(
    session: AsyncSession,
    user_id: int,
    *,
    payment_method: PaymentMethod = PaymentMethod.CARD_TRANSFER,
    payment_status: PaymentStatus = PaymentStatus.PENDING,
    status: OrderStatus = OrderStatus.NEW,
    payment_instructions: dict | None = None,
) -> Order:
    order = Order(
        order_number=f"KANS-{token_hex(6).upper()}",
        user_id=user_id,
        order_type=OrderType.PICKUP,
        status=status,
        customer_name="Receipt Test",
        customer_phone="+998901234567",
        subtotal=Decimal("10000"),
        delivery_fee=Decimal("0"),
        discount=Decimal("0"),
        total=Decimal("10000"),
        payment_method=payment_method,
        payment_status=payment_status,
        payment_instructions=payment_instructions,
        receipt_version=0,
        admin_message_ids={},
        source="webapp",
    )
    session.add(order)
    await session.flush()
    return order


async def test_receipt_owner_method_state_guards(
    db_session: AsyncSession, user: User, tmp_path
) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    content = _image_bytes("PNG")
    card_order = await _new_order(db_session, user.id)
    cash_order = await _new_order(db_session, user.id, payment_method=PaymentMethod.CASH)
    paid_order = await _new_order(db_session, user.id, payment_status=PaymentStatus.PAID)
    completed_order = await _new_order(db_session, user.id, status=OrderStatus.COMPLETED)
    cancelled_order = await _new_order(db_session, user.id, status=OrderStatus.CANCELLED)

    with pytest.raises(ForbiddenError):
        await attach_card_transfer_receipt(
            db_session,
            storage,
            order_id=card_order.id,
            owner_user_id=user.id + 1,
            content=content,
            declared_content_type="image/png",
        )
    with pytest.raises(ForbiddenError):
        await attach_card_transfer_receipt(
            db_session,
            storage,
            order_id=cash_order.id,
            owner_user_id=user.id,
            content=content,
            declared_content_type="image/png",
        )
    for order in (paid_order, completed_order, cancelled_order):
        with pytest.raises(OrderAlreadyProcessedError):
            await attach_card_transfer_receipt(
                db_session,
                storage,
                order_id=order.id,
                owner_user_id=user.id,
                content=content,
                declared_content_type="image/png",
            )

    assert list((tmp_path / "private").glob("*")) == []
    assert card_order.receipt_version == 0


async def test_receipt_content_and_size(
    db_session: AsyncSession, user: User, tmp_path
) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    supported = (
        ("image/jpeg", _image_bytes("JPEG")),
        ("image/png", _image_bytes("PNG")),
        ("image/webp", _image_bytes("WEBP")),
        ("application/pdf", _pdf_bytes()),
    )
    for content_type, content in supported:
        validate_receipt_content(content, content_type)
    validate_receipt_content(_pdf_bytes(MAX_RECEIPT_SIZE_BYTES), "application/pdf")

    png = _image_bytes("PNG")
    exact_limit_png = png + b" " * (MAX_RECEIPT_SIZE_BYTES - len(png))
    order = await _new_order(db_session, user.id)
    saved = await attach_card_transfer_receipt(
        db_session,
        storage,
        order_id=order.id,
        owner_user_id=user.id,
        content=exact_limit_png,
        declared_content_type="image/png",
    )
    assert saved.payment_status == PaymentStatus.RECEIPT_UPLOADED
    assert saved.receipt_version == 1

    with pytest.raises(InvalidFileError):
        validate_receipt_content(exact_limit_png + b"x", "image/png")
    with pytest.raises(InvalidFileError):
        validate_receipt_content(_pdf_bytes(MAX_RECEIPT_SIZE_BYTES + 1), "application/pdf")
    with pytest.raises(InvalidFileError):
        validate_receipt_content(_image_bytes("JPEG"), "image/png")
    with pytest.raises(InvalidFileError):
        validate_receipt_content(b"%PDF-1.7\nmissing eof", "application/pdf")


async def test_inactive_admin_cannot_read_receipt(
    db_session: AsyncSession, user: User, admin: Admin, tmp_path
) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    order = await _new_order(db_session, user.id)
    order = await attach_card_transfer_receipt(
        db_session,
        storage,
        order_id=order.id,
        owner_user_id=user.id,
        content=_image_bytes("PNG"),
        declared_content_type="image/png",
    )
    admin.is_active = False

    with pytest.raises(AdminSessionRequiredError):
        await open_order_receipt(
            db_session,
            storage,
            order_id=order.id,
            user_id=0,
            admin_id=admin.id,
        )


async def test_receipt_replacement(db_session: AsyncSession, user: User, tmp_path) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    order = await _new_order(db_session, user.id)
    first_content = _image_bytes("PNG")
    first = await attach_card_transfer_receipt(
        db_session,
        storage,
        order_id=order.id,
        owner_user_id=user.id,
        content=first_content,
        declared_content_type="image/png",
    )
    first_key = first.receipt_storage_key
    assert first_key is not None
    first_path = storage.resolve(first_key)

    second_content = _image_bytes("WEBP")
    second = await attach_card_transfer_receipt(
        db_session,
        storage,
        order_id=order.id,
        owner_user_id=user.id,
        content=second_content,
        declared_content_type="image/webp",
    )

    assert second.receipt_storage_key != first_key
    assert second.receipt_version == 2
    assert second.payment_status == PaymentStatus.RECEIPT_UPLOADED
    assert first_path.read_bytes() == first_content
    assert storage.resolve(second.receipt_storage_key).read_bytes() == second_content


async def test_legacy_order_has_no_guessed_payment_instructions(
    db_session: AsyncSession, user: User
) -> None:
    legacy_order = await _new_order(db_session, user.id, payment_instructions=None)
    legacy_order = await order_repository.get_by_id(db_session, legacy_order.id)
    assert legacy_order is not None

    output = OrderOut.model_validate(legacy_order)

    assert output.payment_instructions is None
    assert output.has_receipt is False
    assert output.model_dump()["payment_instructions"] is None


async def test_receipt_private_http_read(test_engine: AsyncEngine, tmp_path) -> None:
    async with make_api_case(test_engine, base_url="https://testserver") as case:
        order_id: int | None = None
        admin_id: int | None = None
        try:
            async with case.session_maker() as session:
                order = await _new_order(
                    session,
                    case.user_id,
                    payment_instructions={"card_number": "synthetic-snapshot"},
                )
                admin = Admin(
                    telegram_id=9_000_000_000_000_000 + int(token_hex(4), 16),
                    full_name="Receipt Admin",
                    role=AdminRole.SUPERADMIN,
                )
                session.add(admin)
                await session.flush()
                raw_cookie = token_urlsafe(32)
                now = datetime.now(UTC)
                session.add(
                    AdminSession(
                        admin_id=admin.id,
                        token_hash=sha256(raw_cookie.encode("ascii")).hexdigest(),
                        csrf_token=token_urlsafe(96),
                        auth_epoch=admin.auth_epoch,
                        idle_expires_at=now + timedelta(hours=1),
                        absolute_expires_at=now + timedelta(days=1),
                    )
                )
                await session.commit()
                order_id = order.id
                admin_id = admin.id

            content = _image_bytes("PNG")
            upload = await case.client.post(
                f"/api/v1/orders/{order_id}/receipt",
                headers={"Authorization": f"Bearer {case.token}"},
                files={"file": ("receipt.png", content, "image/png")},
            )
            assert upload.status_code == 200
            uploaded = upload.json()
            assert uploaded["payment_status"] == "receipt_uploaded"
            assert uploaded["receipt_version"] == 1
            assert uploaded["has_receipt"] is True
            assert uploaded["receipt_url"] is None
            assert uploaded["payment_instructions"] == {"card_number": "synthetic-snapshot"}

            owner_read = await case.client.get(
                f"/api/v1/orders/{order_id}/receipt",
                headers={"Authorization": f"Bearer {case.token}"},
            )
            assert owner_read.status_code == 200
            assert owner_read.content == content
            assert owner_read.headers["cache-control"] == "private, no-store"
            assert owner_read.headers["x-content-type-options"] == "nosniff"
            assert owner_read.headers["content-type"] == "image/png"

            other_read = await case.client.get(
                f"/api/v1/orders/{order_id}/receipt",
                headers={"Authorization": f"Bearer {case.other_token}"},
            )
            assert other_read.status_code == 403

            other_with_admin_cookie = await case.client.get(
                f"/api/v1/orders/{order_id}/receipt",
                headers={
                    "Authorization": f"Bearer {case.other_token}",
                    "Cookie": f"__Host-kans-admin={raw_cookie}",
                },
            )
            assert other_with_admin_cookie.status_code == 403

            admin_read = await case.client.get(
                f"/api/v1/orders/{order_id}/receipt",
                headers={"Cookie": f"__Host-kans-admin={raw_cookie}"},
            )
            assert admin_read.status_code == 200
            assert admin_read.content == content
            assert admin_read.headers["cache-control"] == "private, no-store"

            cookie_only_upload = await case.client.post(
                f"/api/v1/orders/{order_id}/receipt",
                headers={"Cookie": f"__Host-kans-admin={raw_cookie}"},
                files={"file": ("receipt.png", content, "image/png")},
            )
            assert cookie_only_upload.status_code == 401

            other_with_admin_cookie_upload = await case.client.post(
                f"/api/v1/orders/{order_id}/receipt",
                headers={
                    "Authorization": f"Bearer {case.other_token}",
                    "Cookie": f"__Host-kans-admin={raw_cookie}",
                },
                files={"file": ("receipt.png", content, "image/png")},
            )
            assert other_with_admin_cookie_upload.status_code == 403

            async with case.session_maker() as session:
                stored = await session.get(Order, order_id)
                assert stored is not None
                assert stored.payment_status == PaymentStatus.RECEIPT_UPLOADED
                assert stored.receipt_storage_key is not None
                assert stored.receipt_file_id is None
                assert stored.receipt_url is None
                private_path = settings.private_media_root_path / stored.receipt_storage_key
                assert private_path.read_bytes() == content
        finally:
            if order_id is not None:
                async with case.session_maker() as session:
                    stored = await session.get(Order, order_id)
                    if stored is not None and stored.receipt_storage_key:
                        (settings.private_media_root_path / stored.receipt_storage_key).unlink(
                            missing_ok=True
                        )
                    await session.execute(delete(Order).where(Order.id == order_id))
                    if admin_id is not None:
                        await session.execute(delete(Admin).where(Admin.id == admin_id))
                    await session.commit()


async def test_public_receipt_path_denied(test_engine: AsyncEngine) -> None:
    async with make_api_case(test_engine) as case:
        public_root = settings.media_root_path
        receipt_dir = public_root / "receipts"
        products_dir = public_root / "products"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        products_dir.mkdir(parents=True, exist_ok=True)
        token = token_hex(8)
        receipt_file = receipt_dir / f"{token}.png"
        product_file = products_dir / f"{token}.txt"
        receipt_file.write_bytes(b"private test receipt")
        product_file.write_bytes(b"public product image placeholder")
        try:
            for path in (
                f"/media/receipts/{receipt_file.name}",
                "/media/receipts",
                "/media/receipts/",
                f"/media/%72eceipts/{receipt_file.name}",
                f"/media/products/%2e%2e/receipts/{receipt_file.name}",
                f"/media/products/%252e%252e/receipts/{receipt_file.name}",
                f"/media/products%2f..%2freceipts/{receipt_file.name}",
            ):
                response = await case.client.get(path)
                assert response.status_code == 404, path

            product_response = await case.client.get(f"/media/products/{product_file.name}")
            assert product_response.status_code == 200
            assert product_response.content == product_file.read_bytes()
        finally:
            receipt_file.unlink(missing_ok=True)
            product_file.unlink(missing_ok=True)


async def test_web_receipt_visible_to_bot_admin(
    db_session: AsyncSession, user: User, admin: Admin, tmp_path
) -> None:
    from app.bot.handlers.admin.orders import send_receipt_to_admin

    class FakeBot:
        def __init__(self) -> None:
            self.photo = None
            self.document = None

        async def send_photo(self, chat_id: int, photo) -> None:
            self.photo = (chat_id, photo)

        async def send_document(self, chat_id: int, document) -> None:
            self.document = (chat_id, document)

    storage = PrivateReceiptStorage(tmp_path / "private")
    order = await _new_order(db_session, user.id)
    content = _image_bytes("WEBP")
    order = await attach_card_transfer_receipt(
        db_session,
        storage,
        order_id=order.id,
        owner_user_id=user.id,
        content=content,
        declared_content_type="image/webp",
    )
    bot = FakeBot()

    await send_receipt_to_admin(
        bot,
        db_session,
        order,
        admin_id=admin.id,
        chat_id=admin.telegram_id,
        storage=storage,
    )

    assert bot.document is not None
    chat_id, upload = bot.document
    assert chat_id == admin.telegram_id
    assert Path(upload.path).read_bytes() == content


async def test_telegram_webp_receipt_is_sent_as_document(
    db_session: AsyncSession, user: User, admin: Admin, tmp_path
) -> None:
    from app.bot.handlers.admin.orders import send_receipt_to_admin

    class FakeBot:
        def __init__(self) -> None:
            self.photo = None
            self.document = None

        async def send_photo(self, chat_id: int, photo) -> None:
            self.photo = (chat_id, photo)

        async def send_document(self, chat_id: int, document) -> None:
            self.document = (chat_id, document)

    order = await _new_order(db_session, user.id)
    order.receipt_content_type = "image/webp"
    order.receipt_file_id = "synthetic-webp-file-id"
    order.payment_status = PaymentStatus.RECEIPT_UPLOADED
    bot = FakeBot()

    await send_receipt_to_admin(
        bot,
        db_session,
        order,
        admin_id=admin.id,
        chat_id=admin.telegram_id,
        storage=PrivateReceiptStorage(tmp_path / "private"),
    )

    assert bot.photo is None
    assert bot.document == (admin.telegram_id, "synthetic-webp-file-id")


async def test_receipt_storage_rejects_traversal(tmp_path) -> None:
    storage = PrivateReceiptStorage(tmp_path / "private")
    for key in (
        "../receipt.png",
        "/tmp/receipt.png",
        "folder/receipt.png",
        "%2e%2e/receipt.png",
        "%252e%252e%252freceipt.png",
        "products/../receipt.png",
        "00000000-0000-4000-8000-000000000001.png/../../secret",
    ):
        with pytest.raises(ValueError):
            storage.resolve(key)


async def test_bot_download_is_bounded_by_advertised_and_actual_size() -> None:
    from app.bot.utils.receipt_upload import download_telegram_receipt

    class FakeBot:
        def __init__(self, content: bytes, advertised_size: int) -> None:
            self.content = content
            self.advertised_size = advertised_size
            self.downloaded = False

        async def get_file(self, file_id: str):
            return SimpleNamespace(file_size=self.advertised_size, file_path="test/path")

        async def download_file(self, file_path: str, *, destination) -> None:
            self.downloaded = True
            for offset in range(0, len(self.content), 64 * 1024):
                destination.write(self.content[offset : offset + 64 * 1024])

    advertised_oversize = FakeBot(_image_bytes("PNG"), MAX_RECEIPT_SIZE_BYTES + 1)
    with pytest.raises(InvalidFileError):
        await download_telegram_receipt(advertised_oversize, "id", "image/png")
    assert not advertised_oversize.downloaded

    actual_oversize_content = _image_bytes("PNG")
    actual_oversize_content += b" " * (
        MAX_RECEIPT_SIZE_BYTES + 1 - len(actual_oversize_content)
    )
    actual_oversize = FakeBot(actual_oversize_content, MAX_RECEIPT_SIZE_BYTES)
    with pytest.raises(InvalidFileError):
        await download_telegram_receipt(actual_oversize, "id", "image/png")


async def test_receipt_redirect_rechecks_fsm_owner_before_storing(
    db_session: AsyncSession, user: User, tmp_path
) -> None:
    from app.bot.handlers.user.receipt_redirect import _finish

    content = _image_bytes("PNG")
    order = await _new_order(db_session, user.id)
    stranger = User(telegram_id=111112, first_name="Different User", language="uz")
    db_session.add(stranger)
    await db_session.flush()

    class FakeState:
        cleared = False

        async def get_data(self):
            return {"order_id": order.id}

        async def clear(self):
            self.cleared = True

    class FakeBot:
        async def get_file(self, file_id: str):
            return SimpleNamespace(file_size=len(content), file_path="test/path")

        async def download_file(self, file_path: str, *, destination) -> None:
            destination.write(content)

    class FakeMessage:
        answers: list[str]

        def __init__(self) -> None:
            self.answers = []

        async def answer(self, value: str) -> None:
            self.answers.append(value)

    state = FakeState()
    message = FakeMessage()
    storage_root = tmp_path / "private"

    await _finish(
        message,
        db_session,
        FakeBot(),
        state,
        stranger,
        file_id="synthetic-telegram-file",
        declared_content_type="image/png",
        translator=lambda key, **kwargs: key,
    )

    assert state.cleared is True
    assert message.answers == ["checkout.invalid_receipt"]
    assert order.receipt_storage_key is None
    assert order.receipt_version == 0
    assert list(storage_root.glob("*")) == []


async def test_receipt_deeplink_uses_saved_card_and_allows_private_replacement(
    db_session: AsyncSession, user: User, tmp_path
) -> None:
    from app.bot.handlers.user.start import _handle_receipt_redirect
    from app.bot.states.receipt_redirect import ReceiptRedirectStates
    from app.bot.utils.i18n import translate
    from app.services.receipt_service import attach_card_transfer_receipt

    class FakeState:
        def __init__(self) -> None:
            self.data = {}
            self.state = None

        async def set_state(self, state) -> None:
            self.state = state

        async def update_data(self, **data) -> None:
            self.data.update(data)

    class FakeMessage:
        def __init__(self) -> None:
            self.answers = []

        async def answer(self, value: str) -> None:
            self.answers.append(value)

    order = await _new_order(
        db_session,
        user.id,
        payment_instructions={"card_number": "old-card-8600", "card_holder": "Old Shop"},
    )
    await attach_card_transfer_receipt(
        db_session,
        PrivateReceiptStorage(tmp_path / "private"),
        order_id=order.id,
        owner_user_id=user.id,
        content=_image_bytes("PNG"),
        declared_content_type="image/png",
    )
    await setting_repository.set_value(db_session, "card_number", "new-card-9900")
    await setting_repository.set_value(db_session, "card_holder", "New Shop")
    message = FakeMessage()
    state = FakeState()

    await _handle_receipt_redirect(
        message,
        db_session,
        user_id=user.id,
        translator=lambda key, **kwargs: translate("uz", key, **kwargs),
        state=state,
        order_id=order.id,
    )

    assert state.state == ReceiptRedirectStates.uploading
    assert state.data == {"order_id": order.id}
    assert len(message.answers) == 1
    assert "old-card-8600" in message.answers[0]
    assert "Old Shop" in message.answers[0]
    assert "new-card-9900" not in message.answers[0]


async def test_receipt_deeplink_legacy_order_requires_support_instead_of_current_card(
    db_session: AsyncSession, user: User
) -> None:
    from app.bot.handlers.user.start import _handle_receipt_redirect
    from app.bot.utils.i18n import translate

    class FakeState:
        state = None

        async def set_state(self, state) -> None:
            self.state = state

        async def update_data(self, **data) -> None:
            raise AssertionError("Legacy orders must not enter receipt upload state")

    class FakeMessage:
        def __init__(self) -> None:
            self.answers = []

        async def answer(self, value: str) -> None:
            self.answers.append(value)

    order = await _new_order(db_session, user.id, payment_instructions=None)
    await setting_repository.set_value(db_session, "card_number", "current-card-9900")
    await setting_repository.set_value(db_session, "card_holder", "Current Shop")
    message = FakeMessage()
    state = FakeState()

    await _handle_receipt_redirect(
        message,
        db_session,
        user_id=user.id,
        translator=lambda key, **kwargs: translate("uz", key, **kwargs),
        state=state,
        order_id=order.id,
    )

    assert state.state is None
    assert len(message.answers) == 1
    assert "yordam" in message.answers[0].casefold()
    assert "current-card-9900" not in message.answers[0]
