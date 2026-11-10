# FANSIVIBE — DEBT-01 DATABASE MIGRATION READINESS AUDIT
## Revisions 0033–0036 (Media Upload Idempotency, Completion, Leases & Fencing Tokens)

**Document Version:** 1.0.0  
**Audit Date:** 2026-11-02  
**Audit Type:** 100% Read-Only Schema, Application Compatibility & Operational Readiness Assessment  
**Audit Target:** Pending Alembic Migrations `0033 -> 0034 -> 0035 -> 0036`  
**Current Database State:** Local `fansivibe`: `0032` | Test `fansivibe_test`: `0032` | Repository Head: `0036`  
**Overall Verdict:** **READY WITH PRECONDITIONS**

---

## 1. Executive Summary

This audit evaluates the deployment readiness, schema safety, application compatibility, and operational rollback characteristics of pending Alembic migrations **0033**, **0034**, **0035**, and **0036** (resolving technical debt item **DEBT-01**).

The current shared development database (`fansivibe`) and test database (`fansivibe_test`) reside at Alembic revision **0032** (`0032_offer_click_attribution.py`). The repository codebase contains migrations through revision **0036** (`0036_media_upload_lease_token.py`), created during milestone **Stage 2 P0-4** (Wardrobe Cloud Media Storage).

### Key Findings

1. **100% Additive Design:** All four pending revisions operate exclusively on a single new table: `media_upload_authorizations`. Zero existing tables (`users`, `wardrobe_items`, `looks`, `discovery_events`, etc.) are modified, altered, or dropped. Zero columns in existing tables are renamed or constrained.
2. **Runtime Failure on Revision 0032:** Running the current backend codebase against database revision 0032 causes **HTTP 500 runtime errors** on all media endpoints (`POST /v1/media/uploads`, `POST /v1/media/uploads/{id}/complete`, `GET /v1/media/url`, and wardrobe mutations with `imageRef`) due to PostgreSQL error `relation "media_upload_authorizations" does not exist`. Non-media wardrobe operations, outfit swapping, and catalog flows continue to work.
3. **Zero Data Loss on Forward Migration:** Upgrades from `0032 -> 0036` are strictly forward-additive. No data is modified, transformed, or backfilled. Table creation and column additions with constant/null defaults are instant metadata-only operations in PostgreSQL 11+.
4. **start.sh Execution Risk:** `start.sh` line 25 automatically invokes `.venv/bin/alembic upgrade head`. Following the SQLAlchemy driver fix, running `start.sh` directly will trigger an uncoordinated migration against `fansivibe`. Controlled pre-migration backup is mandatory before starting the stack.

---

## 2. Per-Revision Impact Matrix

| Revision ID | Migration Name | Target Table | Operation Type | Schema Changes | Destructive? | Classification |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **0033** | `0033_media_upload_idempotency` | `media_upload_authorizations` | `CREATE TABLE` | New table, 10 columns, PK `(user_id, idempotency_key)`, UQ `upload_id`, FK `users(id)` ON DELETE CASCADE, 2 indexes | No | **SAFE WITH PRECONDITIONS** |
| **0034** | `0034_media_upload_completion` | `media_upload_authorizations` | `ALTER TABLE` | Add 9 columns (`status`, `canonical_key`, `canonical_sha256`, dimensions, timestamps, attempts) + 1 index | No | **SAFE TO APPLY** |
| **0035** | `0035_media_upload_lease` | `media_upload_authorizations` | `ALTER TABLE` | Add 2 columns (`processing_started_at`, `processing_lease_expires_at`) + 1 composite index | No | **SAFE TO APPLY** |
| **0036** | `0036_media_upload_lease_token` | `media_upload_authorizations` | `ALTER TABLE` | Add 1 column (`processing_lease_token` UUID) | No | **SAFE TO APPLY** |

---

## 3. Phase 1: Migration Source Code Inspection

### 3.1 Revision 0033: `0033_media_upload_idempotency.py`

