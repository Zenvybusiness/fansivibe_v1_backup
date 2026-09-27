# PHASE 1 STEP 4 — C-04 Scan → Generate Implementation Audit

> Status: AUDIT ONLY. No source/tests/schema/API/Flutter changes, no commit/push.
> Date (UTC): 2026-09-27. All findings read from current code, cited below.
> C-02 and C-03 untouched. Scope note: this audits the **garment** scan
> (`POST /v1/analysis/garment` → `GarmentProfile`) → outfit-generate path.
> The outfit/appearance scan (`recommend_hairstyle`, face_shape-only) is a
> different namespace — already covered by the Step-2 C-04 options A–D
> (still PENDING, unaffected by this audit).

## A. Current scan flow (garment)

`add_wardrobe_item_screen.dart` photo step (`_takePhoto`/`_pickFromGallery`
→ `WardrobePhotoScreen`)
→ `GarmentClient.submitGarmentAnalysisBytes` (multipart `image` → `POST
/v1/analysis/garment`, 20 MB guard, 30 s timeout)
→ router `analysis.py:243 create_garment_run` (content-type/size guards)
→ `CreateGarmentRun` (`application/analysis.py:645`; run_type `garment`,
run row `pending`)
→ `OllamaVisionGarmentAdapter.analyze` (`ai/vision_garment_adapter.py:153`;
strict JSON prompt, canonical-category coercion, `LOW_CONFIDENCE_FLOOR`)
→ run `completed` with `GarmentProfile.to_snapshot()` verbatim (or terminal
`failed` with typed `details.reason`)
→ `GarmentClient.pollGarmentRun` (`GET /v1/analysis/runs/{run_id}`, 30×1 s)
→ `GarmentAnalysisResult.fromJson` (strict; malformed → `FormatException`,
never a fake)
→ `_prefillFromGarment` (exact-match chip preselect only)
→ user confirm/edit → `POST /v1/wardrobe/items` → wardrobe UUID.

## B. Current scan response shape

Completed-run `result` = `GarmentProfile.to_snapshot()`
(`domain/value_objects.py:105`): `category` (canonical code or null),
`subcategory`/`color`/`pattern`/`material`/`style`/`fit` (free strings or
null), `confidence` (float 0–1), `needs_review` (bool), `sourceRunId`
(run UUID string). No item ID, no wardrobe UUID. Run envelope adds
`run_id`, `input_media` (`key/mediaType/sizeBytes/contentHash/analyzer/
uploadedAt`), `status`/`error.details.reason` (`no_garment_detected`,
`ambiguous_subject`, `low_confidence`, `analyzer_unavailable/timeout`,
`invalid_analyzer_response`). Vision is observation-only: null = "not
clearly visible", never a guess; sub-floor confidence fails the run.

## C. Current outfit-generation flow

Builder screens → `OutfitBuilderClient.generateOutfit` (`#41 POST
/v1/outfits/generate`: occasion/mood/fit/colorPalette/seed +
`preferredItemIds?`) → router `routers/outfits.py:117` →
`GenerateOutfit.derive_with_reason` (`application/outfits.py:308`) →
owner wardrobe rows → `generate_outfit_candidates` (reads **`.id` +
`.category` only) → `score_outfit_candidate` (reads color/material/
is_favorite/fit+fit_confidence) → rank → winner. Generation input is
**owned wardrobe rows only** — there is no ad-hoc garment input.

## D. Current outfit-generation input shape

`OutfitGenerateRequest`: 4 validated 1–200 strings + optional `seed` +
optional `preferredItemIds?: UUID[]` (C-03, live). Wardrobe row fields
consumed: `id` (UUID), `category` (canonical code; unknown → ignored),
`color` (`colors.code`; unknown → neutral), `material` (nullable),
`is_favorite`, `fit` + `fit_confidence` (C-02-F evidence, gate ≥ 0.6).
Hard constraints: tops+bottoms mandatory, else no candidates (honest
empty, never fabricated).

## E. Existing transformation / reuse opportunities

- Backend garment→wardrobe/outfit transform: **NONE** (repo-wide grep for
  fromGarment/toWardrobe/prefill/garment_to: zero hits in `backend/app`).
- Flutter `_prefillFromGarment` (`add_wardrobe_item_screen.dart:366`): exact
  case-insensitive chip preselect (subcategory→type, color→color,
  material→texture); near-misses stay unselected; never overwrites user
  picks. `_buildItemName` (texture + type) and `_buildImageRef` (backend
  media values + `sourceRunId`, never invented) complete the save payload.
- Save gate: `AddWardrobeItem` → repo `create`; category/color/material
  enforced by vocab FKs → unknown codes 422 (`wardrobe.py:166-173`).
- Key reuse: the **C-03 `preferredItemIds` field is already live** on #41 —
  a newly saved scanned item's UUID can boost outfits containing it with
  **zero backend changes**.

## F. Field-by-field mapping (scan → generation)

