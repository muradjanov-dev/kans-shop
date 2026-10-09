"""Move recognized legacy public receipts into the persistent private media volume.

The manifest contains paths, hashes, order IDs, and generated private keys only. It never
contains receipt bytes, Telegram file IDs, or raw receipt URLs. Public files are removed only
after both the private object and committed database reference have been verified.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import configure_logging
from app.db.models.enums import PaymentStatus
from app.db.models.order import Order
from app.db.session import async_session_maker

FORMAT_VERSION = 1
_LEGACY_URL = re.compile(
    r"^(?:/media)?/receipts/(?P<order_id>[1-9][0-9]*)\.(?P<ext>jpg|png|webp|pdf)$"
)
_STORAGE_KEY = re.compile(
    r"^(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})"
    r"\.(?P<ext>jpg|png|webp|pdf)$"
)
_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
}


class CutoverError(RuntimeError):
    """A cutover input or invariant failed; public files remain unless already verified."""


def _roots(public_root: Path, private_root: Path) -> tuple[Path, Path]:
    public_input = public_root.expanduser()
    private_input = private_root.expanduser()
    if public_input.is_symlink():
        raise ValueError("MEDIA_ROOT cannot be a symlink")
    if private_input.is_symlink():
        raise ValueError("PRIVATE_MEDIA_ROOT cannot be a symlink")
    public = public_input.resolve()
    private = private_input.resolve()
    if private == public or public in private.parents:
        raise ValueError("PRIVATE_MEDIA_ROOT must be outside MEDIA_ROOT")
    if not public.is_dir():
        raise ValueError("MEDIA_ROOT must be an existing directory")
    if private.exists() and not private.is_dir():
        raise ValueError("PRIVATE_MEDIA_ROOT must be a directory")
    return public, private


def _manifest_path_outside_public(path: Path, public_root: Path) -> Path:
    if path.expanduser().is_symlink():
        raise CutoverError("Receipt manifest cannot be a symlink")
    destination = path.expanduser().resolve(strict=False)
    public = public_root.expanduser().resolve(strict=False)
    if destination == public or public in destination.parents:
        raise CutoverError("Receipt manifest must be outside MEDIA_ROOT")
    return destination


def _hash_file(path: Path) -> tuple[str, int]:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise CutoverError("Receipt path is not a regular file")

    digest = hashlib.sha256()
    size = 0
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    finally:
        os.close(descriptor)
    return digest.hexdigest(), size


def _safe_public_source(public_root: Path, relative: str) -> Path:
    parsed = PurePosixPath(relative)
    if (
        parsed.is_absolute()
        or len(parsed.parts) != 2
        or parsed.parts[0] != "receipts"
        or any(part in {".", ".."} for part in parsed.parts)
    ):
        raise CutoverError("Manifest contains an unsafe public path")
    receipt_dir = public_root / "receipts"
    if receipt_dir.is_symlink():
        raise CutoverError("Public receipt directory cannot be a symlink")
    path = public_root.joinpath(*parsed.parts)
    if path.is_symlink():
        raise CutoverError("Public receipt file cannot be a symlink")
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(public_root)
    except ValueError as exc:
        raise CutoverError("Public receipt path escaped MEDIA_ROOT") from exc
    return path


def _parse_legacy_reference(order: Order) -> tuple[str, str] | None:
    value = order.receipt_url
    if not value or "%" in value or "\\" in value:
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return None
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return None
    if parsed.scheme and not parsed.netloc:
        return None
    match = _LEGACY_URL.fullmatch(parsed.path)
    if match is None or int(match.group("order_id")) != order.id:
        return None
    extension = match.group("ext")
    if order.receipt_content_type not in (None, _CONTENT_TYPES[extension]):
        return None
    return f"receipts/{order.id}.{extension}", extension


def _relevant_orders_query():
    return (
        select(Order)
        .where(
            or_(
                Order.receipt_file_id.is_not(None),
                Order.receipt_url.is_not(None),
                Order.receipt_storage_key.is_not(None),
                Order.payment_status == PaymentStatus.RECEIPT_UPLOADED,
            )
        )
        .order_by(Order.id)
    )


def _private_path(private_root: Path, key: str) -> Path:
    match = _STORAGE_KEY.fullmatch(key) if isinstance(key, str) else None
    if match is None:
        raise CutoverError("Private receipt key is invalid")
    candidate = private_root / key
    if candidate.is_symlink():
        raise CutoverError("Private receipt object cannot be a symlink")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(private_root)
    except ValueError as exc:
        raise CutoverError("Private receipt path escaped PRIVATE_MEDIA_ROOT") from exc
    if not resolved.is_file():
        raise CutoverError("Private receipt object is unavailable")
    return resolved


def _validate_manifest(
    manifest: dict[str, Any], public_root: Path, private_root: Path
) -> None:
    if not isinstance(manifest, dict) or manifest.get("format_version") != FORMAT_VERSION:
        raise CutoverError("Unsupported receipt manifest")
    if manifest.get("public_root") != str(public_root):
        raise CutoverError("Receipt manifest MEDIA_ROOT does not match")
    if manifest.get("private_root") != str(private_root):
        raise CutoverError("Receipt manifest PRIVATE_MEDIA_ROOT does not match")
    entries = manifest.get("entries")
    unresolved = manifest.get("unresolved")
    existing_private = manifest.get("existing_private")
    if (
        not isinstance(entries, list)
        or not isinstance(unresolved, list)
        or not isinstance(existing_private, list)
    ):
        raise CutoverError("Receipt manifest is malformed")
    if (
        set(manifest)
        != {
            "format_version",
            "created_at",
            "public_root",
            "private_root",
            "entries",
            "existing_private",
            "unresolved",
            "public_receipts",
        }
        or not isinstance(manifest["created_at"], str)
        or type(manifest["public_receipts"]) is not int
        or manifest["public_receipts"] < 0
    ):
        raise CutoverError("Receipt manifest is malformed")

    seen_orders: set[int] = set()
    seen_sources: set[str] = set()
    seen_keys: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {
            "order_id",
            "source",
            "sha256",
            "size_bytes",
            "content_type",
            "storage_key",
            "receipt_url_sha256",
        }:
            raise CutoverError("Receipt manifest is malformed")
        order_id = entry.get("order_id")
        source = entry.get("source")
        key = entry.get("storage_key")
        content_type = entry.get("content_type")
        if (
            type(order_id) is not int
            or order_id <= 0
            or not isinstance(source, str)
            or not isinstance(key, str)
            or not isinstance(content_type, str)
            or not isinstance(entry.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            or type(entry.get("size_bytes")) is not int
            or entry["size_bytes"] < 0
            or not isinstance(entry.get("receipt_url_sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", entry["receipt_url_sha256"])
        ):
            raise CutoverError("Receipt manifest entry is invalid")
        key_match = _STORAGE_KEY.fullmatch(key)
        source_match = re.fullmatch(r"receipts/([1-9][0-9]*)\.(jpg|png|webp|pdf)", source)
        if (
            key_match is None
            or source_match is None
            or int(source_match.group(1)) != order_id
            or key_match.group("ext") != source_match.group(2)
            or content_type != _CONTENT_TYPES[source_match.group(2)]
        ):
            raise CutoverError("Receipt manifest entry is invalid")
        if order_id in seen_orders or source in seen_sources or key in seen_keys:
            raise CutoverError("Receipt manifest contains duplicate entries")
        seen_orders.add(order_id)
        seen_sources.add(source)
        seen_keys.add(key)

    reasons = {
        "file_id_only",
        "missing_reference",
        "unrecognized_reference",
        "public_file_missing",
        "private_reference_invalid",
        "public_private_mismatch",
    }
    for row in unresolved:
        if (
            not isinstance(row, dict)
            or set(row) != {"order_id", "reason"}
            or type(row.get("order_id")) is not int
            or row["order_id"] <= 0
            or row.get("reason") not in reasons
        ):
            raise CutoverError("Receipt manifest unresolved entry is invalid")
    for row in existing_private:
        if not isinstance(row, dict) or set(row) != {
            "order_id",
            "storage_key",
            "content_type",
            "sha256",
            "size_bytes",
        }:
            raise CutoverError("Receipt manifest private entry is invalid")
        key = row.get("storage_key")
        if (
            type(row.get("order_id")) is not int
            or row["order_id"] <= 0
            or not isinstance(row.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
            or type(row.get("size_bytes")) is not int
            or row["size_bytes"] < 0
            or not isinstance(key, str)
        ):
            raise CutoverError("Receipt manifest private entry is invalid")
        key_match = _STORAGE_KEY.fullmatch(key)
        if (
            key_match is None
            or row.get("content_type") != _CONTENT_TYPES[key_match.group("ext")]
        ):
            raise CutoverError("Receipt manifest private entry is invalid")


async def build_manifest(
    session: AsyncSession, *, public_root: Path, private_root: Path
) -> dict[str, Any]:
    public, private = _roots(public_root, private_root)
    entries: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    existing_private: list[dict[str, Any]] = []

    orders = (await session.scalars(_relevant_orders_query())).all()
    for order in orders:
        if order.receipt_storage_key:
            try:
                private_file = _private_path(private, order.receipt_storage_key)
                key_match = _STORAGE_KEY.fullmatch(order.receipt_storage_key)
                if key_match is None:
                    raise CutoverError("Private receipt key is invalid")
                extension = key_match.group("ext")
                content_type = _CONTENT_TYPES[extension]
                digest, size = _hash_file(private_file)
                if order.receipt_content_type != content_type:
                    raise CutoverError("Private receipt content type does not match its key")
                existing_private.append(
                    {
                        "order_id": order.id,
                        "storage_key": order.receipt_storage_key,
                        "content_type": content_type,
                        "sha256": digest,
                        "size_bytes": size,
                    }
                )
                if order.receipt_url:
                    reference = _parse_legacy_reference(order)
                    if reference is None:
                        unresolved.append(
                            {"order_id": order.id, "reason": "unrecognized_reference"}
                        )
                        continue
                    relative, legacy_extension = reference
                    source = _safe_public_source(public, relative)
                    try:
                        source_digest, source_size = _hash_file(source)
                    except FileNotFoundError:
                        continue
                    if source_digest != digest or source_size != size:
                        unresolved.append(
                            {"order_id": order.id, "reason": "public_private_mismatch"}
                        )
                        continue
                    entries.append(
                        {
                            "order_id": order.id,
                            "source": relative,
                            "sha256": digest,
                            "size_bytes": size,
                            "content_type": _CONTENT_TYPES[legacy_extension],
                            "storage_key": order.receipt_storage_key,
                            "receipt_url_sha256": hashlib.sha256(
                                order.receipt_url.encode()
                            ).hexdigest(),
                        }
                    )
            except (CutoverError, FileNotFoundError, TypeError):
                unresolved.append(
                    {"order_id": order.id, "reason": "private_reference_invalid"}
                )
            continue

        reference = _parse_legacy_reference(order)
        if reference is None:
            reason = (
                "file_id_only"
                if order.receipt_file_id and not order.receipt_url
                else (
                    "missing_reference"
                    if not order.receipt_file_id and not order.receipt_url
                    else "unrecognized_reference"
                )
            )
            unresolved.append({"order_id": order.id, "reason": reason})
            continue

        relative, extension = reference
        source = _safe_public_source(public, relative)
        try:
            digest, size = _hash_file(source)
        except FileNotFoundError:
            unresolved.append({"order_id": order.id, "reason": "public_file_missing"})
            continue
        entries.append(
            {
                "order_id": order.id,
                "source": relative,
                "sha256": digest,
                "size_bytes": size,
                "content_type": _CONTENT_TYPES[extension],
                "storage_key": f"{uuid4()}.{extension}",
                "receipt_url_sha256": hashlib.sha256(order.receipt_url.encode()).hexdigest(),
            }
        )

    manifest: dict[str, Any] = {
        "format_version": FORMAT_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "public_root": str(public),
        "private_root": str(private),
        "entries": entries,
        "existing_private": existing_private,
        "unresolved": unresolved,
        "public_receipts": _public_receipt_files(public),
    }
    _validate_manifest(manifest, public, private)
    return manifest


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    public_root = Path(manifest["public_root"])
    destination = _manifest_path_outside_public(path, public_root)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_symlink() or destination.exists():
        raise CutoverError("Receipt manifest destination already exists or is a symlink")
    encoded = (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as output:
            output.write(encoded)
            output.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(destination, 0o600)
    directory_fd = os.open(destination.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def load_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path.expanduser()
    try:
        mode = manifest_path.lstat().st_mode
    except FileNotFoundError as exc:
        raise CutoverError("Receipt manifest is missing") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode) or mode & 0o077:
        raise CutoverError("Receipt manifest must be a regular mode-0600 file")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CutoverError("Receipt manifest is unreadable") from exc
    if not isinstance(data, dict):
        raise CutoverError("Receipt manifest is malformed")
    return data


def _ensure_private_root(private_root: Path) -> None:
    if private_root.is_symlink():
        raise CutoverError("PRIVATE_MEDIA_ROOT cannot be a symlink")
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if private_root.is_symlink() or not private_root.is_dir():
        raise CutoverError("PRIVATE_MEDIA_ROOT is not a private directory")
    private_root.chmod(0o700)


def _verify_manifest_source(entry: dict[str, Any], source: Path) -> bool:
    if not source.exists():
        return False
    digest, size = _hash_file(source)
    if digest != entry["sha256"] or size != entry["size_bytes"]:
        raise CutoverError("Public receipt changed after manifest creation")
    return True


def _copy_immutable(source: Path, destination: Path, entry: dict[str, Any]) -> None:
    if destination.exists():
        existing_digest, size = _hash_file(destination)
        if existing_digest != entry["sha256"] or size != entry["size_bytes"]:
            raise CutoverError("Private receipt key already contains different bytes")
        return

    temp_fd, temp_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    temp_path = Path(temp_name)
    copy_digest = hashlib.sha256()
    size = 0
    source_fd: int | None = None
    try:
        os.fchmod(temp_fd, 0o600)
        source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        if not stat.S_ISREG(os.fstat(source_fd).st_mode):
            raise CutoverError("Public receipt path is not a regular file")
        with (
            os.fdopen(temp_fd, "wb", closefd=False) as target,
            os.fdopen(source_fd, "rb", closefd=False) as original,
        ):
            while chunk := original.read(1024 * 1024):
                copy_digest.update(chunk)
                size += len(chunk)
                target.write(chunk)
            target.flush()
            os.fsync(temp_fd)
        if copy_digest.hexdigest() != entry["sha256"] or size != entry["size_bytes"]:
            raise CutoverError("Copied receipt did not match the manifest hash")
        try:
            os.link(temp_path, destination, follow_symlinks=False)
        except FileExistsError:
            existing_digest, existing_size = _hash_file(destination)
            if existing_digest != entry["sha256"] or existing_size != entry["size_bytes"]:
                raise CutoverError(
                    "Private receipt key already contains different bytes"
                ) from None
        destination.chmod(0o600)
        dir_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        with suppress(OSError):
            temp_path.unlink()
        with suppress(OSError):
            os.close(temp_fd)
        if source_fd is not None:
            with suppress(OSError):
                os.close(source_fd)


async def verify_database_reference(
    session: AsyncSession, entry: dict[str, Any], private_root: Path
) -> None:
    order = await session.scalar(select(Order).where(Order.id == entry["order_id"]))
    if (
        order is None
        or order.receipt_storage_key != entry["storage_key"]
        or order.receipt_content_type != entry["content_type"]
        or order.receipt_url is not None
    ):
        raise CutoverError("Database receipt reference did not verify")
    private_file = _private_path(private_root, entry["storage_key"])
    digest, size = _hash_file(private_file)
    if digest != entry["sha256"] or size != entry["size_bytes"]:
        raise CutoverError("Private receipt did not verify after the database update")


async def apply_manifest(
    session: AsyncSession,
    manifest: dict[str, Any],
    *,
    public_root: Path,
    private_root: Path,
) -> dict[str, int]:
    public, private = _roots(public_root, private_root)
    _validate_manifest(manifest, public, private)
    _ensure_private_root(private)
    migrated = already_migrated = 0

    for entry in manifest["entries"]:
        source = _safe_public_source(public, entry["source"])
        order = await session.scalar(
            select(Order).where(Order.id == entry["order_id"]).with_for_update()
        )
        if order is None:
            raise CutoverError("Receipt order no longer exists")

        destination = (
            _private_path(private, entry["storage_key"])
            if (private / entry["storage_key"]).exists()
            else private / entry["storage_key"]
        )
        current_private_reference = (
            order.receipt_storage_key == entry["storage_key"]
            and order.receipt_content_type == entry["content_type"]
        )
        if current_private_reference:
            private_file = _private_path(private, entry["storage_key"])
            digest, size = _hash_file(private_file)
            if digest != entry["sha256"] or size != entry["size_bytes"]:
                raise CutoverError("Private receipt does not match the manifest")
            if order.receipt_url is not None:
                if (
                    hashlib.sha256(order.receipt_url.encode()).hexdigest()
                    != entry["receipt_url_sha256"]
                ):
                    raise CutoverError(
                        "Order receipt reference changed after manifest creation"
                    )
                reference = _parse_legacy_reference(order)
                if reference is None or reference[0] != entry["source"]:
                    raise CutoverError("Order receipt reference is not recognized")
                _verify_manifest_source(entry, source)
                order.receipt_url = None
                await session.flush()
                await session.commit()
                migrated += 1
            else:
                already_migrated += 1
        else:
            current_url = order.receipt_url
            if (
                order.receipt_storage_key is not None
                or current_url is None
                or hashlib.sha256(current_url.encode()).hexdigest()
                != entry["receipt_url_sha256"]
            ):
                raise CutoverError("Order receipt reference changed after manifest creation")
            reference = _parse_legacy_reference(order)
            if reference is None or reference[0] != entry["source"]:
                raise CutoverError("Order receipt reference is not recognized")
            if order.receipt_content_type not in (None, entry["content_type"]):
                raise CutoverError("Order receipt content type changed")
            _verify_manifest_source(entry, source)
            _copy_immutable(source, destination, entry)
            private_file = _private_path(private, entry["storage_key"])
            digest, size = _hash_file(private_file)
            if digest != entry["sha256"] or size != entry["size_bytes"]:
                raise CutoverError("Private receipt does not match the manifest")

            order.receipt_storage_key = entry["storage_key"]
            order.receipt_content_type = entry["content_type"]
            order.receipt_url = None
            await session.flush()
            await session.commit()
            migrated += 1

        await verify_database_reference(session, entry, private)
        if source.exists():
            _verify_manifest_source(entry, source)
            source.unlink()
            dir_fd = os.open(source.parent, os.O_RDONLY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

    return {
        "migrated": migrated,
        "already_migrated": already_migrated,
        "unresolved": len(manifest["unresolved"]),
        "public_receipts": _public_receipt_files(public),
    }


def _public_receipt_files(public_root: Path) -> int:
    receipt_dir = public_root / "receipts"
    if receipt_dir.is_symlink():
        raise CutoverError("Public receipt directory cannot be a symlink")
    if not receipt_dir.exists():
        return 0
    if not receipt_dir.is_dir():
        raise CutoverError("Public receipt directory is not a regular directory")
    count = 0
    for current, directories, files in os.walk(receipt_dir, followlinks=False):
        current_path = Path(current)
        for name in directories:
            if (current_path / name).is_symlink():
                count += 1
        count += len(files)
        for name in files:
            if (current_path / name).is_symlink():
                continue
    return count


async def verify_cutover(
    session: AsyncSession,
    *,
    public_root: Path,
    private_root: Path,
    manifest: dict[str, Any] | None = None,
) -> dict[str, int]:
    public, private = _roots(public_root, private_root)
    if manifest is not None:
        _validate_manifest(manifest, public, private)
    expected = {
        entry["order_id"]: entry for entry in (manifest or {}).get("existing_private", [])
    }
    expected.update(
        {entry["order_id"]: entry for entry in (manifest or {}).get("entries", [])}
    )
    verified_private = 0
    unresolved_ids: set[int] = set()
    orders = (await session.scalars(_relevant_orders_query())).all()
    for order in orders:
        if not order.receipt_storage_key or not order.receipt_content_type:
            unresolved_ids.add(order.id)
            continue
        try:
            path = _private_path(private, order.receipt_storage_key)
            match = _STORAGE_KEY.fullmatch(order.receipt_storage_key)
            if match is None:
                raise CutoverError("Private receipt key is invalid")
            if _CONTENT_TYPES[match.group("ext")] != order.receipt_content_type:
                raise CutoverError("Private receipt type does not match")
            digest, size = _hash_file(path)
            planned = expected.get(order.id)
            if planned and (digest != planned["sha256"] or size != planned["size_bytes"]):
                raise CutoverError("Private receipt hash differs from manifest")
            verified_private += 1
        except (CutoverError, FileNotFoundError, TypeError):
            unresolved_ids.add(order.id)

    if manifest is not None:
        orders_by_id = {order.id: order for order in orders}
        for entry in manifest["existing_private"]:
            order = orders_by_id.get(entry["order_id"])
            if (
                order is None
                or order.receipt_storage_key != entry["storage_key"]
                or order.receipt_content_type != entry["content_type"]
            ):
                unresolved_ids.add(entry["order_id"])
        for entry in manifest["entries"]:
            order = orders_by_id.get(entry["order_id"])
            if (
                order is None
                or order.receipt_storage_key != entry["storage_key"]
                or order.receipt_content_type != entry["content_type"]
                or order.receipt_url is not None
            ):
                unresolved_ids.add(entry["order_id"])
        unresolved_ids.update(item["order_id"] for item in manifest["unresolved"])

    return {
        "verified_private": verified_private,
        "unresolved": len(unresolved_ids),
        "public_receipts": _public_receipt_files(public),
    }


def _default_manifest_path(private_root: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return private_root / ".receipt-cutover" / f"manifest-{timestamp}.json"


def _summary(manifest: dict[str, Any]) -> dict[str, int]:
    return {
        "eligible": len(manifest["entries"]),
        "existing_private": len(manifest["existing_private"]),
        "unresolved": len(manifest["unresolved"]),
        "public_receipts": manifest["public_receipts"],
    }


async def _run(args: argparse.Namespace) -> int:
    public_root = Path(settings.media_root).expanduser()
    private_root = Path(settings.private_media_root).expanduser()
    public, private = _roots(public_root, private_root)
    manifest_path = Path(args.manifest).expanduser() if args.manifest else None
    if manifest_path is not None:
        manifest_path = _manifest_path_outside_public(manifest_path, public)

    async with async_session_maker() as session:
        if args.dry_run:
            manifest = await build_manifest(session, public_root=public, private_root=private)
            manifest_path = manifest_path or _default_manifest_path(private)
            write_manifest(manifest_path, manifest)
            print(json.dumps({**_summary(manifest), "manifest": str(manifest_path)}))
            return 0 if not manifest["unresolved"] else 2

        if args.apply:
            if manifest_path is None:
                raise CutoverError("--apply requires --manifest PATH")
            manifest = load_manifest(manifest_path)
            result = await apply_manifest(
                session,
                manifest,
                public_root=public,
                private_root=private,
            )
            print(json.dumps(result))
            return 0 if not result["unresolved"] else 2

        verify_manifest = load_manifest(manifest_path) if manifest_path else None
        result = await verify_cutover(
            session,
            public_root=public,
            private_root=private,
            manifest=verify_manifest,
        )
        print(json.dumps(result))
        return 0 if not result["unresolved"] and not result["public_receipts"] else 2


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="report and save a restricted manifest"
    )
    mode.add_argument(
        "--apply", action="store_true", help="apply a previously reviewed manifest"
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="read-only private reference and public path check",
    )
    parser.add_argument("--manifest", help="restricted local manifest path")
    return parser.parse_args(argv)


async def _main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        return await _run(args)
    except Exception as exc:
        print(
            f"receipt cutover stopped; no unverified public source was removed ({type(exc).__name__})",
            file=sys.stderr,
        )
        return 1


def main() -> None:
    configure_logging()
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
