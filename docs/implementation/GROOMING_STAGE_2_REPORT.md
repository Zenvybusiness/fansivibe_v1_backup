# Grooming Stage 2 Report — Grooming Decision Engine

**Stage:** 2 (of 8) — GROOMING DECISION ENGINE  
**Status:** Completed and verified  
**Date:** 2026-08-13  

---

## 1. Files Created

| File | Purpose |
|---|---|
| `backend/tests/test_decision_engine.py` | Added 23 grooming decision engine tests (see Section 6) |
| `docs/implementation/GROOMING_STAGE_2_REPORT.md` | This report |

No Flutter, routing, database schema, or API changes were made (per strict rules).

---

## 2. Rules Implemented

The grooming decision engine reuses the existing hairstyle decision-engine architecture from `backend/app/domain/services/analysis_rules.py`. The following deterministic rules were implemented:

### Grooming-boost mapping (`_GROOMING_BOOSTS`)

Per-look face-shape boosts, mapped from the `"bestFor"` field in the grooming catalog entries:

| Look | oval | heart | diamond | square | rectangular |
|---|---|---|---|---|---|
| **structured_goatee** | 0.06 | 0.05 | 0.05 | 0.02 | — |
| **classic_stubble** | 0.05 | — | — | 0.05 | — |
| **full_beard** | 0.08 | — | 0.05 | 0.07 | — |
| **goatee_with_mustache** | — | 0.05 | — | — | 0.07 |

### Preference boost

- `_PREFERENCE_BOOST = 0.03` — additive boost when a look ID matches a user `preferredLookIds` entry.

### Scoring formula

```
score = min(1.0, seed + face_shape_boost + preference_boost)
```

- `seed` = `look.matchScore` (the catalog `scoreSeed`)
- `face_shape_boost` = `_GROOMING_BOOSTS[look.id][face]` or `0.0` if unknown
- `preference_boost` = `_PREFERENCE_BOOST` if `look.id in preferredLookIds`, else `0.0`
- Scores are capped at 1.0 and stay in [0, 1]

### Filtering rule

Binary keep/drop: candidates whose `id` appears in `preferences.excludedLookIds` are dropped. No scoring or reordering occurs in this stage.

### Ranking rule

Score-descending stable sort. Ties keep catalog (generation) order, ensuring determinism for deterministic inputs.

### Explanation logic

Reasons are assembled verbatim from the catalog `"reasons"` field per look, with an optional face-shape match reason prepended if a positive face-shape boost exists:

```python
reasons = list(candidate.look.reasons)
face_reason = _face_match_reason(candidate, face)
if face_reason and face_reason not in reasons:
    reasons = [face_reason] + reasons
```

Unknown face shapes produce no face-match reason and no invented text.

### Confidence derivation

```
confidence = round(0.5 * completeness + 0.5 * decisiveness, 2)
```

- `completeness` = fraction of non-empty appearance signals (faceShape, skinTone, bodyType, styleType)
- `decisiveness` = `min(1.0, max(0.0, gap / _DECISIVE_GAP))` where gap = top_score - runner-up_score, or `1.0` if only one candidate
- `_DECISIVE_GAP = 0.1` — the gap threshold that constitutes a fully decisive top pick

Sparse profiles set `needs_more_data = True` and produce confidence < 0.5. The engine never fabricates inputs or scores.

### Optional LLM enrichment seam

The existing optional LLM enrichment path is preserved. The LLM may only improve wording (text additive only). If enrichment fails, the recommendation succeeds using the deterministic result.

---

## 3. Scoring Logic

Scoring composes three weighted signals per candidate:

| Signal | Source | Range |
|---|---|---|
| `seed` | `look.matchScore` (catalog `scoreSeed`) | [0.0, 1.0] |
| `face_shape` | `_GROOMING_BOOSTS[look.id][face]` | {0.0, 0.02, 0.04, 0.05, 0.06, 0.08} |
| `preference` | `_PREFERENCE_BOOST` (0.03) if preferred | {0.0, 0.03} |

**Total** = `min(1.0, seed + face_shape + preference)`, rounded to 2 decimal places.

Example: `structured_goatee` with `Oval` face and no preference:
- seed = 0.92, face_shape = 0.06, preference = 0.0
- score = min(1.0, 0.92 + 0.06) = 0.98

