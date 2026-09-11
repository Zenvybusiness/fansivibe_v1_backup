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
