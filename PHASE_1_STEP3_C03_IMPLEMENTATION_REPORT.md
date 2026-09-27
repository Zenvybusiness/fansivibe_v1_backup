# PHASE 1 STEP 3 — C-03 preferred_item_ids Implementation Report

> Executed 2026-09-27. C-03 IMPLEMENTED on the outfit generate path only. C-02 untouched. No commit/push.

## Behavior (locked contract → live)

- Wire: `POST /v1/outfits/generate` accepts optional `preferredItemIds?: UUID[]`.
  Absent/null/`[]` ≡ empty (byte-identical baseline). Malformed UUID → 422
  (Pydantic UUID parsing, DEC-010 convention). Unknown/foreign IDs → ignored
  to 0 (never 404 — preference is advisory; owner-scoped candidates stay the
  security boundary; no per-ID DB lookup, so no existence oracle).
- Ranking: existing +5/item, cap +15, soft signal only (no filter, no
  generation/tie-break/budget change). OI +0.05/cap +0.15 independent.
- No favorites derivation; double-count policy stays deferred to C-05.

## Files changed

Backend:
- `backend/app/api/schemas/outfits.py` — `preferredItemIds: Optional[list[UUID]] = None`.
- `backend/app/application/outfits.py` — `_normalize_preferred_item_ids`
  (None/non-list → empty; UUID/str → deduped frozenset) + `preferred_item_ids`
  kwarg on `__call__`/`derive_with_reason`/`_derive_outfit` (default preserves
  baseline); passed to `score_outfit_candidate` instead of literal `frozenset()`.
- `backend/app/api/routers/outfits.py` — forwards `request.preferredItemIds`.

Flutter (DTO/client passthrough only — no UI, no auto-populate, no favorites read):
- `lib/features/outfit_builder/data/outfit_models.dart` — optional
  `preferredItemIds` (omitted from wire when null/empty).
- `lib/features/outfit_builder/data/outfit_client.dart` — optional param, sent
  only when non-empty.
- `lib/features/outfit_builder/data/outfit_repository.dart` — passthrough.
- 4 test fakes updated for the new optional param (signature-only, no behavior).

Tests:
- `backend/tests/test_c03_preferred_item_ids.py` — 23 tests (schema matrix,
  normalizer, +5/cap-15, dedup, nonexistent/foreign → 0, empty ≡ baseline, no
  filtering, C-02 palette/fit intact, ceiling 100, tie-break, OI independence,
  derive baseline/foreign/dedup/back-compat, non-outfit callers left empty).
- `test/outfit_builder_api_test.dart` — +2 tests (DTO omit/round-trip, client
  sends-only-when-non-empty).

## Production callers

- Wired: `application/outfits.py` derive (primary — the only path with an
  explicit preference source: the request field).
- Intentionally empty: `events.py:389`, `today.py:188` (no request preference
  input exists — inventing one would mean inferring), `main.py:310` assistant
  path (no explicit source; omits kwarg as before).

## Validation

- Targeted backend: 23/23 new pass; neighbors
  (`test_analysis_rules/decison_engine/ffo_compatibility/c02_palette/c02_fit/analysis_use_case`)
  261 pass / 3 PG-skips.
- Full backend (`DATABASE_URL=sqlite://`, 6 PG-only files ignored for the
  pre-existing sqlite-override collection error): 968 pass / 415 skip /
  3 fail — the 3 fails (2× trending seed-data 500s, 1× soak PG-pool API) are
  sqlite-override artifacts, same class as the Step 2.11 baseline
  (945 pass/415 skip/3 fail+6 errors); +23 = new C-03 tests.
- Flutter: `analyze` 0 issues; `outfit_builder_api+screens` 55+2 pass;
  `auth_flow/data_consistency` pass; `guest_phase2` 2 Discover failures =
  known pre-existing set (baseline records guest_phase2-Discover×2).

## C-02 regression

Palette +5, fit +5 (gate ≥ 0.6, no multiplier), mood 0, compatibility 70,
total 100, tie-break — all asserted in the new test file; neighbor C-02
suites green.

## Unresolved decision (belongs to owner)

Length cap: NOT shipped. Adjacent conventions conflict (wears per-action cap
10 vs reasoning `wardrobe_refs` max 20), so no defensible single limit exists;
per instructions no random number was invented. Scoring caps (15 / 0.15) bound
all effects. Owner picks the cap (or confirms none) in a follow-up.

## Migrations / docs

- Migrations: none. Docs updated: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md`
  (C-03 IMPLEMENTED), `PHASE_1_STEP2_OWNER_DECISIONS.md` (status), this report,
  `CURRENT_STATE.md`. No commit/push.
