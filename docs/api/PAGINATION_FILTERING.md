# Fansivibe — API Pagination, Filtering & Sorting

> **STEP 6 — API CONTRACT DESIGN.** Defines the **pagination, filtering, and
> sorting conventions** for Fansivibe APIs and applies them **only to the
> collections that actually need them**. It fixes the **page-or-cursor
> strategy**, **default limit**, **maximum limit**, **sorting**, **filtering**,
> and **response metadata** for each real list surface (wardrobe, saved looks /
> outfits, events, assistant conversations, discover, recommendation history,
> knowledge), and it explicitly names the resources where pagination **adds no
> value** and is therefore not used. It is the focused companion to
> `API_CONTRACT_RULES.md` (§8.2 list envelope, §10 pagination/filtering/
> sorting API-20…27), `API_LAYER_ARCHITECTURE.md` (§8–10), and
> `API_RESPONSE_CONVENTIONS.md` (§6 pagination format) — it consolidates and
> **finalizes** the cursor metadata names left open there (§14.2), without
> changing any accepted shape.
>
> **Status: contract design only. Nothing is implemented.** No code, no query
> builders, no DTOs, no Flutter changes. The offset list envelope
> `{items,page,page_size,total}` (API-18) and the cursor convention
> (API-21) are unchanged; this document fixes the **per-collection**
> parameters (which strategy, which limits, which filters, which sort keys,
> which metadata) against the accepted inventory.
>
> **Source of truth:** `API_CONTRACT_RULES.md` (§8.2 envelope, §10 API-20…27,
> §12 endpoint catalog), `API_LAYER_ARCHITECTURE.md` (§8 pagination API-20/21,
> §9 filtering API-23/24/25, §10 sorting API-26/27), `API_RESPONSE_CONVENTIONS.md`
> (§6), the sibling module contracts (`WARDROBE_API.md` §4.4,
> `DAILY_OUTFIT_EVENTS_API.md` §4.6, `RECOMMENDATION_API.md` §6,
> `ASSISTANT_API.md` §5.3, `SCAN_API.md` §5.8, `API_CONTRACT_RULES.md`
> §12.5/§12.13), `TABLE_DEFINITIONS.md` (sort/filter keys), and the live repo
> (`backend/app/` — no list endpoint exists yet).

---

## 1. Purpose and scope

This document defines, once, how Fansivibe **list surfaces** paginate, filter,
and sort, then applies the conventions to each collection that actually needs
them:

1. **Wardrobe** — `GET /v1/wardrobe/items` (endpoint 11) — §9.1.
2. **Outfits** — no standalone outfit list; generated outfits are value
   objects, saved outfits live in the shared saved-looks collection (§9.2/§9.3).
3. **Saved looks** — `GET /v1/looks/saved` (endpoint 24) — §9.3.
4. **Recommendations** — generated results are never paginated; the durable
   recommendation surfaces are saved looks + analysis-run history (§9.4).
5. **Events** — `GET /v1/events` (endpoint 27) — §9.5.
6. **Assistant conversations** — `GET /v1/assistant/conversations` (A-3,
   additive, gated on retention) — §9.6.
7. **Discover content** — `GET /v1/looks` (endpoint 43, UC-31, cursor feed) —
   §9.7.

Plus the two other real list surfaces in the inventory: the **knowledge looks
catalog** (`GET /v1/knowledge/looks`) and the **analysis-run history**
(`GET /v1/analysis/runs`), §9.8/§9.9.

It also **explicitly avoids pagination where it provides no value** (§10):
single resources, bounded value objects, tiny controlled vocabularies, and
generated results.

**The three binding rules:**

1. **One envelope family (API-18).** List responses are either the **offset**
   envelope `{items, page, page_size, total}` or the **cursor** envelope
   `{items, next_cursor, has_more}` (feeds only). No module invents another
   list wrapper.
