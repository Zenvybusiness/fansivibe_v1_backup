# Fansivibe — API Contract: Wardrobe

> **STEP 6 — API CONTRACT DESIGN.** Defines the **field-level API contract for
> the Fansivibe wardrobe surface**: list items, retrieve a single item, create,
> update, delete, the category/vocabulary reads, filters, sorting, pagination,
> and the wardrobe insight — with **image/media handling defined separately
> from the JSON data** (the M16 signed-URL flow, referenced). It is the focused
> companion to `API_CONTRACT_RULES.md` (§12.3 wardrobe, §12.5 knowledge,
> §8.2 list envelope, §10 pagination/filtering/sorting, §13.3 wardrobe DTOs)
> and `API_INVENTORY.md` (endpoints 11–15 wardrobe, 19–20 knowledge
> vocabulary, 47–48 media), and it sits beside the sibling contracts
> `PROFILE_ONBOARDING_API.md` (the sync surface that seeded local wardrobe
> data), `RECOMMENDATION_API.md` (the surfaces that consume wardrobe items),
> `SCAN_API.md`/`APPEARANCE_API.md` (the media flow they share), and
> `AUTH_API.md` (identity/ownership).
>
> **Status: contract design only. The wardrobe API is NOT implemented.** No
> code, no `deps.py`, no routers, no SQL migrations, no dependencies, no Flutter
> changes. The live contract (`GET /health`, `POST /v1/assistant/chat`) is
> preserved unchanged. Wardrobe CRUD is **P0** (M3) but the endpoints are **not
> mounted** until the auth seam (D-AUTH-1) lands; the media flow (M16) is
> **sealed** until MS10.3 is decided (API-12) — no fake 200 before either gate.
>
> **Source of truth:** the real Fansivibe repository and the accepted docs —
> the real wardrobe feature (`wardrobe_screen.dart`,
> `wardrobe_item_details_screen.dart`, `add_wardrobe_category_screen.dart`,
> `add_wardrobe_item_screen.dart`, `wardrobe_mock_data.dart`,
> `home_mock_data.dart` `AIWardrobeInsightData`), STEP 3
> `FANSIVIBE_DOMAIN_MODEL_V1.md` (E2 `WardrobeItem`), STEP 4
> `TABLE_DEFINITIONS.md` (`wardrobe_items`, `wardrobe_categories`, `colors`,
> `materials`, `occasions`) + `TRANSACTION_BOUNDARIES.md` (TRX-1) +
> `BUSINESS_CONSTRAINTS.md` (BC-18/BC-29/BC-30/BC-31/BC-41) +
> `DATABASE_DESIGN_RULES.md` (PR-2/PR-3/PR-8),
> STEP 5 `APPLICATION_USE_CASES.md` (UC-10…UC-14) +
> `MEDIA_UPLOAD_ARCHITECTURE.md` (M16 flow, PR-8, TRX-1) +
> `AUTH_AUTHORIZATION_ARCHITECTURE.md` (OW-1) +
> `SECURITY_PRIVACY_DESIGN.md` (MS10.3), STEP 6 `API_CONTRACT_RULES.md`
> (§12.3/§12.5/§8.2/§10/§13.3) + `API_INVENTORY.md` (endpoints 11–15/19–20/
> 47–48).

---

## 1. Purpose and scope

This document defines, for every **required wardrobe operation**, the contract
attributes the STEP 6 design task asks for — **method, path, request schema,
response schema, validation, authorization, errors** (plus security
considerations, side effects, and domain entities, following the same
convention as the sibling contracts). The task's coverage list is mapped
operation by operation (§5):

- **list wardrobe items** — §5.1
- **retrieve wardrobe item** — §5.2
- **create wardrobe item** — §5.3
- **update wardrobe item** — §5.4
- **archive/delete wardrobe item** — §5.5
- **categories** — §5.6 (referenced knowledge vocabulary)
- **filters / sorting / pagination** — §4.4 shared semantics + per-list §5.1
- **wardrobe insight** — §5.7
- **image/media handling** (separate from JSON data) — §4.2 + §5.8

**The three binding design rules of this document:**

1. **Wardrobe is current user-owned state, and every item is owner-scoped**
   (OW-1, BC-18). The five inventory endpoints (11–15) are the required,
   accepted surface; the **single-item retrieve is defined fully here but is
   additive** — the details screen is served from the list today (§5.2). No
   item is ever visible to another user; a foreign or non-existent `item_id`
   → **404-not-403** (API-10).
2. **Image/media is handled separately from normal JSON data.** The item JSON
   endpoints carry **only `imageRef: MediaRef`** — never bytes, never URLs
   (PR-8). Bytes travel through the **M16 signed-URL flow** (`POST
   /v1/media/uploads` → direct PUT to object storage → `POST
   /v1/media/uploads/{id}/complete`), which is **sealed until MS10.3**
   (API-12). §4.2, §5.8.
3. **Category/color/material are knowledge-controlled vocabulary, not
   client hardcodes** (K9.1, API-14). The item's `category`/`color`/`material`
   are **stable vocab codes** (PR-2) validated server-side; display labels come
   from the public knowledge catalog (`GET /v1/knowledge/categories`,
   `GET /v1/knowledge/colors`, referenced §5.6). No free-string categories.

**What it does not do:** implement anything, mount endpoints, change the
frozen assistant DTOs, unseal M16, or re-own the knowledge/media surfaces
(those are referenced, not re-defined). The wardrobe CRUD endpoints and the
insight are owned by this doc; the media upload endpoints (47/48) and the
vocabulary endpoints (19–22) are referenced and kept identical to their
contracts.

### 1.1 Grounding facts (re-verified)

