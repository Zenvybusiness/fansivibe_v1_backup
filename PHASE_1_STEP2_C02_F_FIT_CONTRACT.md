# C-02-F FIT — Proposed Contract (NOT implemented)

> Status: OWNER DECISION: PENDING. Documentation + repository analysis only. No taxonomy created,
> no column added, no code/schema/API/ranking change. Date (UTC): 2026-09-27.

## Verified existing facts (read-only)
- `GarmentProfile.fit` (`domain/value_objects.py:94-103`): free-form observed string or None;
  None = "not clearly visible", never a guess; mapping onto controlled vocab happens at save (user-confirmed).
- Vision extraction (`ai/vision_garment_adapter.py:189-220`): `fit` via `_normalize_text` (nullable);
  run `confidence` 0–1; below `LOW_CONFIDENCE_FLOOR = 0.35` (`vision_appearance_adapter.py:66`) the whole
  run fails (`low_confidence`); `needs_review = True` when category/color/material missing OR
  confidence < 0.6 (`:204-208`); result contract validated (`validate_result`, `:222-254`).
- FFO fit documentation (controlled vocabulary SOURCE, not a live mapping): `fit.schema.json`
  x-values `compression/fitted/regular/relaxed/loose/oversized`; term docs `term-slim-fit` (close to body),
  `term-relaxed-fit` (roomy with ease), `term-regular-fit`; garment docs carry `fit` payloads
  (e.g. wide-leg jeans → relaxed, dark-denim-jeans → slim).
- Sidecar storage: `WardrobeItems.image_ref` JSONB nullable (`models.py:440`); write path accepts
  caller `imageRef` (`routers/wardrobe.py:168-179`); read passthrough (`:62`); NO first-class fit column
  exists on the row (`category_id`/`color_id`/`material_id` only).
- Fit-related ranking/scoring: NONE — no fit term, filter, or points exist anywhere in
  `analysis_rules.py` scoring or `generate_outfit_candidates`.
- Fit is NEVER inferred from prose anywhere in backend (verified: `body_fit` at `outfits.py:256` echoes
  the request id only).

## Proposed fit-evidence rule (smallest deterministic — NOT implemented)
- Usable fit evidence = sidecar/vision `fit` string that (a) comes from a run with confidence ≥ 0.6
  (the existing review floor — proposed, owner to confirm), AND (b) maps onto the frozen request-id map
  below; anything else = missing (neutral, never a confirmed match).
- Request-id map (to freeze, not created): `slim`/`relaxed`/`tailored` → FFO fit names
  (slim→{slim,fitted,compression}, relaxed→{relaxed,loose,oversized}, tailored→{regular,fitted…} —
  CANDIDATE reading only, NOT selected; `tailored` has no exact FFO name and needs an explicit ruling).

## Contract answers
1. Supported values: `slim`, `relaxed`, `tailored` (existing request ids).
2. Source: vision/sidecar `fit` evidence only (never prose, never invented, never category-derived).
3. Confidence threshold: PROPOSED ≥ 0.6 (existing `needs_review` floor); 0.35 is run-survival, NOT
   evidence-usability. Owner to confirm.
4. Fit missing: neutral — contributes nothing, blocks nothing.
5. Fit low-confidence (< threshold or `needs_review` on fit grounds): treated as missing.
6. Hard constraint or ranking signal: PROPOSED ranking signal (evidence is sparse; hard filtering would
   204 ordinary wardrobes and contradicts honest degradation).
7. Requested fit with no matching garments: all candidates neutral on the term; recommendation proceeds;
   explanation states fit was noted but no confirmed-fit pieces exist.
8. Explanation proof: cite `sourceRunId` + confidence + observed string per matched member (provenance R-1);
   no proof → no fit claim in prose (re-ground `body_fit`, currently unconditional at `outfits.py:256`).
9. Migration: NO (sidecar only; first-class column explicitly OUT per instruction).
10. API changes: NO (request field exists).
11. New ranking weights: YES — one evidence-gated sub-term + weight, owner-approved.

OWNER DECISION: C-02-F = LOCKED (owner-approved 2026-09-27)

Locked contract:
1. Fit is a deterministic EVIDENCE-GATED RANKING SIGNAL (not a hard filter; mismatch never auto-removes).
2. Evidence = existing `GarmentProfile.fit` + sidecar `image_ref` only; existing representation, no new column.
3. Threshold LOCKED: confidence >= 0.6 (existing `needs_review` floor). Missing or below-threshold → neutral.
4. Never fabricate fit from prose; never use LLM explanation as fit truth.
5. Request values use an explicit controlled mapping (proposed below); arbitrary strings are never ranking
   instructions.
6. Requires an explicit deterministic weight (see Weight contract below).
7. No migration; no API change unless existing validation cannot represent the controlled values.

### FIT REQUEST MAPPING FREEZE — IMPLEMENTATION INPUT, OWNER APPROVAL REQUIRED (not implemented)
Vocabulary source: `fit.schema.json` x-values {compression, fitted, regular, relaxed, loose, oversized} +
term docs (slim-fit, relaxed-fit, regular-fit; garment payloads). Only these values may appear.

| User request | Existing fit value | Supported? | Evidence source |
|---|---|---|---|
| slim | slim, fitted, compression | PROPOSED yes | FFO term-slim-fit / term-fitted-top / schema x-values, via sidecar `fit` + conf ≥ 0.6 |
| relaxed | relaxed, loose, oversized | PROPOSED yes | FFO term-relaxed-fit / term-wide-leg-jeans (relaxed) / schema x-values, via sidecar `fit` + conf ≥ 0.6 |
| tailored | (no exact FFO name; nearest: regular) | OPEN — owner ruling required | None until ruled; until then `tailored` = context-only, never scored |

No new fit categories invented. Unmapped/unknown sidecar strings = missing (neutral).

### WEIGHT CONTRACT
Fit weight: +5 — LOCKED (deterministic evidence-gated sub-term; budget Option A; NO multiplier).
Fit mapping version MUST be recorded during implementation (version pin + snapshot provenance).
No existing ranking code modified by this lock.
