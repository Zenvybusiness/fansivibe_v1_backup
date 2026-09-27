# C-02-F Fit — BLOCKER (implementation STOPPED, nothing changed)

> Status: BLOCKED → PERSISTENCE DECIDED (Option B locked, implementation NOT started).
> No source modified, no tests added, no migration created, no API/schema change,
> no commit/push. Date (UTC): 2026-09-27. Palette (C-02-P) implementation untouched and intact.

## Owner decision (locked 2026-09-27): OPTION B
Persist Fit and Fit Confidence as structured garment attributes using the existing garment
persistence/domain model. Fit +5 remains locked; confidence gate >= 0.60 remains locked; no
confidence multiplier; missing/unknown fit = 0; tailored unsupported; no LLM ranking; no hard
filtering. Rationale (locked): fit is a deterministic recommendation signal, must survive the
transient vision result, must be available at scoring without run-lookups or media-provenance
hiding, and must not depend on an LLM at ranking time. Do not invent/backfill/infer fit data.

## Locked fit data
- `fit`: structured garment attribute, nullable/optional where evidence absent.
- `fit_confidence`: numeric confidence (0–1) for the detected fit evidence, nullable/optional
  where unavailable.

## Proposed schema location (inspected, NOT created)
- Table `wardrobe_items` (created by `0006_wardrobe_items.py`; model `WardrobeItems`,
  `app/infrastructure/db/models.py:410-448`; chain head is `0022`, so the future migration slot
  is `0023` — NOT created in this step).
- Two nullable additive columns: `fit` (Text, NULL = absent) + `fit_confidence` (Float 0–1, NULL =
  unavailable). No FK (no fit vocab table exists; map stays frozen in code per C-02-F lock).
- Compatible because: sibling first-class scored attrs (`category_id`/`color_id`/`material_id`)
  already live on this row; nullable-additive leaves all existing rows NULL = missing = neutral
  (honest, no backfill); owner CASCADE + RESTRICT-vocab policy untouched; read path already loads
  full rows; optional-field-set update precedent exists (`material_set`/`image_ref_set`); nullable
  additive-column precedent exists (DEC-016 `event_time`).

## Implementation dependencies (all pending, in order)
1. Migration `0023` (columns + downgrade) — STOP + approval before DDL; 2. model fields;
3. garment write path (persist vision `fit`+`confidence` on save, user-confirmed like color);
4. read path (`_derive_outfit` namespace + `_candidate_members` carry fit/confidence);
5. `_fit_points` term (+5, gate ≥ 0.6, no multiplier) in compatibility sum (ceiling stays 70);
6. focused fit tests (21 proofs); 7. ranking regression rerun.

## Verdict
STOP per the locked C-02-F term and the step's STOP condition: the repository's existing fit
evidence does not contain the required confidence value at the scoring boundary, and no honest
plumbing exists without new behavior. Fabricating confidence or scoring a term that can never
fire would violate the lock. Nothing was implemented.

## Exact missing data path (verified read-only)
1. Scoring boundary: `score_outfit_candidate(candidate, items_by_id, ...)` reads per-member
   facts via `_candidate_members` (`analysis_rules.py:1486`): id / category / color / material /
   is_favorite ONLY. No fit. No confidence.
2. Derive path: `_derive_outfit` (`application/outfits.py:378-388`) builds the adapted namespace
   with exactly id/category/color/material/is_favorite from wardrobe records. `image_ref` is not
   read here at all.
3. Sidecar contents: the SOLE `image_ref` writer (`add_wardrobe_item_screen.dart:149-167`,
   `_buildImageRef`) persists media provenance ONLY
   (objectKey/mediaType/sizeBytes/contentHash/isGenerated/uploadedAt/sourceRunId). Zero fit,
   zero confidence in any persisted `image_ref` — reading it at scoring would yield nothing.
4. Transient evidence: `GarmentProfile.fit` + run `confidence` exist in the vision adapter result
   (`vision_garment_adapter.py:189-220`, floor 0.35, review gate 0.6) and possibly in
   `analysis_runs.result` snapshots — but NOTHING links them to wardrobe rows at scoring time.
   The only bridge (`image_ref.sourceRunId` → run result) has no reader; building one means
   per-item run lookups in the derive hot path = new data-access pattern + new behavior.
5. Schema: no fit column, no confidence column on `wardrobe_items` (verified Step 2.3); adding
   either is a migration (STOP + approval, not taken). Populating `image_ref` with fit/confidence
   at save = garment-sidecar redesign, explicitly OUT OF SCOPE for this step.

## Why not a partial implementation
- A `_fit_points` term wired to always-missing evidence scores 0 for every real wardrobe: theater,
  not a ranking signal; its 21-proof test plan could only pass vacuous neutrals while claiming a
  live signal. The lock forbids presenting absent evidence as a feature.
- Request-side `fit` (slim/relaxed/tailored, free-text validated) is present, but scoring it
  against no evidence would be ranking by request echo — the exact fabrication C-02 was locked
  to prevent. `tailored` stays unsupported regardless.

## Unblock options (decided: OPTION B locked above; A/C/D recorded and set aside)
A. Sidecar population (no migration): persist vision `fit` + `confidence` into `image_ref` at
   garment-save time (Flutter `_buildImageRef` + backend passthrough already `dict[str, Any]`),
   then read them in `_derive_outfit` with the locked ≥0.6 gate. Touches save path + Flutter —
   needs explicit approval (sidecar redesign is currently out of scope).
B. First-class columns (migration): `fit` + `fit_confidence` on `wardrobe_items` — migration STOP +
   full proposal required first.
C. Run-join (no schema): resolve `image_ref.sourceRunId` → `analysis_runs.result` at derive time —
   heaviest (N+1 run reads on the hot path, retention/caching questions); not recommended without
   perf design.
D. Keep C-02-F locked-but-dormant: fit stays context/explanation-only (like mood) until A/B/C lands.
   Fit budget +5 remains RESERVED; compatibility ceiling 70 holds (current realistic max 60).

## Compatibility budget note
With fit unimplemented, compatibility maxes at 35+5+5+5+5+5+5 = 65 in practice; the 70 ceiling
(Option A LOCKED) is unchanged and awaits the fit term. No rebalancing needed or performed.
