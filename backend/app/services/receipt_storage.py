import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.core.uploads import MIME_EXTENSIONS

_STORAGE_KEY = re.compile(
    r"^(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
    r"\.(?P<extension>jpg|png|webp|pdf)$"
)


@dataclass(frozen=True)
class StoredReceipt:
    storage_key: str
    content_type: str
    size_bytes: int
    sha256: str


class PrivateReceiptStorage:
    """Store immutable receipt objects below a private, non-static media root."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, content: bytes, content_type: str) -> StoredReceipt:
        extension = MIME_EXTENSIONS.get(content_type)
        if extension is None:
            raise ValueError("Unsupported receipt content type")

        storage_key = f"{uuid4()}.{extension}"
        destination = self.root / storage_key
        try:
            with destination.open("xb") as receipt_file:
                receipt_file.write(content)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

        return StoredReceipt(
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )

    def resolve(self, storage_key: str) -> Path:
        """Resolve only generated UUID object names, rejecting encoded/traversal paths."""
        if not isinstance(storage_key, str) or not _STORAGE_KEY.fullmatch(storage_key):
            raise ValueError("Invalid private receipt storage key")

        candidate = self.root / storage_key
        if candidate.is_symlink():
            raise ValueError("Private receipt storage key cannot be a symlink")
        resolved = candidate.resolve(strict=True)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Receipt path is outside private storage") from exc
        if not resolved.is_file():
            raise ValueError("Receipt object is not a file")
        return resolved
