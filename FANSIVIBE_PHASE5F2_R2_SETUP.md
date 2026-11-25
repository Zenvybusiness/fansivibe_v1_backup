# Fansivibe — Phase 5F.2 / 5F.3A / 5F.3B / 5F.3C: Cloudflare R2 Provisioning & Setup Guide

**Status:** Live Private Cloudflare R2 Bucket, FastAPI Runtime & Signed URL Expiry Verified (`PASS`)  
**Date:** 2026-11-25  
**Scope:** Backend object storage configuration for Wardrobe media and Genlook VTON verification.  
**Current Local Safety Posture:** `MEDIA_STORAGE_PROVIDER=r2` (bucket `fansivibe-media-dev`), `FANSIVIBE_TRYON_PROVIDER=mock`, `GENLOOK_API_KEY` unset, zero Genlook calls or paid credits consumed (`backend/.env.example` retains `MEDIA_STORAGE_PROVIDER=fake` and `FANSIVIBE_TRYON_PROVIDER=mock`).

---

## 1. Existing R2 Architecture Summary

Fansivibe already implements a single, hexagonal object storage layer reused across Wardrobe media (`POST /v1/media/uploads`, `/complete`, `/url`) and Virtual Try-On (`POST /v1/tryon/jobs`, `GET /v1/tryon/jobs/{id}/image`, `DELETE /v1/tryon/jobs/{id}`, retention cleanup, and Genlook garment signing):

| Layer | Component | File |
|---|---|---|
| Port Contract | `ObjectStoragePort` & `Storage*Error` taxonomy | [`storage.py`](backend/app/domain/ports/storage.py) |
| R2 Adapter | `CloudflareR2StorageAdapter` (`boto3` S3 SigV4, path-style, `region="auto"`) | [`storage.py`](backend/app/infrastructure/external/storage.py) |
| DI Seam | `get_storage_adapter()` -> `get_default_storage_adapter(get_settings())` | [`deps.py`](backend/app/api/deps.py) |
| Configuration | `Settings` (`MEDIA_STORAGE_PROVIDER`, `R2_*`, fail-closed validation) | [`settings.py`](backend/app/config/settings.py) |
| Try-On Lifecycle | `store_person_image_async`, `create_confirmed_presigned_input_url`, `execute_tryon_inference`, `delete_job_and_media`, `cleanup_retention_data` | [`tryon.py`](backend/app/application/tryon.py) |

### Security & Privacy Invariants Verified
- **Backend-only credentials:** `R2_ACCESS_KEY_ID` and `R2_SECRET_ACCESS_KEY` (`repr=False`) exist strictly in backend `Settings`. Zero R2 credentials or endpoints exist in Flutter (`newproject/flutter_application_1/lib/`).
- **Private objects only:** Objects are stored under user-scoped keys (`users/{user_id}/wardrobe/...`, `staging/users/{user_id}/wardrobe/...`, `users/{user_id}/tryon/{job_id}/...`) enforced by `validate_scoped_object_key` and OW-1 repository checks.
- **Short-lived presigned URLs:** Generated dynamically in memory (`900s` for client wardrobe display/upload, `300s` for Genlook garment fetch after `object_exists` confirmation), never persisted in PostgreSQL (`tryon_jobs` or `media_upload_authorizations`), and scrubbed (`X-Amz-Signature`, `X-Amz-Credential`, `X-Amz-Security-Token`, `AWSAccessKeyId`) from error messages and logs.
- **Git hygiene:** `.gitignore` ignores `.env` and `.env.*` while preserving placeholder-only [`backend/.env.example`](backend/.env.example).

---

## 2. Exact Cloudflare Dashboard Setup Steps

### Step 1 — Create a Private R2 Bucket
1. Sign in to the **Cloudflare Dashboard** and select **R2 Object Storage**.
2. Click **Create bucket**.
3. **Bucket name:** Choose an environment-specific, lowercase DNS-compliant name (3–63 chars, `[a-z0-9-]`), for example:
   - Local/staging Genlook verification: `fansivibe-media-dev` (or `fansivibe-media-staging`)
   - Production (future): `fansivibe-media-prod`
   > Keep verification and production buckets strictly separate.
4. **Location / Jurisdiction:** Leave **Automatic** (or pick the region nearest your backend/Genlook deployment). Note: unless you explicitly select a Jurisdiction (e.g., `European Union (EU)`), the standard global endpoint `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` applies.
5. Click **Create bucket**.

