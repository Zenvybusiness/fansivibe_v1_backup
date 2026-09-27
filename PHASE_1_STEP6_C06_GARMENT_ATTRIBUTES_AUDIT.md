# PHASE 1 STEP 6 — C-06 Garment Attributes Audit

> Status: AUDIT ONLY. No source/tests/schema/API/Flutter changes, no
> commit/push. Date (UTC): 2026-09-27. All findings read from current code.
> C-01…C-05 untouched.

## Attribute trace table

| ATTRIBUTE | PRODUCED | PERSISTED | READ | SCORED | UI USED | LOST | NOTES |
|---|---|---|---|---|---|---|---|
| category | adapter (`_normalize_category`, canonical codes or null) | YES (`wardrobe_items.category_id` FK → `wardrobe_categories.code`) | YES (generation reads `.id`/`.category`; skeletons, tops+bottoms gate) | structural input (hard constraints), not a score | summary + prefilled category | NO | null → user picks; unknown codes never fabricated |
| subcategory | adapter (free string or null) | NO (no column) | NO | NO | prefill type chip + item name only | YES (past the add screen) | survives only inside the user-confirmed name |
| color | adapter (free string or null) | YES (`color_id` FK → `colors.code`, 17 codes; exact-match-or-user, 422 otherwise) | YES | YES (harmony ±, C-02-P palette +5) | summary + chips | NO | vocab miss → neutral unless user maps |
| pattern | adapter (free string or null) | NO (no column, no vocab table) | NO | NO | summary display only (ephemeral) | YES | disappears with the run result |
| material | adapter (free string or null) | YES (`material_id` nullable FK → `materials.code`, 16 codes) | YES | YES (consistency +5) | summary + chips | NO | null → neutral |
| style | adapter (free string or null) | NO (no column, no vocab table) | NO | NO | summary display only (ephemeral) | YES | FFO-incompatible (see §Style) |
| fit | adapter (free string or null) | YES (`fit` Text, verbatim, nullable) | YES | YES (C-02-F +5, gate ≥ 0.6, no multiplier) | summary | NO | unmapped text → neutral |
| confidence | adapter (float 0–1, category certainty) | PARTIAL (only as `fit_confidence` verbatim) | YES (fit gate only) | gate-only, never multiplied | NO | overall value lost elsewhere | three thresholds exist (see §Confidence) |
| needs_review | adapter rule (deterministic) | NO | NO | NO | summary copy only | n/a (derived, not a fact) | DERIVED STATE, analysis-only |
| sourceRunId | run completion | YES (inside `image_ref` + run row) | provenance/display | NO | photo ref link | NO | save extractor reads appearance snapshots only |

## Durable vs transient facts

- Durable domain attributes (columns, FK-grounded where vocab exists):
  `category`, `color`, `material`, `fit` + `fit_confidence`. All four are
  read at generation/scoring. Nothing else survives.
- Transient (run result + ephemeral UI only): `subcategory` (except via
  name), `pattern`, `style`, overall `confidence`, `needs_review`.
- Provenance (durable, non-scoring): `sourceRunId`, `input_media` inside
  `image_ref`.

## Current scoring usage

`_coverage_points` (category structure), `_color_points` (±),
`_material_points` (+5), C-02-P `_palette_points` (+5), C-02-F
`_fit_points` (+5, gated). Pattern/style/subcategory/confidence-as-signal:
zero references in `analysis_rules.py` (only `pattern` hit is a code
comment). No filter, no multiplier, no second preference system anywhere.

## Pattern findings

No vocabulary table (only `wardrobe_categories`/`colors`/`materials` exist
in `0005`), no column, no schema field, no scoring rule, no generation
use. UI use = one summary row. Information disappears at wardrobe-save:
the save payload (`name/category/color/material/imageRef/fit/
fit_confidence`) has no pattern slot, so the value dies with the run
`result`. Durable pattern needs: new vocab + persistence (column =
migration, or JSONB sidecar) + normalization + weight — all PENDING OWNER
DECISION.

## Style findings

