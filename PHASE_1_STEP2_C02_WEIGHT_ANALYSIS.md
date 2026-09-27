# C-02 Ranking Weight Analysis

> Status: ANALYSIS ONLY. No source/ranking/schema/API/test change, no weights chosen finally,
> no commit/push. Date (UTC): 2026-09-27. All line refs = `backend/app/domain/services/analysis_rules.py`
> unless noted. Nothing below modifies the locked C-02-P/F/M contracts (gate 0.6, neutral-defaults,
> no-filter, no-mood-ranking all preserved).

## Existing Ranking Scale
- Budget 0–100, composed by `compose_candidate_score` (`:1259-1284`): compatibility 0–70 +
  preference 0–15 + favorite 0–15. Each component CLAMPED (`max(0, min(max))`, NaN→0, non-numeric→0);
  negative sub-terms can only pull compatibility toward the 0 floor, never below.
- Compatibility sub-terms (`:1476-1483`): coverage +8/category (5 cats → max 40); color +10/−10;
  material +5; season +5/−5; formality +5; occasion +5. Max 40+10+5+5+5+5 = 70 ✓ (budget exact).
- Preference: +5/item, cap 15 (`:1117-1119`, `:1232-1242`; Step 11 mechanism ×100). Favorite: +5/item,
  cap 15 (`:1226-1229`, `:1245-1256`). Both 0 on all live paths today (frozenset; favorites real).
- Hard constraints vs soft signals: HARD = skeleton legality + tops+bottoms mandatory + 25-cap +
  lexical representatives (`generate_outfit_candidates`, `:1410-1462`, zero scoring inside).
  EVERYTHING else is a soft signal. Palette/fit enter as soft signals per lock (never hard).
- Final: winner `score` → `match_score = round(score/100, 4)` (`application/outfits.py:232`).
- Tie-break (`rank_outfit_candidates`, `:1311-1325`): score desc → item-count desc → canonical ID tuple
  asc. Fully deterministic; no randomness. `seed` only selects among ranked (selector, not a score input).
- Weights are MODULE CONSTANTS, not configuration (`:1214` "not configurable; no config infrastructure").
  No feature flags anywhere on this path.

## Existing Signals
| Existing signal | Current contribution | Type | Weight/range | Source |
|---|---|---|---|---|
| Coverage | +8 per distinct filled category | soft, structural | 0–40 | `:1517-1519` |
| Color harmony/conflict | +10 all-pairs-neutral / −10 any bright–bright / 0 if <2 known | soft | −10…+10 | `:1522-1536`, `:866-874` |
| Material consistency | +5 all-known-natural else 0 | soft | 0–5 | `:1539-1549` |
| Season consistency/conflict | +5 intersect / −5 disjoint / 0 if <2 informative | soft | −5…+5 | `:1552-1568` |
| Formality consistency | +5 single register else 0 | soft | 0–5 | `:1571-1582` |
| Occasion match | +5 one requested occasion suits every member else 0 | soft | 0–5 | `:1585-1601` |
| Preference (saved-taste) | +5/item, cap 15 | soft | 0–15 | `:1117-1142`, `:1232-1242` |
| Favorite | +5/item, cap 15 | soft | 0–15 | `:1245-1256` |
| Generation legality | tops+bottoms mandatory, skeletons, caps | HARD | n/a | `:1410-1462` |

Representative winner band (5-category full coverage, typical wardrobe): compatibility ≈ 40 + color(±10)
+ material(0/5) + season(±5) + formality(0/5) + occasion(0/5) → ≈ 25–70, commonly 45–60; plus
preference 0 + favorite 0–15 live. A +5 term tips close races; it takes ≥15 to rival the capped signals
and 40+ to rival coverage — i.e. single-attribute terms CANNOT dominate by construction.

## Palette Analysis
- Closest precedent: `_OCCASION_MATCH_BONUS = 5.0` — a single requested attribute suiting the candidate.
  Palette-match has identical shape (one request attribute × candidate members). Upper analog:
  `_COLOR_HARMONY_BONUS = 10.0` (pairwise color fact, stronger evidence than a request echo).
### Palette candidate weight range
- Minimum reasonable weight: +5 (occasion-analog; smallest existing positive match bonus).
- Maximum reasonable weight: +10 (color-analog; palette must not outrank demonstrated color harmony).
- Recommended initial value: +5.
- Reason: matches the single-request-attribute precedent exactly; fits inside the 70 compatibility budget
  without crowding (current max is exactly 70 — ADDING any term overflows the budget, so the budget or an
  existing term must be rebalanced at implementation: owner call, flagged not hidden); meaningful (decides
  ties and near-ties) yet structurally unable to dominate (≤½ of color swing, ≤⅛ of coverage).
- Status: OWNER APPROVAL REQUIRED (recommendation only; budget-rebalance decision rides with it).