2. **Strategy follows the collection, not the team (API-20/21).** Stable,
   user-owned collections with a meaningful total and occasional
   page-jumping → **offset**; deep or infinite, engine-ranked feeds with
   unstable totals → **cursor**; everything else → **no pagination** (§3).
3. **Filters and sort keys are server-validated vocabulary (API-23…27).**
   Explicit typed query params, unknown filter value / unknown sort key /
   out-of-bounds limit → `422 VALIDATION_ERROR` with field errors + allowed
   values (API-30, `API_ERROR_CONTRACT.md` §6). Engine-ranked ordering is
   **never** re-sorted by the client or a `sort` param (API-27).

**What it does not do:** implement anything, mount endpoints, add a list
endpoint that is not in the inventory, invent a new envelope, or change the
accepted offset shape. The cursor metadata names (`next_cursor`, `has_more`)
are **finalized here** for the discover feed (UC-31), resolving
`API_RESPONSE_CONVENTIONS.md` §14.2.

### 1.1 Grounding facts (re-verified)

- **Offset pagination is the default (API-20/22).** `?page=1&page_size=20`,
  1-based, default `page_size` 20, bound `[1,100]`; `total` from the same
  query; out-of-bounds `page_size` → `422`. Envelope `{items,page,page_size,
  total}` (`API_CONTRACT_RULES.md` §8.2, `API_RESPONSE_CONVENTIONS.md` §6.1).
- **Cursor pagination is reserved for deep/feed lists (API-21).**
  `?cursor=<opaque>&limit=20`; cursor is server-generated and opaque, encodes
  the last item key; feed ordering stays stable (secondary key = id)
  (`API_CONTRACT_RULES.md` §10, `API_RESPONSE_CONVENTIONS.md` §6.2). The
  discover feed `GET /v1/looks` is the designated cursor consumer (UC-31).
- **Filters are explicit typed query params (API-23/24/25).** Validated
  server-side against the controlled vocabulary → `422` on invalid values. No
  free-form `?filter=json`.
- **Sorting is `?sort=<key>&order=asc|desc` (API-26)** with documented keys
  per endpoint; unknown key → `422`. Personalized/engine-ranked ordering
  (discover match, hair/grooming score) is returned as produced — the API
  never re-sorts engine output (API-27).
- **The accepted catalog already fixes most list surfaces.** W-1 (wardrobe),
  E-2 (events), `GET /v1/looks/saved`, `GET /v1/analysis/runs`,
  `GET /v1/knowledge/looks` all exist in `API_CONTRACT_RULES.md` §12 with
  their filters/sorts; the conversation list (A-3) is additive + gated. This
  document consolidates them and adds the missing **cursor metadata** and the
  **explicit no-pagination** list.
- **Empty is not an error.** Empty list → `200` with `items: []` and
  `total: 0` (offset) or `items: []` + `next_cursor: null` (cursor); a `page`
  beyond the last page → `200` with empty `items` (§8.4). Never a fake error.
- **Pagination never leaks ownership.** Every list is owner-scoped (OW-1);
  pagination slices within the caller's own rows only (`SCAN_API.md` §5.8).

---

## 2. Source of truth and inputs

| Concern | Source |
| --- | --- |
| Offset pagination + envelope | `API_CONTRACT_RULES.md` §8.2/§10 (API-18, API-20/22); `API_LAYER_ARCHITECTURE.md` §8; `API_RESPONSE_CONVENTIONS.md` §6.1 |
| Cursor pagination (feeds) | `API_CONTRACT_RULES.md` §10 (API-21); `API_RESPONSE_CONVENTIONS.md` §6.2 |
| Filtering | `API_CONTRACT_RULES.md` §10 (API-23/24/25); `API_LAYER_ARCHITECTURE.md` §9 |
| Sorting | `API_CONTRACT_RULES.md` §10 (API-26/27); `API_LAYER_ARCHITECTURE.md` §10 |
| Per-collection params (filters/sort/limits) | WARDROBE_API §4.4, DAILY_OUTFIT_EVENTS_API §4.6, RECOMMENDATION_API §6, ASSISTANT_API §5.3, SCAN_API §5.8, API_CONTRACT_RULES §12.5/§12.13 |
| Sort/filter key names | `TABLE_DEFINITIONS.md` (canonical column/field names, A3.1) |
| Validation → 422 field errors | `API_ERROR_CONTRACT.md` §6 (API-30); `ERROR_HANDLING.md` §5.1 |
| Empty-is-not-error | `API_CONTRACT_RULES.md` §8.4; `ERROR_HANDLING.md` §5.12 |
| Owner-only lists (OW-1) | `AUTH_AUTHORIZATION_ARCHITECTURE.md`; `SCAN_API.md` §5.8 |