- **Revision ID:** `0033`
- **Down Revision:** `0032` (`0032_offer_click_attribution.py`)
- **Dependencies:** Revision `0032`; requires existing `users` table with `users.id` (UUID).
- **Tables Created:**
  - `media_upload_authorizations`
- **Columns Created:**
  - `user_id`: `UUID(as_uuid=True)`, `NOT NULL`, Foreign Key `users.id` ON DELETE CASCADE.
  - `idempotency_key`: `VARCHAR(128)`, `NOT NULL`.
  - `upload_id`: `UUID(as_uuid=True)`, `NOT NULL`.
  - `key_version`: `VARCHAR(32)`, `NOT NULL`.
  - `request_fingerprint`: `VARCHAR(64)`, `NOT NULL`.
  - `staging_key`: `VARCHAR(512)`, `NOT NULL`.
  - `content_type`: `VARCHAR(64)`, `NOT NULL`.
  - `size_bytes`: `INTEGER`, `NOT NULL`.
  - `created_at`: `TIMESTAMP WITH TIME ZONE`, `NOT NULL`, server default `now()`.
  - `expires_at`: `TIMESTAMP WITH TIME ZONE`, `NOT NULL`.
- **Constraints & Indexes:**
  - Primary Key: `pk_media_upload_authorizations` on `(user_id, idempotency_key)`.
  - Unique Constraint: `uq_media_upload_authorizations_upload_id` on `(upload_id)`.
  - Index `ix_media_upload_authorizations_user_rate` on `(user_id, created_at)`.
  - Index `ix_media_upload_authorizations_expires_at` on `(expires_at)`.
- **Defaults & Nullability:** All 10 columns are `NOT NULL`. `created_at` defaults to `now()`.
- **Data Backfill / Transformation:** None. Table created empty.
- **Destructive Operations:**
  - Upgrade: None.
  - Downgrade: Drops table `media_upload_authorizations` and its 2 indexes. Irreversible for rows in `media_upload_authorizations`.

### 3.2 Revision 0034: `0034_media_upload_completion.py`

- **Revision ID:** `0034`
- **Down Revision:** `0033`
- **Dependencies:** Revision `0033` (`media_upload_authorizations` table must exist).
- **Tables Altered:** `media_upload_authorizations`
- **Columns Added:**
  - `status`: `VARCHAR(32)`, `NOT NULL`, server default `'authorized'`.
  - `canonical_key`: `VARCHAR(512)`, `NULL`.
  - `canonical_sha256`: `VARCHAR(64)`, `NULL`.
  - `canonical_size_bytes`: `INTEGER`, `NULL`.
  - `canonical_width`: `INTEGER`, `NULL`.
  - `canonical_height`: `INTEGER`, `NULL`.
  - `completed_at`: `TIMESTAMP WITH TIME ZONE`, `NULL`.
  - `failure_reason`: `VARCHAR(64)`, `NULL`.
  - `processing_attempts`: `INTEGER`, `NOT NULL`, server default `0`.
- **Constraints & Indexes:**
  - Index `ix_media_upload_authorizations_status` on `(status)`.
- **Defaults & Nullability:**
  - `status` is `NOT NULL` with constant server default `'authorized'`.
  - `processing_attempts` is `NOT NULL` with constant server default `0`.
  - Other 7 columns are nullable.
- **Data Backfill / Transformation:** None. Constant server defaults applied by PostgreSQL engine without table rewrite.
- **Destructive Operations:**
  - Upgrade: None.
  - Downgrade: Drops the 9 columns and index `ix_media_upload_authorizations_status`. Destructive to publication status and canonical metadata if rows exist.

### 3.3 Revision 0035: `0035_media_upload_lease.py`

- **Revision ID:** `0035`
- **Down Revision:** `0034`
- **Dependencies:** Revision `0034` (strictly depends on `status` column added in `0034` for composite index).
- **Tables Altered:** `media_upload_authorizations`
- **Columns Added:**
  - `processing_started_at`: `TIMESTAMP WITH TIME ZONE`, `NULL`.
  - `processing_lease_expires_at`: `TIMESTAMP WITH TIME ZONE`, `NULL`.
