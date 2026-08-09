# Fansivibe — Media Upload Architecture

> **STEP 5 (final) — BACKEND ARCHITECTURE.** Designs the **image/media upload
> flow** for Fansivibe. **The backend must not unnecessarily proxy large
> image files through application memory.**
>
> Flow:
> **Flutter → Upload authorization → Object Storage → Media Asset → FastAPI →
> AI Processing (if required) → Domain Result**
>
> **Status: architecture design only. Nothing is implemented.** No code,
> directories, dependencies (S3 SDK, boto3, etc.), tables, or endpoints are
> created. Verified: the current repo has no media or object-storage code
> (`backend/app`, `backend/tests` — no s3/storage/multipart matches).
> `TABLE_DEFINITIONS.md` already records `media_assets` as a **non-table**
> (bytes live in object storage behind `MediaRef` columns, PR-8).

---

## 1. Purpose and scope

This document defines the **media lifecycle**: how a Flutter client gets a
media file (photo/scan/image) into Fansivibe **without the FastAPI process
buffering the bytes in memory**, and how the resulting **media asset** is
owned, referenced, processed, and deleted.

It covers all requested aspects:
- upload authorization
- file validation
- MIME type
- size limits
- ownership
- processing status
- deletion
- signed URLs
- private media
- public media

**Key invariant: PR-8 / no-bytes-in-app-memory.** The FastAPI process never
streams large files through RAM. Upload goes **directly from Flutter to
object storage** using a pre-authorized signed URL; FastAPI only records the
**reference** (a `MediaRef`) and orchestrates validation metadata + optional
AI processing (which reads from object storage, not from a client stream).

**Grounding rules from accepted docs:**
- **PR-8 (`DATABASE_DESIGN_RULES.md`):** bytes never in PostgreSQL; tables
  hold only `MediaRef` (object key + media type + optional display metadata);
  `media_assets` is a **non-table** concept — metadata is **soft-derived**
  via `MediaRef` JSONB columns, never a first-class table.
- **TRX-1 (`TRANSACTION_BOUNDARIES.md`):** upload-then-insert — the blob is
  placed in object storage **before** the DB reference insert; orphan blobs
  are swept.
- **API-44 (`API_LAYER_ARCHITECTURE.md`):** multipart upload-then-insert
  pattern; no direct memory proxying.
- **BACKGROUND_JOB_ARCHITECTURE.md:** large media processing is **ASYNC**
  (M16-gated); orphan sweep is a background job; media tasks persist
  `MediaRef`s, never bytes.
- **AUTH_AUTHORIZATION_ARCHITECTURE.md:** `media.user_id` ownership (OW-1);
  404-not-403; signed URL issuance is an owner-scoped operation.
- **MS10.3 (`SECURITY_PRIVACY_DESIGN.md`):** media is privacy-sensitive;
  private by default; erasure must delete bytes.
- **MODULE_MAP M16:** media module is **sealed** until MS10.3 is decided;
  today no media path exists (this doc designs the target).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `backend/app`, `backend/tests` | Verified: no media/object-storage code today. |
| `TABLE_DEFINITIONS.md` | `MediaRef` JSONB columns (`image_ref`, `input_media`); `media_assets` non-table; PR-8. |
| `TRANSACTION_BOUNDARIES.md` | TRX-1 upload-then-insert; orphan sweep post-commit. |
| `API_LAYER_ARCHITECTURE.md` | API-44 multipart upload-then-insert. |
| `BACKGROUND_JOB_ARCHITECTURE.md` | Large media processing ASYNC (M16); orphan sweep job. |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` | OW-1 ownership; signed URL = owner-scoped. |
| `SECURITY_PRIVACY_DESIGN.md` | MS10.3 privacy/erasure. |

---

## 3. The end-to-end flow (target)

```
Flutter
  │  1. POST /v1/media/uploads {purpose, filename, size, content_type}   (auth: Bearer user_id)
  ▼
FastAPI ──▶ upload authorization: owns? purpose allowed? size? MIME?
  │           returns {upload_id, signed PUT URL, expires_at}
  ▼
Flutter ──▶ Object Storage ──PUT bytes via signed URL──▶ (blob stored, zero FastAPI RAM)
  │
  │  2. POST /v1/media/uploads/{upload_id}/complete   (auth: Bearer)
  ▼
FastAPI ──▶ verify blob present + size/hash match → insert MediaRef
  │           (TRX-1 upload-then-insert; orphan sweep if never completed)
  ▼
  optional: AI processing job (ASYNC, reads from object storage)
  ▼