---

## 3. The strategy decision — offset, cursor, or none

Choose by the **shape of the collection**, not by endpoint count:

| Collection characteristic | Strategy |
| --- | --- |
| User-owned, bounded-typical-size, meaningful total, occasional page-jumping, stable identity per item | **Offset** `page`/`page_size` (API-20) |
| Deep or infinite feed, engine-ranked ordering, unstable total, heavy DTOs, "load more" UX | **Cursor** `cursor`/`limit` (API-21) |
| Single resource, bounded value object, tiny controlled vocabulary, generated one-shot result | **No pagination** (§10) |

Applied to the accepted inventory:

| Collection | Endpoint | Strategy |
| --- | --- | --- |
| Wardrobe items | `GET /v1/wardrobe/items` | offset |
| Saved looks (incl. saved outfits) | `GET /v1/looks/saved` | offset |
| Events | `GET /v1/events` | offset |
| Assistant conversations (gated) | `GET /v1/assistant/conversations` | offset |
| Analysis-run history | `GET /v1/analysis/runs` | offset |
| Knowledge looks catalog | `GET /v1/knowledge/looks` | offset |
| Discover look feed | `GET /v1/looks` | **cursor** |
| Outfit/event-outfit generation, today's look, wardrobe insight, learning summary, subscription, run detail, conversation transcript, look detail, knowledge vocabularies | — | **none** |

Why discover is cursor and everything else offset: the discover feed is
engine-ranked (API-27), effectively infinite, and its `total` is meaningless
(the ranking changes with each decision context, R-A16) — offset page numbers
would drift. Wardrobe/saved-looks/events/conversations/runs are stable
user-owned rows with a meaningful count (`total` from the same query, API-22).

---

## 4. Offset pagination (the default)

### 4.1 Parameters

| Param | Rule |
| --- | --- |
| `page` | 1-based; default `1`. A value `< 1` → `422`. |
| `page_size` | default `20`; bound `[1,100]` → out-of-bounds `422` (API-22). |

### 4.2 Response envelope

```json
{
  "items": [ /* DTOs */ ],
  "page": 1,
  "page_size": 20,
  "total": 137
}
```

- `total` is computed **from the same query** (same filters) — never a separate
  unfiltered count (API-20).
- `page`/`page_size` echo the request values (or defaults), so clients can
  render "page X of Y" without state.
- Empty list → `200` with `items: []`, `total: 0`; `page` beyond the last page
  → `200` with `items: []` and the requested `page`/`total` — **never an
  error** (§1.1, API_CONTRACT_RULES §8.4).

### 4.3 Bounds

`page` and `page_size` are integers; a non-integer or a value outside the
allowed range → `422 VALIDATION_ERROR` with field errors + allowed range
(`API_ERROR_CONTRACT.md` §5.1/§6). `total` is a `count`; it may be 0.

---

## 5. Cursor pagination (feeds — discover)

Reserved for the discover feed `GET /v1/looks` (UC-31). **Finalized here:**
the cursor metadata names, resolving `API_RESPONSE_CONVENTIONS.md` §14.2.

### 5.1 Parameters