### Step 2 — Verify the Bucket Remains Strictly Private
1. Open the newly created bucket -> **Settings**.
2. Under **Public access**:
   - Confirm **R2.dev subdomain** is **Disabled**.
   - Confirm **Custom Domains** is **Empty** (do not attach a public domain).
3. *(Optional — only if testing direct browser `PUT` uploads from Flutter Web `flutter run -d chrome`)*:
   - Under **CORS Policy**, add an origin-restricted rule allowing `PUT` and `GET` from your exact local/app origin (never `*` in production) with allowed headers `Content-Type` and `Content-Length`.
   - Note: Mobile native clients and server-to-server Genlook garment fetches do **not** require bucket CORS.

### Step 3 — Identify Account ID & S3-Compatible Endpoint
1. On **R2 Object Storage -> Overview** (or inside Bucket **Settings -> S3 API**), copy:
   - **Account ID** (32-character hex identifier).
   - **S3 API endpoint URL**:
     - Standard bucket: `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`
     - Jurisdiction-restricted bucket (e.g. EU): `https://<R2_ACCOUNT_ID>.eu.r2.cloudflarestorage.com`
   - **Important:** Do **not** append the bucket name to `R2_ENDPOINT_URL`. `CloudflareR2StorageAdapter` uses `addressing_style="path"` and appends `/{bucket}/{key}` automatically.
2. If using the standard global endpoint, setting `R2_ACCOUNT_ID` lets Fansivibe derive `effective_r2_endpoint_url` automatically. If using a jurisdiction-specific endpoint, set `R2_ENDPOINT_URL` explicitly.

### Step 4 — Create a Minimum-Privilege R2 API Token
1. In **R2 Object Storage**, click **Manage R2 API Tokens** -> **Create API token**.
2. **Token name:** e.g. `fansivibe-dev-media-rw` (or `fansivibe-phase5f-verify`).
3. **Permissions:** Select **Object Read & Write**.
   - **Why these exact permissions are required:**
     `CloudflareR2StorageAdapter` executes only:
     - `PutObject` & presigned `PutObject` (person photos, try-on results, wardrobe staging uploads; presigned PUT signs `Content-Type` only, matching `AuthorizeMediaUpload`)
     - `GetObject` & presigned `GetObject` (authenticated wardrobe/try-on reads and `300s` Genlook garment URLs; enforces `1..604800s` TTL bounds)
     - `HeadObject` (`object_exists` durability confirmations and `get_object_metadata`)
     - `CopyObject` (server-side staging-to-canonical promotion in `CompleteMediaUpload`)
     - `DeleteObject` (try-on deletion, retention cleanup, staging cleanup)
     - `HeadBucket` (`check_health()` on `GET /v1/tryon/health`, supported natively on bucket-scoped `Object Read & Write` tokens)
   - **Do NOT grant:**
     - **Admin Read & Write** (bucket creation/deletion, account-wide R2 configuration) unless you specifically need bucket management via API.
     - Account-wide Cloudflare API permissions (Workers, DNS, Billing, Zero Trust).
4. **Specify bucket(s):** Select **Apply to specific buckets only** -> choose **only** your Fansivibe bucket (e.g., `fansivibe-media-dev`). Never scope a dev/test token to "All buckets".
5. **TTL:** Set a bounded expiration (e.g., `7 days` or `30 days` for verification).
6. Click **Create API Token** and immediately copy:
   - **Access Key ID** -> `R2_ACCESS_KEY_ID`
   - **Secret Access Key** -> `R2_SECRET_ACCESS_KEY`
   > Do **not** confuse the Cloudflare "Token value" (Bearer token for Cloudflare REST API v4) with the S3 **Access Key ID** and **Secret Access Key** required by `boto3`. Store the Secret Access Key in your password/secrets manager immediately; Cloudflare shows it only once. Newly created R2 tokens may take ~1–2 minutes to propagate globally.

---

## 3. Required Backend Environment Variables

Add the following to your **gitignored** local `backend/.env` (or secret manager for staging/production). Never put real values in [`backend/.env.example`](backend/.env.example) or Flutter.

