# Purchase release and private-receipt cutover

This is the prepared release procedure for the Kans Shop Netcup stack. All three implementation
phases are integrated: the bot and responsive storefront share customer/cart/order services, the
web admin uses cookie/CSRF sessions and live roles, and transactional outbox/broadcast workers
persist recipient checkpoints. Local final verification passed 377 backend tests, 129 frontend
unit tests and 68 synthetic browser cases, plus lint, typecheck, build and isolated proxy/cutover
checks. Hosted CI for the final commit must still pass before release.

No production configuration, database migration, backup, broadcast or deployment was applied by
this work. Release requires owner review of the concrete diff/settings/schema and verified backups.
The current production images remain `16718babb4dba0b83d925f8b9bb09005e332f53f`.
Browser fixtures and the fabricated Telegram bridge do not prove native-device acceptance.

## Owner-reviewed release sequence

1. **Review the concrete release first.** Review the final diff and exact image SHA, the additive
   Alembic chain, the Kans-only Compose override, the Caddy snippet, the migration summary, and
   current store settings. Recheck the current Caddy peer address on the Kans network before
   approving `TRUSTED_PROXY_CIDRS`; `172.18.0.8/32` is the last read-only observation, not a value
   to reuse after Caddy is recreated. Recheck it after every Caddy recreation. Keep the setting
   limited to that peer. Uvicorn's forwarded
   trust stays narrow so the app can validate X-Forwarded-For itself. Do not add a wildcard, global
   Caddy trusted-proxy setting, or shared-site change.

2. **Verify backups before changing the stack.** Record a successful, restorable database backup
   and a restricted backup of the existing public media volume `kans-shop_kansshop_media`, which
   may still contain legacy receipts. If a private media volume already exists, back it up too.
   Verify timestamps, file sizes, and checksums without printing receipt content. Keep backups
   outside the public media root and restrict access to them.

3. **Apply only the reviewed Kans mount and edge deny.** The Compose override targets the
   production service `kans-api` in project `kans-shop`, adds the named private volume at
   `/app/private_media`, and retains the existing `/app/media` product mount and shared services.
   Update only the Kans site in `/srv/stack/infra/Caddyfile`: install the receipt denial before app
   routing and use the API matcher that includes `/payments/*`. Preserve other Caddy sites and the
   shared Docker network. Public DNS continues to point directly to `159.195.248.216`.

   The following commands use the server-owned stack file and the exact reviewed repository
   checkout that contains this override. Set `RELEASE_CHECKOUT` to that checkout path before use;
   do not substitute an unreviewed worktree.

4. **Start the reviewed image, then inspect a dry run.** The new image runs its compatible additive
   migrations on startup. From the running `kans-api` container, create a mode-0600 restricted
   manifest and review its aggregate counts and unresolved entries:

   ```sh
   docker compose -p kans-shop -f /srv/stack/stacks/kans-shop.yml \
     -f "$RELEASE_CHECKOUT/deploy/kans-shop.private-media.override.yml" \
     exec kans-api python -m scripts.migrate_private_receipts \
     --dry-run --manifest /app/private_media/.receipt-cutover/release-YYYYMMDD.json
   ```

   The configured `MEDIA_BASE_URL` origin is validated. Relative public paths are recognized only
   in the documented receipt shape. Absolute historical URLs from another origin are eligible only
   after the owner explicitly reviews that origin and passes `--legacy-origin <origin>` to dry-run,
   apply, and verify. The value must contain only the scheme, host, and optional port, with no path
   or credentials. Repeat the option for each approved old origin and pass the same list to all
   three modes. A changed `MEDIA_BASE_URL` or origin list makes apply/verify reject the manifest
   unless the exact reviewed origin set is explicitly reconstructed. The manifest records and
   binds that policy. Protocol-relative, credentialed, unknown-origin, malformed, missing,
   symlinked, and traversal references remain unresolved. A stale public URL with a valid private
   object and no matching public source also remains unresolved, so the cutover cannot be declared
   complete. The output contains counts and the manifest path, not receipt bytes, file IDs,
   or raw receipt URLs. The mode-0600 manifest stores hashes, order IDs, generated private keys,
   approved origins, and safe relative paths. Stop and reconcile every unresolved entry explicitly.

5. **Apply the reviewed manifest and verify every reference.** Run the protected copy/DB-update/
   verify/delete sequence with the same manifest, then run the read-only verification:

   ```sh
   docker compose -p kans-shop -f /srv/stack/stacks/kans-shop.yml \
     -f "$RELEASE_CHECKOUT/deploy/kans-shop.private-media.override.yml" \
     exec kans-api python -m scripts.migrate_private_receipts \
     --apply --manifest /app/private_media/.receipt-cutover/release-YYYYMMDD.json

   docker compose -p kans-shop -f /srv/stack/stacks/kans-shop.yml \
     -f "$RELEASE_CHECKOUT/deploy/kans-shop.private-media.override.yml" \
     exec kans-api python -m scripts.migrate_private_receipts \
     --verify --manifest /app/private_media/.receipt-cutover/release-YYYYMMDD.json
   ```

   A nonzero result or any unresolved/public-receipt count blocks completion. Verify that every
   order reference resolves under `PRIVATE_MEDIA_ROOT`, hashes match the manifest, and the public
   receipt directory has no remaining files. Product images remain in the existing public volume.
   The script does not download from Telegram or a remote URL.

6. **Check privacy and routing through the public edge.** Confirm that the exact receipt path,
   descendants, normalized paths, and encoded traversal paths return 404; confirm an old static
   media server and a simulated new legacy receipt write remain blocked through Caddy; and confirm
   product images still return 200. Send only fake invalid callback requests to the existing
   `/payments/*` routes. Do not create a real order or trigger a paid transaction for release
   verification.

7. **Confirm the release evidence.** Check successful GitHub CI and deploy results for the exact
   image SHA, healthy Kans containers, HTTPS health and catalog responses, the registered webhook,
   and the test-environment purchase smoke checks. GitHub CI evidence and deployed SHA must match;
   local Docker results do not substitute for hosted checks or a device review.

## Store readiness

The owner's real delivery fees, minimums, card-transfer details, and provider credentials may still
be unset. Keep unset settings unset. When required store settings are null, the API reports checkout
unavailable while catalog, cart, and order history remain available. Do not add demo prices, a demo
card, or provider credentials to make a readiness check pass. The owner must enter and review real
values through the approved admin flow before checkout is declared ready. Payment-provider
availability and credentials are separate from callback-route reachability.

## Rollback limits

- Keep the Caddy receipt denial and the private volume in place during every rollback. Do not
  restore a public receipt copy.
- Restore only an app image and schema combination whose compatibility has been reviewed. Do not
  downgrade the additive schema as an automatic rollback step.
- An older app image may not be able to display migrated private receipts. The privacy boundary
  remains intact even if receipt display is temporarily unavailable.
- A partial cutover blocks app rollback unless the edge denial remains active. If the denial is
  missing or uncertain, stop and restore that Kans-only edge rule before changing app versions.
- New public files written by a legacy image stay inaccessible through Caddy. Keep the denial
  installed until no legacy image can write to the public receipt directory.