- **The wardrobe is a real, local-only feature today.** Four screens
  (`WardrobeScreen`, `WardrobeItemDetailsScreen`, `AddWardrobeCategoryScreen`,
  `AddWardrobeItemScreen`) read/write `LearningService` (persisted
  `UserModel.wardrobe` via `LocalStore`); no backend exists yet
  (`FEATURE_INVENTORY.md` §4, `SCREEN_DATA_INVENTORY.md` §4.1 "Required future
  backend data: wardrobe CRUD…"). The contract defines the server surface.
- **`wardrobe_items` is a normalized current-state row** (PR-1): `id uuid`,
  `user_id`, `name [1,100]`, `category_id FK wardrobe_categories`,
  `color_id FK colors`, `material_id? FK materials`, `is_favorite`,
  `image_ref? jsonb (MediaRef)`, `created_at`, `updated_at`
  (`TABLE_DEFINITIONS.md` §3.6). No archive column exists.
- **The item DTO is frozen to §13.3:** `WardrobeItem { id*, name*, category*,
  color*, material?, isFavorite, imageRef?: MediaRef, createdAt*, updatedAt* }`;
  `WardrobeItemCreate`, `WardrobeItemPatch` (PATCH partial), `WardrobeInsight
  { title*, insight*, action?, route? }`, `MediaRef` (§13.3). The wire keys
  `category`/`color`/`material` carry the **vocab codes**, resolved to labels
  via knowledge (K9.1, PR-2).
- **The five required operations trace 1:1 to the accepted inventory:**
  `GET /v1/wardrobe/items` (11), `POST /v1/wardrobe/items` (12, UC-10),
  `PATCH /v1/wardrobe/items/{item_id}` (13, UC-11/12), `DELETE
  /v1/wardrobe/items/{item_id}` (14, UC-13), `GET /v1/wardrobe/insight`
  (15, UC-14). All **auth + owner** (OW-1). **No `GET /v1/wardrobe/items/
  {item_id}` exists in the inventory** — §5.2 defines it as additive.
- **Archive is NOT modeled; delete IS supported.** `wardrobe_items` has no
  archive/status column (current state only); there is no archive endpoint.
  Delete (UC-13) removes the row and enqueues the **out-of-DB image deletion**
  after commit; **history is untouched** (BC-41 — `learning_signals` have no FK
  to current state; the `item_added` signal outlives the item).
- **Categories and colors are served by the public knowledge catalog**
  (endpoints 19/20); the mock's category chips and add-item swatches are the
  client renderings. The category **counts** are per-user derived (client
  computes from the list; server-side counts are additive-only). **Materials
  have no dedicated endpoint in the inventory** (§8.7) — the create endpoint
  validates the material code server-side regardless.
- **The item image is a `MediaRef`, not bytes.** `image_ref` holds the object
  key + media type (`MEDIA_UPLOAD_ARCHITECTURE.md` §4); upload uses the
  **signed-URL flow** (endpoints 47/48), which is **sealed until MS10.3**
  (API-12, PR-8). Item JSON never carries the file (§4.2).
- **Wardrobe insight is a derived value** (`GET /v1/wardrobe/insight`,
  UC-14): "consider a lightweight jacket" — derived from wardrobe × catalog,
  sync, `204` on an empty wardrobe (`API_CONTRACT_RULES.md` §12.3).
- **No optimistic versioning on items.** `wardrobe_items` has no `version`
  column (unlike `user_state`); `PATCH` is a natural idempotent merge, and
  concurrent edits are last-write-wins per field — matching the inventory
  (no `If-Match` on `/v1/wardrobe/*`).

---

## 2. Source of truth and inputs

| Input | Role |
| --- | --- |
| `wardrobe_mock_data.dart` | The real item shape (`WardrobeItemData`: id/name/category/color/material/isFavorite), category chips (with `all` pseudo-category), color swatches, textures, `WardrobeInsightData` — the client renderings of the wire DTO. |
| `wardrobe_screen.dart` / `wardrobe_item_details_screen.dart` | The real UX: category filter chips, favorites count, item grid, add/edit/delete actions — grounding filters/sorting/pagination and the detail/delete flows. |
| `home_mock_data.dart` | `AIWardrobeInsightData` ("Wardrobe Gap Detected") — the home rendering of the wardrobe insight. |
| `FANSIVIBE_DOMAIN_MODEL_V1.md` | E2 `WardrobeItem`; E7 `LearningSignal` (`item_added`); vocabulary value objects. |
| `TABLE_DEFINITIONS.md` | `wardrobe_items` (columns/constraints), `wardrobe_categories`/`colors`/`materials`/`occasions` vocab tables; PR-2/PR-3/PR-8. |
| `BUSINESS_CONSTRAINTS.md` | BC-18 (owner CASCADE), BC-29/BC-30/BC-31 (category/color/material FK validity), BC-41 (history independence on delete). |
| `TRANSACTION_BOUNDARIES.md` | TRX-1 (upload-then-insert: blob → object storage → MediaRef → row); delete → out-of-DB image cleanup after commit. |
| `DATABASE_DESIGN_RULES.md` | PR-1 (normalized row), PR-2 (vocab codes), PR-3 (DB-owned identity), PR-8 (no bytes in PG). |
| `APPLICATION_USE_CASES.md` | UC-10 `AddWardrobeItem`, UC-11/12 `UpdateWardrobeItem`, UC-13 `DeleteWardrobeItem`, UC-14 `GetWardrobeInsight`. |
| `MEDIA_UPLOAD_ARCHITECTURE.md` | The M16 signed-URL flow (endpoints 47/48), PR-8 no-bytes-in-app-memory, purpose/size/MIME limits, private-by-default (MS10.3). |
| `AUTH_AUTHORIZATION_ARCHITECTURE.md` / `SECURITY_PRIVACY_DESIGN.md` | OW-1 ownership, 404-not-403; MS10.3 media privacy/erasure. |
| `API_CONTRACT_RULES.md` | Catalog §12.3/§12.5, list envelope §8.2, pagination/filter/sort §10, wardrobe DTOs §13.3, errors §9, idempotency §11. |
| `API_INVENTORY.md` | Endpoints 11–15 (wardrobe), 19–22 (knowledge vocabulary), 47–48 (media, sealed); related domain entities per endpoint. |
| Sibling contracts | `PROFILE_ONBOARDING_API.md` (P-4 sync seeded the local wardrobe; the future server source), `RECOMMENDATION_API.md` (outfit/daily surfaces consume `WardrobeItem`s), `SCAN_API.md`/`APPEARANCE_API.md` (shared M16 media flow), `AUTH_API.md` (Bearer, OW-1). |
| `ERROR_HANDLING.md` | 12-category taxonomy: VALIDATION_ERROR (422), AUTHENTICATION_ERROR (401), NOT_FOUND (404), CONFLICT (409), MEDIA_FAILURE (413/422), RATE_LIMITED (429). |

---

## 3. Operation selection (define only the required operations)

| # | Candidate operation | Decision | Justification |
| --- | --- | --- | --- |
| W-1 | **List wardrobe items** | **Required** — `GET /v1/wardrobe/items` | Endpoint 11; actions 5/6/7 reads; the wardrobe grid + category filter + favorites. §5.1. |
| W-2 | **Retrieve a wardrobe item** | **Defined; additive** — `GET /v1/wardrobe/items/{item_id}` | The task requires the coverage; the resource already exists in the URI map (PATCH/DELETE). **Not in the current 48-endpoint inventory** — the details screen is served from the list today; documented fully, stays unmounted until accepted (API-2). §5.2. |
| W-3 | **Create wardrobe item** | **Required** — `POST /v1/wardrobe/items` | UC-10, endpoint 12, action 5. Vocab-validated create + `item_added` signal. §5.3. |
| W-4 | **Update wardrobe item** | **Required** — `PATCH /v1/wardrobe/items/{item_id}` | UC-11/12, endpoint 13, action 6. Partial merge incl. favorite toggle. §5.4. |
| W-5 | **Delete wardrobe item** | **Required** — `DELETE /v1/wardrobe/items/{item_id}`; **archive NOT supported** | UC-13, endpoint 14, action 7. Hard delete + out-of-DB image cleanup; history untouched (BC-41). No archive column/status exists (§5.5). |
| W-6 | **Categories (and color/material vocabulary)** | **Required (referenced)** — `GET /v1/knowledge/categories` (19), `GET /v1/knowledge/colors` (20) | The controlled vocab the item fields validate against (K9.1); public, versioned (`X-Knowledge-Version`). **Materials read additive** (§8.7). Owned by M5 — referenced, not re-defined. §5.6. |
| W-7 | **Wardrobe insight** | **Required** — `GET /v1/wardrobe/insight` | UC-14, endpoint 15, action 8. Derived gap/health insight; `204` when empty. §5.7. |
| M-1/M-2 | **Item image upload / complete** | **Required (referenced, sealed)** — `POST /v1/media/uploads` + `/complete` | Endpoints 47/48, M16. The **separate** media path (image handling is not in the JSON endpoints). **Not mounted** until MS10.3 (API-12). Owned by M16 — referenced, not re-defined. §5.8. |
| — | **Archive an item** (`POST …/archive`) | **NOT defined** | No archive column/state in the domain; `wardrobe_items` is current state, delete is the only removal (BC-41). §5.5. |
| — | **Bulk/multi-item mutations, move/reorder** | **NOT defined** | No product action or UC supports them; no invented endpoints. |

### 3.1 What the wardrobe surface is (and is not)

The wardrobe surface is **owner-scoped CRUD over one normalized row + the
derived insight**, with vocabulary and media referenced from their own sealed
surfaces:

```
list (W-1) ──► item grid + category filter + favorites   (client renders vocab labels via knowledge)
retrieve (W-2) ──► item details (additive; served from the list today)
create (W-3) ──► row + item_added signal                 (image: MediaRef from M16, if any)
update (W-4) ──► PATCH partial merge (incl. favorite toggle)
delete (W-5) ──► row removed; out-of-DB image sweep; history untouched (BC-41)
insight (W-7) ──► derived WardrobeInsight (204 when empty)
image (M-1/M-2) ──► signed-URL upload → MediaRef → referenced by imageRef (sealed)
vocabulary (W-6) ──► public knowledge catalog (categories/colors; materials additive)
```

There is **no** archive state, **no** wardrobe-item endpoint that carries image
bytes, and **no** client-authored category/color strings (K9.1). Everything
below stays inside the accepted inventory (plus the flagged additive W-2).

---

## 4. Shared semantics (apply to every operation below)

### 4.1 Base URL, headers, format

- All endpoints under `/v1` (API-1); JSON bodies `application/json;
  charset=UTF-8`; keys camelCase; timestamps ISO-8601 UTC (API-19). **No
  multipart on the item endpoints** — item JSON is plain JSON with an
  `imageRef` reference (§4.2).
- Protected endpoints send `Authorization: Bearer <token>` (API-5). Missing /
  invalid / expired / revoked → `401 AUTHENTICATION_ERROR` +
  `WWW-Authenticate: Bearer` (API-7, ERROR_HANDLING §5.2).
- **No `Idempotency-Key`** on item PATCH/DELETE (naturally idempotent, §11).
  Create (W-3) is **not** in the inventory's idempotency-key list; a duplicate
  submit surfaces as a duplicate row (the inventory does not key it — §8.5
  records the choice). Reads are naturally idempotent.
- Every response echoes `X-Request-Id` (OBSERVABILITY §4.1). Knowledge reads
  carry `X-Knowledge-Version` (KN-1).

### 4.2 Image / media handling — separate from the JSON data

**The item JSON never contains image bytes.** The wire carries only
`imageRef?: MediaRef`, which references an object already in storage:

```
MediaRef { objectKey, mediaType, width?, height?, sizeBytes, contentHash,
           isGenerated, uploadedAt }
```

The bytes are moved by the **M16 signed-URL flow** (owned by M16; §5.8):

```
1. POST /v1/media/uploads {purpose, filename, size, contentType}   (auth: owner)
     → 201 { upload_id, signedPutUrl, expiresAt }
2. Flutter PUTs the bytes DIRECTLY to object storage via signedPutUrl
     (zero FastAPI RAM, PR-8)
3. POST /v1/media/uploads/{upload_id}/complete                        (auth: owner)
     → 200 MediaRef          (HEAD/size/hash verified; TRX-1 upload-then-insert)
4. create/update the item with imageRef = that MediaRef              (§5.3/§5.4)
```

Rules that keep media separate and safe:

- **Never in JSON, never in PostgreSQL** (PR-8): no base64, no in-JSON URL.
  `MediaRef` holds the object key, not a long-lived URL; download URLs are
  minted on demand, short-lived, owner-scoped (§4.8 of `MEDIA_UPLOAD_ARCHITECTURE`).
- **Private by default** (MS10.3): user item photos are CRITICAL-adjacent user
  media; no public reads, no URLs in logs, erasure deletes bytes.
- **Purpose/size/MIME validated** at authorization (declared) and at
  `/complete` (verified via HEAD): allow-list `image/jpeg|png|webp`, size
  limits config-driven per purpose (`MEDIA_UPLOAD_ARCHITECTURE` §4.2–§4.4).
- **Deleting an item enqueues out-of-DB byte deletion** after commit (§5.5).
- **Sealed until MS10.3**: the media endpoints are **not mounted**; before
  then, items carry no `imageRef` and no fake 200 is returned (API-12).

### 4.3 Vocabulary — categories, colors, materials (K9.1)

- `category`, `color`, `material` on the wire are **stable vocab codes**
  (`wardrobe_categories.code`, `colors.code`, `materials.code` — PR-2). The
  client maps code → display label from the **public knowledge catalog**
  (`GET /v1/knowledge/categories` 19, `GET /v1/knowledge/colors` 20, §5.6).
- Server-side **vocab validation on every write** (API-14): an unknown code →
  `422 VALIDATION_ERROR` with the allowed values in `details`. No free strings.
- The mock's `all` category chip ("All Items") is a **client-side filter
  pseudo-category** — it is not a vocab code and never reaches the server.
- Category **counts** in the chips are **derived per-user**; the client
  computes them from the list response. Server-side counts are additive-only
  (§8.6).
- **Materials** have no dedicated read endpoint in the inventory (the create/
  update still validate the material code server-side); a `GET
  /v1/knowledge/materials` read is additive (§8.7).

### 4.4 Filters, sorting, pagination (shared for W-1)

- **Filtering (API-23/24/25):** typed query params, vocabulary-validated
  server-side → `422` on invalid values. Accepted filters on the inventory:
  `?category=<code>&color=<code>` (both optional). `material`, `isFavorite`,
  and free-text `q` are **additive-only** (not in the inventory — the favorites
  count today is client-derived from the list). No free-form `?filter=json`.
- **Sorting (API-26):** `?sort=<key>&order=asc|desc` with **documented keys**:
  `created_at` (default), `updated_at`, `name`; `order` default `desc` for
  time keys, `asc` for `name`. Unknown key/order → `422`. The API never
  re-sorts derived engine output (none here — this is user state, not AI
  output).
- **Pagination (API-20):** `?page=1&page_size=20` (1-based; `page` default 1,
  `page_size` default 20, max 100); `total` from the same query. Out-of-bounds
  `page_size` → `422`. Response is the `ListEnvelope`
  `{ items, page, page_size, total }` (§8.2).

### 4.5 Error body (frozen, API-28)

```
{ "error": { "code": "<one of the 12>", "message": "<safe client message>", "details": {...} } }
```

`details` is allow-listed only (ER-1): field errors + allowed values (422),
`item_id` (own item only), `request_id` (500). **Never** image bytes, object
keys, provider internals, or another user's data (C-7/C-8, ER-0/ER-2).

### 4.6 Auth, ownership, privacy

| Requirement | Endpoints |
| --- | --- |
| **Auth** (Bearer → `user_id`) | all of `/v1/wardrobe/*` (list, retrieve, create, update, delete, insight), `/v1/media/*` (when mounted). |
| **Public** | `GET /v1/knowledge/categories`, `GET /v1/knowledge/colors` (no user data, KN-1). |

Authorization is **owner-only (OW-1)** with **404-not-403** (API-10): every
item is scoped to the caller's `user_id`; another user's (or a non-existent)
`item_id` → `404` — no existence leak. Item images are private media (MS10.3):
object keys namespaced `users/{user_id}/wardrobe/…`, only `MediaRef` travels,
bytes never logged/echoed, erasure deletes bytes (TRX-8).

### 4.7 The item DTO (frozen to §13.3)

```
WardrobeItem     { id*, name*, category*, color*, material?, isFavorite,
                   imageRef?: MediaRef, createdAt*, updatedAt* }
WardrobeItemCreate { name*, category*, color*, material?, imageRef? }
WardrobeItemPatch  { name?, category?, color?, material?, isFavorite? }
WardrobeInsight    { title*, insight*, action?, route? }
```

`id` is **DB-owned** (PR-3): a server-generated UUID, never the client's local
Dart id. `createdAt`/`updatedAt` are server-maintained timestamps (the table
has no version column; §1.1).

---

## 5. Operation contracts

### 5.1 W-1 — List wardrobe items (`ListWardrobeItems`, endpoint 11)

- **Method / path:** `GET /v1/wardrobe/items`
- **Request schema:** query params — `category?` (vocab code), `color?` (vocab
  code), `sort?` (`created_at|updated_at|name`), `order?` (`asc|desc`),
  `page?`, `page_size?` (§4.4).
- **Response schema:** `200 OK` — `ListEnvelope { items: WardrobeItem[],
  page, page_size, total }` (§8.2), items newest-first by default. Empty
  result is an empty `items` list with `total=0` — **never an error**.
- **Validation:** `category`/`color` must be valid vocab codes → `422` with
  allowed values; `sort`/`order` from the documented set → `422`;
  `page_size` ∈ `[1,100]` → `422`.
- **Authorization:** **auth** (Bearer); **owner** — the list is always scoped
  to the caller (no cross-user reads).
- **Errors:** `200`; `401`; `422 VALIDATION_ERROR` (filters/sort/pagination);
  `429 RATE_LIMITED`.
- **Security considerations:** only the caller's own items; `imageRef` returns
  references, never bytes/URLs (§4.2); no internals.
- **Side effects:** none — a pure read.
- **Domain entities involved:** E2 `WardrobeItem`; `MediaRef` (optional,
  embedded); vocabulary codes (category/color).
- **Notes:** the client renders the category chips + counts by filtering this
  list client-side (the `all` pseudo-category is local). Favorites count is
  derived from the list today (§4.3).

---

### 5.2 W-2 — Retrieve a wardrobe item (`GetWardrobeItem` — additive, not in the inventory)

- **Method / path:** `GET /v1/wardrobe/items/{item_id}` (`item_id` UUID).
- **Status:** **additive** — defined fully because the task requires the
  coverage; **not in the current 48-endpoint inventory** (API_INVENTORY §4 has
  no single-item read). Today the details screen is served **from the list**
  (the tapped `WardrobeItemData` travels with the route). This GET is the
  natural read on the already-resourced `/v1/wardrobe/items/{item_id}` (§7 URI
  map) and is additive under API-2 when the inventory accepts it.
- **Request schema:** none (`item_id` UUID in path).
- **Response schema:** `200 OK` — `WardrobeItem` (bare, §4.7).
- **Validation:** `item_id` must be a valid UUID → `422`.
- **Authorization:** **auth** (Bearer); **owner** — another user's or
  non-existent `item_id` → `404` (404-not-403).
- **Errors:** `200`; `401`; `404 NOT_FOUND`; `422 VALIDATION_ERROR`.
- **Security considerations:** owner-only; `imageRef` is a reference, never
  bytes (§4.2).
- **Side effects:** none.
- **Domain entities involved:** E2 `WardrobeItem`.

---

### 5.3 W-3 — Create a wardrobe item (`AddWardrobeItem`, UC-10, endpoint 12)

- **Method / path:** `POST /v1/wardrobe/items`
- **Request schema** (`WardrobeItemCreate`):

```
{
  "name": "Merino Crew Neck",     // required, [1,100]
  "category": "tops",             // required — wardrobe_categories code (K9.1)
  "color": "charcoal",            // required — colors code
  "material": "wool",             // optional — materials code
  "imageRef": { …MediaRef… }      // optional — from M16 /complete (when mounted)
}
```

  The image, if any, is **not** in this body — it is a `MediaRef` obtained via
  the separate media flow first (§4.2/§5.8).
- **Response schema:** `201 Created` — `WardrobeItem` (server-assigned `id`,
  `createdAt`, `updatedAt`).
- **Validation:** `name` non-empty `[1,100]` (BC-11); `category`/`color`
  **required** valid vocab codes (BC-29/BC-30) → `422` with allowed values;
  `material` valid code or absent (BC-31); `imageRef` must be the caller's own
  completed upload (object-key ownership checked, TRX-1).
- **Authorization:** **auth** (Bearer); **owner** (OW-1).
- **Errors:** `201`; `401`; `404` (account gone); `422 VALIDATION_ERROR`
  (vocab/name); `409 CONFLICT` (duplicate/limit); `413/422 MEDIA_FAILURE`
  (image reference invalid); `429 RATE_LIMITED`.
- **Security considerations:** vocab is knowledge-controlled (no client
  categories, API-14); image is a reference, never a byte/URL (§4.2); owner
  scoping on the `imageRef` prevents attaching another user's media.
- **Side effects:** **`INSERT wardrobe_items`** (TRX-1: the blob was placed
  before the row when an image exists); emits the **`item_added` learning
  signal** (`learning_signals`, BC-41 history independence); `updated_at =
  created_at` on insert.
- **Domain entities involved:** E2 `WardrobeItem`; E7 `LearningSignal`
  (`item_added`); vocab (category/color/material); `MediaRef` (optional).

---

### 5.4 W-4 — Update a wardrobe item (`UpdateWardrobeItem`, UC-11/12, endpoint 13)

- **Method / path:** `PATCH /v1/wardrobe/items/{item_id}`
- **Request schema** (`WardrobeItemPatch` — partial merge, only present fields
  change):

```
{ "name"?, "category"?, "color"?, "material"?, "isFavorite"? }
```

  PATCH semantics: `null` material clears it; absent fields are untouched.
  The favorite toggle (action 6) is this endpoint with `{"isFavorite": true|false}`.
- **Response schema:** `200 OK` — the updated `WardrobeItem` (server-bumped
  `updatedAt`).
- **Validation:** same vocab/name rules as W-3 for the present fields →
  `422`; `item_id` UUID; `isFavorite` boolean.
- **Authorization:** **auth** (Bearer); **owner** — 404-not-403.
- **Errors:** `200`; `401`; `404 NOT_FOUND`; `409 CONFLICT`; `422
  VALIDATION_ERROR`; `429 RATE_LIMITED`.
- **Security considerations:** partial merge never touches `user_id`, `id`, or
  `created_at`; image replacement (if ever) goes through M16 → new `MediaRef`
  (§4.2).
- **Side effects:** guarded `UPDATE`; `updated_at` bumped. **No signal**
  (favorite/name edits do not emit a learning signal in the accepted model —
  only `item_added`, `look_saved`, etc. are seeded types).
- **Domain entities involved:** E2 `WardrobeItem`.

---

### 5.5 W-5 — Delete a wardrobe item (`DeleteWardrobeItem`, UC-13, endpoint 14) — and why archive is NOT supported

- **Method / path:** `DELETE /v1/wardrobe/items/{item_id}`
- **Request schema:** none (`item_id` UUID in path).
- **Response schema:** `204 No-content`.
- **Validation:** `item_id` UUID → `422`.
- **Authorization:** **auth** (Bearer); **owner** — 404-not-403.
- **Errors:** `204`; `401`; `404 NOT_FOUND`; `409 CONFLICT` (FK refs); `429
  RATE_LIMITED`.
- **Security considerations:** history survives deletion by design (BC-41 —
  `learning_signals`/saved-look snapshots have no FK to the item); images are
  deleted **out-of-DB after commit** (async sweep, §4.7 of
  `MEDIA_UPLOAD_ARCHITECTURE`); erasure semantics never delete another user's
  data.
- **Side effects:** `DELETE wardrobe_items` row; **enqueued out-of-DB image
  byte deletion** after commit (orphan sweep for any never-referenced blob);
  history rows untouched (BC-41). **No archive step exists.**
- **Why archive is NOT supported:** `wardrobe_items` is **current state only**
  — there is no `archived_at`/`status` column, no archive entity, and no
  archive action/UC in the product (`TABLE_DEFINITIONS.md`,
  `APPLICATION_USE_CASES.md`). "Archive" would require a schema + product
  decision first (additive); today **delete is the only removal**. A
  `POST /v1/wardrobe/items/{item_id}/archive` would be an invented endpoint
  (§3).
- **Domain entities involved:** E2 `WardrobeItem` (removed); E7
  `LearningSignal` (survives, BC-41).

---

### 5.6 W-6 — Categories, colors & vocabulary (`ListKnowledgeCategories` 19, `ListKnowledgeColors` 20 — referenced)

- **Method / path:** `GET /v1/knowledge/categories` (endpoint 19),
  `GET /v1/knowledge/colors` (endpoint 20) — plus occasions (21) and items
  (22) as siblings. **Owned by M5; referenced, not re-defined.**
- **Purpose:** serve the controlled vocabulary the item fields validate
  against (K9.1) — the category chips and add-item swatches render these.
- **Request schema:** none.
- **Response schema:** `200 OK` — `VocabularyItem[]`
  (`{ code, label, sortOrder, active }`); `X-Knowledge-Version` header (KN-1).
- **Authentication/authorization:** **public**, none (API-7) — no user data.
- **Validation:** none.
- **Errors:** `200`.
- **Security considerations:** read-mostly system knowledge; versioned so the
  client can refresh on mismatch.
- **Side effects:** none.
- **Domain entities involved:** E5 vocabulary (`wardrobe_categories`,
  `colors`, …).
- **Notes:** **materials** are validated server-side on W-3/W-4 but have no
  dedicated read endpoint in the inventory — a `GET /v1/knowledge/materials`
  is additive (§8.7). The `all` chip and category counts are client-side
  (§4.3).

---

### 5.7 W-7 — Wardrobe insight (`GetWardrobeInsight`, UC-14, endpoint 15)

- **Method / path:** `GET /v1/wardrobe/insight`
- **Request schema:** none.
- **Response schema:** `200 OK` — `WardrobeInsight { title*, insight*,
  action?, route? }`; **`204`** when the wardrobe is empty (empty is not an
  error, §12.3). The home "Wardrobe Gap Detected" and wardrobe "Wardrobe
  Health" cards render this.
- **Validation:** none.
- **Authorization:** **auth** (Bearer); **owner**.
- **Errors:** `200`/`204`; `401`; `429 RATE_LIMITED`.
- **Security considerations:** derived from the user's own wardrobe × the
  catalog; the insight text is **grounded** (never invented gaps — it reflects
  real owned-item analysis); no internals.
- **Side effects:** none — a derived computation (not persisted; the
  `WardrobeInsight` is a value object, §13.3).
- **Domain entities involved:** E2 `WardrobeItem` (read); E5 vocabulary/catalog
  (read).
- **Notes:** the insight carries no `score`/`reasons[]` today (§13.3,
  `RECOMMENDATION_API.md` §4.3) — it is the **insight family** of the common
  recommendation contract, not a scored recommendation.

---

### 5.8 M-1/M-2 — Item image upload / complete (endpoints 47/48 — referenced, sealed)

The wardrobe item **image** is handled entirely here — **separate from the
JSON item endpoints** (the task's requirement). Owned by M16; **not mounted**
until MS10.3 (API-12).

- **M-1 — `POST /v1/media/uploads`** (auth, owner): `UploadRequest { purpose,
  filename, size, contentType }` → `201 { upload_id, signedPutUrl, expiresAt }`.
  Purpose for an item photo is a **user purpose** (config-driven set, e.g.
  `outfit_input`; a dedicated `wardrobe` purpose is additive/config — §8.8).
  Declared size/MIME validated → `413/422 MEDIA_FAILURE`.
- **Byte transfer:** Flutter PUTs directly to object storage (zero FastAPI
  RAM, PR-8); signed URL short-lived, owner-scoped, key-namespaced
  `users/{user_id}/wardrobe/…`.
- **M-2 — `POST /v1/media/uploads/{upload_id}/complete`** (auth, owner):
  verifies blob via HEAD/size/hash → `200 MediaRef` (TRX-1 upload-then-insert;
  orphan sweep for never-completed uploads). Errors: `404`, `413/422
  MEDIA_FAILURE`, `503 EXTERNAL_SERVICE_FAILURE`.
- **Wiring:** the returned `MediaRef` becomes `WardrobeItemCreate.imageRef` /
  the item's `imageRef` (W-3/W-4). **Item JSON never carries bytes or URLs.**
- **Deletion:** removing the item enqueues the byte deletion (W-5); erasure
  (TRX-8) deletes bytes.

### 5.9 The wardrobe flow (a sequence of the above — no new endpoint)

```
read:        GET /v1/knowledge/categories|colors (public, versioned)  →  chips/swatches (client maps code→label)
list:        GET /v1/wardrobe/items?category=&color=&sort=&page=&page_size=  →  grid + counts + favorites (client-side)
details:     W-2 (additive) | today: the tapped item travels from the list
create:      [M-1 POST /v1/media/uploads → PUT bytes → M-2 /complete → MediaRef] → POST /v1/wardrobe/items (imageRef)
update:      PATCH /v1/wardrobe/items/{item_id}  (partial; favorite toggle)
delete:      DELETE /v1/wardrobe/items/{item_id} → 204 (image byte sweep after commit; history untouched)
insight:     GET /v1/wardrobe/insight → WardrobeInsight (204 when empty)
```

---

## 6. Validation reference (shared)

| Field | Rules | Source |
| --- | --- | --- |
| `item_id` | UUID; owned (404-not-403) | path param, OW-1 |
| `name` | non-empty, `[1,100]` | BC-11 / §13.3 |
| `category` | required valid `wardrobe_categories.code` → 422 + allowed values | BC-29, K9.1 |
| `color` | required valid `colors.code` → 422 + allowed values | BC-30, K9.1 |
| `material` | optional valid `materials.code` → 422 + allowed values | BC-31, K9.1 |
| `imageRef` | the caller's own completed `MediaRef` (ownership + existence); never bytes | TRX-1, PR-8 |
| `isFavorite` | boolean | §13.3 |
| `category`/`color` (filters) | valid vocab codes → 422 | API-24/25 |
| `sort` / `order` | `created_at|updated_at|name` × `asc|desc` → 422 | API-26 |
| `page` / `page_size` | 1-based; `page_size` `[1,100]` → 422 | API-20 |

All validation is **server-side** (Flutter never enforces security) and
returns the **safe client message**, never internals (ER-2).

---

## 7. Error reference for this surface

| `error.code` | HTTP | When | Notes |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | bad `name`/vocab/filters/sort/pagination/`item_id` | field errors + allowed values in `details` |
| `MEDIA_FAILURE` | 413/422 | invalid image reference on create/update; M16 upload validation | `details.maxBytes`; sealed until MS10.3 |
| `AUTHENTICATION_ERROR` | 401 | missing/expired/revoked token | + `WWW-Authenticate: Bearer` |
| `NOT_FOUND` | 404 | item not owned / never existed; account gone | 404-not-403, no existence leak |
| `CONFLICT` | 409 | duplicate/limit on create; FK refs on delete | `details.kind` |
| `EXTERNAL_SERVICE_FAILURE` | 502/503 | M16 `/complete` verification (when mounted) | C-8: no storage/provider internals |
| `RATE_LIMITED` | 429 | any endpoint | + `Retry-After` |

---

## 8. Open decisions (carried forward, unchanged where already recorded)

1. **D-AUTH-1 — auth provider** — unchanged; gates mounting the whole P0
   wardrobe surface (endpoints stay unmounted until the seam lands, API-12).
2. **MS10.3 — media seal** — item images depend on M16 unsealing; until then
   no `imageRef` and no fake 200 (§4.2, API-12). Purpose vocabulary and exact
   size/MIME limits are config-driven, finalized at M16.
3. **W-2 single-item GET** — defined but **additive**: not in the current
   48-endpoint inventory; the details screen is served from the list today.
   Accepted (API-2) when the inventory adds the read.
4. **Archive** — **deliberately not defined** (no archive column/state/UC).
   If a soft-delete/archive ships, it adds a `status`/`archived_at` column +
   a controlled key — a product + schema decision first (§5.5).
5. **Idempotency-Key on item create** — the inventory does not key W-3
   (duplicates surface as duplicate rows). Additive if the product wants
   duplicate suppression.
6. **Server-side category counts / extra filters** — chips counts are
   client-derived today; `material`/`isFavorite`/`q` filters and server counts
   are additive-only (API-2).
7. **Materials vocabulary read** — no `GET /v1/knowledge/materials` in the
   inventory; the create/update validate the code server-side anyway.
   Additive read if the add-item swatches move off static config.
8. **Media purpose for wardrobe images** — config-driven user-purpose set
   (e.g. `outfit_input`); a dedicated `wardrobe` purpose is additive/config.
9. All other open decisions from `API_CONTRACT_RULES.md` §16,
   `PROFILE_ONBOARDING_API.md` §8, `RECOMMENDATION_API.md` §8, `SCAN_API.md`
   §8, and `APPEARANCE_API.md` §8 remain open and are unaffected.

---

## 9. Report, assumptions, constraints

**What changed (this step):** added `docs/api/WARDROBE_API.md` — the field-level
API contract for the wardrobe surface. It defines every task operation —
**list** (W-1), **retrieve single item** (W-2, additive), **create** (W-3),
**update** (W-4, PATCH partial incl. favorite), **delete** (W-5, with archive
explicitly not-supported), **categories/vocabulary** (W-6, referenced knowledge
reads), **filters/sorting/pagination** (§4.4), **wardrobe insight** (W-7), and
**image/media handling separate from JSON data** (§4.2 + §5.8, the M16
signed-URL flow) — each with method/path/request/response/validation/
authorization/errors plus security/side-effects/entities, consistent with the
sibling contracts. Nothing is implemented.

**Skills used:** repository + documentation analysis (the real wardrobe screens
+ mock data, `wardrobe_items` + vocab tables, TRX-1, BC-18/29/30/31/41, PR-1/
2/3/8, UC-10…14, MEDIA_UPLOAD_ARCHITECTURE M16 flow + MS10.3, API_CONTRACT_RULES
§12.3/§12.5/§8.2/§10/§13.3, API_INVENTORY endpoints 11–15/19–22/47–48,
ERROR_HANDLING taxonomy) — documentation only.

**Files changed:** `docs/api/WARDROBE_API.md` (new); `CURRENT_STATE.md`
(status).

**Validation run:**
- **Every required operation traces 1:1 to the accepted inventory** — W-1→11,
  W-3→UC-10/12, W-4→UC-11/12/13, W-5→UC-13/14, W-7→UC-14/15; W-6→knowledge
  19/20; media→47/48 (sealed). Paths/methods/auth/UC/errors identical to
  `API_CONTRACT_RULES.md` §12.3/§12.5 and `API_INVENTORY.md` §5.4/§5.6/§5.16.
  **W-2 is explicitly flagged additive** (not in the inventory), archive
  explicitly excluded (§3/§5.5), no invented endpoints.
- **Wire shapes match the accepted sketches AND the real product** — item
  DTOs identical to §13.3 (`WardrobeItem`/`Create`/`Patch`/`Insight`/
  `MediaRef`), field names from `wardrobe_items` columns and
  `wardrobe_mock_data.dart`; `category`/`color`/`material` carry vocab codes
  (K9.1), not display strings.
- **Image/media is structurally separated from JSON data** — item endpoints
  carry only `imageRef: MediaRef` (PR-8); bytes move via the M16 signed-URL
  flow (endpoints 47/48), sealed until MS10.3; no multipart, no base64, no
  URLs in JSON (§4.2/§5.8).
- **Auth/authorization/errors consistent** — all item endpoints auth +
  owner-only (OW-1, 404-not-403); frozen 12-category errors; 401 +
  `WWW-Authenticate`, 429 + `Retry-After`; PATCH/DELETE naturally idempotent
  (§11).
- **`git status --short`:** `docs/api/` now holds API_CONTRACT_RULES.md,
  API_INVENTORY.md, AUTH_API.md, PROFILE_ONBOARDING_API.md, APPEARANCE_API.md,
  SCAN_API.md, HAIRSTYLE_RECOMMENDATION_API.md, RECOMMENDATION_API.md,
  WARDROBE_API.md (untracked) + `CURRENT_STATE.md`; no code, directories, or
  files created.
- No `pytest` run needed: no code changed.

**Remaining issues / follow-ups:**
- The P0 wardrobe endpoints are **not mounted** until D-AUTH-1; item images
  wait on MS10.3/M16 (API-12 — no fake 200).
- W-2 single-item GET, archive, create-idempotency, server-side counts,
  materials read, and the wardrobe media purpose are additive/open (§8).
- Other open decisions unchanged: auth provider (D-AUTH-1), User fields,
  Today'sLookRecord (P1), RecommendationHistory (P3), conversation retention,
  K9.1 knowledge shape, media-privacy (MS10.3), feedback design.

**Assumptions recorded:**
- The details screen is served from the list today; W-2 is defined for
  completeness and accepted additively — it changes nothing until mounted.
- `category`/`color`/`material` are vocab codes resolved to labels client-side
  via the public knowledge catalog (K9.1); the client never sends free strings.
- Item images are private user media (MS10.3): reference-only in JSON, bytes
  via M16, out-of-DB deletion on item delete, byte deletion on erasure.
- Delete is the only removal today; archive is a future product + schema
  decision, not an invented endpoint.
- Category counts and favorites are client-derived from the list; the `all`
  chip is client-side only.

**Constraints honored:** no implementation, the live assistant contract
untouched (F-5), no invented APIs (W-2 flagged additive, archive/media excluded
honestly), item/DTO shapes kept identical to the accepted contract and sibling
docs, the no-internals rule enforced, image/media separated from JSON data, the
UI Change Safety Rule (no UI touched), and the Scope rule (this document +
`CURRENT_STATE.md` only).

---

## 10. Wear intelligence surfacing — W-8/W-9 (STEP 17.2, accepted per DEC-012)

This section is the accepted wire contract for wear surfacing. It binds
`POST`/`GET /v1/wardrobe/wears` (implemented, STEPS 15.3–15.4B) to one
capture surface, and specifies one new read-only summary route
(**not yet implemented** — STEP 17.3). `GET /v1/wardrobe/insight` (W-7,
§5.7) is unchanged and stays wear-free.

### 10.1 Operation selection

| # | Operation | Decision |
| --- | --- | --- |
| W-8 | **Log wear** — `POST /v1/wardrobe/wears` | **Required — exists.** Single capture surface: WARDROBE-004, one item per action (§10.2). No route/shape change here. |
| W-9 | **Wear summary** — `GET /v1/wardrobe/wear-summary` | **Required — accepted, NOT implemented.** Dedicated read-only route (§10.3). STEP 17.3 implements it exactly. |
| — | Extend W-7 with wear | **NOT defined** — rejected (DEC-012 rationale). W-7 shape, verbatim mapping, and 204 semantics stay frozen. |
| — | Outfit-level capture (`selectedItemIds` → one group) | **NOT defined** — deferred (no surface holds authoritative backend UUID sets, §10.2). |
| — | Per-row wear delete/edit | **NOT defined** — deferred (retention rule, §10.7). |

### 10.2 W-8 — Capture surface rule (existing route, new binding)

- **Method / path:** `POST /v1/wardrobe/wears` (unchanged: required
  `Idempotency-Key` header → 422 when missing; body
  `{itemIds: UUID[1..10], wornAt?: ISO-8601}`; `wornAt` omitted → server
  now; future instant → 422; unknown/foreign IDs → 404-not-403; replay →
  201 `created=false`; changed payload → 409; append-only).
- **The one capture surface:** `WardrobeItemDetailsScreen`
  (WARDROBE-004), single item only — one tap sends exactly one backend
  UUID, hence one ledger group of one row (DEC-011 unchanged).
- **UUID gate (product rule):** the control renders if and only if the
  item was loaded from the live backend in the current session. Local
  `LearningService` IDs ("1"–"24") must never be sent
  (`WardrobeClient.logWear` contract); mock-fallback items hide the
  control instead of erroring. The server stays authoritative
  (422/404/409).
- **Explicitly not capture surfaces (v1):** HOME-002 "Wear This Look"
  (components carry mock-catalog IDs with no backend-UUID mapping —
  stays snackbar-only, unchanged); the assistant
  `OutfitRecommendationCard` (`selectedItemIds` are local-snapshot IDs
  echoed through `app/ai/engine.py` and fail save validation with 422 —
  save flow unchanged). No new screen. No automatic logging on save,
  favorite, or any other action.
- **Flutter capture UX states:** 201 `created=true` → logged
  confirmation; 201 `created=false` → neutral already-logged note (never
  presented as a new log); 404 → item gone, hide/disable + refresh data;
  409 → neutral error (same-key reuse with changed payload is a client
  bug); 422/401/5xx/malformed/network → null → "couldn't log, safe to
  retry", retrying with the SAME idempotency key. Failures never
  fabricate success (existing no-mock-fallback rule).

### 10.3 W-9 — Wear summary (`GetWearSummary`, new route)

- **Method / path:** `GET /v1/wardrobe/wear-summary`
- **Status:** **accepted, NOT implemented** (no router/schema/Flutter
  exists; STEP 17.3 builds backend, STEP 17.4 builds Flutter).
- **Request schema:** none.
- **Response schema:** `200 OK` — `WearSummary` (camelCase keys,
  UUID strings, ISO-8601 UTC instants):

```
WearSummary {
  totalWears*: int,                        // == sum(wearCounts) == sum(wearsByCategory)
  wearCounts*: { uuid: int },              // EVERY current item incl. zeros, sorted-id order
  lastWorn*: { uuid: ISO-8601 | null },    // EVERY current item, null = never worn
  mostWornItemIds*: [uuid],                // max-count ties; [] when totalWears == 0
  leastWornItemIds*: [uuid],               // min-count ties over ALL current items; [] only when wardrobe empty
  unwornItemIds*: [uuid],                  // zero-count subset, id asc
  recentlyWornItemIds*: [uuid],            // last wear >= now − 30d inclusive, last-worn desc + id asc
  wearsByCategory*: { code: int },         // current-item vocab codes only, code-sorted, zero-filled
}
```

- **Validation:** none (read). All IDs are backend wardrobe UUIDs;
  category keys are wardrobe-category vocab codes (K9.1).
- **Authorization:** **auth** (Bearer); **owner** (OW-1).
- **Errors:** `200`; `401`; `429 RATE_LIMITED`. Never 204 (a summary of
  an empty wardrobe is a valid zero object, not "no insight" — this is
  the deliberate difference from W-7). Never 404 for empty (same
  reason). Frozen `{error:{code,message,details}}` taxonomy (§4.5).
- **Security considerations:** owner's own history + current items only;
  per-item UUIDs are the owner's own row identities (same exposure as
  the item list); no internals, no ledger payload, no other-user data.
- **Side effects:** none — derived read-only computation over flat
  `wardrobe_wear_events` (SELECT-only, no commit).
- **Domain entities involved:** `wardrobe_wear_events` (read), E2
  `WardrobeItem` (membership/category, read). Never the ledger
  `item_ids` payload, favorites, saved looks, recommendations, or
  created/updated timestamps.

### 10.4 Promoted semantics (product/API contract, from 15.6 convention)

- **Recent:** an item is recent when its last wear is at/after
  `now − 30 days`, boundary inclusive. `now` is server time.
- **Most-worn:** items tied at the maximum wear count; empty list when
  nothing was ever worn (`totalWears == 0`); ordered last-worn desc,
  item id asc.
- **Least-worn:** items tied at the minimum wear count over ALL current
  wardrobe items — never-worn items included when present; empty list
  only when the wardrobe itself is empty. Never-worn (null) sorts before
  any instant, then last-worn asc, then item id asc.
- **Unworn:** the zero-count subset of current items, item id asc.
- **Categories:** categories of the owner's current items only
  (code-sorted, zero-filled); categories with no current items never
  appear.
- **Invariant:** `totalWears == sum(wearCounts) == sum(wearsByCategory)`
  always holds (stale deleted-item rows are ignored everywhere, so sums
  reconcile).
- **Stale/deleted references:** rows whose item no longer exists match
  nothing and are ignored in every field. A deleted item can never be
  newly logged (owner-scoped 404) while its past rows remain history.

### 10.5 Wear copy rules (grounded templates for 17.4 rendering)

v1 copy uses **counts only, never item names** (the summary carries IDs;
name resolution is deferred). Behavioral claims are gated by data
strength; ties are always named as ties.

- **No usable history (`totalWears == 0`):** no wear sentence at all
  (same rule as the saved-look suffix — no claim beats an ungrounded
  one). A summary card may show the static helper "No wears logged
  yet" and counts of 0; no most/least/unworn language even though
  `leastWornItemIds`/`unwornItemIds` are populated.
- **Low-data (`totalWears > 0`):** counts only —
  "Logged N wear(s) across M item(s)." No superlatives from a single
  event beyond what the lists state.
- **Recent (`recentlyWornItemIds` non-empty):** "N item(s) worn in the
  last 30 days." Absent otherwise (never "nothing worn lately").
- **Most-worn (`totalWears > 0`):** "Most-worn: N item(s) at C wears"
  + " (tied)" when the list has >1 member. Never "favorite".
- **Least-worn (`totalWears > 0`):** "Least-worn: N item(s) at C wear(s)"
  + " (tied)" when the list has >1 member. Never "neglected".
- **Unworn (`totalWears > 0`, list non-empty):** "M item(s) not logged
  yet." Never "you never wear …".
- **Category (`wearsByCategory`):** counts only — "M of N logged wears
  are {code}." No balance/rotation judgments.
- **Banned language:** "you never wear", "always", "favorite" (from
  wear), "neglected", "should wear", "need to", "balanced/unbalanced",
  "rotation" as a judgment, "popular". No fabricated behavioral claims.

### 10.6 204 / error / offline (insight safety rule preserved)

| State | W-9 backend | Flutter |
| --- | --- | --- |
| Empty wardrobe | 200 zero object (all maps/lists empty, `totalWears: 0`) | counts-only or hidden; never behavioral text (§10.5) |
| No history, items exist | 200 (`mostWorn: []`, `least/unworn` populated) | no wear sentence (§10.5) |
| 401/429/5xx | frozen error taxonomy, allow-listed `details` only | null → hide card; list stays usable |
| Malformed 200 / network failure | n/a | null → hide card (never render partial maps) |
| Offline | n/a | card hidden; capture control disabled governance per §10.2 (no backend → no provenance → no capture) |

Errors must not fabricate data — the existing Wardrobe Insight safety
rule applies unchanged to the summary surface.

### 10.7 Retention / privacy (accepted rule, no new endpoint)

- Wear history is **append-only and retained indefinitely** — history is
  the product (15.2 Q8 accepted).
- **Account deletion** cascade-erases groups + rows (`user_id → users`
  CASCADE, migrations 0012/0014 — already implemented).
- **Item deletion** preserves rows; stale refs ignored at read
  (No-FK-to-trigger — already implemented).
- **No per-row wear delete/edit endpoint exists in v1** (deferred;
  reconsider only on a real retention demand). No token/image/snapshot
  logging (IDs only in logs).

### 10.8 Reconciliation note (no conflicting duplicate)

`FEEDBACK_LEARNING_API.md` §3/§4.3/§8 ("WEAR NOT supported — no action,
concept, signal type, or endpoint exists") is a STEP-6 design-time
statement that predates the 15.x wear-event foundation. It is superseded
ONLY for capture/summary existence. Its signal-model rules stand
unchanged and are reaffirmed here: no `worn` signal type, M10 remains
the sole writer of `learning_signals`, no client signal-submit endpoint,
wear never becomes a preference write, and regenerating/saving without
wearing carries no wear meaning. That document is intentionally not
edited (frozen STEP-6 design record); this section is the single home
for the wear wire contract.

### 10.9 Explicitly deferred (not in this contract)

Multi-item/outfit-level capture; HOME-002 and assistant-card capture
(blocked on the local-ID → backend-UUID sync repair); wear sentences
inside W-7; per-row wear delete/edit; retention expiry; item-name
rendering in wear copy; any outfit-generation, wardrobe-CRUD, media,
auth, feedback, or learning-surface change.
