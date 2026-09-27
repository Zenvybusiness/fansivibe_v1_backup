# PHASE 1 STEP 3 — C-03 preferred_item_ids Contract Audit

> Status: AUDIT ONLY. C-03 NOT locked, NOT implemented. No source/tests/schema/API/Flutter changes,
> no commit/push. Date (UTC): 2026-09-27. All findings read-only, cited to current code.
> C-02 untouched (verified: no C-02 file or constant in this investigation's scope).

## A. Every relevant definition
Three distinct namespaces — do NOT conflate:
1. `preferred_item_ids: Optional[FrozenSet[str]]` — wardrobe-item UUID set for OUTFIT candidate
   scoring (`analysis_rules.py:1133` `preference_contribution`, `:1233` `candidate_preference_points`,
   `:1612` `score_outfit_candidate`, `:1731/:1798` `compute_outfit_intelligence`, `:2019` read site;
   `ai/engine.py:107` `handle()` kwarg; `ffo_compatibility.py:93` projection input).
2. `HairstylePreferences.preferredLookIds: frozenset[str]` (`value_objects.py:62`) — CATALOG
   hairstyle/grooming look codes (e.g. `"classic_pompadour"`), scored +0.03 on the 0–1 hairstyle
   confidence (`analysis_rules.py:293-306`). Different IDs, different scale, different surface.
   NOT part of C-03's outfit question, recorded here only to prevent confusion.
3. `resolve_preferred_item_ids(*, saved_looks, user_id)` (`analysis_rules.py:1160-1192`) — builds
   namespace-1 sets from `saved_looks` rows. Tested (`test_analysis_use_case.py:1864+`), never
   called in production.

## B. Every producer/caller
- Flutter producers: NONE. Zero `preferredItemIds`/`preferred_item` references in `lib/` (verified).
  No picker, no request field, no DTO carries it.
- API/request schemas containing it: NONE. `OutfitGenerateRequest` has occasion/mood/fit/colorPalette
  only; `AssistantRequest` has messages + user only (`schemas.py:46-48`). There is NO wire field;
  `docs/` contains ZERO `preferred_item_ids` references (no product language anywhere).
- Backend producers: `resolve_preferred_item_ids` (exists, tested, UNCALLED in production).
- Production callers passing real IDs: NONE.
  - `application/outfits.py:392` (`GenerateOutfit`), `events.py:389`, `today.py:188`: literal
    `frozenset()` — documented in-module (`outfits.py:10-14`: "the preferred-item set stays empty
    (M8-C/M9 precedent — `resolve_preferred_item_ids` is never consulted here)").
  - `ai/engine.py:206-210, 464-468`: `frozenset(preferred_item_ids) if preferred_item_ids else
    frozenset()` — fed by `handle()` kwarg, which production `main.py:310` NEVER passes
    (passes only `preferred_occasions`). Always empty in production.
  - Tests are the ONLY callers with non-empty sets (mechanism coverage, never liveness).

## C. Every consumer (where it reaches ranking)
1. `score_outfit_candidate` → `candidate_preference_points` → `preference` sub-score (0–15) →
   `compose_candidate_score` → rank → select. Live in code, dead in production (empty input).
2. `compute_outfit_intelligence` → `preference_contribution` (+0.05/item, cap +0.15) added to the
   0–1 OI confidence (`:1806-1824`). Sole production caller `engine.py:286` receives the empty set.
3. `ffo_compatibility` → `user_preference` 0..1 projection (`round(pts/15, 2)`). Same empty input.
4. Effects when active: RANKING ONLY. Generation (`generate_outfit_candidates` reads id/category
   only), hard constraints (skeletons + tops+bottoms), tie-break (score→count→IDs), and explanations
   (no preferred-id prose exists) are all untouched by the mechanism.

## D. Actual identifier type
Wardrobe-item UUIDs (owner's `wardrobe_items.id`), canonicalized via `_canonical_item_id` (UUID
parse; non-UUID strings NEVER match). NOT garment/run IDs, NOT outfit IDs, NOT catalog codes
(those live in namespace A.2). Source: `snapshot.selectedItemIds` of `source_context == "outfit"`
saved-look rows (DEC-010 validation guarantees those are owned wardrobe UUIDs at save time).

## E. Current behavior (edge matrix — from code, all with empty production input = no-op)
- ID exists in candidate: +5/item (candidate scale) / +0.05 (OI confidence), caps apply, no stacking.
- ID absent from candidates: contributes 0 (set intersection).
- Foreign/other-user ID: can only match owner-scoped candidates → 0 in practice (see F).
- Duplicates: set semantics — never stack (`:1196-1197` tested).
- Empty list/None: 0, byte-identical baseline (`:1169-1177` tested).
- Very large list: linear set intersection over ≤25 candidates × ≤5 IDs; bounded by caps; no perf
  cliff (no DB per ID — the set is pre-resolved).

## F. Authorization behavior
No dedicated auth check exists on the IDs — and none is needed AS DESIGNED: matching happens
against the already owner-scoped candidate set (owner's wardrobe rows / owner's evaluated item).
A foreign ID cannot match and silently contributes 0. The RESOLVER is owner-scoped at the source
(`list_for_user`, OW-1; failures degrade to empty, never throw). Caveat for options below: any
option accepting CLIENT-SUPPLIED ids inherits this property only while candidates stay
owner-scoped — a future cross-user candidate source would need explicit validation (none exists).

## G. Existing scoring behavior (+5/cap vs the 100-point score)
- Candidate scale: `candidate_preference_points` = `preference_contribution × 100` → +5/item, cap 15,
  inside `preference` 0–15 of the 0–100 compose (`:1226-1242`). Independent of favorite (+5/item,
  cap 15, separate term — same candidate CAN collect both today if wired).
- OI confidence scale: +0.05/item, cap +0.15, inside the 0–1 STEP 7A formula (`:1806-1824`).
- Hairstyle scale (namespace A.2, for contrast): +0.03 flat per preferred catalog look, 0–1 scale.
- Today all three preference inputs read 0 in production (empty sets / empty Preferences).

## H. Product unknowns (owner must decide — NOT chosen here)
U-1. What SHOULD "preferred" mean: explicit per-request picks (A), favorites-derived (B),
  saved-taste automatic (C), or nothing — remove (D)?
U-2. Scope: AI Stylist generate only, or also assistant/event/today paths that share the scorer?
U-3. If explicit: where does the user pick (builder multi-select? which surfaces?), and is it a
  guarantee (filter) or a boost (ranking)?
U-4. Double-count policy: may one item collect preference + favorite + palette + fit simultaneously?
U-5. Explanation: must the response disclose which preferred items influenced the pick (AI-0 honesty
  currently has no preferred-id prose)?

## I. Plausible contract options (smallest supported by architecture; none selected)
### Option A — Explicit per-request picks (ranking boost)
- Soft (boost, not filter; hard-guarantee variant noted but NOT recommended — risks 204s).
- Generation: untouched. Ranking: existing +5/cap-15 term, no scoring change.
- API: YES (new optional request field, e.g. `preferredItemIds: UUID[]`, validated UUID + owner
  check at the M7/DEC-010 precedent). Flutter: YES (multi-select picker on builder).
- Auth: reuse owner-scoped candidate matching (F); request IDs validated as UUIDs, unknown/foreign
  → 0 or 404-per-field (decision). Scoring: NO change. Compatible: fully (call-sites + schema).
### Option B — Favorites-derived (automatic)
- Soft. Generation: untouched. Ranking: REUSES term but DOUBLE-COUNTS with the existing favorite
  term (+5/+5 stack on the same item) unless favorite is excluded when preferred fires (new rule).
- API: NO. Flutter: NO (implicit; explainability copy needed). Auth: none new.
- Scoring: NEEDS the anti-double-count rule (a real scoring change). Compatible with friction.
### Option C — Saved-taste automatic (wire existing resolver)
- Soft. Generation: untouched. Ranking: existing term, zero scoring change — smallest backend delta
  (replace 3 `frozenset()` call-sites with `resolve_preferred_item_ids(...)` results).
- API: NO. Flutter: NO. Auth: none (resolver already OW-1).
- Scoring: NO change. Compatible: fully. Caveat: changes event/today/outfit rankings the moment it
  lands (silent behavior shift for users with outfit saves — needs the U-2 scope call + disclosure).
### Option D — Remove/deprecate
- Zero behavior change (already inactive). Resolver + term + tests become dead code → remove or
  mark deprecated with liveness-proof tests. Kills A–C until reintroduced. Cheapest if taste stays
  count-based (DEC-019 §B).

## J. Dependencies per option
- A: needs C-05 scope (taste vs explicit), UUID validation precedent (M7), builder UI work; INFORMS
  U-3/U-5 (guarantee + disclosure wording).
- B: needs the double-count ruling FIRST (blocks); interacts with favorite term tests; needs
  explanation copy (implicit effect must be disclosed).
- C: needs U-2 scope + U-5 disclosure; no code dependency beyond call-sites; REVEALS the
  preference-vs-favorite overlap for saved favorited items in outfit saves.
- D: none; records the decision so the mechanism isn't half-revived later.
- All: independent of C-02 (no shared terms except the 70-budget ceiling — preference lives in its
  own 0–15 lane), C-06, C-07; orthogonal to C-09/C-10.

## Fewest-architectural-changes option (NOT a product selection)
Option C (3 call-site swaps, zero schema/API/UI/scoring/auth changes). Stated as effort fact only;
the silent-ranking-shift caveat (I.C) is exactly why effort ≠ decision.

## K–M. Confirmations
K. C-02 untouched: no C-02 file, constant, term, test, or doc edited in this step (verified via
  scope discipline; C-02-P/F implementations intact).
L. No source/schema/API changes: working tree holds only this audit doc + 3 status-doc edits below.
M. Nothing committed or pushed.