```dotenv
# --- Media Storage / Cloudflare R2 (Backend Only) ---
MEDIA_STORAGE_PROVIDER=r2
R2_BUCKET_NAME=<your-private-r2-bucket-name>
R2_ACCESS_KEY_ID=<your-r2-s3-access-key-id>
R2_SECRET_ACCESS_KEY=<your-r2-s3-secret-access-key>
# Set R2_ACCOUNT_ID for standard global endpoint, or set R2_ENDPOINT_URL for jurisdiction endpoints:
R2_ACCOUNT_ID=<your-cloudflare-32-char-account-id>
# R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
R2_REGION=auto
R2_CONNECT_TIMEOUT_S=5.0
R2_READ_TIMEOUT_S=15.0
R2_MAX_RETRIES=2

# --- Keep Try-On on safe default until R2 connectivity is verified ---
FANSIVIBE_TRYON_PROVIDER=mock
FANSIVIBE_TRYON_ENABLED=true
```

### Secure Local File Permissions
```bash
chmod 600 backend/.env
git check-ignore -v backend/.env
```
Confirm `git status` never lists `backend/.env`.

---

## 4. Safe Connectivity Verification Procedure (Zero Genlook / Zero Paid Credits)

After populating `backend/.env` with R2 credentials (keeping `FANSIVIBE_TRYON_PROVIDER=mock`):

1. **Run the automated safe live R2 verification script (recommended):**
   ```bash
   backend/.venv/bin/python backend/scripts/verify_r2_live.py
   ```
   This script reads gitignored `backend/.env` without enabling Genlook, verifies `head_bucket` connectivity, validates `1..604800s` TTL bounds (`300s` Genlook and `60s` probe), uploads a synthetic non-personal 64x64 WebP probe under `users/00000000-0000-0000-0000-000000000000/tryon/r2-live-probe-.../probe.webp`, confirms unsigned access is blocked (`400/401/403/404`), retrieves the object via presigned GET URL, verifies byte-for-byte SHA-256 and Pillow WebP integrity, deletes the object, and confirms post-delete `404`. It never prints credentials, complete signed URLs, or sensitive headers. Exit codes: `0` (`PASS`), `1` (`FAIL`), `2` (`BLOCKED` if R2 credentials are not yet provisioned).

2. **Check `Settings` and `CloudflareR2StorageAdapter` bucket health (`head_bucket`) manually (run from repo root):**
   ```bash
   PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
   import asyncio
   from app.config.settings import get_settings, clear_settings_cache
   from app.infrastructure.external.storage import (
       create_storage_adapter,
       CloudflareR2StorageAdapter,
   )

   clear_settings_cache()
   s = get_settings()
   assert s.media_storage_provider == "r2", s.media_storage_provider
   assert s.tryon_provider == "mock", "Keep mock until operator authorizes live Genlook"
   adapter = create_storage_adapter(s)
   assert isinstance(adapter, CloudflareR2StorageAdapter)
   print("Health:", asyncio.run(adapter.check_health()))
   PY
   ```
   Expected output: `Health: {'provider': 'r2', 'status': 'healthy', 'bucket': '<bucket>', 'latency_ms': ...}` — no credentials or URLs printed.

3. **Check backend health endpoint (optional while backend is running):**
   ```bash
   curl -s http://localhost:8000/v1/tryon/health | python3 -m json.tool
   ```
   Verify `"storage": {"provider": "r2", "status": "healthy", ...}` and `"provider": {"provider": "mock", ...}`.

---

## 5. Rollback Procedure

To revert local/dev storage back to zero-cloud in-memory fake storage immediately:
1. In `backend/.env`, set:
   ```dotenv
   MEDIA_STORAGE_PROVIDER=fake
   FANSIVIBE_TRYON_PROVIDER=mock
   ```
   and clear or remove `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` if no longer needed.
2. Restart the backend process (`uvicorn`) so `get_settings()` and `get_default_storage_adapter()` reload cleanly.
3. If an R2 token was exposed or is no longer needed, revoke it immediately in **Cloudflare Dashboard -> R2 Object Storage -> Manage R2 API Tokens -> Revoke**.

---

## 6. Automated Local Test Commands (Isolated / Mocked)

> **Note:** When `backend/.env` sets `MEDIA_STORAGE_PROVIDER=r2`, prefix offline/DB `pytest` runs inside `backend/` with `MEDIA_STORAGE_PROVIDER=fake` (or run from `/tmp`) so test fixtures that instantiate `get_settings()` without mocking `get_storage_adapter` do not write test objects to the live R2 bucket.

