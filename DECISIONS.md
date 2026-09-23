# Fansivibe Decisions

This file records accepted major product and architecture decisions.

Do not record trivial implementation choices.

## DEC-001 — Flutter Frontend

Status: Accepted

Fansivibe uses Flutter as its primary application frontend.

Changing frontend technology requires project-owner approval.

---

## DEC-002 — Feature-First Architecture

Status: Accepted

Major product capabilities are organized as independent features.

Example:

features/
├── home/
├── discover/
├── wardrobe/
├── outfit_scan/
└── hairstyle/

New features should be addable without restructuring unrelated features.

---

## DEC-003 — Backend Direction

Status: Accepted Direction

Python FastAPI is the intended backend technology.

Flutter must not directly depend on individual AI providers.

---

## DEC-004 — Database Direction

Status: Accepted Direction

PostgreSQL is the intended primary relational database.

---

## DEC-005 — Primary Navigation

Status: Accepted

Primary navigation:

- Home
- Discover
- Stylist
- Wardrobe
- Profile

---

## DEC-006 — Repository Memory

Status: Accepted

AI agents do not share chat history.

Repository documentation and actual code are the shared source of truth.

`CURRENT_STATE.md` tracks current development state.

---

## DEC-007 — Incremental Development

Status: Accepted

Fansivibe is built feature by feature.

Ordinary feature tasks must not perform unrelated architecture migrations.

---

## DEC-008 — Declarative Routing with go_router

Status: Accepted

Routes are declared centrally using `package:go_router` with
`StatefulShellRoute.indexedStack` for persistent tab navigation.

- All route name strings are centralized in `lib/app/router/route_names.dart`.
- The single `GoRouter` config lives in `lib/app/router/app_router.dart`.
- Cross-feature screen imports are eliminated — screens navigate by name only.
- Screen data is passed through `state.extra` as typed objects or `Map<String, String>`.
- Route builders null-check `state.extra` to handle GoRouter 17 eager evaluation.

This replaces raw `Navigator.push(MaterialPageRoute(...))` calls spread across
all screen files.

---

## DEC-009 — STEP 7 Hairstyle Vertical Slice: Mounting + Gating Decisions (D1–D5)

Status: Accepted

The first production vertical slice (hairstyle recommendation) is implemented
end-to-end (Flutter → FastAPI → PostgreSQL → rules engine → save → feedback
signal) per `docs/implementation/STEP_7_HAIRSTYLE_IMPLEMENTATION_PLAN.md`. The
five gating decisions were approved before implementation:

- **D1 — Dev auth seam.** Until D-AUTH-1 lands, `app/api/deps.py` maps a Bearer
  token (`FANSIVIBE_DEV_TOKEN`, default `dev`) to the seeded dev user. Owner
  scoping (404-not-403) is fully enforced; real auth swaps in additively behind
  the same seam.
- **D2 — Profile-only pass.** Analysis submits `faceProfileRef` only; face-image
  upload is deferred behind sealed MS10.3. No fake analysis: no stored face
  shape → `422 INSUFFICIENT_USER_DATA` (client falls back to the offline mock).
- **D3 — Database layer.** SQLAlchemy 2.0 + `psycopg` (binary) + Alembic; a
  `postgres` service was added to `docker-compose.yml`. Minimal STEP-4 table
  subset (8 models) with a server-side `complete_analysis_run` SQL function
  (TRX-5 write-once guard).
- **D4 — AI enrichment scope.** The rules-only decision engine is the
  deliverable; optional LLM wording enrichment of `description` reuses the
  `llm_backend.py` seam (never structure/scores) and degrades safely.
- **D5 — Save behavior.** "Save Style"/"Try This Style" POST `#23`
  (`POST /v1/looks/saved`) with an `Idempotency-Key` (replay → original/409);
  TRX-3 commits save + `look_saved` signal together; the existing snackbar
  confirmation is preserved.

Also accepted (documented deviations kept honest): mounting analysis before
D-AUTH-1/MS10.3 is a documented, dev-seam-only deviation (no fake 200s); the
analysis run contract, `{error:{code,message,details}}` taxonomy, and the
202-`{run_id}` never-idempotent submit follow
`docs/api/FANSIVIBE_API_CONTRACT_V1.md`.
## DEC-010 — Saved-Look Domain Discriminator (STEP 11.16)

Status: Accepted

`saved_looks.source_context` (`hairstyle`/`grooming`/`outfit`, CHECK-guarded,
NULL = legacy row written before the contract) is the authoritative
backend-owned answer to "is this save an outfit, hairstyle, or grooming
save". `look_id IS NULL`, title text, `learning_signals.context`, and
unvalidated snapshot inspection must never be used as domain discriminators.
Outfit `snapshot.selectedItemIds` is validated (UUID list), ownership-checked
against the owner's wardrobe via the existing owner-scoped lookup, and
persisted canonically (sorted unique UUID strings). Unknown/foreign item IDs
reject the save (404, nothing stored); malformed IDs are 422.

## DEC-011 — Wear-Action Durable Ledger (STEP 15.4B)

Status: Accepted

One `POST /v1/wardrobe/wears` is one logical wear action: flat item-level
`wardrobe_wear_events` rows persist the history, while a durable
`wardrobe_wear_groups` ledger row owns idempotency —
`UNIQUE(user_id, idempotency_key)` guarantees one user + one key = one
group, so concurrent same-key writers serialize instead of fusing groups.
The ledger row `id` is the `wear_group_id` shared by the action's event
rows; its `item_ids` JSONB plus the worn instant define replay equivalence
(canonical sorted-unique UUIDs; omitted `wornAt` excluded) and are never
intelligence input. The per-row `UNIQUE(user_id, idempotency_key,
wardrobe_item_id)` (migration 0013) remains as defense-in-depth.

## DEC-012 — Wear Intelligence Surfacing (STEP 17.2)

Status: Accepted

Wear intelligence reaches users through exactly two surfaces: single-item
capture on `WARDROBE-004` and one dedicated read-only summary route.
Nothing else changes: no new screen, no outfit-save behavior change, no
`GET /v1/wardrobe/insight` (W-7) shape change, no migration, no
`learning_signals` change.

- **Decision.** (1) Capture: one "I wore this" action on
  `WardrobeItemDetailsScreen` (WARDROBE-004) for a single item only —
  one tap is one `POST /v1/wardrobe/wears` with one `itemIds` entry,
  hence one ledger group of one row (DEC-011 unchanged). (2) Read: a
  dedicated `GET /v1/wardrobe/wear-summary` returning the `WearSummary`
  facts as data (counts, instants, ID lists) — W-7 keeps its frozen
  `{title, insight, action?, route?}` text shape and stays wear-free.
- **Rationale.** WARDROBE-004 is the only existing surface that can hold
  an authoritative backend wardrobe UUID (it loads backend-first via
  `WardrobeRepository.getItem`; the mock path is the fallback). HOME-002
  components carry mock-catalog IDs with no backend-UUID mapping
  (`daily_outfit_mock_data.dart`), and the assistant card's
  `selectedItemIds` are local-snapshot IDs echoed through the backend
  engine (`app/ai/engine.py`) that fail save validation with 422
  (`application/saved_looks.py`), so neither can supply `POST /wears`
  input. A dedicated route (not a W-7 extension) preserves the frozen
  insight contract, its verbatim text-only Flutter mapping, and its
  204-on-empty semantics — a summary of an empty wardrobe is a valid
  zero object, not "no insight".
- **Accepted API shape.** `GET /v1/wardrobe/wear-summary` → 200
  `WearSummary {totalWears, wearCounts{uuid:int}, lastWorn{uuid:ISO|null},
  mostWornItemIds[], leastWornItemIds[], unwornItemIds[],
  recentlyWornItemIds[], wearsByCategory{code:int}}`; auth + owner
  (OW-1); 401/429 only; never 204, never 404 for empty (empty wardrobe
  → zero object). Capture reuses the existing `POST /v1/wardrobe/wears`
  unchanged (required `Idempotency-Key`, 1–10 canonical IDs, `wornAt`
  omitted → server now, future → 422, unknown/foreign → 404, replay →
  201 `created=false`, changed payload → 409). Full wire contract:
  `docs/api/WARDROBE_API.md` §10.
- **Accepted semantics (promoted from 15.6 implementation convention to
  product/API contract).** Recent = last wear at/after `now − 30 days`
  (inclusive). Most-worn = max-count ties, `[]` when `total == 0`,
  last-worn desc + id asc. Least-worn = min-count ties over ALL current
  items (unworn included), `[]` only when the wardrobe is empty,
  None-first + last-worn asc + id asc. Unworn = zero-count items, id
  asc. Categories = current-item vocab codes only, code-sorted,
  zero-filled. Invariant `total == sum(counts) == sum(categories)`.
  Stale/deleted-item rows ignored everywhere. Grounded only in flat
  `wardrobe_wear_events` — never ledger payload, favorites, saves,
  recommendations, or timestamps.
- **Save ≠ wear rule.** Saving an outfit, favoriting an item, or saved-look
  presence never means worn and never logs wear. No automatic wear
  logging exists. "Wear This Look" (HOME-002) is not a wear action and
  stays as-is until that screen is bound to backend UUIDs.
- **UUID boundary.** Local `LearningService` IDs ("1"–"24") must never be
  sent to `POST /wears` (`WardrobeClient.logWear` contract). The capture
  control renders only for backend-loaded items; mock-fallback items
  hide it. The server stays authoritative (422 malformed, 404
  unknown/foreign).
- **Retention rule.** Wear history is append-only and retained
  indefinitely (history is the product). Account delete cascade-erases
  groups + rows (migrations 0012/0014, already implemented). Item delete
  preserves rows; stale refs are ignored at read (already implemented).
  No per-row delete/edit endpoint exists in v1. No token/image/snapshot
  logging (IDs only).
- **Consequences.** STEP 17.3 implements `GET /v1/wardrobe/wear-summary`
  exactly per §10 (no Flutter). STEP 17.4 builds the Flutter summary
  surface (DTO/client/repo/card, null-safe, no new screens). STEP 17.5
  wires the WARDROBE-004 capture control (no auto-logging). W-7,
  outfit generation, wardrobe CRUD, and the feedback/learning surfaces
  stay untouched.
- **Explicitly deferred.** Multi-item/outfit-level capture
  (`selectedItemIds` → one group); HOME-002 and assistant-card capture
  (blocked on the local-ID → backend-UUID sync repair); wear sentences
  inside W-7; per-row wear delete/edit; retention expiry; item-name
  rendering in wear copy (v1 copy uses counts only).
