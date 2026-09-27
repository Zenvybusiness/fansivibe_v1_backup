# PHASE 1 STEP 4 — C-04 Implementation Report (Option A: post-save Build with this item)

> Executed 2026-09-27. Flutter-only. No backend, ranking, vision, DB, or
> migration changes. C-02 and C-03 behavior untouched. No commit/push.

## Flow (locked)

photo → garment analysis → user confirm/edit → wardrobe save → created
**wardrobe UUID** → "Build with this item" → existing Outfit Builder
(user picks the 4 prefs) → generation with `preferredItemIds: [uuid]` →
existing C-03 +5 boost → regenerate preserves the id.

## Files changed

- `lib/features/wardrobe/presentation/add_wardrobe_item_screen.dart` —
  success now keeps the created item (`_savedItem`) and shows post-save
  actions instead of popping: confirmation + `Done` (existing pop-with-item
  contract) + `Build with this item` (primary, **server ids only**:
  hidden on failure, on empty id, and on guest `local-*` ids via the
  existing `local-` convention). Navigates with
  `pushNamed(buildOutfit, extra: {'preferredItemId': uuid})`. No image
  path / run id / raw garment JSON leaves the screen — UUID only.
- `lib/features/outfit_builder/presentation/build_outfit_screen.dart` —
  optional `preferredItemId`, forwarded into the generation extra
  alongside the unchanged 4 prefs + event context.
- `lib/features/outfit_builder/presentation/outfit_generation_screen.dart` —
  optional `preferredItemId`; sent as `preferredItemIds: [id]` (null/empty
  ≡ baseline omit); carried into the recommendation request map so
  regenerate stays faithful.
- `lib/features/outfit_builder/presentation/outfit_recommendation_screen.dart` —
  regenerate passes `preferredItemIds` from the request (1 line).
- `lib/app/router/app_router.dart` — both builders read the optional
  `preferredItemId` extra key (existing `Map<String,String>` contract kept;
  all prior keys untouched).

Tests: `add_wardrobe_item_screen_test.dart` (save→actions+Done pops;
local-id hides Build; navigation carries exactly the UUID; back-nav
returns), `outfit_builder_screens_test.dart` (new C-04 group of 4:
extra contents, generation forward, null baseline, regenerate preserve;
fake records `genPreferredIds`), `wardrobe_garment_flow_test.dart`
(save expectation updated to the new success step).

## Callers deliberately unchanged

Events/today/assistant generation paths, vision adapters, `GarmentProfile`,
M7 save validation, candidate generation/ranking, C-02 terms, C-03
semantics and caps. Guests: builder gate stops before any derive, so the
omitted id can never reach the wire.

## Validation

- `flutter analyze lib test`: 0 issues.
- Targeted: add-item 13/13, outfit_builder screens 40/40 + api 22/22,
  garment flow 17/17, wardrobe/auth/data_consistency green.
- Full Flutter: 1086 pass / 19 fail — failing file set identical to the
  recorded baseline (auth_screens, clothes, for_you, guest_phase2-Discover×2,
  widget_test×2); zero failures in any touched file.
- Backend: no changes; C-03 + C-02 suites re-ran green (53 pass/1 PG-skip).

## Docs

CONTRACTS C-04 → implemented-Option-A pointer; OWNER_DECISIONS C-04 →
Option A LOCKED; this report; CURRENT_STATE entry. Audit doc stands.
