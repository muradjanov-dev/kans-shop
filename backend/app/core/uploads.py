import warnings
from collections.abc import Buffer
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.core.exceptions import InvalidFileError

MAX_RECEIPT_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_RECEIPT_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}

MIME_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "application/pdf": "pdf",
}

_PIL_FORMATS = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}


class BoundedBytesIO(BytesIO):
    """A BytesIO that refuses writes once the bounded upload size is exceeded."""

    def __init__(self, limit: int = MAX_RECEIPT_SIZE_BYTES) -> None:
        super().__init__()
        self.limit = limit
        self._bytes_written = 0

    def write(self, data: Buffer, /) -> int:
        size = memoryview(data).nbytes
        if self._bytes_written + size > self.limit:
            raise InvalidFileError("File too large", details={"max_bytes": self.limit})
        written = super().write(data)
        self._bytes_written += written
        return written


def validate_receipt_content(content: bytes, declared_content_type: str) -> None:
    """Validate receipt size, declared MIME type, and the bounded file signature."""
    if len(content) > MAX_RECEIPT_SIZE_BYTES:
        raise InvalidFileError("File too large", details={"max_bytes": MAX_RECEIPT_SIZE_BYTES})
    if declared_content_type not in ALLOWED_RECEIPT_MIME_TYPES:
        raise InvalidFileError(
            "Unsupported file type", details={"content_type": declared_content_type}
        )
    if declared_content_type == "application/pdf":
        if not content.startswith(b"%PDF-") or not content[-2048:].rstrip().endswith(b"%%EOF"):
            raise InvalidFileError("Invalid PDF receipt")
        return

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != _PIL_FORMATS[declared_content_type]:
                    raise InvalidFileError(
                        "Receipt content does not match its declared type",
                        details={"content_type": declared_content_type},
                    )
                image.verify()
    except InvalidFileError:
        raise
    except (
        OSError,
        ValueError,
        SyntaxError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidFileError(
            "Invalid image receipt", details={"content_type": declared_content_type}
        ) from exc