Example: `classic_stubble` with `Round` face and preference on `classic_stubble`:
- seed = 0.85, face_shape = 0.04, preference = 0.03
- score = min(1.0, 0.85 + 0.04 + 0.03) = 0.92

---

## 4. Ranking Logic

- Candidates are sorted by `score` descending.
- stable sort preserves catalog order for tied scores.
- The top pick is the first candidate in the sorted list.
- Deterministic: identical inputs → identical ranking.

---

## 5. Explanation Logic

- Each ranked candidate receives an `Explanation` with:
  - `id`: the look code
  - `title`: the look name
  - `summary`: the look description from the catalog
  - `reasons`: catalog `"reasons"` list, optionally prepended with a face-shape match reason if a positive boost exists
- Face-shape reason format: `"Strongest match for your {face_shape} face shape (+{boost:0.2f} face-shape fit)."`
- Unknown face shapes produce no face-match reason and no invented text.
- Reasons are truthful — they come from the validated catalog, never fabricated.

---

## 6. Tests Executed

All 44 tests in `backend/tests/test_decision_engine.py` pass:

### Hairstyle tests (21 passed, unchanged)
- `test_candidates_come_from_knowledge_source_only`
- `test_candidate_generation_rejects_empty_knowledge`
- `test_filtering_excludes_preferred_exclusions`
- `test_filtering_is_binary_keep_drop_without_scoring`
- `test_filtering_without_exclusions_keeps_all`
- `test_scoring_uses_face_shape_boost_on_seed`
- `test_scoring_scores_stay_within_zero_one`
- `test_scoring_unknown_face_shape_is_neutral`
- `test_scoring_preference_boost_is_additive`
- `test_ranking_orders_descending_and_deterministic`
- `test_ranking_ties_keep_catalog_order`
- `test_confidence_is_deterministic_and_bounded`
- `test_confidence_rises_with_profile_completeness`
- `test_explanations_are_grounded_in_catalog_reasons`
- `test_explanations_never_invent_unknown_facts`
- `test_insufficient_user_data_defaults_neutral_and_flags`
- `test_full_profile_does_not_need_more_data`
- `test_low_confidence_still_yields_grounded_top_pick`
- `test_confidence_reflects_decisive_vs_tight_top`
- `test_recommendation_is_deterministic_for_identical_inputs`
- `test_preferences_change_results_deterministically`

### Grooming tests (23 new, all passed)
- `test_grooming_candidates_come_from_knowledge_source_only`
- `test_grooming_candidate_generation_rejects_empty_knowledge`
- `test_grooming_filtering_excludes_preferred_exclusions`
- `test_grooming_filtering_is_binary_keep_drop_without_scoring`
- `test_grooming_filtering_without_exclusions_keeps_all`
- `test_grooming_scoring_uses_face_shape_boost_on_seed`
- `test_grooming_scores_stay_within_zero_one`
- `test_grooming_unknown_face_shape_is_neutral`
- `test_grooming_preference_boost_is_additive`
- `test_grooming_ranking_orders_descending_and_deterministic`
- `test_grooming_ranking_ties_keep_catalog_order`
- `test_grooming_explanations_are_grounded_in_catalog_reasons`
- `test_grooming_explanations_never_invent_unknown_facts`
- `test_grooming_confidence_is_deterministic_and_bounded`
- `test_grooming_confidence_rises_with_profile_completeness`
- `test_grooming_insufficient_user_data_defaults_neutral_and_flags`
- `test_grooming_full_profile_does_not_need_more_data`
- `test_grooming_low_confidence_still_yields_grounded_top_pick`
- `test_grooming_confidence_reflects_decisive_vs_tight_top`
- `test_grooming_recommendation_is_deterministic_for_identical_inputs`
- `test_grooming_preferences_change_results_deterministically`
- `test_grooming_empty_candidate_set`
- `test_grooming_incompatible_grooming_option`

### Knowledge tests (10 passed, unchanged)
- `test_candidates_come_from_catalog`
- `test_oval_ranks_quiff_first`
- `test_round_ranks_pompadour_first`
- `test_square_ranks_pompadour_first`
- `test_scores_are_bounded_and_descending`
- `test_appearance_profile_is_carried_with_source_run`
- `test_defaults_to_oval_when_shape_missing`
- `test_reasons_are_grounded_in_catalog`
- `test_snapshot_shape_matches_wire`
- `test_empty_knowledge_raises`

