# Fansivibe — Media Storage Design

> **STEP 4 (continuation) — DATABASE DESIGN.** Defines the PostgreSQL **metadata
> model** for every Fansivibe media type. **The database never stores large
> image binaries** (PR-8): binaries live in **object storage**, and PostgreSQL
> holds only a `MediaRef` value (object key/URL + media type + display
> metadata) on the owning row. No media table is created; no blob column exists.
>
> **Status: documentation only. No storage is implemented. No SQL, no
> PostgreSQL database, no migrations, no repositories, no endpoints, no object
> storage buckets created, no application code changes, nothing deleted.**
>
> **Sources:** `DATABASE_DESIGN_RULES.md` PR-8 + §9 (media policy, `MediaRef`
> shape, MS10.3 gate), `DOMAIN_TABLE_MAPPING.md` §3/§5 (`MediaRef` verdict),
> `TABLE_DEFINITIONS.md` (`image_ref`, `input_media`, `snapshot` columns),
> `RELATIONSHIP_CONSTRAINTS.md` (§6 no-media-FK, CASCADE user lifecycle),
> `HISTORY_AND_VERSIONING.md` (scan/snapshot retention), `STORAGE_INVENTORY.md`
> (object-storage assignments and retention per object), and the domain docs
> (R19/R29/R37, `MediaRef` in `DOMAIN_ENTITIES.md` §3.1).

---

## 1. Purpose and method

Object storage is assumed for **all** binary files; the domain model explicitly
requires no other strategy for any media type (verified across the domain docs —
every media relationship is `MediaRef → object storage`, R19/R29/R37). This
document defines:

| # | Element | Meaning |
| --- | --- | --- |
| 1 | Owner | Who owns the blob (user / system / AI-output-bound-to-user). |
| 2 | Purpose | Why the image exists. |
| 3 | Storage location | The object-storage bucket/prefix layout. |
| 4 | Metadata | What PostgreSQL stores about the blob (the `MediaRef` JSONB value). |
| 5 | MIME type | Allowed media types. |
| 6 | Dimensions | Stored display metadata (width/height; variant thumbnails). |
| 7 | created_at | Where the creation time lives (`uploaded_at` in the ref + owner row time). |
| 8 | Deletion behavior | When and how the blob is removed. |
| 9 | Retention considerations | How long it is kept, per policy. |
| 10 | Relationship to domain entity | The referencing table/column and lifecycle. |

**Gate:** per rules-doc §9, **no media *storage* is implemented until the
media-privacy policy (MS10.3) is decided.** The `MediaRef` reference columns
below are already part of the schema; the object-storage configuration and blob
lifecycle are gated on MS10.3.

---

## 2. Core principle — the database stores references, never bytes

- PostgreSQL stores **no `BYTEA` column, no base64, no media table**.
- Each binary lives in object storage; the owning row holds a **`MediaRef`**
  JSONB value that points at it (`DOMAIN_TABLE_MAPPING.md` §3.6, §5).
- The `MediaRef` value has **no FK** and no join axis (rules §8) — it is
  reference metadata, read whole with its owner (`RELATIONSHIP_CONSTRAINTS.md`
  §6: no media FK).
- Blob lifecycle **follows the referencing row** (§7): delete the row → the blob
  is deleted by a cleanup job; retention rules decide when rows (and their
  blobs) are pruned (§8).

---

## 3. The `MediaRef` logical contract

The JSONB shape stored in `image_ref` / `input_media` columns (and embedded in
`snapshot` payloads where images ride along). Fields in **bold** are always
present; the rest are optional display/integrity metadata.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| **`object_key`** | `text` | yes | Object-storage key (or signed URL) of the binary (§4 layout). |
| **`media_type`** | `text` | yes | MIME type (e.g. `image/jpeg`). |
| `width` | `int` | no | Display width in px (thumbnail/derived; never used as a query axis). |
| `height` | `int` | no | Display height in px. |
| `size_bytes` | `int` | no | Binary size, for budgeting/quota. |
| `content_hash` | `text` | no | e.g. `sha256:...` — integrity/dedup, never a join key. |
| `is_generated` | `bool` | no | True for AI-generated output (distinct audit/retention semantics, §8). |
| `uploaded_at` | `timestamptz` | no | When the blob was written; the row's `created_at` remains the entity time. |
| `variants` | `jsonb` | no | Optional `{thumb: {object_key,width,height}}` references for downscaled copies. |

