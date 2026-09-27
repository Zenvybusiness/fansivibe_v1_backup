# C-02-M MOOD — Proposed Contract (NOT implemented)

> Status: OWNER DECISION: PENDING. Documentation + repository analysis only. No taxonomy invented,
> no mapping invented, no weights, no code/schema/API change. Date (UTC): 2026-09-27.

## Verified repository fact
There is NO backend structured mood data: no mood table, column, vocabulary, taxonomy, mapping, term,
or score input. `mood` exists ONLY as (a) Flutter picker ids `minimal`/`bold`/`classic`/`eclectic`
(`outfit_builder_mock_data.dart:50-75`), (b) free-string request field 1–200 chars
(`api/schemas/outfits.py:34`, `_validate_preference("mood")` at `application/outfits.py:326`),
(c) verbatim echo `selected_mood` (`outfits.py:263`, port doc `ports/repositories.py:244`).

## Structured style/vibe candidates examined (all rejected as mood support)
- `style_profile.style_type`: free string from the appearance pipeline (`analysis_rules.py:83` reads it
  with `or ""`); face/hairstyle-derived, NOT a mood taxonomy — repurposing it would be silent invention.
- Occasion codes (9 canonical, DEC-014): occasion ≠ mood; already scored via `_occasion_points`.
- FFO `aesthetic`/`style` term docs and `styleDna` display projections: knowledge/display artifacts with
  no per-wardrobe-item attribution and no derive-path wiring — not usable without a content gate
  (DEC-014 #22 precedent: seed content requires separately supplied list).
- `GarmentProfile.style`: free-form vision string, unpersisted first-class — evidence for C-06, not a mood map.
- CONCLUSION: no existing representation can legitimately support mood ranking today.

## Proposed contract: MOOD = context/explanation-only until a taxonomy is approved
## Contract answers
1. Current mood values: `minimal`, `bold`, `classic`, `eclectic` (Flutter ids + labels/descriptions).
2. Controlled or arbitrary: ARBITRARY STRINGS backend-side (1–200 free text accepted; only the Flutter
   picker constrains them in practice).
3. Backend data representing them: NONE.
4. Ranking without fabrication: IMPOSSIBLE today — any mood weight/filter would invent semantics.
5. Missing data contract required: an explicitly approved structured mood/style taxonomy (codes +
   deterministic per-garment attribution rule or category/style→mood map) with seeded content;
   until then ranking/filtering on mood is FORBIDDEN.
6. Safe interim behavior: accept + validate non-empty (existing), carry as normalized context,
   echo honestly, ZERO effect on candidate generation / hard constraints / ranking / weights.
7. Explanation says: the requested vibe as user-stated context ("requested Minimal vibe") PLUS what the
   engine actually used (occasion, colors, coverage) — description of the decision, per C-02 lock §7.
8. The system must explicitly NOT claim: that any garment was measured as a mood, any mood-match score,
   mood-based filtering/exclusion, or that prose mentioning mood implies engine use.

OWNER DECISION: C-02-M = LOCKED — CONTEXT/EXPLANATION ONLY (owner-approved 2026-09-27)

## Closure verification (Step 2.12, 2026-09-27): CLOSED — repository already conforms
Repo-wide `mood` grep (backend/app): hits ONLY in request validation (`api/schemas/outfits.py:34`
non-empty; `application/outfits.py:326` `_validate_preference`), prose echo (`selected_mood` in
`_to_recommendation`, `routers/outfits.py:69`, port docs `ports/repositories.py:224,244`).
ZERO hits in `analysis_rules.py` scoring; `score_outfit_candidate` has no mood parameter;
no mood filter, weight, taxonomy, column, or LLM ranking exists. No violation found → NO source
change made. Doctors' orders preserved: ranking = 0, context/explanation only, no taxonomy,
no weighting, no hard filtering, no LLM ranking. CLOSED/LOCKED.

Locked contract: Mood flows validated-request-context → explanation/context ONLY. It MUST NOT enter
candidate filtering, generation, ranking score, hard constraints, or garment classification.
NOT approved as mood-ranking sources: style_type, occasions, FFO aesthetics, GarmentProfile.style.
Forbidden: arbitrary mood weights, LLM-based ranking, invented mood→garment mappings, fake taxonomy.
Future mood ranking needs a separate explicit contract (taxonomy, mapping, evidence, version, weights,
fallback, explanation semantics, negative tests).

### WEIGHT CONTRACT
Mood ranking weight: NOT APPLICABLE — MOOD IS NOT A RANKING SIGNAL.