`garment.style` (free vision string, e.g. observed descriptor) is NOT
compatible with: (a) outfit style taxonomy — none exists server-side
(C-02-M closed: no backend mood/style data); (b) FFO aesthetics — JSON
knowledge schemas carrying string arrays (`brand/designer/trend`) and
0–1 weight dicts (`user_style.aesthetics`), with no live outfit-pipeline
consumption (`ffo_compatibility` reads per-row `silhouette` attrs that
wardrobe rows do not carry). Different types, different scales, no
mapping, no wiring. Same verdict as pattern: vocab + persistence +
weight + owner call required; until then analysis-only.

## Confidence findings

One number, three separate jobs — do not unify: (1) `LOW_CONFIDENCE_FLOOR
= 0.35` fails the run (`low_confidence`); (2) `< 0.6` (or missing core
facts) sets `needs_review` (deterministic review routing); (3) persisted
verbatim as `fit_confidence`, consumed ONLY as the C-02-F ≥ 0.6 gate
(never multiplied). Confidence is overall category certainty, NOT
attribute-specific. Persisting per-attribute confidences would be new
schema + new semantics — not proposed.

## image_ref findings

Verdict: **A (truly lost elsewhere) + provenance-only sidecar — NOT a
shadow domain store.** Backend stores the Flutter-supplied dict verbatim
(`routers/wardrobe.py:183`, `repositories.py:590`); Flutter builds it
exclusively from run `input_media` + run id (`_buildImageRef`: key,
mediaType, sizeBytes, contentHash, analyzer, uploadedAt, sourceRunId).
Zero analysis attributes (pattern/style/confidence) enter it. It is never
read by generation/scoring. It MUST NOT be promoted into scoring without
a contract: media provenance is not attribute evidence.

## Levels (fact / derived / signal)

- FACT: category, subcategory, color, pattern, material, style, fit,
  confidence, sourceRunId (+ input_media).
- DERIVED STATE: `needs_review` (rule), canonicalization/coercion,
  chip preselects, `fit_confidence` reuse.
- DECISION SIGNAL (live): category structure, color ±, material +5,
  palette +5, fit +5 (gated). Pattern/style/subcategory/confidence are
  NOT signals and must not be silently promoted.

## Product decisions required

1. Pattern: vocab source + persistence shape (column vs sidecar) +
   normalization + weight + filter-vs-signal. 2. Style: same set, plus
   explicit ruling that garment free-text stays separate from FFO/outfit
   taxonomies until a mapping contract exists. 3. Subcategory: keep in
   name/chips only, or persist? 4. Per-attribute confidences: collect at
   all? 5. Any new weight (stop condition fires on all scoring changes).

## Classification + recommended smallest path

- A (complete): category, color, material, fit + fit_confidence.
- B (persisted, narrowly used): sourceRunId/input_media (provenance).
- C: none — nothing observed is both available and persist-worthy
  without a decision.
- D (lost): pattern, style, subcategory (past name), overall confidence.
- E/F: pattern/style activation (decision + migration-or-sidecar).
- G (remain analysis-only): needs_review, per-run confidence display,
  pattern/style until ordered.
- Recommendation: **no C-06 implementation now.** Everything safely
  consumable is already live; the rest needs vocab + weight + owner
  calls. If ordered later: sidecar-first for pattern/style display
  richness (no migration), columns + locked weight only for scoring —
  never both at once, never without the taxonomy.

## Control

- Files inspected: `vision_garment_adapter.py`, `value_objects.py`
  (`GarmentProfile`), `application/analysis.py` (`CreateGarmentRun`),
  `routers/analysis.py`, `garment_client/models.dart`,
  `add_wardrobe_item_screen.dart` (prefill/summary/imageRef/save),
  `wardrobe.py` (Add/Log/List/Summary) + `routers/wardrobe.py`,
  `models.py` (`WardrobeItems`), `repositories.py` (record/repo),
  `analysis_rules.py` (generation + all scoring terms),
  `ffo_compatibility.py`, FFO schemas, migrations
  0005/0006/0022/0023.
- Tests inspected (read-only, none run): `test_garment_analysis.py`,
  `wardrobe_garment_flow_test.dart`, `test_c02_fit.py`,
  `test_analysis_rules.py`. Baselines stand.
- C-02/C-03/C-04/C-05: untouched (zero edits outside the two docs).
  No migration required (audit only). Nothing committed or pushed.
  STOP — C-06 NOT implemented.