**Why JSONB here (per `JSONB_STRATEGY.md` §4.10):** the reference is a small,
optional-metadata value read as a unit with its owner; it is never filtered,
joined, or counted; it points **outward** to object storage. A media table or
typed columns would add empty fields and a join axis that does not exist.

---

## 4. Storage-location layout (object-storage prefixes)

Binaries are namespaced by owner and kind so keys are user-scoped (PR-10),
auditable, and enumerable for cleanup:

| Area | Prefix pattern | Example |
| --- | --- | --- |
| User-uploaded (wardrobe/other) | `users/{user_id}/wardrobe/{item_id}/main.{ext}` | `users/u1/wardrobe/w1/main.jpg` |
| Scan inputs (face/outfit) | `users/{user_id}/scans/{run_id}/input.{ext}` | `users/u1/scans/r42/input.jpg` |
| Generated output | `users/{user_id}/generated/{run_id}/{seq}.{ext}` | `users/u1/generated/r42/1.jpg` |
| Saved-look images | `users/{user_id}/savedlooks/{saved_look_id}/main.{ext}` | `users/u1/savedlooks/s9/main.jpg` |
| Profile/avatar (future) | `users/{user_id}/avatar.{ext}` | `users/u1/avatar.jpg` |
| System catalog (discover/hairstyle refs) | `catalog/{catalog_kind}/{code}/{variant}.{ext}` | `catalog/looks/lk-01/main.jpg` |

Buckets themselves are a deployment concern (object storage config, gated by
MS10.3); the prefix scheme above is the key contract the DB metadata records.

---

## 5. Media-type catalog — master matrix

| Media type | Owner | Purpose | DB home (reference) | Storage prefix | MIME | Deletion | Retention |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Profile image | User | avatar/identity display | **future** `users`/`user_state` `avatar_ref` (no column today) | `users/{user_id}/avatar` | `image/jpeg`, `image/png`, `image/webp` | replaced on change; deleted with account | user lifecycle |
| Face scans | User | face-analysis input evidence (R37) | `analysis_runs.input_media` | `users/{user_id}/scans/{run_id}` | `image/jpeg`, `image/png` | deleted with run/user; auto-expire unless saved | §1.6: latest per source; older pruned unless saved |
| Outfit scans | User | outfit-analysis input evidence | `analysis_runs.input_media` | `users/{user_id}/scans/{run_id}` | `image/jpeg`, `image/png`, `image/webp` | same as face scans | same as face scans |
| Wardrobe item images | User | item display in wardrobe (R19) | `wardrobe_items.image_ref` | `users/{user_id}/wardrobe/{item_id}` | `image/jpeg`, `image/png`, `image/webp` | deleted with the item (CASCADE) | user lifecycle |
| Hairstyle reference images | System | catalog references for hair analysis (P1) | system catalog content (future `looks`/catalog refs) | `catalog/hairstyles/{code}` | `image/jpeg`, `image/png` | never user-deleted; deprecate | versioned content, deprecate not delete |
| Generated images | User-bound AI output | AI-generated look/result images | inside `analysis_runs.result` / `saved_looks.snapshot` (refs) | `users/{user_id}/generated/{run_id}` | `image/jpeg`, `image/png`, `image/webp` | follows the saved look / run retention; deleted with user | kept while referenced by a run/save |
| Discover images | System | catalog look images (R29) | `looks.image_ref` | `catalog/looks/{code}` | `image/jpeg`, `image/png`, `image/webp` | never user-deleted; deprecate | versioned content, deprecate not delete |
| Other user-uploaded media | User | any future upload | `MediaRef` on the owning entity | `users/{user_id}/{kind}/{entity_id}` | `image/*` | follows the owning row | user lifecycle |

All media shares the **same contract**: object storage + `MediaRef` metadata on
the owning row; bytes never in PostgreSQL; blob lifecycle follows the
referencing row (§7); retention per policy (§8).