| Param | Rule |
| --- | --- |
| `cursor` | **server-generated, opaque** token encoding the last item key; clients **never construct** it. Absent/omitted on the first request. |
| `limit` | default `20`; max `50`. `0`, negative, or `> 50` → `422`. (Feeds carry heavy DTOs; the tighter max keeps a page small.) |

### 5.2 Response envelope

```json
{
  "items": [ /* LookSummary[] */ ],
  "next_cursor": "7a2b3c4d…",
  "has_more": true
}
```

- `next_cursor` is the opaque token for the **next** page; `null` (or absent)
  when there are no more pages.
- `has_more` is a boolean the client can check before issuing the next request
  ("load more" UX) — it mirrors whether `next_cursor` is present.
- **No `total`** — feed totals are unstable (engine-ranked, API-27); inventing
  one would be misleading.
- **Stable ordering (API-21):** the engine ranking is the primary order; the
  server adds a **secondary sort key (item `id`)** so the cursor window never
  shifts between pages.

### 5.3 Bounds

A malformed or expired `cursor` (not issued by the server) → `422
VALIDATION_ERROR`. An `unknown` cursor value is never silently reset to page 1.
`limit` out of range → `422`.

---

## 6. Sorting

- **Syntax:** `?sort=<key>&order=asc|desc` (API-26). `order` omitted → the
  key's documented default (below).
- **Keys are documented per collection** (§9). Unknown key or order → `422`
  with field errors + allowed values.
- **Defaults:** time keys sort `desc` (newest first) unless a collection
  documents otherwise (events sort `event_date` `asc` — soonest first);
  name/alpha keys sort `asc`.
- **Never re-sort engine output (API-27):** discover match order, hairstyle/
  grooming/grooming scores, and any Decision-Engine ordering are returned **as
  produced**; no `sort` param exists on those surfaces. If a collection is
  engine-ordered, its sort keys are limited to what the engine supports (or
  none).
- **Keys are DTO field names** (`createdAt`, `updatedAt`, `name`,
  `eventDate`) — never table/column names (C-7, A3.1).

---

## 7. Filtering

- **Syntax:** explicit typed query params per collection (§9), e.g.
  `?category=<code>&color=<code>`, `?from=<YYYY-MM-DD>`, `?occasion=<code>`.
- **Vocabulary-validated server-side (API-23/24/25):** a filter value that is
  not a known code / not a valid date → `422` with field errors + the allowed
  values (`API_ERROR_CONTRACT.md` §6). Clients never filter download-and-locally
  (API-25).
- **No free-form `?filter=json`** anywhere (API-24).
- **Client-side pseudo-filters stay client-side:** the wardrobe `all` chip,
  favorites count, and category chips are derived from the list in the client
  (WARDROBE_API §4.4/§5.1) — no server-side count/favorite endpoints.
- **Additive-only:** any filter a collection would like later (e.g.
  `material`, `isFavorite`, `sourceContext`, `eventType`, date-range) is
  additive-only (§9, API-2) — never silently mounted.

---

## 8. Response metadata

Two list envelopes only (§3/§4/§5):

| Envelope | Fields | Used by |
| --- | --- | --- |
| Offset | `items`, `page`, `page_size`, `total` | wardrobe, saved looks, events, conversations, analysis runs, knowledge looks |
| Cursor | `items`, `next_cursor`, `has_more` | discover feed |

Rules:

- **`items`** are **summary DTOs**, not full detail DTOs, where the DTO is
  heavy — e.g. scan history rows carry no `result` (SCAN_API §5.8); the detail
  read (`GET .../{id}`) returns the full DTO. Avoids bloated list payloads.
- **No message previews / content in list rows** where user content is
  involved (conversation summaries expose `messageCount` only — ASSISTANT_API
  §5.3).
- **No `total` on cursor feeds** (§5.2).
- **Empty is `200`** with `items: []` (and `total: 0` / `next_cursor: null`) —
  never a 404 or 500 (§1.1).