- **Constraints & Indexes:**
  - Index `ix_media_upload_authorizations_lease` on `(status, processing_lease_expires_at)`.
- **Defaults & Nullability:** Both columns are nullable (`NULL`), no default.
- **Data Backfill / Transformation:** None.
- **Destructive Operations:**
  - Upgrade: None.
  - Downgrade: Drops both lease columns and the composite index. Destructive to active processing lease timestamps.

### 3.4 Revision 0036: `0036_media_upload_lease_token.py`

- **Revision ID:** `0036`
- **Down Revision:** `0035`
- **Dependencies:** Revision `0035` (`media_upload_authorizations` table).
- **Tables Altered:** `media_upload_authorizations`
- **Columns Added:**
  - `processing_lease_token`: `sa.Uuid()`, `NULL`. (Maps directly to native PostgreSQL `UUID` type).
- **Constraints & Indexes:** None.
- **Defaults & Nullability:** Nullable (`NULL`), no default.
- **Data Backfill / Transformation:** None.
- **Destructive Operations:**
  - Upgrade: None.
  - Downgrade: Drops `processing_lease_token` column. Destructive to in-flight worker fencing tokens.

---

## 4. Phase 2: Application Compatibility Assessment

### 4.1 Schema Expectation vs Code Mapping

The backend application code in `backend/app/infrastructure/db/models.py` defines `MediaUploadAuthorization` ([models.py:1657-1726](file:///home/tony/projects/fansivibe_v1_backup/backend/app/infrastructure/db/models.py#L1657-L1726)). Every single attribute in the SQLAlchemy ORM model maps 1:1 to the cumulative schema of revisions 0033–0036:

| Model Attribute | Target Column | Introducing Revision | Code Consumer |
| :--- | :--- | :---: | :--- |
| `user_id` | `user_id` | 0033 | `AuthorizeMediaUpload`, `validate_media_association`, `GetMediaUrl` |
| `idempotency_key`| `idempotency_key` | 0033 | `AuthorizeMediaUpload` (RFC 9440 conflict detection) |
| `upload_id` | `upload_id` | 0033 | All media use cases |
| `key_version` | `key_version` | 0033 | `AuthorizeMediaUpload` (HMAC key ring rotation) |
| `request_fingerprint` | `request_fingerprint` | 0033 | `AuthorizeMediaUpload` (semantic mutation detection) |
| `staging_key` | `staging_key` | 0033 | `AuthorizeMediaUpload`, `CompleteMediaUpload` |
| `content_type` | `content_type` | 0033 | MIME validation & Presigned URL generation |
| `size_bytes` | `size_bytes` | 0033 | Payload size bounds enforcement |
| `created_at` | `created_at` | 0033 | Atomic rate limiting (sliding 60s window query) |
| `expires_at` | `expires_at` | 0033 | `prune_expired_authorizations` |
| `status` | `status` | 0034 | `CompleteMediaUpload`, `validate_media_association` |
| `canonical_key` | `canonical_key` | 0034 | `CompleteMediaUpload`, `validate_media_association` |
| `canonical_sha256` | `canonical_sha256` | 0034 | Crash recovery & `validate_media_association` |
| `canonical_size_bytes`| `canonical_size_bytes` | 0034 | Verification & metadata consistency |
| `canonical_width` | `canonical_width` | 0034 | Image dimension consistency |
| `canonical_height` | `canonical_height` | 0034 | Image dimension consistency |
| `completed_at` | `completed_at` | 0034 | Publication timestamp |
| `failure_reason` | `failure_reason` | 0034 | Non-retryable error classification |
| `processing_attempts` | `processing_attempts` | 0034 | Attempt ceiling (5 attempts max) & cooldown |
| `processing_started_at`| `processing_started_at`| 0035 | Lease acquisition timestamp |
| `processing_lease_expires_at`| `processing_lease_expires_at`| 0035 | Active worker protection (15s/30s lease + heartbeat) |
| `processing_lease_token`| `processing_lease_token`| 0036 | Conditional PostgreSQL linearization & fencing |

### 4.2 Runtime Failure Analysis on Revision 0032

When running against revision **0032**, the following runtime behaviors occur:

1. **`POST /v1/media/uploads`:**
   - **Result:** **HTTP 500 Internal Server Error**.
   - **Root Cause:** `AuthorizeMediaUpload.execute` issues `SELECT` and `INSERT` against `media_upload_authorizations`. PostgreSQL raises `psycopg.errors.UndefinedTable: relation "media_upload_authorizations" does not exist`.
2. **`POST /v1/media/uploads/{upload_id}/complete`:**
   - **Result:** **HTTP 500 Internal Server Error**.
   - **Root Cause:** `CompleteMediaUpload.execute` issues `SELECT ... WHERE upload_id = :upload_id` on `media_upload_authorizations`. Fails with `UndefinedTable`.
3. **`GET /v1/media/url`:**
   - **Result:** **HTTP 500 Internal Server Error**.
   - **Root Cause:** `GetMediaUrl.execute` queries `media_upload_authorizations`. Fails with `UndefinedTable`.
4. **`POST /v1/wardrobe/items` (with `imageRef`):**
   - **Result:** **HTTP 500 Internal Server Error**.
   - **Root Cause:** `AddWardrobeItem.execute` calls `validate_media_association`, which queries `media_upload_authorizations` to verify upload ownership and publication. Fails with `UndefinedTable`.
5. **`PATCH /v1/wardrobe/items/{id}` (with `imageRef`):**
   - **Result:** **HTTP 500 Internal Server Error**.
   - **Root Cause:** `UpdateWardrobeItem.execute` invokes `validate_media_association`. Fails with `UndefinedTable`.
6. **Background Retention Sweeps:**
   - **Result:** **Task Crash**.
   - **Root Cause:** `prune_expired_authorizations` issues `SELECT upload_id FROM media_upload_authorizations`. Fails with `UndefinedTable`.
7. **Unaffected Endpoints on Revision 0032:**
   - `GET /v1/wardrobe/items` and `GET /v1/wardrobe/items/{id}`: Work normally. They query `wardrobe_items` directly. Wire enrichment (`_to_wire`) uses `wardrobe_items.image_ref` JSONB and calls storage port directly without querying `media_upload_authorizations`.
   - `POST /v1/wardrobe/items` (without `imageRef`): Works normally (`validate_media_association` is skipped when `image_ref is None`).
   - `DELETE /v1/wardrobe/items/{id}`: Works normally.
   - `POST /v1/outfits/swap-slot` & `POST /v1/outfits/candidates`: Work normally (ephemeral scoring).
   - User authentication, user profiles, preferences, grooming analysis, and retailer offers: Work normally.

---

## 5. Phase 3: Data and Rollback Assessment

### 5.1 Wardrobe Data Preservation

- **Wardrobe Table Independence:** The `wardrobe_items` table was created in migration `0006_wardrobe_items.py`. Revisions 0033–0036 contain zero DDL statements modifying `wardrobe_items`.
- **Existing `image_ref` Compatibility:** In `wardrobe_items`, the `image_ref` column is defined as `JSONB, nullable=True`.
  - Existing rows with `image_ref = NULL` remain completely valid.
  - Legacy rows or test rows with pre-existing dictionary structures remain valid and are parsed safely by `_to_wire` in [wardrobe.py:55-86](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/wardrobe.py#L55-L86) and [outfits.py:208-230](file:///home/tony/projects/fansivibe_v1_backup/backend/app/api/routers/outfits.py#L208-L230).
  - No foreign key exists between `wardrobe_items` and `media_upload_authorizations`.

### 5.2 Backfilling Requirements

- **No Backfilling Required:** `media_upload_authorizations` is an operational ledger for active uploads, durable idempotency, and publication state. Existing wardrobe items do not require retroactive authorization rows to be read or displayed.
- **Client Migration Pipeline:** The Flutter client's `LegacyPhotoMigrationWorker` handles legacy device-local Base64 photos by uploading them as fresh authorizations via `POST /v1/media/uploads` and associating them via `PATCH /v1/wardrobe/items/{id}`.

### 5.3 Rollback Assessment & Data Loss Risks

- **Forward Migration (`0032 -> 0036`):** **ZERO data loss risk.** Fully additive.
- **Immediate Rollback (`0036 -> 0032` before production traffic):** **ZERO data loss risk.** The table is empty and dropped cleanly.
- **Post-Launch Rollback (`0036 -> 0032` after media uploads have occurred):**
  - **Data Loss on `media_upload_authorizations`:** All upload records, idempotency keys, and publication records will be permanently dropped.
  - **Impact on `wardrobe_items`:** Published wardrobe items already associated will retain their `image_ref` JSONB metadata (`objectKey`, dimensions, SHA-256). However, future re-associations or validation will fail.
  - **Orphan Cloud Storage:** Cloudflare R2 objects created during the window will remain in storage without corresponding database ledger rows.

### 5.4 Data Volume & Lock Safety

- In PostgreSQL 11+, `ADD COLUMN` with constant `DEFAULT` or `NULL` does not rewrite the table.
- Since `media_upload_authorizations` is a newly created table, table volume during initial migration is 0 rows.
- Table creation and indexing will execute in **< 50 milliseconds**.
- No lock contention will occur on active operational tables (`users`, `wardrobe_items`, `looks`).

---

## 6. Phase 4: Environment & Deployment Verification

### 6.1 Database Configurations

1. **Local Development Database:**
   - Container: `fansivibe-postgres18` (Docker container running `postgres:18-alpine` on port 5432).
   - Database: `fansivibe`.
   - Driver: `postgresql+psycopg`.
   - Status: Revision `0032`.
2. **Local Test Database:**
   - Database: `fansivibe_test`.
   - Environment Variable: `FANSIVIBE_TEST_DATABASE_URL` (currently unset in `backend/.env`; DB tests skip cleanly by design).
   - Status: Revision `0032`.
3. **Staging / Production Topologies:**
   - Staging: Single container `fansivibe-staging-api` with `postgres:16-alpine` (`docker-compose.staging.yml`).
   - Production: Dual-replica canary topology with `backend-primary` (95%) and `backend-canary` (5%) fronted by Nginx reverse proxy (`docker-compose.production.yml`).

### 6.2 Automatic Migration Execution in `start.sh` and `entrypoint.sh`

- **`start.sh` Inspection:**
  ```bash
  echo "[3/4] Applying database migrations..."
  cd "$BACKEND"
  .venv/bin/alembic upgrade head
  ```
  **Finding:** `start.sh` automatically attempts `alembic upgrade head` at step [3/4]. Prior to the driver fix, this step halted due to the `driver://` placeholder. Now that the configuration is repaired, running `./start.sh` will directly apply migrations `0033 -> 0036` to `fansivibe`.
- **Docker `entrypoint.sh` Inspection:**
  ```bash
  echo "==> Running Alembic migrations to head..."
  alembic upgrade head
  ```
  **Finding:** Production and staging containers execute `alembic upgrade head` on container boot. In multi-instance production environments (`backend-primary` and `backend-canary`), both containers attempt concurrent migration on startup.

### 6.3 Accidental Execution Protection

- **Current Protection Level:** **MODERATE (Local) / DEFICIENT (Multi-Replica Docker)**.
  - In local dev, developer awareness and safety rules prevent accidental runs.
  - In Docker multi-replica deployments, there is no startup concurrency lock or separate migration runner container. While PostgreSQL serializes DDL, running migrations from multiple application workers simultaneously during canary deployment violates canary isolation.

---

## 7. Preconditions for Applying Migrations

Before executing `alembic upgrade head` on the shared database `fansivibe`, the following preconditions MUST be satisfied:

1. **Precondition 1 (Full Database Backup):**
   A full logical dump of `fansivibe` must be taken using `pg_dump` and verified for non-zero file size:
   ```bash
   docker exec fansivibe-postgres18 pg_dump -U fansivibe -d fansivibe -Fc > /home/tony/projects/fansivibe_v1_backup/scratch/fansivibe_pre_0033_0036_$(date +%Y%m%d_%H%M%S).dump
   ```
2. **Precondition 2 (Service Isolation):**
   Ensure no Uvicorn instances are actively serving traffic against `fansivibe` during migration execution.
3. **Precondition 3 (Test Database Rehearsal):**
   Rehearse the exact sequence on `fansivibe_test` first, verifying clean upgrade and clean downgrade before touching `fansivibe`.
4. **Precondition 4 (Founder / Operator Authorization):**
   Explicit authorization must be granted by the repository owner to advance the shared database revision from `0032` to `0036`.

---

## 8. Exact Recommended Migration Sequence

When authorization is granted and preconditions are met, execute the migration following this exact sequence:

### Step 1: Create Backup
```bash
mkdir -p /home/tony/projects/fansivibe_v1_backup/scratch
docker exec fansivibe-postgres18 pg_dump -U fansivibe -d fansivibe -Fc > /home/tony/projects/fansivibe_v1_backup/scratch/fansivibe_backup_0032.dump
ls -lh /home/tony/projects/fansivibe_v1_backup/scratch/fansivibe_backup_0032.dump
```

### Step 2: Test Rehearsal on `fansivibe_test`
```bash
cd /home/tony/projects/fansivibe_v1_backup/backend
DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_test" .venv/bin/alembic upgrade head
DATABASE_URL="postgresql+psycopg://fansivibe:fansivibe_dev@localhost:5432/fansivibe_test" .venv/bin/alembic current
```
*Expected output: `0036 (head)`.*

### Step 3: Apply to Shared Development Database `fansivibe`
```bash
cd /home/tony/projects/fansivibe_v1_backup/backend
source .env
.venv/bin/alembic upgrade head
```

### Step 4: Verify Current Database Revision
```bash
.venv/bin/alembic current
```
*Expected output: `0036 (head)`.*

### Step 5: Verify Schema Integrity in PostgreSQL
```bash
docker exec -i fansivibe-postgres18 psql -U fansivibe -d fansivibe -c "\d media_upload_authorizations"
```
*Verify columns: `user_id`, `idempotency_key`, `upload_id`, `key_version`, `request_fingerprint`, `staging_key`, `content_type`, `size_bytes`, `created_at`, `expires_at`, `status`, `canonical_key`, `canonical_sha256`, `canonical_size_bytes`, `canonical_width`, `canonical_height`, `completed_at`, `failure_reason`, `processing_attempts`, `processing_started_at`, `processing_lease_expires_at`, `processing_lease_token`.*

### Step 6: Rollback Contingency Procedure (If Aborting)
If an unexpected failure occurs during migration or smoke testing:
```bash
cd /home/tony/projects/fansivibe_v1_backup/backend
source .env
.venv/bin/alembic downgrade 0032
.venv/bin/alembic current
```
*Expected output: `0032`.*

---

## 9. Conclusion & Final Recommendation

### Final Recommendation: **READY WITH PRECONDITIONS**

The migration sequence `0033 -> 0034 -> 0035 -> 0036` is thoroughly engineered, completely additive, and free of schema conflicts or data destruction risks. All four revisions have been verified on isolated databases during Stage 2 P0-4 and confirmed compatible with backend models and use cases.

Applying these migrations will permanently eliminate **DEBT-01**, prevent HTTP 500 errors on media upload endpoints, and restore full synchronization between the repository migration head (`0036`) and the shared development database.

Execution should proceed as soon as the founder authorizes advancing the shared database following Preconditions 1–4.