---

## 6. Per-type detail

### 6.1 Profile image

- **Owner:** user.
- **Purpose:** avatar/identity display (today `ProfileData.avatarInitials` is a
  String — no image persisted).
- **Storage location:** `users/{user_id}/avatar.{ext}`.
- **Metadata:** `MediaRef` (object_key, media_type, width, height,
  `is_generated: false`, uploaded_at).
- **MIME type:** `image/jpeg`, `image/png`, `image/webp`.
- **Dimensions:** square crop preferred (e.g. 512×512 display; optional thumb
  variant in `variants`).
- **created_at:** `uploaded_at` in the ref; the profile row's `updated_at` on
  change.
- **Deletion behavior:** old blob removed on replacement; deleted with the
  account (user lifecycle).
- **Retention:** until replaced or account erasure.
- **Relationship to domain entity:** **future** — no column exists in the
  finalized schema. When the auth/profile feature lands, a `MediaRef` column on
  `users`/`user_state` carries it (decision pending; gate MS10.3).

### 6.2 Face scans

- **Owner:** user (the binary); the run is user-owned history.
- **Purpose:** the input evidence of a face analysis (R37) — required for
  reproducibility of the result.
- **Storage location:** `users/{user_id}/scans/{run_id}/input.{ext}`.
- **Metadata:** `analysis_runs.input_media` = `MediaRef` (object_key,
  media_type, width, height, `is_generated: false`, uploaded_at).
- **MIME type:** `image/jpeg`, `image/png`.
- **Dimensions:** as captured; optional downscaled analysis variant in
  `variants`.
- **created_at:** `uploaded_at` in the ref; `analysis_runs.created_at` for the
  run.
- **Deletion behavior:** with the run (retention prune) or with the account
  (CASCADE from `users` via `analysis_runs`).
- **Retention:** `STORAGE_INVENTORY.md` §1.6 — keep the latest per source
  image; older runs pruned unless the user saved the look. Raw scans
  auto-expire unless saved.
- **Relationship to domain entity:** `analysis_runs.input_media` (P2 table);
  the run is the reproducibility anchor (`engine_version` + `result` + this ref).

### 6.3 Outfit scans

- **Owner:** user.
- **Purpose:** the input evidence of an outfit analysis (`run_type =
  'outfit'`).
- **Storage location:** `users/{user_id}/scans/{run_id}/input.{ext}`.
- **Metadata:** `analysis_runs.input_media` = `MediaRef`.
- **MIME type:** `image/jpeg`, `image/png`, `image/webp`.
- **Dimensions:** as captured.
- **created_at:** `uploaded_at`; `analysis_runs.created_at`.
- **Deletion behavior:** with the run/account, same as §6.2.
- **Retention:** same as §6.2.
- **Relationship to domain entity:** `analysis_runs.input_media`; identical
  contract to face scans, distinguished only by `run_type`.

### 6.4 Wardrobe item images

- **Owner:** user.
- **Purpose:** display the item in the wardrobe (R19); optional today (no
  images persist).
- **Storage location:** `users/{user_id}/wardrobe/{item_id}/main.{ext}`.
- **Metadata:** `wardrobe_items.image_ref` = `MediaRef`.
- **MIME type:** `image/jpeg`, `image/png`, `image/webp`.
- **Dimensions:** as uploaded; optional square thumb in `variants`.
- **created_at:** `uploaded_at`; `wardrobe_items.created_at`.
- **Deletion behavior:** deleted with the item — `wardrobe_items` deletion
  (CASCADE from `users`) triggers blob cleanup (§7).
- **Retention:** user lifecycle (item lives → image lives; item/user removed →
  image removed).
- **Relationship to domain entity:** `wardrobe_items.image_ref` (P0); the only
  JSONB on a current-state row and it is a *reference*, never a blob (PR-8).

### 6.5 Hairstyle reference images

- **Owner:** system (catalog content).
- **Purpose:** reference looks for the hair-analysis pipeline and "Save Style"
  (P1).
- **Storage location:** `catalog/hairstyles/{code}/main.{ext}`.
- **Metadata:** `MediaRef` in system catalog content (future; rides in
  `looks`/catalog payload per K9.1).