Domain Result (owner-scoped MediaRef available to UC-5…27 / media tasks)
```

**The FastAPI process never sees the file bytes** — only metadata + a
completed/reference confirmation. This satisfies "do not unnecessarily proxy
large image files through application memory."

---

## 4. Design decisions

### 4.1 Upload authorization

- `POST /v1/media/uploads` (authenticated, `get_current_user_id`):
  - validates the **purpose** (e.g. `scan`, `outfit_input`, `profile`,
    `generated`) — purpose must be in the allowed set for the caller
    (user purposes; system purpose reserved for internal generation).
  - validates **declared size + content_type** against limits (below).
  - returns a **signed PUT URL** (object storage, e.g. S3 presigned PUT) +
    `upload_id` + `expires_at`.
- **Only the URL is returned; no bytes flow through FastAPI.** The signed URL
  is scoped to the **owner** (OW-1) and to the single declared object key
  (prefix `users/{user_id}/...`), preventing cross-user writes.
- **Uploads are never completed without the authenticated owner.**

### 4.2 File validation

- Validation is **two-phase** (nothing can be fully validated before the
  bytes exist, but the process never buffers them):
  1. **Declared metadata** (at `POST /media/uploads`): size within limits,
     MIME in allow-list, purpose valid → issue signed URL.
  2. **Post-upload verification** (at `/complete`): FastAPI checks the blob
     via **object-storage metadata/HEAD** (size, content-type, checksum —
     read from the storage provider, not from memory): size matches declared
     (abuse guard), content-type matches allow-list, optional content hash.
- **AI/malware inspection** (if required) runs in the **async processing
   job** reading the blob from object storage — still no app-memory proxy.

### 4.3 MIME type

- Allow-list (server-controlled): `image/jpeg`, `image/png`, `image/webp`
  (+ `image/heic` if supported by the pipeline), and for generated images the
  service's own output MIMEs. Client-declared MIME must match the verified
  blob content-type (reject mismatch → 422 `MEDIA_FAILURE`/validation).
- MIME is recorded on the `MediaRef` (`media_type`) for display without
  opening the blob.

### 4.4 Size limits

- Per-purpose limits (config-driven, expandable — no hardcoded constants):
  - `scan` / `outfit_input` / `profile`: e.g. ≤ 15–20 MB (vision input).
  - `generated`: bounded by service output.
- Limits are enforced **twice**: declared (at authorization) and verified
  (at `/complete` via HEAD size). A blob exceeding limits is **rejected and
  marked for orphan sweep** (never referenced).
- **Rejection never proxies the bytes** — HEAD checks only.

### 4.5 Ownership

- Object key is namespaced: `users/{user_id}/{upload_id}.{ext}`.
- `MediaRef` rows/references carry `user_id` (OW-1): every query (GET/update/
  complete/delete/sign) is filtered by the authenticated user. Cross-user
  access → 404-not-403 (API-10).
- Children (analysis runs, media tasks) inherit the parent's ownership.

### 4.6 Processing status

- A media **asset reference** carries a lifecycle state:
  `pending_upload → uploaded → processing (optional) → ready | failed`.
- State is **row-derived** (per BACKGROUND_JOB_ARCHITECTURE §5): an upload
  row transitions `pending_upload → uploaded` at `/complete`; if an AI
  processing job is required (analysis, generation), it transitions
  `processing → ready | failed` write-once (TRX-5), exposing `error.code`
  (`MEDIA_FAILURE`, `AI_FAILURE`, `PROCESSING_FAILURE`).
- **No AI processing for plain photos that need none** — the job is created
  only when the consuming use case requires it ("if required").

### 4.7 Deletion

- Owner-scoped `DELETE /v1/media/…` marks the reference deleted (logical
  tombstone for audit/erasure) and **enqueues byte deletion** (object
  storage delete) as an **async post-commit sweep** (TRX-1 §5 / job
  architecture §5.5).
- **Erasure (MS10.3)** requires byte deletion in object storage + reference
  removal — the async sweep guarantees this.
- **Orphan sweep:** any uploaded blob without a completed reference (aborted,
  validation-rejected, failed job) is deleted by the periodic cleanup job.

### 4.8 Signed URLs

- **Upload** (PUT): signed, short-lived (e.g. 10–15 min), single key,
  owner-scoped, `Content-Type`/size pinned at issuance.
- **Download** (GET): issued **per-request** by an owner-scoped endpoint,
  short-lived, only for the owning user (or the system/generated pipeline).
- **Never stored/returned as long-lived URLs in the DB** — `MediaRef` holds
  the object key, not a URL; URLs are minted on demand (revocable via
  signature expiry + key rotation).

### 4.9 Private media

- **Default: private.** Every user-owned media reference is private; blob
  access is denied unless a signed URL is minted for the owner.
- Access rules: owner only; admin only via audited elevated path; system
  (AI pipeline) via its service principal reading within its own job scope.
- Privacy-sensitive (MS10.3): no public CDN exposure, no unauthenticated
  reads, no URLs in logs.

### 4.10 Public media

- **Public media is the exception, explicitly opted-in and bounded:** only
  **generated output** the user chooses to share (or explicit `public=true`
  flags on a *whitelisted* purpose like a shareable saved look) becomes
  readable via a signed/stable public URL.
- Public URLs are minted from `MediaRef` + `public` flag; the **bytes stay in
  object storage** (never re-proxied through FastAPI on every request).
- **No user scan/photo is ever public by default** (MS10.3; no shame, no
  exposure). Revocation = delete/unsign.

---

## 5. Current state and sequencing

- **Today:** no media code exists; assistant has no media path (A3.1).
- **M1–M4:** no media changes; assistant + 19 tests stay green.
- **M16 (media module) is sealed** until MS10.3 (media privacy/erasure) is
  decided. The media upload flow **ships only with M16**, implementing:
  `POST /v1/media/uploads` (+`/complete`), object storage adapter
  (`infrastructure/storage`), ownership-guarded MediaRef columns, orphan
  sweep job, signed URL minting.
- Until M16: `MediaRef` columns exist in the schema (PR-8) but no upload
  endpoints are exposed.

---

## 6. Report, assumptions, constraints

**What changed (this step):** added `MEDIA_UPLOAD_ARCHITECTURE.md` — the
media upload flow design. Nothing implemented.

**Skills used:** repository analysis (verified no media/storage code in
`backend/app` + `backend/tests`; `TABLE_DEFINITIONS.md` records
`media_assets` as a non-table with `MediaRef` JSONB) — architecture
documentation only.

**Files changed:** `docs/backend/MEDIA_UPLOAD_ARCHITECTURE.md` (new).

**Validation run:**
- Flow matches the required chain: Flutter → upload authorization → object
  storage → media asset → FastAPI → AI processing (if required) → domain
  result, and **no large file is proxied through FastAPI memory** (signed
  direct PUT; FastAPI only does HEAD/metadata checks + DB reference).
- Each requested consideration is addressed: upload authorization (§4.1),
  file validation (§4.2), MIME type (§4.3), size limits (§4.4), ownership
  (§4.5), processing status (§4.6), deletion (§4.7), signed URLs (§4.8),
  private media (§4.9), public media (§4.10).
- Consistent with accepted docs: PR-8 (no bytes in PG, MediaRef), TRX-1
  (upload-then-insert + orphan sweep), API-44, OW-1 (owner-scoped), MS10.3
  (private by default, erasure deletes bytes), job architecture (async
  processing + sweep, row-derived status).
- `git status --short`: only this new doc + `CURRENT_STATE.md` update; no
  code, directories, or files created. No pytest run needed (no code change).

**Remaining issues / follow-ups:**
- **Concrete object-storage provider** (S3-compatible vs GCS vs MinIO) is
  **not chosen** — this doc defines the `infrastructure/storage` adapter seam;
  the provider choice and SDK (e.g. boto3) land with M16. No dependency added.
- **MS10.3 remains open** — it gates M16; until decided, the media module is
  sealed and this flow is not implemented.
- Signed URL duration, size limits, and MIME allow-list are examples; exact
  values are config-driven and finalized at M16.
- No `DECISIONS.md` entry added (documentation only).

**Assumptions recorded:**
- Object storage is S3-compatible (bounded assumption for the adapter seam;
  provider-neutral otherwise).
- FastAPI performs metadata-only verification (HEAD/size/type/hash) at
  `/complete`; byte-level scanning (if any) happens in the async job.
- Private-by-default (MS10.3); public media is explicit, whitelisted, and
  revocable.
- Generated images are stored as media assets too (reuse the same flow).

**Constraints honored:** PR-8 (no bytes in PG/app memory), TRX-1
(upload-then-insert, orphan sweep), API-44 (multipart upload-then-insert),
OW-1 (owner-scoped media), MS10.3 (privacy/erasure), job architecture (async
processing, row-derived status, sweep), the Scope rule (this document only),
and no implementation (media module sealed until M16/MS10.3).