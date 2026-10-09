from __future__ import annotations

import os
import warnings
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image

from app.core.config import settings
from app.core.exceptions import InvalidFileError

MAX_BROADCAST_PHOTO_BYTES = 5 * 1024 * 1024
_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", "jpg"),
    "image/png": ("PNG", "png"),
    "image/webp": ("WEBP", "webp"),
}
SUPPORTED_BROADCAST_IMAGE_TYPES = frozenset(_IMAGE_TYPES)


def _validated_image(content: bytes, content_type: str) -> tuple[str, str]:
    expected = _IMAGE_TYPES.get(content_type)
    if expected is None:
        raise InvalidFileError("Unsupported broadcast image type")
    if not content or len(content) > MAX_BROADCAST_PHOTO_BYTES:
        raise InvalidFileError(
            "Broadcast image is empty or too large",
            details={"max_bytes": MAX_BROADCAST_PHOTO_BYTES},
        )
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                actual_format = image.format
                image.verify()
            with Image.open(BytesIO(content)) as image:
                image.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning, OSError, ValueError):
        raise InvalidFileError("Broadcast image content is invalid") from None
    if actual_format != expected[0]:
        raise InvalidFileError("Broadcast image content does not match its media type")
    return expected


def _broadcast_directory() -> Path:
    private_root = settings.private_media_root_path.resolve()
    directory = private_root / "broadcasts"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory = directory.resolve()
    try:
        directory.relative_to(private_root)
    except ValueError:
        raise RuntimeError(
            "Broadcast media directory must remain under private media root"
        ) from None
    os.chmod(directory, 0o700)
    return directory


def store_broadcast_photo(*, content: bytes, content_type: str) -> str:
    """Store a bounded campaign photo outside public media and return its opaque UUID key."""
    _validated_image(content, content_type)
    directory = _broadcast_directory()
    storage_key = str(uuid4())
    path = directory / storage_key
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)
    return storage_key


def read_broadcast_photo(storage_key: str) -> tuple[bytes, str]:
    """Resolve a server-generated UUID key and return bytes plus a safe Telegram filename."""
    try:
        parsed = UUID(storage_key)
    except (AttributeError, TypeError, ValueError):
        raise InvalidFileError("Invalid broadcast photo key") from None
    canonical_key = str(parsed)
    private_root = settings.private_media_root_path.resolve()
    path = (_broadcast_directory() / canonical_key).resolve()
    try:
        path.relative_to(private_root)
    except ValueError:
        raise InvalidFileError("Invalid broadcast photo key") from None
    content = path.read_bytes()
    _image_format, extension = _validated_image(content, _content_type_for_bytes(content))
    return content, f"broadcast.{extension}"


def _content_type_for_bytes(content: bytes) -> str:
    try:
        with Image.open(BytesIO(content)) as image:
            image_format = image.format
    except (Image.DecompressionBombError, OSError, ValueError):
        raise InvalidFileError("Stored broadcast image content is invalid") from None
    for content_type, (expected_format, _extension) in _IMAGE_TYPES.items():
        if image_format == expected_format:
            return content_type
    raise InvalidFileError("Stored broadcast image type is unsupported")