- **MIME type:** `image/jpeg`, `image/png`.
- **Dimensions:** fixed catalog aspect; optional variants.
- **created_at:** catalog content versioning (`content_version`), not user time.
- **Deletion behavior:** never user-deleted; **deprecate**, never delete while
  referenced (R30 semantics).
- **Retention:** versioned content — deprecate not delete.
- **Relationship to domain entity:** system catalog content (P1, gated by the
  hair pipeline); **no column exists in the finalized schema today**.

### 6.6 Generated images

- **Owner:** user-bound AI output (the blob is system-generated but
  user-scoped).
- **Purpose:** AI-generated look/result images shown to the user; persisted
  only as part of a run result or a saved look.
- **Storage location:** `users/{user_id}/generated/{run_id}/{seq}.{ext}`.
- **Metadata:** `MediaRef` (`is_generated: true`) embedded in
  `analysis_runs.result` and/or `saved_looks.snapshot`.
- **MIME type:** `image/jpeg`, `image/png`, `image/webp`.
- **Dimensions:** output size; optional thumb variants.
- **created_at:** `uploaded_at`; parent run/save `created_at`.
- **Deletion behavior:** follows the referencing run/saved look; deleted with
  the account. Not part of the immutable DB *text* snapshot semantics — the
  blob is cleaned when the reference is pruned.
- **Retention:** kept while a run or saved look references it; pruned with the
  run (§1.6) or the save.
- **Relationship to domain entity:** embedded refs inside `analysis_runs.result`
  and `saved_looks.snapshot` (JSONB); never a top-level column.

### 6.7 Discover images

- **Owner:** system (catalog content).
- **Purpose:** catalog look images for Discover (R29).
- **Storage location:** `catalog/looks/{code}/main.{ext}`.
- **Metadata:** `looks.image_ref` = `MediaRef`.
- **MIME type:** `image/jpeg`, `image/png`, `image/webp`.
- **Dimensions:** fixed catalog aspect; optional variants.
- **created_at:** catalog `content_version`/`published_at`.
- **Deletion behavior:** never user-deleted; deprecate via `deprecated_at`.
- **Retention:** versioned content — deprecate not delete; never deleted while
  referenced (R30).
- **Relationship to domain entity:** `looks.image_ref` (P0 catalog asset ref).

### 6.8 Other user-uploaded media

- **Owner:** user.
- **Purpose:** any future user upload (e.g. an event or look photo not in the
  current model).
- **Storage location:** `users/{user_id}/{kind}/{entity_id}/main.{ext}`.
- **Metadata:** `MediaRef` on the owning entity; same contract as §6.4.
- **MIME type:** `image/*` (validated at upload).
- **Dimensions:** as uploaded; optional variants.
- **created_at:** `uploaded_at`; owner row `created_at`.
- **Deletion behavior:** follows the owning row (deletion of the entity removes
  its blob).
- **Retention:** user lifecycle; no new column added until a feature needs one
  (PR-12).
- **Relationship to domain entity:** a `MediaRef` reference column **added only
  when the owning feature exists** — never a speculative media table.

---

## 7. Deletion behavior — blob lifecycle follows the referencing row

The DB holds only the reference, so "deleting media" has two coordinated
actions:

1. **Delete the referencing row** (current state or history retention) — the
   `MediaRef` JSONB goes with it. For user-owned media this is the CASCADE path
   from `users` (`RELATIONSHIP_CONSTRAINTS.md` §5.1); for history it is the
   retention prune (`analysis_runs`).
2. **Delete the blob** in object storage — an **async cleanup job** that reads
   the removed rows' `object_key`s and deletes the binaries. The database never
   triggers object-storage deletion in the same transaction; the reference is
   the source of truth for cleanup.

Rules:

| Rule | Detail |
| --- | --- |
| User-owned blobs | deleted with the entity/account (CASCADE semantics + cleanup job). |
| Scan blobs | retained per §1.6; pruned with the run under retention, never in-place mutated. |
| Catalog blobs (discover/hairstyle refs) | never deleted while referenced; deprecate only. |
| Generated blobs | follow the referencing run/saved look; orphaned blobs (no row references them) are swept by the cleanup job. |
| Account erasure | full cascade removes all user-scoped refs; the cleanup job then deletes all `users/{user_id}/...` blobs — the complete right to erasure from §3 of `RELATIONSHIP_CONSTRAINTS.md`. |