- **Owner-only (OW-1):** every list slices the caller's own rows; pagination
  never leaks another user's items (§1.1).

---

## 9. Per-collection application

| # | Collection | Endpoint | Strategy | Default / Max | Filters (accepted) | Sort keys (default order) |
| --- | --- | --- | --- | --- | --- | --- |
| 9.1 | Wardrobe | `GET /v1/wardrobe/items` | offset | 20 / 100 | `category`, `color` | `createdAt` (desc) · `updatedAt` (desc) · `name` (asc) |
| 9.2 | Outfits (generated/event) | value objects — **no list** | none | — | — | — |
| 9.3 | Saved looks (incl. saved outfits) | `GET /v1/looks/saved` | offset | 20 / 100 | (none today; `sourceContext` additive) | `createdAt` (desc) |
| 9.4 | Recommendation history | `GET /v1/analysis/runs` (+ `GET /v1/looks/saved`) | offset | 20 / 100 | `runType` | `createdAt` (desc) |
| 9.5 | Events | `GET /v1/events` | offset | 20 / 100 | `from` | `eventDate` (asc) |
| 9.6 | Assistant conversations (gated) | `GET /v1/assistant/conversations` | offset | 20 / 100 | (none) | `updatedAt` (desc) |
| 9.7 | Discover content | `GET /v1/looks` | **cursor** | 20 / 50 | `occasion`, `style`, `fit` | engine-ranked (API-27, no `sort`) |
| 9.8 | Knowledge looks catalog | `GET /v1/knowledge/looks` | offset | 20 / 100 | `occasion`, `style` | catalog `sortOrder` |
| 9.9 | Analysis-run history | `GET /v1/analysis/runs` | offset | 20 / 100 | `runType` | `createdAt` (desc) |

### 9.1 Wardrobe — `GET /v1/wardrobe/items` (W-1, endpoint 11)

- **Strategy:** offset (API-20). Request: `?category=&color=&sort=&order=&page=&page_size=`.
- **Filters:** `category` (vocab code), `color` (vocab code) — server-validated
  → `422` with allowed values. `material`, `isFavorite`, free-text `q` are
  **additive-only** (not in the inventory; favorites today are client-derived,
  WARDROBE_API §4.4).
- **Sort:** `createdAt` (default, desc), `updatedAt` (desc), `name` (asc).
- **Metadata:** offset envelope. Items newest-first by default. Empty wardrobe
  → `200` `items:[] total:0`.
- **Pagination value:** real — a wardrobe grows with every uploaded item and
  the grid renders in pages.

### 9.2 Outfits — generated results are value objects, not a collection

- `POST /v1/outfits/generate` (endpoint 41) and `POST /v1/events/{event_id}/
  outfit` (endpoint 30) each return a **single** `OutfitRecommendation` value
  object (`RECOMMENDATION_API.md` §4.3) — never a paginated collection.
- **There is no `/v1/outfits` list endpoint** in the accepted inventory, and
  none is invented here (API-2/API-12). A saved outfit is a `SavedLook`
  snapshot (`POST /v1/outfits/saved` → `SavedLook`, UC-30, TRX-3) and is
  **listed via the saved-looks collection** (§9.3).
- A filtered "my outfits" view would ride `GET /v1/looks/saved` with an
  **additive** `sourceContext` filter (§9.3) — no new endpoint.

### 9.3 Saved looks (incl. saved outfits) — `GET /v1/looks/saved` (endpoint 24)

- **Strategy:** offset. Request: `?sort=createdAt&page=&page_size=`.
- **Filters:** none in the inventory today. `sourceContext` (the §3.1 type
  vocabulary: `outfit` | `hairstyle` | `grooming` | `daily` | `event` | …) is
  **additive-only** — it is the future "saved outfits" / "saved hairstyles"
  filter over the same type-agnostic collection (RECOMMENDATION_API §4.8).
