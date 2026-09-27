# PHASE 1 STEP 2.2 — C-02 Implementation Readiness

> Status: READINESS ONLY. C-02 LOCKED (Option B, owner-approved 2026-09-27). No source modified,
> no tests, no migration, no API/ranking/schema change, no commit/push.
> Method: read-only verification of current code. All paths below are WHERE work would go, not changes.

## C-02 is LOCKED

Mood / Fit / Palette are genuine AI Stylist recommendation inputs. Implementation NOT started.

---

### Existing data supporting Mood
- Exact source: `newproject/flutter_application_1/lib/features/outfit_builder/data/outfit_builder_mock_data.dart:50-75`
  (`BuilderOption.moodOptions`: `minimal`/`bold`/`classic`/`eclectic`); picked at
  `build_outfit_screen.dart:190`, routed via `app_router.dart:262`, posted by `outfit_client.dart:67,75`
  as free-string `mood`; backend validated 1–200 chars (`api/schemas/outfits.py:34`,
  `application/outfits.py:326`), echoed at `outfits.py:263` (`selected_mood`).
- Current representation: request-scoped id string → prose echo. No persistence, no vocabulary table.
- Deterministic logic today: NO — zero mood data exists anywhere in backend repository (no mood column,
  table, taxonomy, or mapping; only the request echo + port doc `ports/repositories.py:244`).
- Gaps: needs an explicit deterministic mood→repo-data mapping designed and approved before mood may
  affect filtering/ranking (approved contract §6). Until then: normalized context in, explanation-only out.

### Existing data supporting Fit
- Exact source: same mock file `:77-96` (`fitOptions`: `slim`/`relaxed`/`tailored`); same Flutter path
  (`build_outfit_screen.dart:32,202-204`, generation screen, `outfit_client.dart`, `_validate_preference("fit")`
  at `application/outfits.py:327`); echoed into `body_fit` prose at `outfits.py:256`.
- Current representation: request-scoped id string → prose echo. `wardrobe_items` has NO fit column
  (`models.py:410-440`: `category_id`/`color_id`/`material_id`/`image_ref` only).
- Deterministic logic today: PARTIAL — reliable per-item fit data does NOT exist first-class, BUT fit
  evidence exists: vision garment adapter extracts `fit` (`ai/vision_garment_adapter.py:81,203-240`)
  into `GarmentProfile.fit` (`domain/value_objects.py:100`); FFO fit schema + fit term docs
  (`fit.schema.json` x-values compression…oversized; `term-slim-fit`/`term-relaxed-fit`/`term-regular-fit`;
  garment docs carrying `fit` payloads) provide a controlled vocabulary source.
- Gaps: no persisted per-item fit (sidecar/C-06 path only); `slim`/`relaxed`/`tailored` request ids need a
  documented map onto evidence values; confidence gating needed (vision fit is evidence, not truth).
  Unsupported fit values must never read as confirmed matches.

### Existing data supporting Palette
- Exact source: same mock file `:98-117` (`colorPaletteOptions`: `monochrome`/`warm`/`cool` with
  descriptions naming member colors); same Flutter path; validated (`outfits.py:328`); echoed into
  `color_harmony` prose at `outfits.py:250-255` (palette id + ACTUAL member `color` list — the only
  echo already grounded in real data).
- Current representation: request-scoped id string. `colors` vocab table EXISTS (FK-guarded codes,
  `models.py:363`); every wardrobe item carries a real `color_id`.
- Deterministic logic today: CLOSEST TO READY — deterministic `_color_points` sub-term already scores
  actual color harmony (`analysis_rules.py` scoring; `score_outfit_candidate:1612-1648` sums coverage,
  color, material, season, formality, occasion). What is MISSING: any `monochrome`/`warm`/`cool` →
  color-code-set mapping in backend (repo-wide: none). The mapping must be documented (approved contract),
  then palette becomes a color-set filter/boost over real `color_id`s.
- Gaps: palette→color-set mapping (design + approve); weight for the palette term (weight stop condition).

### Recommendation pipeline insertion point (existing locations, changes NOT made)
- Request entry: `backend/app/api/routers/outfits.py:120-122` (passes `mood`/`fit`/`colorPalette` through) +
  `api/schemas/outfits.py:26-35` (free-string validation — normalization belongs here or in use case).
- Normalization: `backend/app/application/outfits.py:325-328` (`_validate_preference` ×4 — extend from
  non-empty check to controlled-vocab mapping; NOT done now).
- UserContext: EXISTS at `backend/app/models/schemas.py:32` but serves the ASSISTANT path
  (`ai/engine.py`, `ai/tools.py`), NOT the derive path. `GenerateOutfit.__call__` (`outfits.py:350+`)
  takes occasion/mood/fit/color_palette + composes `occasions` (`:371-375`). Reuse rule: extend the
  existing request-context/occasions-composition pattern — do NOT create a parallel state object.
- Candidate generation: `generate_outfit_candidates` (`analysis_rules.py:1410-1462`) reads ONLY
  `.id`/`.category`, tops+bottoms mandatory, cap 25, zero scoring — palette/fit FILTERS would insert
  here (post-approval only).
- Hard constraints: skeleton compatibility + tops+bottoms mandatory (same function); no mood/fit/palette
  constraint exists.
- Ranking: `score_outfit_candidate` (`:1612-1648`) — new sub-terms (palette-set, fit-evidence, mood-map)
  would add here beside `_occasion_points` (post-approval only; weights frozen until then).
- Explanation: `_to_recommendation` (`outfits.py:181-265`) — prose MUST be re-grounded to the actual
  signals consumed (today it echoes request ids unconditionally; e.g. `:256` claims fit with no evidence).

### Required future implementation steps (smallest safe sequence; NOT started)
1. Freeze palette→color-set mapping (documented; consult `colors` table codes) — no code.
2. Freeze fit evidence rule (sidecar read + confidence gate + request-id map) — depends on C-06 direction.
3. Freeze mood mapping (explicit deterministic repo-supported map) or formally scope mood to
   context+explanation-only with honest copy.
4. Normalize at validation (`_validate_preference` → controlled values; unknown → 422 per existing taxonomy
   pattern, never silent drop).
5. Add sub-terms beside `_occasion_points` with owner-approved weights (one dimension at a time; assert
   ranked-order deltas in tests, never HTTP-200-only).
6. Re-ground `_to_recommendation` prose to consumed signals (evidence-conditional sentences; never claim
   matches without evidence).
7. Contract-drift + negative tests per dimension (unknown ids, empty wardrobe, no-evidence items,
   guest/authed, provider-down independence — ranking is zero-AI so provider matrix is trivially green).

### What CAN vs CANNOT be implemented deterministically today
- CAN: palette filtering/boosting IN PRINCIPLE as soon as the color-set map is frozen (all data present:
  `color_id` per item + `_color_points` pattern + `colors` vocab).
- CAN with evidence discipline: fit boosting ONLY for items with sidecar/vision fit evidence above a
  frozen confidence floor; everything else degrades to no-fit-signal (never a confirmed match).
- CANNOT: mood affecting ranking — no supporting data exists; any mood weight today would be fabrication.
  Mood enters as normalized context + honest explanation until step 3 above lands.
- CANNOT without owner weight approval: any new ranking sub-term (stop condition stands).
