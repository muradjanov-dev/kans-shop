"""Cutover safety tests for legacy public receipt files and the Kans edge proxy."""

import hashlib
import importlib.util
import ipaddress
import json
import random
import shutil
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import OrderStatus, OrderType, PaymentMethod, PaymentStatus
from app.db.models.order import Order
from app.db.models.user import User


def _migrator():
    path = Path(__file__).parents[1] / "scripts" / "migrate_private_receipts.py"
    if not path.is_file():
        pytest.fail("receipt cutover migrator is missing")
    spec = importlib.util.spec_from_file_location("migrate_private_receipts", path)
    if spec is None or spec.loader is None:
        pytest.fail("receipt cutover migrator could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _legacy_order(
    session: AsyncSession,
    user: User,
    *,
    receipt_url: str | None,
    receipt_file_id: str | None = None,
) -> Order:
    order = Order(
        order_number=f"KANS-{uuid4().hex[:12].upper()}",
        user_id=user.id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        customer_name="Cutover Test",
        customer_phone="+998901234567",
        subtotal=10000,
        delivery_fee=0,
        discount=0,
        total=10000,
        payment_method=PaymentMethod.CARD_TRANSFER,
        payment_status=PaymentStatus.RECEIPT_UPLOADED,
        receipt_file_id=receipt_file_id,
        receipt_url=receipt_url,
        receipt_version=1,
        admin_message_ids={},
        source="webapp",
    )
    session.add(order)
    await session.flush()
    return order


async def test_receipt_cutover_preserves_content(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    receipt_dir = public_root / "receipts"
    receipt_dir.mkdir(parents=True)
    original = b"synthetic receipt bytes retained exactly\x00\xff"
    order = await _legacy_order(
        db_session,
        user,
        receipt_url="pending",
        receipt_file_id="synthetic-telegram-file-id-must-not-enter-manifest",
    )
    # Receipt URLs are keyed by order id, so set the row first, then materialize its file.
    order.receipt_url = _configured_receipt_url(cutover, order.id, "pdf")
    source = receipt_dir / f"{order.id}.pdf"
    source.write_bytes(original)
    original_hash = hashlib.sha256(original).hexdigest()

    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )
    with pytest.raises(cutover.CutoverError, match="outside MEDIA_ROOT"):
        cutover.write_manifest(public_root / "receipt-cutover.json", manifest)
    manifest_path = tmp_path / "restricted" / "receipt-cutover.json"
    cutover.write_manifest(manifest_path, manifest)
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    serialized_manifest = manifest_path.read_text()
    assert original.decode("latin1") not in serialized_manifest
    assert "synthetic-telegram-file-id-must-not-enter-manifest" not in serialized_manifest
    assert order.receipt_url not in serialized_manifest

    loaded_manifest = cutover.load_manifest(manifest_path)
    result = await cutover.apply_manifest(
        db_session,
        loaded_manifest,
        public_root=public_root,
        private_root=private_root,
    )

    assert result["migrated"] == 1
    assert order.receipt_storage_key is not None
    private_file = private_root / order.receipt_storage_key
    private_sha256 = hashlib.sha256(private_file.read_bytes()).hexdigest()
    assert private_sha256 == original_hash
    assert order.receipt_content_type == "application/pdf"
    assert order.receipt_url is None
    assert order.receipt_file_id == "synthetic-telegram-file-id-must-not-enter-manifest"
    assert order.receipt_version == 1
    assert not source.exists()


async def test_cutover_partial_failure_keeps_backup(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    (public_root / "receipts").mkdir(parents=True)
    original = b"backup remains until the database reference is verified"
    order = await _legacy_order(db_session, user, receipt_url=None)
    order.receipt_url = _configured_receipt_url(cutover, order.id, "pdf")
    source = public_root / "receipts" / f"{order.id}.pdf"
    source.write_bytes(original)
    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )

    async def fail_reference_check(*_args, **_kwargs):
        raise RuntimeError("injected database reference verification failure")

    monkeypatch.setattr(cutover, "verify_database_reference", fail_reference_check)
    with pytest.raises(RuntimeError, match="verification failure"):
        await cutover.apply_manifest(
            db_session,
            manifest,
            public_root=public_root,
            private_root=private_root,
        )

    assert source.read_bytes() == original
    assert order.receipt_storage_key is not None
    assert (private_root / order.receipt_storage_key).is_file()