- **Sort:** `createdAt` (desc). No engine re-sort (a saved list is user state).
- **Metadata:** offset envelope; items are `SavedLook` summaries (snapshot
  reference + `sourceContext` + `createdAt`), full snapshot via the detail
  read.
- **Pagination value:** real — saved looks accumulate across every
  recommendation surface.

### 9.4 Recommendations — never a paginated generated result

- **Generated recommendations are bounded value objects:** Shape A async run
  result `{ context, recommendations: { top, alternatives } }` and Shape B sync
  DTOs (`OutfitRecommendation`, `TodayLook`, `HairstyleRecommendation`) —
  `top`/`alternatives` is a small, fixed set, **never paginated**
  (RECOMMENDATION_API §4.7).
- **No `/v1/recommendations/*` list exists** (RECOMMENDATION_API §3.3 — the
  anti-fragmentation design has type-agnostic save/feedback/history).
- The durable recommendation collections are **saved looks** (§9.3, offset)
  and **analysis-run history** (§9.9, offset); the P3 `recommendation_history`
  trace, when it ships, reuses the same offset conventions
  (RECOMMENDATION_API §4.8).
- **Pagination value:** on the durable surfaces (yes), on a generated result
  (no — the result is a fixed recommendation set, not a scrollable list).

### 9.5 Events — `GET /v1/events` (E-2, endpoint 27)

- **Strategy:** offset. Request: `?from=&sort=eventDate&order=&page=&page_size=`.
- **Filters:** `from` (`YYYY-MM-DD`, events on/after that date) —
  server-validated → `422` (DAILY_OUTFIT_EVENTS_API §4.6). `eventType` and
  date-range are **additive-only**.
- **Sort:** `eventDate` only (default, `asc` — soonest-first, "upcoming" view);
  `order=desc` supported for past events.
- **Metadata:** offset envelope with `EventSummary[]` (no event-outfit
  snapshot in the list — the detail is served from the list today, E-3
  additive).
- **Pagination value:** real — events accumulate and the default view is a
  bounded upcoming window.

### 9.6 Assistant conversations — `GET /v1/assistant/conversations` (A-3)

- **Status:** **additive** (not in the accepted inventory) and **gated** on the
  conversation-retention decision (G6/G7). **NOT mounted** — no fake 200
  (API-12). Defined here so the conventions are settled when it ships.
- **Strategy:** offset. Request: `?page=&page_size=&sort=updatedAt`.
- **Filters:** none. **Sort:** `updatedAt` only (desc). `updatedAt` is the
  natural recency key for "continue where I left off".
- **Metadata:** offset envelope with `ConversationSummary { conversationId,
  startedAt, updatedAt, messageCount }` — **no message preview** (no user
  content in a list, ASSISTANT_API §5.3). Transcript = `GET
  /v1/assistant/conversations/{conversation_id}` (A-4, also gated).

### 9.7 Discover content — `GET /v1/looks` (GetLookFeed, endpoint 43, UC-31)

- **Strategy:** **cursor** (API-21) — the designated feed consumer.
  Request: `?occasion=&style=&fit=&cursor=&limit=`.
- **Filters:** `occasion`, `style`, `fit` — validated against the controlled
  vocabulary → `422` with allowed values (API-23). No `sort` — the feed is
  **engine-ranked** and returned as produced (API-27).
- **Metadata:** cursor envelope `{ items, next_cursor, has_more }` (§5.2).
  **No `total`** (unstable ranking).
- **Pagination value:** the defining case — a deep, infinite, personalized
  feed with a "load more" UX.
- **Note:** the public catalog read `GET /v1/knowledge/looks` (§9.8) is the
  offset-paginated, non-personalized sibling; the two are distinct resources
  (API_CONTRACT_RULES §12.5 vs §12.13).

### 9.8 Knowledge looks catalog — `GET /v1/knowledge/looks` (endpoint 18)