- **Supersession note.** `docs/api/FEEDBACK_LEARNING_API.md` §3/§4.3/§8
  ("WEAR NOT supported — no endpoint exists") predates the 15.x
  foundation and is superseded ONLY for capture/summary existence
  (`POST`/`GET /v1/wardrobe/wears` exist; W-9 is accepted). Its
  signal-model rules stand unchanged: no `worn` signal type, M10 is the
  sole writer of `learning_signals`, no client signal-submit, wear never
  becomes a preference write. That document is intentionally not edited
  here (frozen STEP-6 design record).

---

## DEC-013 — Saved Looks Completion (STEP 18.2)

Status: Accepted

Saved Looks completes with one owner-scoped physical delete plus one
authoritative Flutter list surface. No migration, no new endpoint family,
no save-behavior change, no signal-model change, no Discover/Home backend
wiring. DEC-010/DEC-011/DEC-012 untouched.

- **Backend delete (endpoint #25).** `DELETE
  /v1/looks/saved/{saved_look_id}`: auth via `Depends(get_current_user_id)`;
  path param is a UUID (`422 VALIDATION_ERROR` when malformed — wardrobe
  `{item_id}` precedent); owner-scoped read via the existing
  `SavedLookRepository.get_for_user` (unknown/foreign id → `404 NOT_FOUND`,
  never 403 — OW-1); success physically deletes the `SavedLooks` row and
  commits, returning `204` with an empty body; repeated DELETE of the same
  id → `404`. Single-row transaction following `DeleteWardrobeItem`
  (`get_by_id → delete → commit`); no learning-signal write on delete (no
  `look_unsaved` vocabulary exists; M10 sole-writer rules unchanged). The
  row's `snapshot` is deleted with the row; `learning_signals` rows are
  preserved (no FK from signals to saved looks — No-FK-to-trigger rule), so
  history survives list removal. No `Idempotency-Key` on DELETE (C-12/API-33
  keys only the POST family; `FANSIVIBE_API_CONTRACT_V1.md` §3.6 lists
  DELETE as naturally idempotent). No cascade side effects: the only inbound
  FKs are conditional-future (`feedback_events.target_saved_look_id`,
  `recommendation_history`, both `SET NULL`, neither table exists).
- **Append-only reconciliation.** Inventory #25's "(append-only storage;
  history rules apply)" describes the storage class, not a delete
  prohibition: `HISTORY_AND_VERSIONING.md` classifies `saved_looks` as
  CURRENT_STATE list + immutable snapshot per row with "add/remove only";
  `SECURITY_PRIVACY_DESIGN.md` removes saved looks "by user or at erasure"
  (R5); BC-39 requires feedback targets to survive saved-look removal (`SET
  NULL`). Append-only protects snapshots/signals/runs (R31, TRX-3/TRX-5, S-8
  no run delete) — list membership stays user-mutable. Hence physical
  delete; no soft-delete column invented.
- **Flutter source of truth: Option B (`GET /v1/looks/saved`).** The
  endpoint returns every type (hairstyle/grooming/outfit/legacy) with full
  snapshot, `lookId`, `sourceRunId`, `createdAt` — the exact JSON the
  `SavedLooksScreen` cards already render. Option A (hairstyle+grooming
  services merged) is rejected: both services call the same endpoint
  without a source filter, so merging duplicates every row, has no paging,
  no deterministic merge order, and no delete path. Option C (merge backend
  with `LearningService.savedLooks` title strings) is rejected: title
  strings carry no IDs/snapshots, cannot address a DELETE, and would
  duplicate backend rows. The screen consumes the `SavedLookList` envelope
  through one saved-looks read; client placement follows the existing
  feature-first pattern (profile owns its screen's data access) with the
  project null-on-failure convention (17.4 precedent).
- **List semantics (existing contract, no wire change).** `GET
  /v1/looks/saved?page=&page_size=` (defaults 20, bounds `[1,100]` → 422
  outside); `createdAt` desc; offset envelope `{items,page,page_size,total}`;
  empty → `200` with `items:[]`; deterministic tiebreak `id` desc at
  implementation level (wardrobe `id`-tiebreak precedent; no client-visible
  change). Duplicates are impossible (one row per save; idempotent replay
  returns the original). No `sourceContext` filter is added (additive-only
  future per `PAGINATION_FILTERING.md` §9.3).
- **Saved-look types (one list, newest-first regardless of type).**
  Hairstyle/grooming render with the existing card patterns (title,
  `sourceContext` eyebrow, snapshot `matchScore`/`description`/`reasons`,
  `sourceRunId` footer — all present verbatim in the backend snapshot).
  Outfit renders generically in v1: OUTFIT eyebrow + title + persisted
  `selectedItemIds` count ("N items"), no item-name resolution (enriched
  rendering deferred — mirrors the DEC-012 item-name deferral).
  Legacy/NULL `source_context` renders generically (SAVED LOOK eyebrow +
  title), never inferred (DEC-010). Stale/deleted wardrobe refs never hide
  a row (R31 frozen snapshot; BC-36/BC-37 survival precedents); v1 shows
  the persisted count verbatim.
- **Delete UX (minimum, `SavedLooksScreen` only, no redesign, no new
  routes).** Per-card delete affordance following the wardrobe
  `_deleteItem` precedent: `AlertDialog` confirm (Cancel/Delete) → pending
  guard with disabled control → repo delete → success snackbar + row
  removal with list reload (next-page fill); failure snackbar + row
  retained (no optimistic removal); `404` means already gone → remove the
  row with an "already removed" snackbar; network failure → retained row
  with a "check your connection" retry copy (wardrobe precedent). Router,
  cards, and design tokens untouched.
- **Ownership/errors.** Auth 401; unknown/foreign/malformed-unknown id 404
  (404-not-403); malformed UUID 422; 204 has an empty body; no new error
  codes (frozen taxonomy).
- **Save ↔ delete consistency.** `POST /v1/looks/saved` stays authoritative
  (TRX-3, outfit UUID validation with 404/422, replay/409 — unchanged).
  Discover (`look_details_screen.dart:327`) and Home
  (`daily_outfit_screen.dart:1172`) mock saves stay local-only: Discover
  mock IDs (`fy_*`/`tr_*`) map to no catalog code and no valid
  `sourceContext`; Home mock carries no backend UUIDs (DEC-012). Wiring
  them without a mapping decision is forbidden (UUID boundary preserved).
  Assistant outfit saves (`sourceContext: "outfit"`, `lookId: null`) flow
  into the same list unchanged. Local `LearningService.savedLooks` title
  strings are display hints only (no IDs, no remove API — none invented);
  backend delete does not touch them.
- **Explicitly out of scope.** Migrations; POST/GET behavior changes; a
  `sourceContext` query filter; per-row edit; signal/history writes on
  delete; Discover/Home backend save wiring; UUID-sync repair; outfit
  item-name resolution; `recommendation_history` (P3); feedback (M11);
  design-system changes.
- **Deferred (not blocking).** Enriched outfit card rendering with resolved
  item names; additive `sourceContext` list filter.

---

## DEC-014 — M5 Knowledge Decision Freeze (STEP 19.4)

Status: Accepted

M5 Knowledge HTTP Reads (endpoints #18–22, module M5) has no remaining
product decision that would require invention during implementation
(step B-B), except the #22 initial-content supply gate noted below.
Specification only: no code, no migration, no route, no Flutter, no
catalog modification in this step. DEC-010/DEC-011/DEC-012/DEC-013
untouched.

- **P-1 — Occasions (#21 `GET /v1/knowledge/occasions`).** The canonical
  knowledge occasions are exactly these 9 codes, with deterministic
  `sortOrder` 1..9 in this exact order:

  | code | label | sortOrder |
  | --- | --- | --- |
  | `casual` | Casual | 1 |
  | `formal` | Formal | 2 |
  | `business` | Business | 3 |
  | `date` | Date Night | 4 |
  | `party` | Party | 5 |
  | `travel` | Travel | 6 |
  | `workout` | Workout | 7 |
  | `other` | Other | 8 |
  | `office` | Office | 9 |

  - #21 is NOT the `event_types` database table. The 8 event-type codes
    required by `DAILY_OUTFIT_EVENTS_API.md`
    (`casual, formal, business, date, party, travel, workout, other`,
    verified in `event_mock_data.dart:10-31`) are all covered.
  - `office` remains because it is already attested by production backend
    intent/analysis/builder logic (`catalog.py:360` `OCCASIONS`,
    `ai/intent.py:28,110-111`, `ai/engine.py:42,142`,
    `ai/tools.py:27`, `domain/services/analysis_rules.py:858-862,915`,
    `domain/value_objects.py:263`).
  - Discover-only codes are NOT added: `work`, `evening`, `weekend`,
    `event` (verified as `OccasionFilters.options` in
    `discover_mock_data.dart:820-844`, free-text `occasion` strings
    elsewhere — never backend codes). `all` is a UI meta-filter, NOT a
    vocabulary row. No additional occasion codes may be invented.
  - `date` has the canonical display label `Date Night` (already the
    `event_mock_data.dart` label; the older `offline_assistant.dart:131`
    `ClarificationOption(label: 'Date', value: 'date')` rendering is
    superseded for knowledge display). `office` and `business` remain
    distinct canonical codes.
  - No `event_types` table is created in M5; that belongs to M8 Events
    (`TABLE_DEFINITIONS.md` §4 `user_events.event_type_id`, §6
    `event_types` row).
- **P-2 — ItemReference (#22 `GET /v1/knowledge/items`).** #22 is a
  system-owned garment/item-type reference catalog. It is NOT
  user-owned `wardrobe_items`, purchasable products, outfit components,
  saved-look `selectedItemIds`, or media references. Its purpose is to
  provide stable backend-owned item-type codes for future
  wardrobe/builder consumers, independent of user ownership.
  - **Frozen wire shape:** `{ code*, label*, category*, sortOrder* }` —
    `code` stable and machine-readable; `label` user-facing; `category`
    a canonical wardrobe-category code; `sortOrder` deterministic. No
    `user_id`, no price, no vendor, no inventory/stock, no image/media
    requirement, no wardrobe UUID, no ownership semantics. User wardrobe
    rows are never exposed through #22; `category` is never confused
    with a specific wardrobe item.
  - **Frozen storage:** the K9.1 permitted versioned-backend-config
    approach for the initial implementation
    (`TABLE_DEFINITIONS.md` §6: "Either DB rows **or** versioned backend
    config (the K9.1 decision)"; `DATABASE_DESIGN_RULES.md` §16.5). No
    `items` table is created merely to manufacture content — verified no
    authoritative DB-backed item catalog exists (no `items` table in any
    migration 0001–0015; `AddItemConfig` in `wardrobe_mock_data.dart` is
    Flutter mock config with conflicting category codes
    `tops/bottoms/shoes/layers` vs backend `tops/bottoms/outerwear/
    footwear/accessories`; the 24-row `WARDROBE` list in `catalog.py`
    is named items, not a type catalog).
  - **Remaining product-content gate [U]:** initial seed contents are
    NOT frozen here — no authoritative garment-type list exists in the
    repository to adopt verbatim, and no list is invented in this step.
    B-B implements the frozen shape/storage/purpose; serving content
    requires a separately supplied seed list.
- **P-3 — Knowledge look filters (#18 `GET /v1/knowledge/looks`).**
  Honest v1 behavior is frozen: the endpoint keeps `page`/`page_size`,
  deterministic catalog ordering, `ListEnvelope`, empty result → `200`,
  invalid pagination → `422`, and `X-Knowledge-Version`. For
  `occasion`/`style`: no look occasion attributes are invented, nothing
  is inferred from `description`/`kind`/`reasons`/`stylingTips` or other
  free text, no style vocabulary is invented, and the current looks
  catalog (8 rows: 4 hairstyle + 4 grooming, fields
  `code/title/description/reasons/stylingTips/maintenance/bestFor/
  scoreSeed` — verified in `catalog.py:117-300` and migration `0003`)
  is not pretended to be filterable when its rows lack those
  attributes. Until authoritative attribution exists, any supplied
  `occasion`/`style` filter returns `422` with a truthful error that
  does not claim unsupported allowed values; an unfiltered request
  remains valid and returns the paginated catalog. The existing look
  catalog is not modified and no occasion/style columns or tables are
  added in M5.
- **Consequences.** B-B implements the M5 reads exactly per these
  freezes plus the unchanged contracts (`API_CONTRACT_RULES.md` §12.5,
  `FANSIVIBE_API_CONTRACT_V1.md` knowledge sections, `API_INVENTORY.md`
  #18–22, `PAGINATION_FILTERING.md` §§9.8/10). No contradiction with
  `TABLE_DEFINITIONS.md` knowledge sections, `BACKEND_MODULE_MAP.md`
  M5, or `KNOWLEDGE_ARCHITECTURE.md` (KN-2/KN-5/KN-9 system-owned
  read-mostly separation preserved).
- **Explicitly deferred.** `event_types` table + M8 Events writes (M8);
  authoritative look occasion/style attribution (future content work);
  #22 seed content (product-content gate above, not a shape blocker).

---

## DEC-015 — M8 Events Decision Freeze (STEP 19.7)

Status: Accepted

Resolves the 19.6 implementation blockers for M8 Events (#26–30,
UC-18–21) from authoritative sources only. Specification only: no code,
no migration, no routes, no Flutter, no tests. DEC-009–014 untouched.

- **R36 preference feed (U-PREF).** The updated data is
  `user_state.preferences.preferredOccasions: string[]` holding event
  TYPE CODES, never labels (PROFILE_ONBOARDING_API §§3.1/5.3,
  RELATIONSHIP_CONSTRAINTS R2/R36 "preferences reference vocab ids",
  422 on non-vocab). Lifecycle is add-only (domain model:
  PreferredOccasions = "additive"; never removed, not on update, not
  on delete — BC-41). CREATE appends the code if absent (trimmed,
  server-deduplicated); UPDATE appends the new code if absent and the
  type changed, else no-op; DELETE touches nothing. "Refresh" is this
  same append-if-absent with the current code. No cap (none
  documented). No learning-signal write (UC-18 repos exclude signals;
  no backend `occasion_preferred` code exists). TRX-7 ("No
  multi-table unit", STEP 4) overrules DAILY §5.4's "same transaction"
  phrase: INSERT commits tier-1 first, preference follows as a
  sequential second unit. If the preference write fails the event 201
  stands (a 500-after-commit would induce F-8 duplicates — the worse
  outcome; the feed is re-derivable via PATCH /me or later events).
- **Time (U-TIME-STORAGE/FORMAT).** Wire `time?` is frozen; persistence
  is the one schema confirm pending (see below). Format is strict
  `HH:mm` both directions (documented `19:00` example); null allowed
  (optional); empty string / seconds / 12h labels → 422; no timezone
  (wall-clock label, never converted). No `event_date`-as-timestamp
  (contradicts BC-57/date semantics).
- **Text bounds (U-BOUNDS).** Time bounds = format (above). Location/
  notes numeric caps are the second pending confirm (see below).
- **Event outfit (U-OUTFIT-MOOD).** E-6 returns the canonical shared
  `OutfitRecommendation` DTO (no second DTO, M13 reuses this mapping).
  `selectedMood`, `selectedColorPalette`, and component `colorHex`
  have no server source and are OMITTED from E-6 responses per the
  AI-0 honesty rule (REC_API §4.2: uncomputed fields absent, never
  fabricated — the M5 P-3 precedent); `selectedOccasion` is the event
  TYPE CODE (K9.1; mock labels are display only); clients derive hex
  from their own color tables. Winner→DTO field sources are frozen
  (components ← owned rows, matchScore ← winner 0..1, reasons ←
  rationales); prose composition stays inference-bounded by honesty.
- **Conflicts/idempotency (U-409, Decision 10).** No 409 trigger is
  implemented in M8 v1 (no key per F-8/V1 §3.6, no unique constraint);
  409 stays in the canonical error set as reserved, never emitted.
  Repeats create separate rows; no replay. Past-event generation is
  allowed (no source restricts it). E-3 stays DEFERRED [D] (additive,
  served-from-list; later mount needs no product decision).
- **event_types seed (Decision 9).** Exactly 8 codes with mockTypes
  labels (date → Date Night); `sort_order = 0` for all rows (0005
  precedent verbatim — no invented ordering) with deterministic
  `(sort_order, code)` reads; `active = true`; codes immutable
  (PR-3 deprecate-not-delete); M5 occasions remain separate; office
  excluded. Seeded by the M8-A migration (DBR:562).
- **Explicitly pending owner one-liners (not blockers for M8-A):**
  (1) persist `time` as nullable `event_time time` column (only
  coherent option: request-only breaks list `time`; timestamp
  contradicts BC-57); M8-A ships tables without it, column follows
  additively. (2) location ≤200 / notes ≤2000 chars (BC-13 family
  precedent, far above mock usage).

---

## DEC-016 — M8 Events Final Schema/Text Bounds Freeze (STEP 19.8)

Status: Accepted

Closes the two 19.7 owner one-liners. No authoritative source
contradicts either rule (verified: no TIME prohibition in
DATABASE_DESIGN_RULES/TABLE_DEFINITIONS, open slot DAILY §8.3;
no free-text cap conflict in BUSINESS_CONSTRAINTS). DEC-015
unchanged.

- **`event_time TIME NULL` on `user_events`.** `event_date` stays
  `DATE`; `event_time` is optional wall-clock time only — never
  converted, never timezone-aware. Wire stays strict `HH:mm` both
  directions; responses serialize `TIME` as `HH:mm`. Null/absent =
  no time supplied. Smallest coherent representation: the contract
  already exposes `time?` on create/update/detail/list
  (`EventSummary.time`), so request-only persistence would leave
  list `time` sourceless, and a timestamp would contradict the
  frozen DATE semantics (BC-57). Implementation doc-touches (not
  contradictions): TABLE_DEFINITIONS column row + "Types used",
  TRX-7 row-content parenthetical.
- **Text bounds.** `location`: nullable, max 200 chars (BC-13 title/
  label family, exact). `notes`: nullable, max 2000 chars (new
  magnitude; nothing caps free text lower; satisfies DAILY
  "bounded"). Conventions frozen: null/absent = no value (clears on
  PUT); supplied text must be non-empty (`""` → 422, the uniform
  `min_length=1` / `BETWEEN 1 AND n` lower bound); lengths in
  characters via the stack native measure (Pydantic `len` +
  `char_length` CHECK — no byte counting, no trimming, no other
  normalization, matching required-field behavior today);
  over-limit → 422, never truncated.

---

## DEC-017 — M9 Today's Look Specification Freeze (STEP 19.9)

Status: Accepted

Freezes the complete M9 Today's Look contract (#31–33, UC-16/17)
from authoritative sources only. Specification/decision work: no code,
no migration, no routes/schemas/repos/use-cases/models, no Flutter
production change, no tests. DEC-009–016 untouched.

- **C1 persistence (A): FROZEN — derived-only, no `today_look_records`
  table.** `TABLE_DEFINITIONS.md` §4.6, `DATABASE_DESIGN_RULES.md` §6.2,
  `DAILY_OUTFIT_EVENTS_API.md` §8.2/`API_CONTRACT_RULES.md` §16.3 (open
  P1 gate, default transient), UC-16/17 (non-transactional computation;
  INSERT only "when the P1 table exists"), TRX-2/TRX-4 (generation =
  computation, never truth). No model, migration, or test for the table
  exists (verified: migrations 0001–0015, `models.py`, `tests/`). GET and
  POST stay coherent without it: both derive per-request from UserState
  + owned wardrobe + optional nearest event + weather hint; nothing is
  read or written; save persists independently via M7 `saved_looks`
  (TRX-3). Gated reference schema if history is ever wanted (NOT
  created): `id uuid PK gen_random_uuid()`, `user_id FK users CASCADE
  NOT NULL`, `day date NOT NULL`, `snapshot jsonb NOT NULL`,
  `occurred_at timestamptz NOT NULL`, `UNIQUE (user_id, day)` (BC-5),
  append-only INSERT/SELECT.
- **GET #31 (B): FROZEN.** `GET /v1/looks/today`, registered before
  `/v1/looks/today/save`, `/v1/looks/saved*`, `/v1/looks`, `/v1/looks/{look_id}`
  (§7 guard). Auth Bearer → `user_id` (401 + `WWW-Authenticate`);
  owner-only OW-1 (always derived for the caller). Query `variant?`
  optional only — no pagination anywhere in M9 sources. Malformed
  `variant` → 422 (bounds UNRESOLVED, recommend ≤64 opaque string).
  `200` bare `TodayLook` (derived-look family: `title*/occasion*/weather?/
  description*/matchScore* 0–100 int/styleScore*/components*/reasons*/
  styleDna*/wardrobeContext*/aiSelectionReason?/confidenceBoost?/
  aiInsights[]/alternatives[]/dailyStyleTip?`); no envelope; `confidence`/
  `tradeOffs`/`expiresAt` absent (AI-0). Engine-ranked order, API never
  re-sorts (API-27). Components MUST be owned `wardrobe_items` UUIDs
  (BC-56 domain validation). Empty wardrobe or no legal candidate
  (tops+bottoms mandatory per the STEP-13 generator) → 404 NOT_FOUND
  ("none found", UC-17/INVENTORY #31/DAILY §5.1). 422 variant; 429
  generic (+ `Retry-After`); NO 503 on GET (weather-port failure
  degrades to absent weather per BA-6 rule 2 — never an error); never
  409. Side effects none (read-only, TRX-2). Repeated GET over unchanged
  inputs is deterministic.
- **POST #32 (C): FROZEN.** `POST /v1/looks/today` (method distinguishes
  it from GET). `seed?` optional; different result per seed (UC-16,
  INVENTORY #32, DAILY §5.2). Same seed + same inputs → same result
  [I] (deterministic-pipeline consequence); different seed differs on a
  best-effort basis [I] — NOT an absolute guarantee (bounded candidate
  space can collide, e.g. a single candidate). Persists nothing; changes
  no server-side "current look" (none exists). Never idempotent, no
  `Idempotency-Key` (§11 keyed list excludes it; DAILY §5.2). Errors:
  200; 401; 422 malformed seed; 404 when nothing derivable (UC-16 —
  DAILY §5.2's omission reported below); 503 EXTERNAL_SERVICE_FAILURE on
  generation failure (C-8, no internals); 429. Independent of GET (no
  shared state; no variant↔seed cross-equivalence claimed [U]).
- **POST #33 (D): FROZEN except sourceContext [U].** `POST
  /v1/looks/today/save` (guard order above). Delegates verbatim to M7
  `SaveRecommendation` (no per-type save endpoint, REC_API §3.3): body
  `SaveLookRequest{lookId?, title 1–200 (BC-11), sourceContext,
  snapshot = the TodayLook verbatim (R31)}` + required `Idempotency-Key`
  (missing → 422); TRX-3 true transaction (`INSERT saved_looks` +
  `INSERT learning_signals(look_saved)`, exactly one signal, rollback +
  `DATABASE_FAILURE` on failure); replay same key+payload → original
  (`created=false`), conflicting payload → 409 `CONFLICT`
  (`details.kind`); `lookId`/`sourceRunId` null (no catalog/run, DEC-013
  assistant-outfit precedent). Snapshot item IDs validated per the M7
  outfit rule: UUID strings (malformed → 422), each owner-scoped
  `get_by_id` (unknown/foreign → 404-not-403, nothing stored),
  canonical sorted-unique before the idempotency compare. Local/mock IDs
  (`1`–`24`, `comp_*`, `alt_*`) fail closed (422/404) — never dropped,
  never stored; the client must never send them. **sourceContext:
  UNRESOLVED (blocks save only):** DAILY §5.3 names `"daily"`, but the
  implemented CHECK (`0009`, `models.py`, use case, schema) accepts only
  `hairstyle`/`grooming`/`outfit`. Neither inventing `"outfit"` for a
  derived-look DTO (DEC-010 honesty) nor assuming `"daily"` (422 today)
  is authoritative. RECOMMENDED: migration adding `'daily'` to the CHECK
  + use-case/schema allow-list; owner to confirm.
- **DTO boundary (E): FROZEN TodayLook direct; C12 mapping UNRESOLVED.**
  M9 returns the canonical `TodayLook`, never `OutfitRecommendation`
  (different families, REC_API §§4.3/5; no second DTO). Authoritative
  field sources when mapped: components ← owned rows
  (id/name/category/color/material), matchScore ← winner score on the
  family 0–100 int scale, reasons ← grounded rationales; optional
  `weather/aiSelectionReason/confidenceBoost/aiInsights/alternatives/
  dailyStyleTip` omitted when uncomputed (AI-0 honesty; M5 P-3 and
  DEC-015 precedents). Winner→DTO mechanical mapping (incl. score
  rescale and component-id ↔ `selectedItemIds` linkage for save-time
  validation) has no authoritative source — defined at implementation
  from the frozen STEP-13 generate→score→rank→select pattern, not prior
  foundation. DEC-015 event-outfit boundary respected (ensemble DTO,
  `selectedOccasion` = event code, mood/palette/hex omitted).
- **Event influence (F): optional seeding FROZEN; filter/tie-break
  UNRESOLVED.** Nearest/upcoming M8 event MAY seed occasion-aware
  derivation (INVENTORY #32 "optional nearest event", UC-16, MODULE_MAP
  M9 reads events via port, R35-style). No event → derive from
  StyleProfile + wardrobe + weather hint (never 404 for missing event
  alone). Only the occasion seeds (location/title/notes do NOT
  influence [I], DEC-015 occasion-only precedent). Nearest definition
  (date filter ≥ server-UTC today, time/tie-break) is unspecified —
  RECOMMENDED [I]: min `event_date` ≥ today, tie-break `event_time`
  NULLS LAST then `id` asc (M8 list defaults support it); owner to
  confirm or ship the no-event path first.
- **Weather C9 (G): FROZEN — optional, absent in v1.** `WeatherProvider`
  port defined, `weather.py` NOT BUILT; literal `'68°F • Partly Cloudy'`
  is mock-only (BACKEND_ARCHITECTURE_RULES §7, DATABASE_DESIGN_RULES
  weather-never-a-table, MVP_SCOPE P3 MUST-NOT-build). `weather` is
  output-only inside `TodayLook`, omitted when the port has no data
  (DAILY §4.2); client never sends it; no weather API; no fake provider
  or hardcoded wire claims. A future provider is hint-only, never
  authoritative, and its failure degrades (never 503 for weather alone).
- **Flutter (H): FROZEN.** New `features/home/data/`: `TodayLook` DTO
  models (verbatim wire), `TodayLookClient` (3 methods; baseUrl/
  dev-token/12s/null-on-failure per the M5 knowledge precedent),
  `TodayLookRepository` (nullable passthrough, NO mock merge).
  Backend-first `DailyOutfitScreen`/`TodaysLookCard`: truthful
  loading/error+retry/empty states (shared views); regenerate = POST
  `?seed=` replacing the look (failure retains + truthful copy);
  save = POST save with fresh `Idempotency-Key` (blocked on the
  sourceContext decision — never send `"daily"` until accepted);
  offline/null = unavailable (LearningService title strings stay
  display hints only); backend UUIDs only. Mock layout/animations/tokens
  (incl. the 65/35 card rule) reused as presentation only; snackbar-only
  `_handleGenerateAnother`/`_handleSaveOutfit` rewired; `_handleWearThis`
  stays NON-wear per DEC-012 (save ≠ wear; HOME-002 capture deferred).
- **Routing/error/auth/idempotency (I): FROZEN.** Auth on all three
  (401); UUID malformed → 422; owner checks 404-not-403; 404 cases per
  B–D; 422 validation (field_errors + allowed); 429 generic; 503 POST
  generation only; save DB failure → 500 `DATABASE_FAILURE` (M7
  precedent). Idempotency: GET natural; POST regenerate never keyed;
  POST save keyed (replay → original, conflict → 409). No fake success.
- **Lifecycle (J): FROZEN on M7.** POST save (#33→TRX-3 + `look_saved`)
  → GET saved (#24, `createdAt` desc envelope; TodayLook rows render
  generically, enriched item-name rendering deferred per DEC-013) →
  DELETE saved (#25: confirm + pending guard + 204 + reload;
  404 → already-gone) → GET confirms gone. Delete writes no signal;
  signals/snapshots survive list removal (BC-41/R31). No wear logging
  anywhere in this lifecycle.
- **Reported disagreements (authoritative first):** (1) DAILY §5.3
  `sourceContext: "daily"` vs the implemented 3-value CHECK —
  implementation wins until a migration lands (U-SOURCE-CONTEXT). (2)
  UC-16 404 "no looks available" on POST vs DAILY §5.2 omitting 404 —
  the use case wins (frozen above). (3) "different result per seed"
  read absolutely vs bounded candidate space — best-effort reading
  frozen (C).
- **Unresolved register:** U-SOURCE-CONTEXT (blocks save impl only);
  U-EVENT-NEAREST (blocks event-seeded path only; no-event path ships
  without it); U-VARIANT-BOUND/U-SEED-BOUND (non-blocking; ≤64 opaque
  recommended); C12 mechanical mapping (implementation-time, not prior).
  **Deferred:** `today_look_records` history (P1 gate), weather
  provider, enriched rendering, outfit-level wear capture.
- **Readiness: CONDITIONALLY READY** (GET + regenerate/no-event path
  implementable once C12 is mapped during implementation; save waits on
  the one-line sourceContext answer; event seeding waits on M8-A tables
  + the tie-break one-liner).

---

## DEC-018 — M9 Remaining Decisions Final Resolution (STEP 19.10)

Status: Accepted

Resolves the DEC-017 unresolved register (U-SOURCE-CONTEXT,
U-EVENT-NEAREST, U-VARIANT-BOUND, U-SEED-BOUND, C12) from authoritative
sources only. Specification/decision work: no code, no migration, no
routes/schemas/repos/use-cases/models, no Flutter production change, no
tests. DEC-009–017 untouched.

- **1. U-SOURCE-CONTEXT: ACCEPTED — `sourceContext = "daily"`
  (FROZEN).** Authority chain (contract deduction, not invention):
  (a) `RECOMMENDATION_API.md` §3.1 fixes the daily-outfit type code as
  `"daily"`; (b) §4.8 defines `sourceContext` as "the type code (§3.1)";
  (c) the §4.1 envelope carries `"daily"` in the type union, derived
  from surface/`sourceContext`; (d) `DAILY_OUTFIT_EVENTS_API.md` §5.3
  (the endpoint-33 owner) names `sourceContext: "daily"` explicitly.
  No source caps the vocabulary at three — `0009`'s list is an
  implementation timestamp from before any daily save path existed, not
  a product exclusion; DEC-010/013 never forbid future values. The M9
  save batch therefore needs one additive migration + allow-list widen
  (NOT this step): CHECK `IN (..., 'daily')`, schema `Literal` +4th
  value, `_SOURCE_CONTEXTS` + `"daily"`, and the `selectedItemIds`
  ownership-validation predicate extended from `== "outfit"` to
  `in ("outfit", "daily")` (required — otherwise daily item IDs skip
  BC-56 validation). No existing behavior breaks: a CHECK widen admits
  a superset (all existing rows/values valid; legacy NULL untouched);
  list/detail/delete stay type-agnostic (daily rows included, correct);
  the outfit-scoped predicates stay byte-identical — `get_outfit_coverage`,
  `resolve_preferred_item_ids`, and the W-7 saved-outfit follow-up keep
  `== "outfit"`, so daily rows are ignored exactly like
  hairstyle/grooming today (frozen insight/preference numbers preserved;
  future inclusion is additive). Signal context carries
  `{source_context: "daily", look_id: null}`; idempotency compare is
  unchanged (it already includes context). `"wardrobe"` still 422, so
  the existing negative tests are unaffected. Doc-touches at
  implementation (DEC-016 precedent, not contradictions):
  `TABLE_DEFINITIONS.md` `saved_looks` gains the `source_context` row
  (it predates `0009`), port comments enumerating three values gain the
  fourth.
- **2. U-EVENT-NEAREST: rule frozen (FROZEN core + labeled INFERENCE
  detail).** FROZEN: event influence is optional — no event → derive
  from StyleProfile + wardrobe (+ absent weather) and never 404 for the
  missing event alone ("optional nearest event", UC-16); only
  `event_type_id` is consumed — date/time/location/title/notes do NOT
  influence derivation (R35 occasion-seeding + DEC-015 occasion-only
  precedent + AI-0 honesty; the restriction is the absence of any
  source, stated, not silent). INFERENCE (stated why: no M9/M8 source
  defines "nearest"): candidate set = owner's events with `event_date`
  >= server-UTC-today — today's events QUALIFY (supported by the M8
  on/after filter semantics and upcoming-view default; coherence: a
  same-day event is the strongest occasion signal, excluding it would be
  the invented restriction; the server-UTC-today datum itself is
  inherited [I] from M8 E-1); order `event_date ASC, event_time ASC
  NULLS LAST (explicit), id ASC`; first row or none (NULL placement is
  explicit and deterministic; id-asc mirrors the STEP-13 lexical
  tie-break pattern). Scoring input occasions [I]: `[event code] +
  persisted preferred_occasions`, deduped (both are authoritative inputs
  individually; their composition is unspecified — the engine degrades
  gracefully for unknown codes). Needs M8-A tables at implementation
  (sequencing, not a decision gap); the no-event path needs nothing.
- **3/4. U-VARIANT-BOUND / U-SEED-BOUND: no authoritative maximum
  exists (FROZEN finding).** The only bound in any source is "optional,
  bounded → 422" (`DAILY` §6, API-24) — no number anywhere, so no
  maximum is frozen and none is invented. Convention-backed floor
  [I]: absent → default derivation; supplied `""` → 422 (uniform
  `min_length=1` convention, DEC-016). Maximum stays
  implementation-time/non-blocking: recommended ceiling ≤200 (BC-13
  family; bounds any echo/log exposure), enforced as 422 if applied and
  documented at implementation. Bounds never affect the determinism
  guarantees; variant↔seed namespace equivalence remains unclaimed.
- **5. C12 mapping: frozen as far as sources permit.**
  FROZEN: selection = generate→score→rank→`select_best_outfit_candidate`
  (the single deterministic ranking contract, STEP-13 code); no winner
  → 404 (DEC-017-B). `matchScore` source = winner score on the native
  0–100 scale (13.2 budget comment + derived-look family scale — no
  rescale needed). Components = one per winner member with `id`/`name`
  from the owned row (BC-56); `colorHex` omitted (verified no hex
  source — the same fact as DEC-015). `reasons` required but
  grounded-only (catalog/sub-term-derived, never invented — REC_API
  §4.5 + Explanation-stage rule + AI-0). `occasion` = seeding event
  code when event-seeded (K9.1 code-on-wire, DEC-015 analogy), else the
  preferred-occasion derivation. `selectedItemIds` = canonical
  sorted-unique winner UUIDs as an additive top-level TodayLook field
  (API-2 additive-only; the mechanism that reuses M7 validation
  verbatim). Seed/variant only select among ranked legal candidates
  (same seed + same inputs → same pick; never invents). INFERENCE:
  nearest-int + clamp 0–100 for `matchScore`; category/color/material ←
  vocab-code columns (K9.1; labels forbidden on wire); `styleDna` ← the
  4-field StyleProfile projection; `wardrobeContext.totalItems` ←
  wardrobe count, `matchingItems` ← winner size; alternatives ←
  `ranked[1:3]` minimal mapping (score ← candidate score; stable ids
  derived from member UUIDs, never mock ids); scoring-occasion
  composition (see 2). UNRESOLVED but bounded (implementation-time,
  honesty-bounded, never blocking): `title` (wire-required; grounded
  inputs only, no possession/weather claims unless verified);
  `reasons` sentence templates (sub-term/catalog-derived only);
  `styleScore` computation (0–100 int required — the assistant-path 87
  default is documented non-user-specific and must NOT be reused);
  `wardrobeContext.insight` / `aiInsights` content / `dailyStyleTip` /
  `aiSelectionReason` / `confidenceBoost` (v1 default: OMIT unless
  grounded, AI-0); `styleDna` absent-subfield tolerance (recommend
  omit-absent; never 404 for profile gaps — 404 is "none found" only);
  the seed→index function.
- **6. Weather: DEC-017-G CONFIRMED UNCHANGED (FROZEN).** Optional/
  absent, no provider, no fabrication, no weather-induced failure.
- **7. Persistence: DEC-017-A CONFIRMED UNCHANGED (FROZEN).**
  Derived-only; no `today_look_records` in M9 v1.
- **8. Save lifecycle (FROZEN):** `POST /v1/looks/today/save`
  `{lookId: null, title 1–200, sourceContext: "daily", snapshot:
  TodayLook verbatim incl. selectedItemIds, Idempotency-Key}` →
  `SaveRecommendation` → 201 + exactly one `look_saved` (TRX-3) → `GET
  /v1/looks/saved` shows the row (existing generic SAVED LOOK eyebrow +
  description footer, zero screen change; badge-scale normalization for
  the 0–100 family is a deferred Flutter implementation detail with no
  contract impact) → `DELETE /v1/looks/saved/{id}` → 204 → GET confirms
  gone. Replay → original, conflicting key reuse → 409 (C-12/API-33).
  No wear logging anywhere (DEC-012); daily rows never feed W-7
  coverage or preferred-item resolution (predicates frozen, see 1).
- **9. Readiness: READY FOR IMPLEMENTATION.** Every DEC-017 blocker is
  resolved authoritatively above; residuals are bounded implementation
  details (never blockers) plus pure sequencing: CHECK-widen migration
  rides inside the save batch, M8-A lands before the event-seeded path
  (no-event path first is allowed), Flutter after backend. Dependency
  map unchanged from 19.9 (M2/M3/M5/M6-pattern/M7 complete; M8
  sequencing-only; M10 via M7; M13 not required; weather absent by
  design).

---

## DEC-019 — M10 Learning Summary Specification Freeze (STEP 19.11)

Status: Accepted

Freezes the complete M10 Learning Summary contract (#34, F-3/R-3) from
authoritative sources only. Specification/decision work: no code, no
migration, no routes/schemas/repos/use-cases/models, no Flutter
production change, no tests. DEC-009–018 untouched.

### 0. M10 state audit (FROZEN findings unless marked)

1. Exists (backend): `learning_signals` model + `(user_id, occurred_at)`
   index + `(user_id, signal_type, occurred_at)` index (0004); 5 seeded
   signal codes (`look_saved`, `analysis_updated` via 0001;
   `outfit_selected` via 0008; `suggestion_opened`,
   `assistant_navigation` via 0015); writers `SaveRecommendation`
   (TRX-3 one `look_saved`), analysis runs (`analysis_updated` +
   `outfit_selected`), `SubmitAssistantCardFeedback` (card mapping,
   append-only, 204); `user_state` 1:1 projection
   (`style_profile`/`preferences`/`flags`/`version`); `saved_looks`,
   `wardrobe_items`, `wardrobe_wear_events/groups`, wear-summary read.
2. Persisted: `learning_signals` rows (owner-scoped, append-only);
   `user_state`; `saved_looks`; `wardrobe_items`; wear ledger/rows. No
   persisted score, streak, activity day, or summary row exists.
3. Calculated locally (device-only, never sent): `LearningService.
   styleScore` = `60 + wardrobe.length.clamp(0,20) +
   (savedLooks.length*2).clamp(0,20)` (`learning_service.dart:240-244`);
   in-memory `signals` list + `shared_preferences` blob
   (`fansivibe.user_model.v1`); only `preferredOccasions` syncs via
   `PATCH /v1/users/me`.
4. Mock-only: every `StyleScoreData.mock` (84 + breakdown 92/85/88/72),
   `StyleStreakData.mock` (12/28/156, 4/7, day scores 87/84/91/88),
   `TodaysLookData.mock`/`DailyOutfitData.mock` (`styleScore: 87`,
   `matchScore: 91`, `comp_*`), `ProfileData.mock` (84, previews
   87/82/91/85), hardcoded `'87'` badges, `offline_assistant` 86/87/88
   fallbacks. No `GET /v1/learning/summary` on either side.
5. Documented but not implemented: `style_score_records` (E8),
   `activity_days` (E9), `application/learning.py`, `StyleScore/
   ActivityDay` repos and derive/record use cases, `GET /learning/
   summary` ("may expose later", MODULE_MAP M10). Zero model/migration/
   repo/route/test hits for either table (migrations 0001–0015
   verified).
6. Authoritative inputs today: the 5 seeded codes above (FK RESTRICT —
   anything else 500s on flush). Doc-only codes `item_added`,
   `style_updated`, `occasion_preferred`, `assistant_message` have no
   backend rows (DEC-015 confirms no backend `occasion_preferred`;
   `AddWardrobeItem` "emits item_added" is aspirational — no signal
   call). Wear writes zero signals (DEC-012). Nothing reads
   `learning_signals` for derivation today.
7. Missing for backend summary: both history tables; streak-day rule
   (C11); breakdown shape; inner DTO types; N/ordering for recents;
   empty-state selection; dedicated M10 use cases.
8. Missing for Flutter: client/repo/DTO, backend-first states, UUID-only
   wiring, offline/empty truthfulness.
9. Must NOT be reused: `LearningService` math + signal names
   (`item_added/item_removed/item_updated/style_updated/
   occasion_preferred/assistant_message` have no server rows);
   local IDs (`1`–`24`, `1`–`5`, `comp_*`, `alt_*`); every mock
   score/streak value; assistant-path hardcoded `87`
   (`ai/engine.py:266-271`, explicitly non-user-specific per DEC-018);
   candidate `matchScore`/`compose_candidate_score`, wear aggregates,
   `users.memorySummary` (wrong families).

### A. Summary contract #34 (FROZEN)

- `GET /v1/learning/summary`, sync, no input (no query/body/key):
  INVENTORY #34 (`:147`, `:810-824`), CONTRACT_RULES §12.9 (`:507`),
  V1 (`:270`), FEEDBACK §5.3 (`:469-483`).
- Auth Bearer → `user_id`, owner-only OW-1 (caller's own summary):
  FEEDBACK `:481-482`, INVENTORY `:818-819`, SECURITY_REVIEW `:643`.
- 200 bare `LearningSummary { styleScore*, breakdown*, streak*,
  recentSignals* }` — all four required (`*` per V1 `:334-335`):
  V1 `:428`, FEEDBACK `:313`, `:476-479`. Bare (not enveloped) per
  single-derived-value-object rule (PAGINATION `:440-444`,
  CONVENTIONS `:172-180`, `:220-221`). No pagination (PAGINATION
  `:152`: "none"); deterministic ordering n/a (single object).
- Errors FROZEN: `200; 401 AUTHENTICATION_ERROR; 429 RATE_LIMITED`
  (FEEDBACK `:483` fuller target; INVENTORY `—.` and RULES/V1
  `200`-only are abbreviations — same pattern as endpoint-17 I-3). No
  422 (no input), no 404 trigger (caller-scoped singleton, no
  id-addressed resource), no 409 (no key), no 503 listed. Wire errors
  `{error:{code,message,details?}}` + `X-Request-Id` (global
  conventions). Naturally idempotent, no key (FEEDBACK `:336`).
- Empty-state: UNRESOLVED (non-blocking for freeze, blocking for
  implementation). No #34 source selects `200+needs_data` vs `204`
  vs zero-valued object; INVENTORY errors blank; FEEDBACK says
  "Validation: none". Do not assume.
- Inner wire types for `breakdown`/`streak`/`recentSignals[]`,
  nullability beyond top-level `*`, and `N` for "last N": UNRESOLVED.
  CONTRACT_RULES §13 has no M10 sketch. Nothing invented here.

### B. Score (FROZEN + one resolved tension)

- Tension resolved authoritative-first: FEEDBACK §4.4 "derived 0–100
  int (60 base, +1/item ≤20, +2/saved ≤20)" vs DBR/HISTORY live
  formula vs TABLE "formula 60–100; range 0–100" vs FEEDBACK §5.3
  "accepted 0–100 progressive derivation" vs TodayLook `styleScore`.
  Resolution: the FORMULA is single and frozen —
  `60 + min(wardrobe_count,20) + min(saved_count*2,20)`, int,
  derived range 60–100 (DBR `:60-61`, HISTORY `:110`,
  FEEDBACK `:114-115`, APPEARANCE_API `:591-592`,
  `learning_service.dart:240-244`). "0–100" is the WIRE/COLUMN range
  (V1/FEEDBACK DTO type + BC-7 `CHECK(score BETWEEN 0 AND 100)` drift
  tolerance `:117`), not a competing formula. Rounding: integer by
  construction (counts only). Min 60 / max 100 behavior follows the
  clamps; column admits 0–100 regardless of drift.
- Inputs FROZEN: owned `wardrobe_items` count (+1 each, cap +20) +
  owned `saved_looks` count (+2 each, cap +20) + base 60. Style
  profile does NOT contribute; wear does NOT contribute (no `worn`
  signal, DEC-012 save≠wear); assistant/card feedback does NOT
  contribute to the number (evidence rows only); raw M11 reactions do
  NOT contribute (gated, aggregation-only when built). Current-state
  (recomputable cache), never stored as truth (DBR `:592-593`,
  `:102-103`); history lives in `style_score_records`.
- Never reuse the assistant-path `87` or any mock score (DEC-018
  prohibition restated).
- TodayLook `styleScore` linkage: UNRESOLVED (bounded). No source
  binds TodayLook `styleScore` (0–100 int, DEC-017/018) to the M10
  formula vs `style_score_records.score` vs an independent 0–100.
  Different DTO families; do not conflate at implementation without a
  follow-up decision.

### C. Breakdown (UNRESOLVED, blocking)

- FROZEN: concept only — "component contributions"
  (FEEDBACK `:315`) persisted as nullable `breakdown jsonb`
  ("Immutable `StyleScoreBreakdownItem` snapshot",
  TABLE `:334`). No field list, calculation, range, ordering, or
  empty behavior in any source. Marked UNRESOLVED rather than
  invented. Implementation must freeze the field set first
  (recommended: wardrobe-points vs saved-points contributions
  mirroring §B, but owner to confirm — not frozen here).

### D. Streak / C11 (FROZEN frame + UNRESOLVED rule)

- FROZEN: current streak is a derived cache recomputed from
  `activity_days` (HISTORY `:111`, DBR `:377-381`); table is immutable
  per-day history (`UNIQUE(user_id,day)`, `styled bool DEFAULT false`,
  nullable `summary jsonb`, `occurred_at`; TABLE `:353-380`);
  append-only INSERT/SELECT (PR-2/PR-5); `day`/`recorded_at` are
  calendar `date` (trend/query axis).
- UNRESOLVED (blocking, nothing silently inferred): what sets
  `styled=true` (any-signal vs narrower set; BC-60 punts
  daily-look↔styled coupling to domain; M9 "today active → emit
  signal" suggests event-driven but no UC writes `activity_days`);
  UTC vs user-local date; whether today counts; consecutive-day
  definition (gap tolerance, first-day value, missing-day reset);
  timezone handling; future-date handling. No source defines any of
  these.

### E. Recent signals / activity (FROZEN + UNRESOLVED)

- FROZEN: only persisted seeded rows can appear (5 codes today;
  §G); exposed as typed signal labels (E7) — evidence, never raw
  feedback text (FEEDBACK `:316-317`, `:478-479`, `:566`, SECURITY
  `:643`); owner-isolated (OW-1); `context` small optional, never a
  filter axis (TABLE `:228`); no FK to trigger — history survives
  deletion (BC-41, TABLE `:233-236`).
- UNRESOLVED: signal-type allow-list for the surface (all persisted
  vs subset); ordering (recommended [I]: `occurred_at` desc — not
  frozen); maximum count `N` (no number anywhere); empty behavior
  (see §A).

### F. History / snapshots (FROZEN + UNRESOLVED + DEFERRED)

- Writer FROZEN: M10 sole writer (PR-7, MODULE_MAP `:370-372`);
  others emit via signal port (BA-6). Retention FROZEN: append-only
  while account lives; cascade-erases on account delete (no orphaned
  rows). Uniqueness FROZEN: score — none beyond PK (multiple/day
  allowed, TABLE `:338-339`); activity — `UNIQUE(user_id,day)`
  (TABLE `:370-371`). Day semantics FROZEN: `recorded_at`/`day`
  calendar `date`, `occurred_at` instant. Current-vs-history FROZEN:
  current derived cache, tables are history (DBR `:592-593`).
- Cadence (when snapshots are written — per-signal, batch,
  deferred/aggregate P1 per MODULE_MAP `:368-369`): UNRESOLVED.
- Necessity: `activity_days` REQUIRED for streak (FROZEN
  dependency — streak has no other source); `style_score_records`
  DEFERRED for v1 current-score-only (history/trend only);
  `today_look_records` NOT required (FROZEN per DEC-017/018,
  conditional-gated TABLE `:382-387`). Tables alone do not unblock —
  streak rule (§D) and breakdown (§C) still required.

### G. Signal inputs (FROZEN map)

| Signal | Writer / path | M10 v1 input? | Status |
| --- | --- | --- | --- |
| `look_saved` | `SaveRecommendation` TRX-3 | YES (strongest personalization input) | FROZEN |
| `analysis_updated` | analysis runs | YES (history/recents) | FROZEN |
| `outfit_selected` | outfit runs | YES (history/recents) | FROZEN |
| `suggestion_opened` / `assistant_navigation` | `SubmitAssistantCardFeedback` append-only | YES (evidence/recents; never score math) | FROZEN |
| `item_added` / `style_updated` / `occasion_preferred` / `assistant_message` | doc-only (no backend rows; DEC-015 confirms no backend `occasion_preferred`) | NO until seeded | DEFERRED (gap) |
| wear (`worn`) | none exists | EXCLUDED (DEC-012) | FROZEN |
| `item_removed` / `item_updated` / Flutter-local names | on-device blob only | EXCLUDED | FROZEN |
| regenerate/no-save | no signal type exists | EXCLUDED | FROZEN |

Score math consumes COUNTS (wardrobe/saved), not signal rows
directly; signals feed history/recents/personalization. Never treat
every DB row as a score input.

### H. Privacy / ownership (FROZEN)

- Every signal/score/activity row belongs to one user (`user_id NOT
  NULL FK CASCADE`, BC-20/22/23); owner-only serve (OW-1,
  404-not-403 class rule); account delete cascade-erases all history
  (R3–R9, TRX-8, PR-10); no orphaned/kept signals.
- Derived summary from caller's own history + current state only;
  never another user's data, never raw `reason`/feedback text beyond
  the request echo (FEEDBACK §4.6–4.7). Wardrobe UUIDs/names,
  saved-look snapshots, card titles/IDs: NOT in v1 summary (no source
  puts them there; default omit per AI-0 honesty; revisit only with
  the §C breakdown decision). Labels bounded 1–200 (BC-12); no
  appearance/image/token logging.

### I. Transaction / read model (FROZEN)

- Hybrid: read-time derivation (current score/streak/summary) +
  snapshot-backed history (`style_score_records`/`activity_days`).
  GET writes nothing ("Side effects: none — a pure read",
  FEEDBACK `:486`; computation non-transactional per TRX
  `:230-234`). Single-row snapshot INSERTs are MVCC-atomic, no
  explicit multi-row unit (TRX `:204-218`); TRX-3/TRX-6 coupling
  rules for save/profile writes stand unchanged.
- Layering: `LearningSignalRepository` / `StyleScoreRepository` /
  `ActivityDayRepository` + record/derive/read use cases (MODULE_MAP
  `:359-366`); M10 sole writer, others via signal port. Current
  direct `insert_look_saved` calls are pre-M10 seams to route via M10
  at implementation (behavior-preserving).

### J. Flutter integration (FROZEN)

- Surfaces: INVENTORY actions (8,28 profile) name Profile/Home, but
  SCREEN_MAP defines no score/streak/summary binding (HOME-001/002,
  PROFILE-001..006 only) — binding UNRESOLVED; existing
  `StyleScoreCard`/`StyleStreakCard` mocks are presentation
  placeholders only. 65/35 card rule + tokens preserved; no new
  screens/routes in v1.
- Data layer (knowledge-precedent pattern): verbatim-wire DTO models,
  client (baseUrl/dev-token/12s/null-on-failure, 1 GET method),
  nullable-passthrough repository with NO mock merge. Backend-first
  truthful loading/error+retry/empty; offline/null = unavailable.
- Local math as truth REMOVED at implementation: `LearningService.
  styleScore`/signals stop being the displayed score (presentation
  fallback prohibited — no fake `87`, no mock merge). Keep as
  presentation-only: layout/animations; `preferredOccasions`
  write-through PATCH (not learning math); assistant offline local
  `recordSignal` as offline-queue display only.

### K. Cross-feature (FROZEN)

- HARD: M7 Saved Looks (saved count + `look_saved` TRX-3); Wardrobe
  items (wardrobe count). SOFT: Assistant Card Feedback (evidence
  signals → recents/personalization, never score); M9 Today's Look
  (via M7 saves only; "today active → emit signal" P1 idea has no UC
  and writes nothing today); M4/M14 personalization reads (consume,
  never write). DEFERRED: M11 `feedback_events` (gated; aggregation
  only when built); Wear Intelligence (no signal, save≠wear); M8
  Events (R36 add-only codes, no signal); M13 engine (shared DTO
  mapping only); `today_look_records`/weather/enriched rendering.

### L. Classification register

- FROZEN: §A route/method/auth/bare/no-pagination/naturally-
  idempotent/200-401-429; §B formula/inputs/range/current-cache/87-
  ban; §E–I privacy/ownership/pure-read/retention/uniqueness/day-
  semantics/signal-map-allow-list/wear-exclusion; §J no-fake-score +
  data-layer pattern; §K hard/soft/deferred split;
  `today_look_records` not required.
- INFERENCE (labeled, not frozen): recents `occurred_at`-desc
  recommendation; breakdown mirroring score terms (proposal only).
- UNRESOLVED (blocking implementation): empty-state selection; inner
  DTO types; breakdown field set; full C11 streak rule; recents
  allow-list/ordering/N; snapshot cadence; Profile/Home binding;
  TodayLook-`styleScore` linkage.
- DEFERRED: `style_score_records` history/trend; unseeded 4 signal
  codes; M11/wear/M8-signal/M13/enrichment/weather.

### N. Readiness: NEEDS FOUNDATION

- Dependency map: M2 user_state ✓ · M3 wardrobe (counts) ✓ ·
  M5 vocab (separate, no dep) · M6 engine (rules only) · M7 saves +
  signals ✓ · M8 (none) · M9 (via M7 only) · M11 (deferred) · M13
  (not required) · wear (excluded) · history tables ✗ missing.
- Sequence: 1) freeze §L UNRESOLVED (streak rule, breakdown fields,
  inner DTO + N/ordering, empty-state, binding) → 2) M10-A foundation
  (`style_score_records` + `activity_days` models/migration/indexes/
  ports/repos + signal-port routing) → 3) M10-B summary GET (derive
  score/streak/recents + mapping + errors) → 4) Flutter data layer +
  backend-first surfaces (local math demoted) → 5) history/trend
  (deferred `style_score_records` reads).
- Foundation required: two P1 tables + M10 use cases + the §L
  decisions. No implementation without them (all-four-required
  contract cannot be honestly served from counts alone).
- Future test obligations (none written): auth/isolation/empty-user/
  zero-counts (60 floor)/cap behavior (20/20)/score determinism/
  breakdown-shape/recents ordering+N/typed-labels-only (no raw
  text)/streak sequence incl. gaps+today+future-dates/UTC-vs-local/
  cross-user isolation/no-write-on-GET/cascade-erasure/Flutter
  models/client/repo/offline/UUID-safety/no-mock-merge/no-fake-87.

---

## DEC-020 — M10 Learning Summary Remaining Decisions Final Resolution (STEP 19.12)

Status: Accepted

Resolves the DEC-019 blocking register (A–H) from authoritative sources
only, with INFERENCE explicitly labeled where multi-source derivation
permits implementation without invention. Specification/decision work: no
code, no migration, no routes/schemas/repos/use-cases/models, no Flutter
production change, no tests. DEC-009–019 untouched (DEC-019 §L register
is closed by this entry, not edited).

### A. Empty-state contract (INFERENCE selection + FROZEN bans)

- Selection INFERENCE: a user with zero wardrobe / zero saves / zero
  signals (or any combination) receives `200` with the zero-valued
  `LearningSummary`: `styleScore 60`, zero-contribution breakdown (per
  §B), `streak 0`, `recentSignals []`. Basis: all four keys are
  required `*` (V1 `:428`, FEEDBACK `:313` — an empty body would violate
  the shape); GET is a pure read with no 404 trigger named in any of the
  three contract rows (INVENTORY `:822-824` blank errors, RULES `:507`
  `200`-only, FEEDBACK `:483` `200;401;429`); the frozen formula is total
  over counts, so every input combination has a defined number (§A4
  below). 204 rejected [I]: bodiless success contradicts the
  four-required-keys shape plus the V1/FEEDBACK 200 rows. 404-for-empty
  rejected [I]: caller-scoped singleton, no id-addressed resource (same
  coherence reading as DEC-019 §A). No new wire field is added.
- FROZEN: `styleScore` is legitimately `60` with zero inputs
  (`60+0+0` arithmetic from the frozen formula — DBR `:60`,
  HISTORY `:110`, APPEARANCE_API `:591-592`, FEEDBACK `:114-115`).
- FROZEN: no `needsData`/`needs_data` field is emitted (wire invention;
  the generic `200+needs_data/204 per use case` rule in CONTRACT_RULES
  `:298-302`, CONVENTIONS `:138-141`, ERROR_CONTRACT `:132-134` never
  names #34 — verified: only UC-14/UC-28 are named; `needsData`
  camelCase has zero docs hits; zero `204` hits near any #34
  definition). Combinations behave identically: signals never enter
  score math (§B), so wardrobe×saves counts alone fix the number.

### B. Breakdown DTO + calculation (content FROZEN/INFERENCE; names UNRESOLVED)

- Formula restated unchanged (DEC-019 §B): total `= 60 +
  min(wardrobe_count,20) + min(saved_count*2,20)`.
- Content FROZEN: breakdown decomposes the total into exactly its
  "component contributions" (FEEDBACK `:315`): fixed base `60` +
  `wardrobePoints = min(wardrobe_count,20)` (cap +20) + `savedPoints =
  min(saved_count*2,20)` (cap +20). Total included as the identity
  `total == styleScore` (arithmetic fact, not a second computation).
  Ordering INFERENCE: base → wardrobe → saved (formula order).
  Labels server-owned INFERENCE: every persisted label is server-set
  (save title, card `cardTitle ?? cardId ?? interactionType`,
  analysis run labels — writers own the strings; no client free text
  reaches the summary). Empty behavior INFERENCE: zero inputs →
  zero contributions with `total 60` (follows §A).
- UNRESOLVED (blocking, per the no-invention rule for wire fields):
  exact wire field names and object-vs-array framing. No source defines
  them (exhaustive search: only the concept phrase, nullable
  `breakdown jsonb` immutable snapshot in TABLE `:334`, and the banned
  UI-only mock categories Fit/Color/Occasion/Creativity in
  DATA_MODEL_INVENTORY `:304-305`, which contradict the formula terms
  and must NOT be reused). Owner one-liner required: confirm names (and
  framing) satisfying the content constraints above, or supply an
  alternative. Nothing is invented here.

### C. Inner DTO types (FROZEN + INFERENCE)

| Field | Type | Req | Meaning | Source | Persisted or derived |
| --- | --- | --- | --- | --- | --- |
| `styleScore` | int 0–100 scale, 60–100 emitted | * | progressive derived score | FEEDBACK `:314`, APPEARANCE_API `:580-582, :591-593` | derived cache (counts); history column `style_score_records.score` DEFERRED (§F) | FROZEN |
| `breakdown` | content per §B (names pending) | * | component contributions reproducing the total | FEEDBACK `:315`, TABLE `:334` | derived per request; snapshot jsonb only when history lands | content FROZEN/INFERENCE, names UNRESOLVED |
| `streak` | int ≥ 0, current consecutive styled days | * | E9-derived current streak (§D) | FEEDBACK `:315` "streak: E9 activity days", HISTORY `:111` | derived per request from `activity_days`; richer timeline fields DEFERRED (additive later) | INFERENCE (minimal; UI-only `StyleStreakData` shape explicitly NOT adopted) |
| `recentSignals` | string[] (signal `label` texts, ≤200 chars each) | * | last N typed-signal labels as evidence | FEEDBACK `:316-317`, `:478-479`, `:566`, SECURITY `:643` | derived per request from `learning_signals`; type/context/occurredAt NOT exposed (§E) | INFERENCE (grammar + label column BC-12 + privacy rules; object-shape rejected as invention) |

- Never confused (FROZEN restatement): not outfit `matchScore` (0–1 /
  0–100 generation quality), not wear aggregates, not
  `feedback_events` (gated M11), not TodayLook fields (§H).

### D. C11 streak rule (fully frozen as INFERENCE set D1–D10)

1. Trigger INFERENCE: ANY persisted `learning_signals` row for the
   caller marks its day styled. Allow-list = all rows for the user (5
   seeded codes today; future seeded codes included automatically).
   Basis: E9 "derived from activity/signals" states the set generically
   (HISTORY `:87`, MVP_SCOPE `:86`, MODULE_MAP `:353-356`); no source
   narrows it, and narrowing would be the invention; the lone
   saves-only line (GROOMING blueprint `:562`) is non-normative prose
   and loses authoritative-first to the DB/API generics (19.7 ranking
   precedent). Excluded: wear (no signal exists, DEC-012), Flutter-local
   names (no server rows, FK `RESTRICT`), doc-only 4 codes until seeded
   (cannot occur — `models.py:216` + FK).
2. Day datum INFERENCE: server-UTC calendar date of the signal's
   `occurred_at` (server `now()` default — all three writers omit the
   column: `repositories.py:418-441`, `models.py:216`). Basis: UTC-Z
   wire convention (CONTRACT_RULES `:143`), DEC-018 server-UTC-today
   precedent (labeled [I] from M8 E-1), wear UTC normalization; no
   user-timezone source exists anywhere.
3. Today counts INFERENCE (excluding an unfinished today would be the
   invented restriction; "current" semantics).
4. Consecutive INFERENCE: calendar `day` difference exactly 1.
5. Missing day INFERENCE: breaks the run (no grace/pausing source).
6. Anchor + examples INFERENCE: anchor = today if styled else
   yesterday; streak = run length back from anchor over styled days;
   unstyled anchor → 0. `none → 0`; `one active day → 1`;
   `yesterday-only → 1`; `today-only → 1`; `gap of ≥1 day → trailing
   run from anchor` (e.g. styled Mon,Tue,Fri, today Fri → 1; today Sat
   unstyled → anchor Fri → 1).
7. Future rows INFERENCE: `day > server-UTC today` rows are ignored by
   derivation (no CHECK forbids storing; writers store server now so
   they should not occur; wear future→422 analogy only).
8. Derivation INFERENCE: select caller's `styled=true` days with `day ≤
   today`, order `day` desc, walk from anchor while adjacent. Read-time,
   GET writes nothing (FEEDBACK `:486`, TRX §5).
9. Response field: `streak` int per §C.
10. First styled day → 1 (run length 1, follows rule 6).

### E. Recent signals (INFERENCE set)

- Allow-list INFERENCE: every persisted caller row (all 5 codes today;
  no source excludes any persisted type — exclusion would be
  invention). Raw `reason`/feedback text never leaks (FROZEN:
  FEEDBACK `:316-317, :478-479, :566`, SECURITY `:363, :643`).
- Ordering INFERENCE: `occurred_at` desc, `id` desc tiebreak
  (saved-looks newest-first `id`-desc precedent, DEC-013; wear
  `worn_at`-desc/`id`-asc pattern). "Last N" implies recency; columns
  unstated nowhere else.
- Maximum N INFERENCE: server default `20` (list `page_size` default
  convention — CONVENTIONS `:102`, RULES C-11, PAGINATION `:169`;
  #34 itself takes no pagination params per PAGINATION `:152, :442`).
  Fewer rows → fewer entries, never padded. FROZEN finding: no
  authoritative N exists (verified zero-number search).
- Representation INFERENCE: `string[]` of `label` texts (§C); `context`
  never exposed (AI-0 honesty + privacy minimalism — contexts carry
  internal `look_id`/`run_id` linkage; TABLE `:228` bounds it only as
  "never a filter axis"). Empty INFERENCE: `[]`.

### F. History snapshot cadence (INFERENCE + FROZEN)

- `activity_days` write INFERENCE: synchronous per-qualifying-write
  daily upsert riding the SAME commit as the signal write
  (`INSERT … ON CONFLICT (user_id,day) DO UPDATE styled=true`;
  `summary` stays NULL in v1 — no aggregate content defined, honesty).
  Basis: `UNIQUE(user_id,day)` (BC-4) forces daily granularity;
  single-row atomicity (TRX `:204-208`); read-freshness for GET (the
  "deferred/aggregate" phrase in MODULE_MAP `:368-369` attaches to
  score recomputation, not streak); same-commit correctness (a
  sequential second unit after TRX-3 could lose the day on failure
  with no replay path — keyed-save replay returns the original
  without rewriting). Analysis dual-signal commits upsert once.
- FROZEN finding: NO retrospective backfill (no source requires it;
  none is silently created). Consequence: streak accrues prospectively
  from M10-A deploy; past signals remain visible via recents only.
- FROZEN: v1 summary does NOT require `style_score_records` reads —
  current score is a recomputable cache (HISTORY `:108-120, :186-192`,
  DBR `:60-61, :102-103, :592`, APPEARANCE_API `:591-593`, TABLE
  `:320-324`).

### G. Profile / Home binding (INFERENCE + FROZEN)

- INFERENCE: BOTH. Home glance = score + streak via the existing
  `StyleScoreCard`/`StyleStreakCard` (presentation placeholders become
  backend-fed); Profile detail = score + streak + recents (breakdown
  rendering follows the §B one-liner). Basis: INVENTORY `(8,28
  profile)` + FEEDBACK `:487-489` profile screens + TABLE `:320-323`
  "Home trend and Profile history" + MVP_SCOPE `:86` "home + profile
  cards" + SCREEN_DATA_INVENTORY/FEATURE_DATA_MATRIX mock mounts.
- FROZEN: no new screen/route (DEC-007; no source requires one;
  SCREEN_MAP IDs are doc-only and map to existing
  `home`/`daily-outfit`/`profile/*` routes). Score + streak display on
  both; recents on Profile; truthful loading/error+retry/empty and
  offline-unavailable with no fake scores (conventions + 87 ban).

### H. TodayLook `styleScore` linkage (FROZEN separation)

- FROZEN: M10 `styleScore`, `style_score_records.score`, TodayLook
  `styleScore`, and `OutfitRecommendation.matchScore` are separate DTO
  families — no source connects them (DAILY `:278-282`, REC_API
  `:282, :300-306, :446`, V1 `:424-428` define shapes only; DEC-017-E
  and DEC-018-C12 leave the computation source-open with the 87 ban).
  TodayLook MUST NOT depend on M10 (its DEC-017/018 derivation inputs
  are UserState + wardrobe + event + weather hint; M9 is READY on that
  basis). Any future unification is DEFERRED.

### I. M10-A foundation (REQUIRED vs DEFERRED)

- REQUIRED for v1: `activity_days` migration (table + `UNIQUE
  (user_id,day)` BC-4 + `(user_id,day)` index A8) / model / repo
  (`ActivityDayRepository`); M10 use cases (derive-streak-per-§D,
  get-summary-per-§§A–C,E; record path stays the existing writers);
  reuse of the existing `LearningSignalRepository` (no change);
  per-write upsert wiring preserving TRX-3/TRX-6/single-commit
  boundaries, payloads, error codes, and idempotency (keyed-save
  replay, card-feedback append-only). No new seeds (5 codes suffice;
  4 gap codes NOT required). No writer behavior change (route-via-M10
  only if byte-identical, else leave direct writes).
- DEFERRED: `style_score_records` migration/model/repo + trend reads;
  backfill (none); `today_look_records` (NOT required, restated);
  unseeded signal codes; M11/wear/M8-signal/M13/weather/enrichment.

### J. Classification register + anti-invention statement

- FROZEN: §A 60-floor + no-`needs_data`-field; §B formula/content/total
  identity; §C `styleScore` + confusion bans; §E raw-text ban; §F
  no-backfill + score-history deferral; §G no-new-screen; §H family
  separation + TodayLook independence; §I required/deferred split.
- INFERENCE (explicitly labeled above, implementable as frozen): §A
  zero-object selection + 204/404-for-empty rejection; §B ordering +
  server-labels + zero-breakdown; §C `streak` int + `recentSignals`
  string[]; §D full C11 (D1–D10); §E allow-list/order/N/empty/context
  omission; §F upsert cadence + NULL summary; §G both-surface binding.
- UNRESOLVED (sole blocker): §B wire field names + object/array
  framing — the owner one-liner. Nothing else remains UNRESOLVED.
- DEFERRED: score history/trend, richer streak fields (additive),
  recents element enrichment (additive), gap signal codes, M11, wear,
  M8-signal, M13, weather.
- Unresolved items must not be silently invented at implementation:
  the §B names ship only via the one-liner; INFERENCE items ship as
  specified above (owner override before M10-B adopts it, else
  implement verbatim).

### K. Readiness: NEEDS FOUNDATION

- One wire one-liner (§B names/framing) + M10-A tables/use-cases (§I).
  Nothing else blocks: score math, streak rule, recents, cadence,
  binding, linkage, and empty-state are all implementable above.
- Implementation sequence (after the one-liner): 1) M10-A foundation
  (migration/model/repo/use-cases + upsert wiring + tests) → 2) M10-B
  backend `GET /v1/learning/summary` (derive + mapping + 200/401/429 +
  tests) → 3) Flutter data layer (DTO/client/repo per knowledge
  precedent + tests) → 4) Home + Profile backend-first binding (local
  math demoted, no fake scores + tests) → 5) cross-layer regression
  (lifecycle + isolation + no-write-on-GET + cascade-erasure).

---

## DEC-021 — M10 Learning Summary Breakdown Wire Contract Owner Decision (STEP 19.13)

Status: Accepted

Closes the sole DEC-020 blocker (§B wire names/framing) by explicit owner
decision. Decision/specification only: no code, no migration, no
routes/schemas/repos/use-cases/models, no Flutter production change, no
tests. DEC-009–020 unchanged.

- **Source re-check (FROZEN finding).** Authoritative sources still do
  not define breakdown wire names/framing (verified this step:
  docs-wide zero hits for `wardrobePoints`/`savedPoints`/breakdown
  object; API docs carry only the field name `breakdown` plus
  "component contributions" — FEEDBACK_LEARNING_API `:315`). The
  contract below is therefore an owner decision, not a source
  deduction. Calculation/content is unchanged from DEC-019 §B / DEC-020
  §B (base 60, wardrobePoints cap +20, savedPoints cap +20, formula
  order base → wardrobe → saved). Old Flutter mock categories (Fit,
  Color, Occasion, Creativity) remain banned; no additional dimensions.
- **Breakdown wire contract (FROZEN).** Framing: object. Exact JSON,
  camelCase field names verbatim, no additional fields in M10 v1:
  `breakdown { base: int, wardrobePoints: int, savedPoints: int, total:
  int }` with `base = 60`, `wardrobePoints = 0..20`, `savedPoints =
  0..20`, `total = 60..100`, and the invariant `total == styleScore`
  (base + wardrobePoints + savedPoints). Zero-input state:
  `{base: 60, wardrobePoints: 0, savedPoints: 0, total: 60}` (follows
  DEC-020 §A). Caps behavior follows the frozen formula
  (`min(wardrobe_count,20)`, `min(saved_count*2,20)`).
- **Readiness: READY FOR IMPLEMENTATION.** No UNRESOLVED item remains;
  DEC-020 INFERENCE items ship verbatim (owner override only before
  M10-B adopts them). First batch is still foundation: 1) M10-A
  `activity_days` foundation + signal-write upsert wiring → 2) M10-B
  `GET /v1/learning/summary` backend → 3) Flutter data layer → 4) Home
  + Profile backend-first binding → 5) cross-layer regression.

---

## DEC-GUEST-01 � Guest Access to AI Stylist Tab

Status: Accepted (owner-directed, 2026-09-23)

Users who choose Continue Without Account reach the AI Stylist tab (/stylist exactly) as explicit guests without a session token. The guard exception is scoped to that one tab: all other shell branches and every nested /stylist/* action still redirect unauthenticated users to /entry. Guest capture stays on the public onboarding chain (iAnalysis ? YourAnalysisScreen); the real analysis pipeline (hairstyleProcessing ? backend) remains authenticated-only. No token is minted for guests and no backend auth is bypassed � API clients keep resolving tokens through AuthSession and 401 honestly.