**No orphan policy gap:** because every blob's `object_key` is namespaced by
owner and entity (`§4`), an idempotent sweep over removed-row keys can never
touch another user's media (PR-10).

---

## 8. Retention considerations

| Media type | Retention policy |
| --- | --- |
| Profile image | until replaced or account erasure. |
| Face/outfit scans | `STORAGE_INVENTORY.md` §1.6 — latest per source image kept; older runs pruned **unless the user saved the look**; raw scans auto-expire unless saved. |
| Wardrobe item images | item/user lifecycle. |
| Hairstyle reference images | versioned content; deprecate not delete. |
| Generated images | while referenced by a run or saved look; else pruned. |
| Discover images | versioned content; deprecate not delete. |
| Other uploads | user lifecycle. |

**Global gate:** no media *storage* is configured until **MS10.3** (media
privacy policy) is decided. The `MediaRef` reference columns ship regardless;
blob persistence, bucket config, CDN, and privacy copy are all gated.

---

## 9. Relationship to domain entities — summary

| Domain entity | Reference column / payload | Media types |
| --- | --- | --- |
| `users` / `user_state` | future `avatar_ref` (no column today) | profile image |
| `analysis_runs` | `input_media` | face scans, outfit scans |
| `analysis_runs` | `result` (embedded refs, `is_generated: true`) | generated images |
| `saved_looks` | `snapshot` (embedded refs) | generated images |
| `wardrobe_items` | `image_ref` | wardrobe item images |
| `looks` | `image_ref` | discover images |
| `looks`/catalog (P1, future) | catalog payload (K9.1) | hairstyle reference images |
| any future entity | new `MediaRef` column only when the feature lands | other user-uploaded media |

**Integrity semantics:** every reference is a `MediaRef` JSONB value with **no
FK** and no join axis (rules §8; `RELATIONSHIP_CONSTRAINTS.md` §6 — "no media
table and no FK to object storage"). The blob lifecycle follows the row; the
DB is never the store of truth for the bytes.

---

## 10. Report — summary

- **Object storage is assumed for every binary**; the domain model requires no
  other strategy for any media type (R19/R29/R37 all resolve to `MediaRef →
  object storage`).
- **PostgreSQL stores only `MediaRef` metadata** (object_key, media_type,
  width/height, size, hash, `is_generated`, uploaded_at, variants) on the
  owning row; **no media table, no `BYTEA`, no base64, no GIN**.
- **Eight media types defined** with owner, purpose, storage location,
  metadata, MIME, dimensions, created_at, deletion behavior, retention, and
  domain relationship: profile image (future), face scans, outfit scans,
  wardrobe item images, hairstyle reference images (P1), generated images,
  discover images, other user-uploaded media.
- **Deletion and retention follow the referencing row**: CASCADE for user-owned
  blobs + async cleanup job; scan retention per §1.6 (latest kept, older pruned
  unless saved); catalog content deprecate-not-delete; account erasure removes
  all user blobs (complete erasure).
- **Gates:** MS10.3 (media privacy) before any storage is configured; new
  `MediaRef` columns only when their features land (PR-12).
- **Consistent with the whole STEP 4 set:** same reference columns as
  `TABLE_DEFINITIONS.md`, same CASCADE/retention as `RELATIONSHIP_CONSTRAINTS.md`
  and `HISTORY_AND_VERSIONING.md`, same JSONB rationale as `JSONB_STRATEGY.md`
  §4.10.

---

## Constraints honored

- No SQL, no PostgreSQL database, no migrations, no repositories, no endpoints,
  no object-storage buckets, no application code changes, no dependencies,
  nothing deleted.
- Every media decision traces to PR-8/§9 and the finalized domain model
  (R19/R29/R37, `MediaRef`); nothing is invented beyond the domain model.
- The real Fansivibe repository is the source of truth; the separate reference
  project was not merged.