```bash
# Migration consistency tests
backend/.venv/bin/pytest \
  backend/tests/test_media_api.py::TestMigration0033Metadata \
  backend/tests/test_production_hardening.py::TestMigrationReadiness -v

# Phase 5F.2 / 5F.3A R2 readiness, live-probe unit tests, & security tests (zero live calls)
backend/.venv/bin/pytest backend/tests/test_r2_phase5f2_readiness.py -v

# Safe live R2 connectivity probe (reads backend/.env; exits 2 BLOCKED if unprovisioned)
backend/.venv/bin/python backend/scripts/verify_r2_live.py

# Isolated live signed URL expiration verification (3s TTL -> waits -> confirms 403 ExpiredRequest)
backend/.venv/bin/python backend/scripts/verify_r2_expiry.py

# Existing storage adapter, config, and DI suites
backend/.venv/bin/pytest \
  backend/tests/test_storage_adapter.py \
  backend/tests/test_storage_config.py \
  backend/tests/test_storage_di.py \
  backend/tests/test_fake_storage.py -v

# Media API, Try-on security, and Genlook mocked flow
backend/.venv/bin/pytest \
  backend/tests/test_media_api.py \
  backend/tests/test_tryon_phase5e_1_security_hardening.py \
  backend/tests/test_tryon_phase5d_commercial_and_reliability.py \
  backend/tests/test_tryon_phase5f_genlook.py -v

(cd /tmp && PYTHONPATH=/home/tony/projects/fansivibe_v1_backup/backend \
  /home/tony/projects/fansivibe_v1_backup/backend/.venv/bin/pytest \
  /home/tony/projects/fansivibe_v1_backup/backend/tests/test_settings.py -v)
```

---

## 7. Live Verification Evidence (Phase 5F.3B — 2026-11-25)

Reviewed execution of `backend/.venv/bin/python backend/scripts/verify_r2_live.py` against local `backend/.env` (zero secrets, keys, account IDs, or signed URLs logged):

| Check | Result | Observed Evidence |
|---|---|---|
| Real R2 credentials & endpoint | **PASS** | `Settings(_env_file=backend/.env)` loaded `MEDIA_STORAGE_PROVIDER=r2`, `R2_BUCKET_NAME=fansivibe-media-dev`, `R2_REGION=auto`, and real `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`; `create_storage_adapter()` built a real `CloudflareR2StorageAdapter` (`s3_client=None`) with `boto3` S3 SigV4 path-style client targeting `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` and real `httpx.Client`. |
| Bucket connectivity (`HeadBucket`) | **PASS** | `HEALTH=status:healthy latency_ms:1116.61` on `fansivibe-media-dev`. |
| Synthetic image upload | **PASS** | Uploaded in-memory 64x64 RGB WebP probe (`88` bytes) under `users/00000000-0000-0000-0000-000000000000/tryon/r2-live-probe-<uuid>/probe.webp`; `object_exists` returned `True`. |
| Unsigned public access rejected | **PASS** | Unauthenticated `GET` to path-style endpoint URL returned `UNSIGNED_GET_HTTP=400`. |
| Signed GET retrieval | **PASS** | `60s` SigV4 presigned GET URL returned `SIGNED_GET_HTTP=200`. |
| SHA-256 & image integrity | **PASS** | Downloaded payload matched `BYTES_VERIFIED=88`, SHA-256 `e1d14bed02558c068737e6f5d8bef6eba012eceab6efc7d26e6af2e528c631d0`, and Pillow `WEBP` `(64, 64)` decode. |
| Deletion & post-deletion 404 | **PASS** | `delete_object` succeeded, `object_exists` returned `False`, and re-fetching signed GET URL returned `POST_DELETE_GET_HTTP=404`. |
| Leftover test objects | **PASS** | `list_objects_v2(Bucket="fansivibe-media-dev", MaxKeys=100)` after run returned `BUCKET_KEY_COUNT=0` (`LEFTOVER_PROBE_KEYS_COUNT=0`). |
| `.env` gitignored & restrictive permissions | **PASS** | `backend/.env` permissions `0o600` (`-rw-------`); ignored by `.gitignore:7` and `backend/.gitignore:7`; untracked in `git ls-files`; root `.env` absent. |
| `FANSIVIBE_TRYON_PROVIDER=mock` | **PASS** | Verified `Settings(_env_file=backend/.env).tryon_provider == "mock"` (`FANSIVIBE_TRYON_ENABLED=True`). |
| Zero Genlook requests made | **PASS** | `verify_r2_live.py` contains no Genlook imports/calls, `FANSIVIBE_TRYON_PROVIDER=mock`, and `GENLOOK_API_KEY` is unset. |
| Signed URL TTL configuration check | **PASS** | Bounds `0` and `604801` rejected with `StoragePayloadError`; SigV4 `AWS4-HMAC-SHA256` and `X-Amz-Expires` (`300s` Genlook TTL, `60s` probe TTL) verified. |
| Actual live URL expiration test | **PASS (Phase 5F.3C)** | `backend/scripts/verify_r2_expiry.py` verified `3s` SigV4 presigned GET URL returned `PRE_EXPIRY_HTTP=200` (SHA-256 verified), waited `6.0s`, and confirmed live R2 rejected the same URL with `POST_EXPIRY_HTTP=403` (`ExpiredRequest` / `Request has expired`), with `CLEANUP_VERIFIED=True` and `0` leftover objects. |