| Scan field | Generation field | Class |
|---|---|---|
| `category` (canonical or null) | candidate `category` | directly reusable iff non-null; null → user picks (unknown categories ignored by generation) |
| `color` (free string or null) | scoring `color` (`colors.code`) | transformable iff exact vocab match, else user-confirms; miss → neutral |
| `material` (free or null) | scoring `material` | same as color (nullable → neutral) |
| `fit` + `confidence` | C-02-F evidence (`fit`, `fit_confidence`, gate ≥ 0.6) | directly reusable; unmapped fit text / low conf → neutral |
| `subcategory` | — (chip preselect + item name only) | stored-but-not-consumed by generation |
| `pattern`, `style` | — (no columns, no scoring term) | unavailable to generation |
| `needs_review` | — | UI-only, ignored |
| `sourceRunId` / `run_id` | `imageRef.sourceRunId` on save; outfit-save provenance via existing `saved_looks` extractor | reusable as provenance, not as ranking input |
| `input_media` | `imageRef` sidecar on save | reusable; generation never reads images |
| IDs | — (scan produces none) | unavailable → save-for-UUID or ephemeral adapt |

## G. Information that would be lost

`pattern` + `style` are lost at save (no columns, no scoring terms — same
class as the C-06 sidecar question, out of scope here). `subcategory`
survives only inside the item name/type chip. Free-form `color`/`material`
that miss the vocab are dropped unless the user maps them. `confidence`
survives only as `fit_confidence` (gate-only, never a multiplier).
Nothing scored is fabricated: every miss degrades to neutral.

## H. Existing user flows that already work

1. Scan garment only ✓ (photo → run → result display, honest failures).
2. Scan → save garment to wardrobe ✓ (prefill → user confirm → UUID).
5. Scan → edit garment ✓ (chips editable before save; existing picks kept).
Flows 3 (scan → generate), 4 (generate without saving), 6 (add to outfit),
7 (scan → recommendation) do **NOT** exist: zero scan/garment/photo
references anywhere under `lib/features/outfit_builder`.

## I. Scan → Generate gaps

1. No navigation from the garment/add flow to the builder (dead end after
   save: `Navigator.pop` with the created item only).
2. No mechanism to carry the scanned item's identity into generation
   except manual re-selection (wardrobe list → builder has no
   preferred-item picker; C-03 field has no Flutter producer yet).
3. No ephemeral (unsaved) generation input — #41 accepts wardrobe rows
   only; `GarmentProfile` has no ID and no adapter into candidates.

## J. Persistence / identity implications

- Option A (save-then-generate): identity = the saved wardrobe UUID
  (owner-scoped, M7/OW-1 compatible, C-02 fit evidence + C-03 boost work
  as-is). Cost: creates a row per scan the user keeps — correct if the
  user wants the item; wrong to force-save just to generate.
- Option B (ephemeral): identity = none — needs a new unpersisted-item
  input on #41 plus ownership/fabriction guards (a client-supplied
  category/color/material set). No new table, but a new validation
  surface and a second candidate-member source. Heavier and riskier.
- Verdict in §K/L: A first; B only on explicit owner order.

## K. Product decision required

One: after a garment save, does the product offer "Build outfit with this
item" (Option A — explicit per-request boost via the live C-03 field), or
must generation also work on unscanned/unsaved garments (Option B —
ephemeral input, new contract)? If A: no further semantic call — the
item is an ordinary wardrobe row. The Step-2 C-04 A–D (appearance-scan
framing) stays PENDING and separate; nothing here selects among them.

## L. Recommended minimum implementation path (next step, NOT this one)

Option A, backend-free: post-save CTA on the add screen ("Build outfit
with this item") → builder/generation pass `preferredItemIds: [<new
UUID>]` → existing +5 boost ranks outfits containing the scanned item;
empty wardrobe otherwise behaves exactly as today. No schema, migration,
ranking, vision, or M7 change. Option B needs its own contract first.

## M. Files/functions that would need modification (next step)

- `lib/features/wardrobe/presentation/add_wardrobe_item_screen.dart`
  (post-save CTA carrying the created UUID).
- Builder → generation navigation + `OutfitBuilderClient.generateOutfit`
  call site (forward `preferredItemIds`; client already supports it).
- Tests: widget test for the CTA + client passthrough (already covered),
  backend none (C-03 matrix already pins the boost).
- Explicitly NOT: `analysis_rules.py` scoring/generation, vision
  adapters, `GarmentProfile`, routers/schemas, M7 save validation, DB.

## N. What must NOT be modified

C-02 palette/fit terms, budget, gates; C-03 wire semantics and caps;
`GarmentProfile`/adapter honesty rules (null stays null, floors stay);
M7/DEC-010 validation; candidate generation + hard constraints; no new
models, tables, dependencies, or duplicate transforms.

## O–Q. Confirmations and tests inspected

- O. C-02 untouched: no C-02 file/constant/term referenced beyond
  read-only reuse (`_fit_points` gate cited, not changed).
- P. C-03 untouched: field + caps cited as the reuse vehicle; no
  semantic change proposed.
- Q. Tests inspected (read-only): `test/wardrobe_garment_flow_test.dart`
  (parse/transport/photo/prefill/save groups), `backend/tests/
  test_garment_analysis.py` (adapter + `CreateGarmentRun`),
  `test_m11_p3_wardrobe_to_outfit.py` (real-UUID bridge precedent),
  `test_analysis_rules.py` + `test_c02_fit.py` (generation input
  contract), `test/outfit_builder_api_test.dart` (C-03 passthrough).

## R–T. Change control

- R. Files changed during this audit: `PHASE_1_STEP4_C04_SCAN_GENERATE_AUDIT.md`
  (new) + `CURRENT_STATE.md` (entry). No other files touched.
- S. Source/schema/migration changes: NONE (verified via `git status`;
  audit added docs only).
- T. Nothing committed or pushed. STOP after audit — C-04 NOT implemented.