async def test_cutover_repeat_is_idempotent(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    (public_root / "receipts").mkdir(parents=True)
    original = b"one immutable receipt object"
    order = await _legacy_order(db_session, user, receipt_url=None)
    order.receipt_url = _configured_receipt_url(cutover, order.id, "jpg")
    source = public_root / "receipts" / f"{order.id}.jpg"
    source.write_bytes(original)
    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )

    first = await cutover.apply_manifest(
        db_session, manifest, public_root=public_root, private_root=private_root
    )
    migrated_key = order.receipt_storage_key
    second = await cutover.apply_manifest(
        db_session, manifest, public_root=public_root, private_root=private_root
    )

    assert first["migrated"] == 1
    assert second["already_migrated"] == 1
    assert order.receipt_storage_key == migrated_key
    assert len(list(private_root.glob("*.jpg"))) == 1
    assert next(private_root.glob("*.jpg")).read_bytes() == original
    assert not source.exists()


async def test_verify_checks_existing_private_hash_without_mutating_references(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    public_root.mkdir()
    private_root.mkdir()
    order = await _legacy_order(db_session, user, receipt_url=None)
    storage_key = f"{uuid4()}.jpg"
    private_file = private_root / storage_key
    private_file.write_bytes(b"already private receipt")
    order.receipt_storage_key = storage_key
    order.receipt_content_type = "image/jpeg"
    before = (order.receipt_storage_key, order.receipt_content_type, order.receipt_url)

    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )
    valid = await cutover.verify_cutover(
        db_session,
        public_root=public_root,
        private_root=private_root,
        manifest=manifest,
    )
    private_file.write_bytes(b"private receipt changed after manifest creation")
    changed = await cutover.verify_cutover(
        db_session,
        public_root=public_root,
        private_root=private_root,
        manifest=manifest,
    )

    assert valid["verified_private"] == 1
    assert valid["unresolved"] == 0
    assert changed["verified_private"] == 0
    assert changed["unresolved"] == 1
    assert (order.receipt_storage_key, order.receipt_content_type, order.receipt_url) == before
    assert changed["public_receipts"] == 0


async def test_cutover_reports_file_id_only_and_unrecognized_references(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    (public_root / "receipts").mkdir(parents=True)
    file_id_only = await _legacy_order(
        db_session, user, receipt_url=None, receipt_file_id="synthetic-file-id"
    )
    traversal = await _legacy_order(
        db_session,
        user,
        receipt_url=f"/media/receipts/%2e%2e/{user.id}.jpg",
        receipt_file_id=None,
    )
    traversal.receipt_url = f"/media/receipts/%2e%2e/{traversal.id}.jpg"

    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )
    unresolved = {entry["order_id"]: entry["reason"] for entry in manifest["unresolved"]}

    assert unresolved[file_id_only.id] == "file_id_only"
    assert unresolved[traversal.id] == "unrecognized_reference"
    assert manifest["entries"] == []
    assert not private_root.exists()


async def test_cutover_rejects_unknown_network_path_and_credentialed_origins(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    receipt_dir = public_root / "receipts"
    receipt_dir.mkdir(parents=True)
    parsed_base = urlsplit(cutover.settings.media_base_url)
    credentialed_netloc = f"user:synthetic@{parsed_base.netloc}"
    unknown_order = await _legacy_order(db_session, user, receipt_url="pending")
    unknown_order.receipt_url = (
        f"https://unknown.example/media/receipts/{unknown_order.id}.jpg"
    )
    network_path_order = await _legacy_order(db_session, user, receipt_url="pending")
    network_path_order.receipt_url = (
        f"//{parsed_base.netloc}/media/receipts/{network_path_order.id}.jpg"
    )
    credentialed_order = await _legacy_order(db_session, user, receipt_url="pending")
    credentialed_order.receipt_url = urlunsplit(
        (
            parsed_base.scheme,
            credentialed_netloc,
            f"{parsed_base.path.rstrip('/')}/receipts/{credentialed_order.id}.jpg",
            "",
            "",
        )
    )
    for order in (unknown_order, network_path_order, credentialed_order):
        (receipt_dir / f"{order.id}.jpg").write_bytes(b"same-looking local receipt")

    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )
    unresolved = {entry["order_id"]: entry["reason"] for entry in manifest["unresolved"]}

    assert manifest["entries"] == []
    assert unresolved == {
        unknown_order.id: "unrecognized_reference",
        network_path_order.id: "unrecognized_reference",
        credentialed_order.id: "unrecognized_reference",
    }
    assert not private_root.exists()


