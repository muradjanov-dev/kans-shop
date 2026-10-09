from aiogram import Bot

from app.core.exceptions import InvalidFileError
from app.core.uploads import (
    MAX_RECEIPT_SIZE_BYTES,
    BoundedBytesIO,
    validate_receipt_content,
)


async def download_telegram_receipt(
    bot: Bot, file_id: str, declared_content_type: str
) -> bytes:
    telegram_file = await bot.get_file(file_id)
    if (
        telegram_file.file_size is not None
        and telegram_file.file_size > MAX_RECEIPT_SIZE_BYTES
    ):
        raise InvalidFileError("File too large", details={"max_bytes": MAX_RECEIPT_SIZE_BYTES})
    if not telegram_file.file_path:
        raise InvalidFileError("Telegram receipt file has no path")

    destination = BoundedBytesIO()
    await bot.download_file(telegram_file.file_path, destination=destination)
    content = destination.getvalue()
    validate_receipt_content(content, declared_content_type)
    return content