## Fit Analysis
- Same scale, same precedents as palette (single requested attribute × per-member evidence).
- Extra condition: evidence-gated (sidecar `fit` + conf ≥ 0.6 LOCKED); missing/below → neutral 0.
### Fit candidate weight range
- Minimum reasonable weight: +5 (occasion-analog).
- Maximum reasonable weight: +10 (color-analog ceiling; fit evidence is weaker than persisted `color_id`,
  so exceeding the color bonus is unjustified).
- Recommended initial value: +5.
- Reason: symmetric with palette (both are one request attribute); the evidence gate already discounts
  fit relative to palette (fewer members contribute), so equal nominal weight yields smaller effective
  influence — honest without extra math.
- Status: OWNER APPROVAL REQUIRED.

## Confidence Treatment
- Locked contract: conf < 0.6 → neutral; conf ≥ 0.6 → eligible. (Unchanged by this analysis.)
- Repository evidence: NO confidence-multiplied term exists anywhere on this path. The 0.35 floor is
  run-survival, the 0.6 floor is review-routing — both are GATES, never multipliers. The scale comment
  (`:1199-1201`) deliberately separates 0–100 scores from 0–1 confidence "so the two can never be confused".
- Option A (fixed +5 after gate): COMPATIBLE — identical shape to every existing sub-term (fixed points
  or neutral). Recommended.
- Option B (confidence-weighted, e.g. +5 × conf): NOT compatible without new design — first of its kind;
  compresses +5 to +3.0…+5.0 over the eligible band (weakens the signal unevenly, rewards high-conf
  runs over informative ones, mixes the deliberately separated scales). Requires explicit approval +
  scale design; NOT proposed.
- Confidence treatment: GATE ONLY (0.6 LOCKED). No multiplier.

## Tailored Fit Investigation
- Searched: FFO docs/schemas/terms, fit enums/constants, garment adapters, value objects, serializers,
  tests, fixtures, seeds, frontend values (repo-wide `tailored` grep, 61 hits).
- Result: NO exact supported value. FFO fit names = {compression, fitted, regular, relaxed, loose,
  oversized} + term docs (slim, relaxed, regular). `tailored` occurs ONLY as: Flutter request id
  (`outfit_builder_mock_data.dart:91`) + Discover mock filter chip (`discover_mock_data.dart:905`,
  UI mock, no backend counterpart) + test fixtures echoing `bodyFit` prose + English prose
  ("tailored trousers/outfits" in catalog/FFO rationales/use_cases — descriptions, not values).
- LOCK: `tailored` = currently UNSUPPORTED. Not in the ranking map; no mapping fabricated; no taxonomy
  added; request stays neutral/context-only until a future owner-approved mapping exists.

## Ranking Domination Analysis
- Could a new +5 palette/fit term dominate? NO. Static budget proof: max single structural signal is
  coverage 40; max swing is color 20 (−10…+10); capped taste signals 15 each. A +5 fixed term is
  ⅛ of coverage, ¼ of color swing, ⅓ of a taste cap — it decides ties and ±5 races only.
- Representative: two candidates at 55 vs 52 (typical band): +5 palette-match flips the order (meaningful ✓);
  a 55 vs 40 gap is unmoved (no domination ✓). Missing-evidence candidates score 0 on the term, exactly
  as occasion-less candidates score 0 on `_occasion_points` today.
- Even at the +10 ceiling, the term stays below preference/favorite caps and far below coverage —
  domination is structurally impossible without touching existing weights (explicitly out of scope).

## Versioning / Provenance
- Ranking versions: NONE EXIST for the STEP-13 candidate path — no version constant, flag, or config
  (explicit "not configurable" at `:1214`). (FFO/reasoning version pins — `REASONING_CONTRACT_VERSION`,
  corpus digests — belong to a different subsystem and do not cover outfit ranking.)
- Existing provenance: winner `score` + `reasons` + `selected_*` echoes + `source_run_id` in snapshots.
- Smallest future home (NOT created): one module constant beside `_CANDIDATE_*_MAX` (e.g. a scoring-rules
  version string) + echo it in run-snapshot provenance, following the FFO pin pattern. Owner approves
  at implementation; nothing created in this step.

## Proposed Implementation Inputs
| Input | Value | Status |
|---|---|---|
| Palette weight | +5 (range +5…+10; budget-rebalance rides with it) | OWNER APPROVAL REQUIRED |
| Fit weight | +5 fixed after gate (range +5…+10; NO confidence multiplier) | OWNER APPROVAL REQUIRED |
| Fit confidence gate | 0.6 | LOCKED |
| Mood weight | N/A | LOCKED |
| Tailored mapping | unsupported — context-only, no map, no taxonomy | LOCKED |
| Ranking version pin | smallest home identified, not created | OWNER APPROVAL REQUIRED at implementation |