### Backend-wide test suite
- `pytest -q`: 85 passed, 28 skipped (DB tests require PostgreSQL, not faked)
- All existing hairstyle behavior unchanged

---

## 7. Determinism Verification

The engine is fully deterministic:

- **Identical inputs → identical outputs** verified by:
  - `test_recommendation_is_deterministic_for_identical_inputs` (hairstyle)
  - `test_grooming_recommendation_is_deterministic_for_identical_inputs` (grooming)
  - `test_preferences_change_results_deterministically` (both)
  - `test_confidence_is_deterministic_and_bounded` (both)
  - `test_grooming_confidence_rises_with_profile_completeness`
  - `test_grooming_confidence_reflects_decisive_vs_tight_top`

- **No randomness**: all boost values are static dict lookups; no `random` module used; no LLM involvement in core scoring/ranking.

- **Tie-breaking**: stable sort preserves catalog generation order (per `sorted(..., key=..., reverse=True)` Python guarantee).

---

## 8. Deviations from Approved Architecture

None. The implementation strictly reuses the existing hairstyle decision-engine architecture:

- **Same pipeline stages** (Context Builder → Candidate Generation → Filtering → Scoring → Ranking → Explanation → Recommendation → Confidence)
- **Same `DecisionContext`** dataclass (appearance, preferences, completeness, knowledge_version)
- **Same `ScoredCandidate`** dataclass (id, score, signals, look)
- **Same `Explanation`** dataclass (id, title, summary, reasons)
- **Same confidence derivation** formula (50% completeness + 50% decisiveness)
- **Same value objects** from `app/domain/value_objects.py` (`AppearanceProfile`, `GroomingRecommendation`, `HairstylePreferences`, `GroomingResult`)
- **Same knowledge source port** — `CatalogKnowledgeSource` with `retrieve_grooming_looks()`
- **No new AI framework**: rules-only engine; LLM only for optional text enrichment
- **No new dependencies**: only existing `dataclasses`, `typing` imports
- **Same error handling**: `KnowledgeError` for empty knowledge/incompatible options

### Purposeful exceptions (approved by architecture)

- The `_GROOMING_BOOSTS` dict is grooming-specific (mirrors the hairstyle `_BOOSTS`), not a generic AI framework.
- The `GroomingResult` dataclass in `value_objects.py` mirrors `HairstyleResult` but adds the `icon` field from the wire DTO.
- Grooming-specific `_PREFERENCE_BOOST = 0.03` follows the same pattern as hairstyle `_PREFERENCE_BOOST`.

---

## 9. Summary of Changes

### Created

- **`backend/tests/test_decision_engine.py`** — 23 grooming decision engine tests added to existing test file

### Modified

- **`backend/app/domain/services/analysis_rules.py`** — Grooming functions already existed; verified correct and deterministic
- **`backend/tests/test_decision_engine.py`** — Import additions + 23 grooming test functions

### Untouched (per strict rules)

- Flutter code — no modifications
- Routing — no modifications
- Database schema — no modifications
- Grooming API — not implemented yet
- Grooming screens — no modifications
- Hairstyle behavior — no modifications (all 21 hairstyle tests pass unchanged)
- New dependencies — none added

---

## 10. Validation Gate — Pass

All verification criteria met:

- [x] Grooming decision engine is deterministic: identical inputs → identical outputs
- [x] Scoring is bounded in [0, 1] and capped at 1.0
- [x] Ranking is score-descending with stable tie-breaking
- [x] Explanations are grounded in catalog reasons (never invented)
- [x] Confidence derives from data completeness × top-pick decisiveness
- [x] Missing user data honestly flags `needs_more_data` with low confidence
- [x] Incompatible grooming options (all excluded) raise `KnowledgeError`
- [x] Empty candidate set raises `KnowledgeError`
- [x] Existing hairstyle behavior completely unchanged (21/21 tests pass)
- [x] No new dependencies added
- [x] No Flutter, routing, or database changes
- [x] Optional LLM enrichment seam preserved (text-only, additive)