async def test_missing_public_file_with_private_copy_keeps_stale_url_unresolved(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    (public_root / "receipts").mkdir(parents=True)
    private_root.mkdir()
    order = await _legacy_order(db_session, user, receipt_url="pending")
    order.receipt_url = _configured_receipt_url(cutover, order.id, "jpg")
    order.receipt_storage_key = f"{uuid4()}.jpg"
    order.receipt_content_type = "image/jpeg"
    (private_root / order.receipt_storage_key).write_bytes(b"already private receipt")
    before = (order.receipt_url, order.receipt_storage_key, order.receipt_content_type)

    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )
    verified = await cutover.verify_cutover(
        db_session,
        public_root=public_root,
        private_root=private_root,
        manifest=manifest,
    )
    verified_without_manifest = await cutover.verify_cutover(
        db_session, public_root=public_root, private_root=private_root
    )

    assert manifest["entries"] == []
    assert manifest["unresolved"] == [
        {"order_id": order.id, "reason": "legacy_public_url_stale"}
    ]
    assert verified["unresolved"] == 1
    assert verified_without_manifest["unresolved"] == 1
    assert (order.receipt_url, order.receipt_storage_key, order.receipt_content_type) == before


async def test_existing_private_public_url_resumes_when_source_matches(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    receipt_dir = public_root / "receipts"
    receipt_dir.mkdir(parents=True)
    private_root.mkdir()
    order = await _legacy_order(db_session, user, receipt_url="pending")
    order.receipt_url = _configured_receipt_url(cutover, order.id, "jpg")
    order.receipt_storage_key = f"{uuid4()}.jpg"
    order.receipt_content_type = "image/jpeg"
    original = b"private copy written before the database reference"
    (private_root / order.receipt_storage_key).write_bytes(original)
    source = receipt_dir / f"{order.id}.jpg"
    source.write_bytes(original)

    manifest = await cutover.build_manifest(
        db_session, public_root=public_root, private_root=private_root
    )
    result = await cutover.apply_manifest(
        db_session,
        manifest,
        public_root=public_root,
        private_root=private_root,
    )
    verified = await cutover.verify_cutover(
        db_session,
        public_root=public_root,
        private_root=private_root,
        manifest=manifest,
    )

    assert result["migrated"] == 1
    assert order.receipt_url is None
    assert order.receipt_storage_key is not None
    assert (private_root / order.receipt_storage_key).read_bytes() == original
    assert not source.exists()
    assert verified["unresolved"] == 0
    assert verified["public_receipts"] == 0


async def test_explicit_legacy_origin_is_bound_to_manifest_apply_and_verify(
    db_session: AsyncSession,
    user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    receipt_dir = public_root / "receipts"
    receipt_dir.mkdir(parents=True)
    legacy_origins = ("https://legacy.kans.example",)
    order = await _legacy_order(db_session, user, receipt_url="pending")
    order.receipt_url = f"https://legacy.kans.example/media/receipts/{order.id}.jpg"
    source = receipt_dir / f"{order.id}.jpg"
    source.write_bytes(b"explicitly approved old-origin receipt")

    manifest = await cutover.build_manifest(
        db_session,
        public_root=public_root,
        private_root=private_root,
        legacy_origins=legacy_origins,
    )
    with pytest.raises(cutover.CutoverError, match="origin policy"):
        await cutover.apply_manifest(
            db_session,
            manifest,
            public_root=public_root,
            private_root=private_root,
        )
    assert source.read_bytes() == b"explicitly approved old-origin receipt"

    result = await cutover.apply_manifest(
        db_session,
        manifest,
        public_root=public_root,
        private_root=private_root,
        legacy_origins=legacy_origins,
    )
    monkeypatch.setattr(cutover.settings, "media_base_url", "https://changed.example/media")
    with pytest.raises(cutover.CutoverError, match="origin policy"):
        await cutover.verify_cutover(
            db_session,
            public_root=public_root,
            private_root=private_root,
            manifest=manifest,
            legacy_origins=legacy_origins,
        )

    assert result["migrated"] == 1
    assert order.receipt_url is None
    assert not source.exists()


async def test_cutover_refuses_private_root_inside_public(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = public_root / "private"
    public_root.mkdir()

    with pytest.raises(ValueError, match="outside"):
        await cutover.build_manifest(
            db_session, public_root=public_root, private_root=private_root
        )


async def test_cutover_refuses_symlinked_public_receipt(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    public_root = tmp_path / "public"
    private_root = tmp_path / "private"
    receipt_dir = public_root / "receipts"
    receipt_dir.mkdir(parents=True)
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"must not follow this symlink")
    order = await _legacy_order(db_session, user, receipt_url=None)
    order.receipt_url = _configured_receipt_url(cutover, order.id, "pdf")
    (receipt_dir / f"{order.id}.pdf").symlink_to(outside)

    with pytest.raises(cutover.CutoverError, match="symlink"):
        await cutover.build_manifest(
            db_session, public_root=public_root, private_root=private_root
        )


async def test_cli_dry_run_and_verify_write_a_restricted_manifest(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    manifest_path = tmp_path / "restricted" / "cutover.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_private_receipts",
            "--dry-run",
            "--manifest",
            str(manifest_path),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["eligible"] == 0
    assert report["unresolved"] == 0
    assert manifest_path.stat().st_mode & 0o777 == 0o600
    assert set(report) == {
        "eligible",
        "existing_private",
        "unresolved",
        "public_receipts",
        "manifest",
    }

    verified = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_private_receipts",
            "--verify",
            "--manifest",
            str(manifest_path),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["unresolved"] == 0

    applied = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_private_receipts",
            "--apply",
            "--manifest",
            str(manifest_path),
        ],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert applied.returncode == 0, applied.stderr
    assert json.loads(applied.stdout)["migrated"] == 0


async def test_cli_reuses_explicit_legacy_origin_policy_across_modes(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    manifest_path = tmp_path / "restricted" / "origin-policy.json"
    legacy_origin = "https://legacy.kans.example"
    script = [sys.executable, "-m", "scripts.migrate_private_receipts"]
    common = ["--manifest", str(manifest_path)]
    created = subprocess.run(
        [*script, "--dry-run", *common, "--legacy-origin", legacy_origin],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert created.returncode == 0, created.stderr
    allowed_origins = json.loads(manifest_path.read_text())["approved_origins"]
    assert legacy_origin in allowed_origins

    omitted = subprocess.run(
        [*script, "--apply", *common],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert omitted.returncode == 1
    assert "CutoverError" in omitted.stderr

    applied = subprocess.run(
        [*script, "--apply", *common, "--legacy-origin", legacy_origin],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    verified = subprocess.run(
        [*script, "--verify", *common, "--legacy-origin", legacy_origin],
        cwd=Path(__file__).parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert applied.returncode == 0, applied.stderr
    assert verified.returncode == 0, verified.stderr


def _docker(args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    if shutil.which("docker") is None:
        pytest.skip("isolated cutover integration tests require Docker")
    result = subprocess.run(
        ["docker", *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(f"docker {' '.join(args[:3])} failed: {result.stderr[-4000:]}")
    return result


def _network(tmp_path: Path) -> tuple[str, str]:
    inspect = _docker(["network", "ls", "--quiet"]).stdout.splitlines()
    used: list[ipaddress.IPv4Network] = []
    for network_id in inspect:
        details = _docker(["network", "inspect", network_id]).stdout
        for item in json.loads(details)[0].get("IPAM", {}).get("Config") or []:
            subnet = item.get("Subnet")
            if subnet:
                used.append(ipaddress.ip_network(subnet, strict=False))

    candidates = [ipaddress.ip_network(f"192.168.{octet}.0/24") for octet in range(200, 255)]
    random.Random(str(tmp_path)).shuffle(candidates)
    subnet = next(
        candidate
        for candidate in candidates
        if not any(candidate.overlaps(existing) for existing in used)
    )
    network_name = f"kans-cutover-{uuid4().hex[:10]}"
    _docker(["network", "create", "--driver", "bridge", "--subnet", str(subnet), network_name])
    return network_name, str(subnet)


def _container_name(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def _configured_receipt_url(cutover, order_id: int, extension: str) -> str:
    return f"{cutover.settings.media_base_url.rstrip('/')}/receipts/{order_id}.{extension}"


def _port(container_name: str, exposed_port: int = 80) -> int:
    output = _docker(["port", container_name, f"{exposed_port}/tcp"]).stdout.strip()
    return int(output.rsplit(":", 1)[1])


def _request(host: str, port: int, path: str, *, method: str = "GET", body: bytes = b""):
    with socket.create_connection((host, port), timeout=3) as connection:
        request = (
            f"{method} {path} HTTP/1.1\r\n"
            f"Host: kans-cutover.test\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii") + body
        connection.sendall(request)
        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b"".join(chunks)
    header, _, response_body = raw.partition(b"\r\n\r\n")
    status_line = header.split(b"\r\n", 1)[0].split()
    if len(status_line) < 2:
        raise AssertionError(f"invalid HTTP response from isolated container: {raw!r}")
    status = int(status_line[1])
    return status, response_body


def _wait_for_port(port: int) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            _request("127.0.0.1", port, "/")
            return
        except (AssertionError, OSError):
            pass
        time.sleep(0.2)
    pytest.fail("isolated container did not start listening")


def _repo_file(relative: str) -> Path:
    return Path(__file__).parents[2] / relative


async def test_old_image_cannot_expose_receipts(
    db_session: AsyncSession, user: User, tmp_path: Path
) -> None:
    cutover = _migrator()
    snippet = _repo_file("deploy/kans-shop.caddy.snippet")
    if not snippet.is_file():
        pytest.fail("Kans receipt-deny Caddy snippet is missing")

    public_root = tmp_path / "public-media"
    private_root = tmp_path / "private-media"
    receipt_dir = public_root / "receipts"
    product_dir = public_root / "products" / "1"
    receipt_dir.mkdir(parents=True)
    product_dir.mkdir(parents=True)
    order = Order(
        order_number=f"KANS-{uuid4().hex[:12].upper()}",
        user_id=user.id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        customer_name="Legacy Image Test",
        customer_phone="+998901234567",
        subtotal=10000,
        delivery_fee=0,
        discount=0,
        total=10000,
        payment_method=PaymentMethod.CARD_TRANSFER,
        payment_status=PaymentStatus.RECEIPT_UPLOADED,
        receipt_url="pending",
        receipt_version=1,
        admin_message_ids={},
        source="webapp",
    )
    db_session.add(order)
    # The database order id is assigned before the old image's public filename.
    await db_session.flush()
    order.receipt_url = _configured_receipt_url(cutover, order.id, "png")
    original = b"old-image-public-copy"
    (receipt_dir / f"{order.id}.png").write_bytes(original)
    product = product_dir / "catalog.png"
    product.write_bytes(b"public-product-image")

    network_name, _ = _network(tmp_path)
    media_volume = _container_name("legacy-media")
    seed_name = _container_name("media-seed")
    legacy_name = _container_name("legacy-static")
    caddy_name = _container_name("caddy-edge")
    old_nginx = tmp_path / "legacy-nginx.conf"
    old_nginx.write_text(
        "server { listen 8000; server_name _; " "location /media/ { alias /media/; } }\n"
    )
    caddy_file = tmp_path / "Caddyfile"
    caddy_file.write_text(":80 {\n import /etc/caddy/kans-shop.caddy.snippet\n}\n")
    try:
        # Confirm the upstream reproduces the previous public static behavior first.
        _docker(["volume", "create", media_volume])
        _docker(
            [
                "run",
                "--detach",
                "--name",
                seed_name,
                "--volume",
                f"{media_volume}:/media",
                "alpine:3.21",
                "sleep",
                "300",
            ]
        )
        _docker(["cp", f"{public_root}/.", f"{seed_name}:/media/"])
        _docker(
            [
                "create",
                "--name",
                legacy_name,
                "--network",
                network_name,
                "--network-alias",
                "kans-api",
                "--publish",
                "127.0.0.1::8000",
                "--volume",
                f"{media_volume}:/media:ro",
                "nginx:1.27-alpine",
            ]
        )
        _docker(["cp", str(old_nginx), f"{legacy_name}:/etc/nginx/conf.d/default.conf"])
        _docker(["start", legacy_name])
        upstream_port = _port(legacy_name, 8000)
        _wait_for_port(upstream_port)
        status, body = _request("127.0.0.1", upstream_port, f"/media/receipts/{order.id}.png")
        assert status == 200 and body == original

        manifest = await cutover.build_manifest(
            db_session, public_root=public_root, private_root=private_root
        )
        result = await cutover.apply_manifest(
            db_session,
            manifest,
            public_root=public_root,
            private_root=private_root,
        )
        assert result["migrated"] == 1
        assert not (receipt_dir / f"{order.id}.png").exists()

        _docker(
            [
                "create",
                "--name",
                caddy_name,
                "--network",
                network_name,
                "--publish",
                "127.0.0.1::80",
                "caddy:2.10-alpine",
                "caddy",
                "run",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ]
        )
        _docker(["cp", str(caddy_file), f"{caddy_name}:/etc/caddy/Caddyfile"])
        _docker(["cp", str(snippet), f"{caddy_name}:/etc/caddy/kans-shop.caddy.snippet"])
        _docker(["start", caddy_name])
        caddy_port = _port(caddy_name)
        _wait_for_port(caddy_port)

        # An app rollback can create a new public copy; the edge must keep it denied.
        new_legacy_receipt = receipt_dir / "rollback-write.jpg"
        new_legacy_receipt.write_bytes(b"new legacy receipt after rollback")
        _docker(["exec", seed_name, "rm", "-f", f"/media/receipts/{order.id}.png"])
        _docker(
            ["cp", str(new_legacy_receipt), f"{seed_name}:/media/receipts/rollback-write.jpg"]
        )
        direct_status, direct_body = _request(
            "127.0.0.1", upstream_port, "/media/receipts/rollback-write.jpg"
        )
        assert direct_status == 200 and direct_body == new_legacy_receipt.read_bytes()

        paths = [
            "/media/receipts",
            "/media/receipts/",
            f"/media/receipts/{order.id}.png",
            "/media/receipts/rollback-write.jpg",
            "/media/%72eceipts/rollback-write.jpg",
            "/media/products/../receipts/rollback-write.jpg",
            "/media/products/%2e%2e/receipts/rollback-write.jpg",
            "/media/products/%252e%252e/receipts/rollback-write.jpg",
            "/media/products%2f..%2freceipts/rollback-write.jpg",
        ]
        for path in paths:
            status, _ = _request("127.0.0.1", caddy_port, path)
            assert status == 404, path

        status, body = _request("127.0.0.1", caddy_port, "/media/products/1/catalog.png")
        assert status == 200
        assert body == b"public-product-image"
    finally:
        for name in (caddy_name, legacy_name, seed_name):
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)
        subprocess.run(
            ["docker", "volume", "rm", media_volume], capture_output=True, check=False
        )
        subprocess.run(
            ["docker", "network", "rm", network_name], capture_output=True, check=False
        )


def test_kans_proxy_routes_callbacks(tmp_path: Path) -> None:
    snippet = _repo_file("deploy/kans-shop.caddy.snippet")
    if not snippet.is_file():
        pytest.fail("Kans API Caddy matcher is missing")

    repo_root = Path(__file__).parents[2]
    image = f"kans-receipt-probe:{uuid4().hex[:10]}"
    network_name, subnet = _network(tmp_path)
    subnet_base = ipaddress.ip_network(subnet)
    caddy_ip = str(subnet_base.network_address + 2)
    api_ip = str(subnet_base.network_address + 3)
    client_a_ip = str(subnet_base.network_address + 4)
    client_b_ip = str(subnet_base.network_address + 5)
    api_name = _container_name("receipt-api-probe")
    caddy_name = _container_name("caddy-api-edge")
    caddy_file = tmp_path / "Caddyfile"
    caddy_file.write_text(":80 {\n import /etc/caddy/kans-shop.caddy.snippet\n}\n")
    app_module = tmp_path / "cutover_proxy_probe.py"
    app_module.write_text(textwrap.dedent("""
            from fastapi import FastAPI, Request
            from app.api import rate_limit
            from app.api.payments_webhooks import router as payment_router
            from app.api.rate_limit import RateLimitMiddleware, trusted_client_ip

            class MemoryRedis:
                def __init__(self):
                    self.counts = {}
                async def incr(self, key):
                    self.counts[key] = self.counts.get(key, 0) + 1
                    return self.counts[key]
                async def expire(self, key, seconds):
                    return True
                async def eval(self, script, key_count, key, seconds):
                    return await self.incr(key)

            redis = MemoryRedis()
            rate_limit.get_redis = lambda: redis
            rate_limit.CODE_EXCHANGE_LIMIT = 1
            app = FastAPI()
            app.state.bot = None
            app.add_middleware(RateLimitMiddleware)
            app.include_router(payment_router)

            @app.post("/api/v1/auth/customer/code")
            async def code_exchange_probe(request: Request):
                return {"client_ip": trusted_client_ip(request)}
            """).strip() + "\n")

    built = False
    try:
        _docker(["build", "--tag", image, str(repo_root / "backend")], timeout=300)
        built = True
        _docker(
            [
                "create",
                "--name",
                api_name,
                "--network",
                network_name,
                "--ip",
                api_ip,
                "--network-alias",
                "kans-api",
                "--env",
                f"TRUSTED_PROXY_CIDRS={caddy_ip}/32",
                "--env",
                "BOT_TOKEN=123456:synthetic-cutover-token",
                "--env",
                "BOT_USERNAME=cutover_test_bot",
                "--env",
                "WEBHOOK_SECRET=synthetic-cutover-webhook-secret",
                "--env",
                "DATABASE_URL=postgresql+asyncpg://test:test@127.0.0.1/kansshop_test",
                "--env",
                "DATABASE_URL_SYNC=postgresql+psycopg://test:test@127.0.0.1/kansshop_test",
                "--env",
                "REDIS_URL=redis://127.0.0.1:6379/0",
                "--env",
                "JWT_SECRET=synthetic-cutover-jwt-secret-long-enough-for-tests",
                "--env",
                "PYTHONPATH=/tmp:/app",
                "--env",
                "PAYME_SECRET_KEY=",
                "--entrypoint",
                "uvicorn",
                image,
                "cutover_proxy_probe:app",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
                "--forwarded-allow-ips=127.0.0.1",
            ]
        )
        _docker(["cp", str(app_module), f"{api_name}:/tmp/cutover_proxy_probe.py"])
        _docker(["start", api_name])
        _docker(
            [
                "create",
                "--name",
                caddy_name,
                "--network",
                network_name,
                "--ip",
                caddy_ip,
                "--network-alias",
                "kans-caddy",
                "caddy:2.10-alpine",
                "caddy",
                "run",
                "--config",
                "/etc/caddy/Caddyfile",
                "--adapter",
                "caddyfile",
            ]
        )
        _docker(["cp", str(caddy_file), f"{caddy_name}:/etc/caddy/Caddyfile"])
        _docker(["cp", str(snippet), f"{caddy_name}:/etc/caddy/kans-shop.caddy.snippet"])
        _docker(["start", caddy_name])

        def client_request(client_ip: str, forwarded: str, path: str, body: bytes = b""):
            python = textwrap.dedent("""
                import json, sys, time, urllib.error, urllib.request
                url, spoofed, path, body_text = sys.argv[1:]
                data = body_text.encode() if body_text else None
                headers = {"X-Forwarded-For": spoofed}
                if data is not None:
                    headers["Content-Type"] = "application/json"
                request = urllib.request.Request(url + path, data=data, headers=headers, method="POST")
                for attempt in range(100):
                    try:
                        response = urllib.request.urlopen(request, timeout=2)
                        status, payload = response.status, response.read().decode()
                        break
                    except urllib.error.HTTPError as error:
                        status, payload = error.code, error.read().decode()
                        if status not in (502, 503, 504) or attempt == 99:
                            break
                        time.sleep(.1)
                    except (urllib.error.URLError, TimeoutError):
                        if attempt == 99:
                            raise
                        time.sleep(.1)
                print(json.dumps({"status": status, "body": payload}))
                """).strip()
            raw = _docker(
                [
                    "run",
                    "--rm",
                    "--network",
                    network_name,
                    "--ip",
                    client_ip,
                    "--entrypoint",
                    "python",
                    "python:3.12-alpine",
                    "-c",
                    python,
                    "http://kans-caddy",
                    forwarded,
                    path,
                    body.decode(),
                ],
                timeout=30,
            ).stdout.strip()
            return json.loads(raw.splitlines()[-1])

        first = client_request(
            client_a_ip,
            "198.51.100.111",
            "/api/v1/auth/customer/code",
        )
        repeated = client_request(
            client_a_ip,
            "198.51.100.222",
            "/api/v1/auth/customer/code",
        )
        second_client = client_request(
            client_b_ip,
            client_a_ip,
            "/api/v1/auth/customer/code",
        )
        assert first["status"] == 200
        assert json.loads(first["body"])["client_ip"] == client_a_ip
        assert repeated["status"] == 429
        assert second_client["status"] == 200
        assert json.loads(second_client["body"])["client_ip"] == client_b_ip

        callback = client_request(
            client_a_ip,
            "198.51.100.250",
            "/payments/payme",
            b'{"jsonrpc":"2.0","id":"synthetic-invalid","method":"Ping","params":{}}',
        )
        assert callback["status"] == 200
        assert "error" in json.loads(callback["body"])
    finally:
        for name in (caddy_name, api_name):
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)
        subprocess.run(
            ["docker", "network", "rm", network_name], capture_output=True, check=False
        )
        if built:
            subprocess.run(["docker", "image", "rm", image], capture_output=True, check=False)


def test_private_media_override_preserves_shared_mounts(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("Compose override validation requires Docker")
    compose = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, text=True, check=False
    )
    if compose.returncode != 0:
        pytest.skip("Compose override validation requires Docker Compose")

    repo_root = Path(__file__).parents[2]
    override = repo_root / "deploy" / "kans-shop.private-media.override.yml"
    base = tmp_path / "production-shape.yml"
    base.write_text(textwrap.dedent("""
            services:
              kans-api:
                image: synthetic.invalid/kans-api:test
                environment:
                  DATABASE_URL: postgresql+asyncpg://synthetic.invalid/kans
                  REDIS_URL: redis://synthetic.invalid:6379/0
                volumes:
                  - kansshop_media:/app/media
                networks:
                  - shared-kans-network
            volumes:
              kansshop_media:
                name: kans-shop_kansshop_media
            networks:
              shared-kans-network:
                name: kans-shop_default
                external: true
            """).strip() + "\n")
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            "kans-shop",
            "--project-directory",
            str(tmp_path),
            "-f",
            str(base),
            "-f",
            str(override),
            "config",
            "--format",
            "json",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    service = rendered["services"]["kans-api"]
    mounts = {volume["target"]: volume["source"] for volume in service["volumes"]}

    assert mounts["/app/media"] == "kansshop_media"
    assert mounts["/app/private_media"] == "kansshop_private_media"
    assert rendered["volumes"]["kansshop_media"]["name"] == "kans-shop_kansshop_media"
    assert rendered["volumes"]["kansshop_private_media"]["name"] == (
        "kans-shop_kansshop_private_media"
    )
    assert service["environment"]["DATABASE_URL"] == (
        "postgresql+asyncpg://synthetic.invalid/kans"
    )
    assert service["environment"]["REDIS_URL"] == "redis://synthetic.invalid:6379/0"
    assert service["environment"]["PRIVATE_MEDIA_ROOT"] == "/app/private_media"
    assert service["environment"]["TRUSTED_PROXY_CIDRS"] == "172.18.0.8/32"
    assert set(service["networks"]) == {"shared-kans-network"}
    assert not service.get("ports")


def test_frontend_image_nginx_serves_static_spa_only(tmp_path: Path) -> None:
    config = _repo_file("frontend/nginx.conf")
    index = tmp_path / "index.html"
    index.write_text("<!doctype html><title>synthetic storefront</title>\n")
    container = _container_name("frontend-static")
    try:
        _docker(
            [
                "create",
                "--name",
                container,
                "--publish",
                "127.0.0.1::80",
                "nginx:1.27-alpine",
            ]
        )
        _docker(["cp", str(config), f"{container}:/etc/nginx/conf.d/default.conf"])
        _docker(["cp", str(index), f"{container}:/usr/share/nginx/html/index.html"])
        _docker(["start", container])
        port = _port(container)
        _wait_for_port(port)

        route_status, route_body = _request("127.0.0.1", port, "/product/42")
        api_status, api_body = _request("127.0.0.1", port, "/api/v1/health")

        assert route_status == 200
        assert route_body == index.read_bytes()
        assert api_status == 200
        assert api_body == index.read_bytes()
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container], capture_output=True, check=False
        )


def test_local_compose_nginx_configuration_validates_in_docker(tmp_path: Path) -> None:
    if shutil.which("docker") is None:
        pytest.skip("Nginx configuration validation requires Docker")
    config = _repo_file("nginx/nginx.conf")
    container = _container_name("local-nginx-config")
    network, _ = _network(tmp_path)
    try:
        _docker(
            [
                "create",
                "--name",
                container,
                "--network",
                network,
                "--network-alias",
                "api",
                "nginx:1.27-alpine",
            ]
        )
        _docker(["cp", str(config), f"{container}:/etc/nginx/conf.d/default.conf"])
        _docker(["start", container])
        _docker(["exec", container, "nginx", "-t"])
    finally:
        subprocess.run(
            ["docker", "rm", "--force", container], capture_output=True, check=False
        )
        subprocess.run(["docker", "network", "rm", network], capture_output=True, check=False)
