# C-02 Compatibility Budget Rebalance Proposal

> Status: LOCKED — OPTION A (owner-approved 2026-09-27).
> BUDGET REBALANCE = LOCKED — OPTION A. No option implemented; no source/ranking/schema/API/test
> change; no commit/push. Date (UTC): 2026-09-27.
> Refs: `backend/app/domain/services/analysis_rules.py` (constants `:1476-1483`, clamp `:1270-1284`,
> budget comment `:1221-1229`).

## 1. Current compatibility budget (verified, max side)
| Component | Max | Min | Nature |
|---|---|---|---|
| Coverage (+8/filled category, 5 cats) | 40 | 0 | structural, strongest |
| Color harmony/conflict | +10 | −10 | pairwise gate |
| Material consistency | +5 | 0 | bonus-only |
| Season consistency/conflict | +5 | −5 | symmetric |
| Formality consistency | +5 | 0 | bonus-only |
| Occasion match | +5 | 0 | single-request-attribute precedent |
| **Total max** | **70** | — | exact budget |

TOTAL contract: compatibility 0–70 + preference 0–15 + favorite 0–15 = 0–100. Preference/favorite caps,
tie-break (score→count→canonical IDs), and hard constraints (generation) are FROZEN — not rebalanced.

## 2. New required signals (locked, not yet implemented)
- Palette: +5 max, soft signal, missing/unknown color neutral, `_color_points` UNCHANGED.
- Fit: +5 max, soft signal, gate conf ≥ 0.6 (else neutral), no multiplier, no column.
- Mood: 0. Tailored: unsupported.
- Naïve stacking (70+5+5=80) is FORBIDDEN — it silently rewrites the 0–100 contract. 10 points of
  existing maxima must move.

## 3. Candidate rebalance options (exact numbers, max side)
### Option A — Coverage 8→7/cat AND color bonus +10→+5 (penalty −10 kept)
- 35 + 5 + 5 + 5 + 5 + 5 + palette 5 + fit 5 = 70 ✓
- Effect: every signal survives with identical semantics; the two largest maxima trim modestly.
  Coverage stays dominant (35 vs 5s). Color keeps its −10 conflict teeth (penalty untouched → conflict
  behavior byte-identical); only the harmony reward halves.
- Behavior: near-ties shift toward palette/fit-matched candidates (INTENDED); coverage-differentiated
  races compress by ≤5; conflict/season-floor behavior unchanged (clamp + penalties intact).
- Cost: harmony reward asymmetry (+5/−10) — documented, no hidden change.

### Option B — Coverage 8→6/cat only (40→30)
- 30 + 10 + 5 + 5 + 5 + 5 + palette 5 + fit 5 = 70 ✓
- Effect: single-cut simplicity, but coverage — the strongest structural signal, mirrored from OI
  coverage preference — loses 25% of its voice. Fuller-vs-sparser races flatten noticeably; palette/fit
  relatively over-weighted vs today's hierarchy.
- Behavior: largest semantic drift of the viable options. NOT recommended.

### Option C — Color bonus +10→+5 AND occasion +5→+0 (partial, REJECTED)
- Frees 10 arithmetically but DELETES the occasion signal — the very precedent new terms mirror, and a
  live user-facing promise ("Matched for {occasion}"). Semantic destruction, not rebalancing. REJECTED.

### Forbidden (not options)
- Touching preference/favorite caps, the 0–100 total, tie-break, hard constraints, or `_color_points`
  internals — all frozen by prior locks.

## 4. Numerical effect summary
| | Coverage | Color max | Mat | Season max | Form | Occ | Pal | Fit | Total |
|---|---|---|---|---|---|---|---|---|---|
| Current | 40 | +10 | 5 | +5 | 5 | 5 | — | — | 70 |
| Option A (recommended) | 35 | +5 | 5 | +5 | 5 | 5 | 5 | 5 | 70 |
| Option B | 30 | +10 | 5 | +5 | 5 | 5 | 5 | 5 | 70 |

(Minima unchanged in all options: color −10, season −5, rest 0; clamp logic untouched.)

## 5. Behavioral consequences
- Both viable options only re-rank candidates within ±5..10 points of each other; landslides (≥15 gaps
  from coverage/preference/favorite) are immovable by the new terms — domination stays impossible.
- Option A additionally halves the harmony reward: all-neutral-pair candidates gain relatively vs
  harmonized ones (by 5). This is the single honest trade-off and is confined to close races.
- 204/empty behavior, retry/polling, idempotency, and explanation shapes are unaffected (score inputs
  only; no flow change).

## 6. Recommended option (repository architecture only)
**Option A.** Reason: preserves the EXISTENCE and ORDER of every current signal (no deletion, no
demotion below new terms), keeps coverage dominant (35 ≫ 5), keeps conflict penalties byte-identical
(smallest behavior delta), and pays the 10 points from the two largest maxima rather than gutting one
signal (B) or deleting a live promise (C). It mirrors the codebase's own convention: named constants,
no hidden multipliers, neutral-on-missing.

## 7. Final approved 0–70 compatibility formula (LOCKED — OPTION A, NOT implemented)
```
Coverage 35 (7/category)
Color 5 (bonus; penalty −10 kept, internals unchanged)
Material 5
Season 5 (min −5 kept)
Formality 5
Occasion 5
Palette 5 (neutral on missing/unknown/unassigned)
Fit 5 (neutral on missing/<0.6/unmapped; NO multiplier)
Compatibility total 70
```
Global contract unchanged: compatibility 0–70 + preference 0–15 + favorite 0–15 = 0–100.
Preference/favorite caps, tie-break, hard constraints: untouched.

## Confidence contract (LOCKED, restated)
`fit_confidence < 0.6 → fit signal = 0`; `≥ 0.6 → eligible for +5`. NEVER `5 × confidence`.
No multipliers anywhere on this path.

## Palette / Fit / Mood contracts (LOCKED, restated, unchanged this step)
- Palette +5 LOCKED (soft, never filter); sets: monochrome = neutral set; warm/cool/blush/stone
  per C-02-P doc (set freeze still approval-required as implementation input).
- Fit +5 LOCKED (soft, gate ≥ 0.6, missing/low/unmapped neutral, no LLM, no column, NO multiplier);
  slim/relaxed maps proposed, tailored unsupported (map freeze still approval-required).
- Mood 0, context/explanation only; future ranking needs a separate contract.
- Mood 0, context/explanation only; future ranking needs a separate contract.

## Versioning / provenance (smallest home, NOT created)
- No ranking version pin exists on the STEP-13 path (verified Step 2.5). Future home: one module constant
  beside `_CANDIDATE_*_MAX` (scoring-rules version covering weights + gate + palette/fit map versions),
  echoed in run-snapshot provenance beside existing `score`/`reasons`/`selected_*`/`source_run_id`.
  Creation awaits implementation approval.
