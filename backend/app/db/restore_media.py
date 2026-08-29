"""Re-download media referenced by the database from Telegram back onto disk.

Product images and receipts live under MEDIA_ROOT. Before that path was backed by a Railway
volume, every deploy replaced the container filesystem and silently wiped them, leaving
`product_images` / `orders` rows pointing at URLs that 404 — the storefront then renders every
product with a broken image. Telegram keeps the original files addressable by `file_id`
indefinitely, so those rows are enough to rebuild the directory from scratch.

Idempotent: a file already present on disk is skipped unless --force is passed.
Usage: python -m app.db.restore_media [--force] [--receipts]
"""

import asyncio
import sys

from sqlalchemy import select

from app.bot.loader import create_bot
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.models.order import Order
from app.db.models.product_image import ProductImage
from app.db.session import async_session_maker

log = get_logger(__name__)


async def restore_product_images(bot, session, *, force: bool) -> tuple[int, int, int]:
    rows = (
        await session.scalars(
            select(ProductImage).order_by(ProductImage.product_id, ProductImage.sort_order)
        )
    ).all()

    restored = skipped = failed = 0
    for image in rows:
        if not image.telegram_file_id:
            # Uploaded through the admin REST endpoint rather than the bot — no file_id to
            # re-fetch, so this one can only be re-uploaded by hand.
            log.warning(
                "restore_skipped_no_file_id", image_id=image.id, product_id=image.product_id
            )
            failed += 1
            continue

        product_dir = settings.media_root_path / "products" / str(image.product_id)
        destination = product_dir / f"{image.sort_order}.jpg"
        if destination.exists() and not force:
            skipped += 1
            continue

        product_dir.mkdir(parents=True, exist_ok=True)
        try:
            await bot.download(image.telegram_file_id, destination=destination)
        except Exception as exc:
            log.error(
                "restore_failed",
                image_id=image.id,
                product_id=image.product_id,
                error=str(exc),
            )
            failed += 1
            continue

        # Keep the stored URL consistent with where the file actually landed.
        expected_url = (
            f"{settings.media_base_url}/products/{image.product_id}/{destination.name}"
        )
        if image.url != expected_url:
            log.info("restore_url_corrected", image_id=image.id, url=expected_url)
            image.url = expected_url
        restored += 1

    return restored, skipped, failed


async def restore_receipts(bot, session, *, force: bool) -> tuple[int, int, int]:
    orders = (
        await session.scalars(
            select(Order).where(Order.receipt_file_id.is_not(None)).order_by(Order.id)
        )
    ).all()

    restored = skipped = failed = 0
    receipts_dir = settings.media_root_path / "receipts"
    for order in orders:
        # The extension is not recorded separately; receipts are stored as .jpg unless the
        # saved URL says otherwise (the bot writes .pdf for document uploads).
        ext = "pdf" if (order.receipt_url or "").endswith(".pdf") else "jpg"
        destination = receipts_dir / f"{order.id}.{ext}"
        if destination.exists() and not force:
            skipped += 1
            continue

        receipts_dir.mkdir(parents=True, exist_ok=True)
        try:
            await bot.download(order.receipt_file_id, destination=destination)
        except Exception as exc:
            log.error("restore_receipt_failed", order_id=order.id, error=str(exc))
            failed += 1
            continue
        restored += 1

    return restored, skipped, failed


async def main() -> None:
    configure_logging()
    force = "--force" in sys.argv
    include_receipts = "--receipts" in sys.argv

    bot = create_bot()
    try:
        async with async_session_maker() as session:
            restored, skipped, failed = await restore_product_images(bot, session, force=force)
            log.info(
                "product_images_restored", restored=restored, skipped=skipped, failed=failed
            )
            print(f"product images: restored={restored} skipped={skipped} failed={failed}")

            if include_receipts:
                r, s, f = await restore_receipts(bot, session, force=force)
                log.info("receipts_restored", restored=r, skipped=s, failed=f)
                print(f"receipts: restored={r} skipped={s} failed={f}")

            await session.commit()
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