- **Strategy:** offset. Request: `?occasion=&style=&page=&page_size=`.
- **Filters:** `occasion`, `style` (catalog codes) — validated → `422`.
- **Sort:** catalog `sortOrder` (server-provided); no client `sort` (the
  catalog is knowledge content, K9.1).
- **Metadata:** offset envelope with `LookSummary[]`; `X-Knowledge-Version`
  header (KN-1).

### 9.9 Analysis-run history — `GET /v1/analysis/runs` (S-9, endpoint 40)

- **Strategy:** offset. Request: `?runType=&sort=createdAt&order=&page=&page_size=`.
- **Filters:** `runType` (`outfit` | `hairstyle` | `grooming`) — validated
  against the run_types codes → `422` (SCAN_API §5.8). `face` has no endpoint.
- **Sort:** `createdAt` only (desc — newest scan first).
- **Metadata:** offset envelope; list rows are **run summaries with no
  `result`** (the immutable result snapshot is only in the run detail
  `GET /v1/analysis/runs/{run_id}`, S-5/S-6) — keeps history reads light.
- **Pagination value:** real — run history is append-only (PR-5/6) and grows
  with every scan.

---

## 10. Where pagination provides no value (explicitly avoided)

Pagination is **not** applied to:

| Resource | Why no pagination |
| --- | --- |
| `GET /health`, `GET /v1/looks/today`, `POST /v1/looks/today` | single value object |
| `POST /v1/assistant/chat` | single exchange, bare `AssistantReply` (F-13) |
| `GET /v1/wardrobe/insight`, `GET /v1/learning/summary` | single derived value object |
| `GET /v1/subscriptions/me` | single resource (0..1 per user, R10) |
| `GET /v1/looks/{look_id}`, `GET /v1/events/{event_id}`, `GET /v1/analysis/runs/{run_id}`, `GET /v1/assistant/conversations/{conversation_id}` | detail reads return one DTO |
| `POST /v1/outfits/generate`, `POST /v1/events/{event_id}/outfit` | one `OutfitRecommendation` value object |
| Async run `result` (`top`/`alternatives`) | fixed bounded recommendation set (Shape A) |
| `GET /v1/knowledge/categories`, `colors`, `occasions`, `items` | tiny controlled vocabularies — returned in full as bare arrays (`VocabularyItem[]`), no envelope (API_CONTRACT_RULES §12.5) |
| `POST /v1/auth/*`, `POST /v1/looks/saved`, `POST /v1/outfits/saved`, etc. | writes return the created single resource |

Rule of thumb: if a surface returns **one** thing, a **fixed small set**, or a
**short closed vocabulary**, pagination is machinery without value — return
the resource bare (or as the small set) and skip the envelope. Pagination is
added only where a collection can grow beyond a screenful and the user
navigates it (the §9 list).

---

## 11. Validation reference

- **Offset conventions identical** to `API_CONTRACT_RULES.md` §10 (API-20/22)
  and `API_RESPONSE_CONVENTIONS.md` §6.1: 1-based `page`, `page_size` default
  20, bound `[1,100]`, `total` from the same query, envelope
  `{items,page,page_size,total}`.
- **Cursor conventions identical** to `API_CONTRACT_RULES.md` §10 (API-21):
  opaque server-generated `cursor`, stable secondary key; the metadata field
  names (`next_cursor`, `has_more`, no `total`) are **finalized here** for the
  discover feed (UC-31), resolving `API_RESPONSE_CONVENTIONS.md` §14.2.
- **Per-collection params match the sibling contracts 1:1** — W-1
  (WARDROBE_API §4.4/§5.1), E-2 (DAILY_OUTFIT_EVENTS_API §4.6/§5.2), A-3
  (ASSISTANT_API §5.3), S-9 (SCAN_API §5.8), discover/knowledge
  (API_CONTRACT_RULES §12.13/§12.5), saved looks (API_CONTRACT_RULES §12.6),
  recommendation surfaces (RECOMMENDATION_API §4.7/§6).