---

## 8. FastAPI Runtime & Application-Level Verification (Phase 5F.3C — 2026-11-25)

| Check | Result | Observed Evidence |
|---|---|---|
| Stale server replacement | **PASS** | Stopped pre-existing stale Uvicorn PID `17760` (started `19:35:05` on `FakeStorageAdapter`) and restarted via `./start.sh` (PID `79201`, `--host 100.105.35.91 --port 8000`). Hardened `Settings.effective_r2_endpoint_url` to normalize `R2_ACCOUNT_ID` when provided as an `https://<account_id>.r2.cloudflarestorage.com` URL. |
| Runtime DI & health | **PASS** | `get_storage_adapter()` selects `CloudflareR2StorageAdapter`; `GET /health` -> `200 ok`; `GET /ready` -> `200 connected`; `GET /v1/tryon/health` -> `200 healthy`, `provider.provider="mock"`, `storage.provider="r2"`, `storage.status="healthy"`, `storage.bucket="fansivibe-media-dev"`. |
| Wardrobe Media API lifecycle | **PASS** | Real JWT auth (`POST /v1/auth/register`) -> `POST /v1/media/uploads` (201) -> presigned R2 `PUT` (200, synthetic 64x64 WebP) -> `POST /v1/media/uploads/{id}/complete` (200 canonical WebP promotion & staging delete) -> `GET /v1/media/url` (401 unauth, 404 OW-1 other user, 200 owner presigned R2 GET + WebP decode) -> `POST /v1/wardrobe/items` (201) -> cleanup. |
| Virtual Try-On API lifecycle | **PASS** | `POST /v1/tryon/jobs` (401 unauth, 422 missing consent, 422 foreign garment, 202 owner with synthetic 128x128 JPEG persisted in R2) -> `GET /v1/tryon/jobs/{id}` (404 OW-1, 200 owner `completed` with mock `result.svg` in R2) -> `GET /v1/tryon/jobs/{id}/image` (401 unauth, 404 OW-1, 200 `image/svg+xml` with `TEST DATA`) -> `DELETE /v1/tryon/jobs/{id}` (404 OW-1, 204 owner deleting both R2 objects). |
| Leftover test objects & accounts | **PASS** | Both synthetic accounts deleted via `DELETE /v1/users/me` (204); `list_objects_v2` on `fansivibe-media-dev` confirmed `0` remaining keys. |

---

## 9. Remaining Blockers Before Live Genlook Verification

1. **Operator R2 Provisioning:** **DONE** — Private bucket `fansivibe-media-dev` and `backend/.env` R2 credentials provisioned (`0o600`, gitignored).
2. **Live R2 Connectivity, Runtime & Expiry Smoke Tests:** **DONE** — `verify_r2_live.py` (`PASS`), FastAPI runtime & app-level R2 lifecycles (`PASS`), and `verify_r2_expiry.py` (`PASS`, `200 -> 403 ExpiredRequest`) all verified with `0` leftover objects.
3. **Operator Genlook Enablement & Credits:** `GENLOOK_API_KEY` and explicit operator authorization to switch `FANSIVIBE_TRYON_PROVIDER=genlook` for live paid smoke testing remain pending.
4. **Pre-Production Compliance:** Genlook Data Processing Agreement (DPA) execution and legal review remain required before any production rollout.