- **No new endpoints:** outfits/recommendations lists resolve to the existing
  saved-looks + run-history collections; the conversation list is documented
  as additive + gated (API-2/API-12).
- **Validation errors** follow `API_ERROR_CONTRACT.md` §5.1/§6 (422 field
  errors + allowed values); empty lists are `200`, never errors (§1.1).
- No code, routers, DTOs, or Flutter changes; `git status --short` shows only
  this doc + `CURRENT_STATE.md` (no `pytest` run needed).

---

## 12. Open decisions

1. **Cursor metadata — resolved here.** `{items, next_cursor, has_more}`,
   `limit` default 20 / max 50 (§5), finalize the discover feed; no `total` on
   feeds. (Resolves `API_RESPONSE_CONVENTIONS.md` §14.2/§14.3.)
2. **Additive filters** (each a product decision before mounting, API-2):
   wardrobe `material`/`isFavorite`/`q`; saved-looks `sourceContext`;
   events `eventType`/date-range.
3. **Conversation list** — mounts only with the retention decision (G6/G7);
   conventions are settled here, the endpoint stays unmounted (API-12).
4. **`recommendation_history` (P3)** — when it ships it reuses the offset
   conventions; the trace shape is not part of this task.
5. **Unchanged project-wide opens** — auth provider (D-AUTH-1), knowledge
   shape (K9.1), media privacy (MS10.3), feedback design (PR-12), User fields,
   Today'sLookRecord (P1).

---

## 13. Report, assumptions, constraints

**What changed (this step):** added `docs/api/PAGINATION_FILTERING.md` — the
pagination/filtering/sorting conventions: the strategy decision (offset vs
cursor vs none, §3), the offset contract (§4), the cursor contract with
finalized metadata (§5), sorting (§6), filtering (§7), response metadata (§8),
the per-collection application for wardrobe, outfits/saved looks,
recommendations, events, assistant conversations, discover, knowledge, and
run history (§9), and the explicit no-pagination list (§10). **No
implementation; no new endpoints; no new envelope; no accepted shape
changed** — only the previously-open cursor metadata was finalized for the
discover feed.

**Skills used:** repository analysis (`API_CONTRACT_RULES.md` §8.2/§10/§12,
`API_LAYER_ARCHITECTURE.md` §8–10, `API_RESPONSE_CONVENTIONS.md` §6,
WARDROBE_API §4.4, DAILY_OUTFIT_EVENTS_API §4.6, RECOMMENDATION_API §4.7/§6,
ASSISTANT_API §5.3, SCAN_API §5.8, API_INVENTORY) + design-doc synthesis —
documentation only.

**Files changed:** `docs/api/PAGINATION_FILTERING.md` (new).

**Validation run:**
- **Every collection traces to the accepted inventory** — wardrobe→11, saved
  looks→24, events→27, runs→40, discover→43, knowledge→18; outfits and
  recommendations honestly resolve to value objects + the saved-looks/
  run-history collections (no invented `/v1/outfits`, no
  `/v1/recommendations/*`, API-2); conversations→A-3 additive + gated (API-12).
- **Conventions identical to the source docs** — offset per API-20/22 (envelope
  unchanged), cursor per API-21, filters per API-23/24/25, sort per API-26/27
  (never re-sort engine output), 422 field errors per `API_ERROR_CONTRACT.md`,
  empty-is-200 per §8.4. Only the open cursor metadata names were finalized
  (API_RESPONSE_CONVENTIONS §14.2).
- `git status --short`: docs/api/ holds 14 untracked API docs
  (PAGINATION_FILTERING.md added) + modified CURRENT_STATE.md; no code,
  directories, or files created.

**Remaining:** STEP 6 design continues. The remaining feature-module contracts
and the media/outfits surface must apply these conventions (offset vs cursor,
default/max limits, server-validated filters/sorts, the two envelopes) with no
new wrapper and no pagination where §10 says none. Open decisions in §12.
