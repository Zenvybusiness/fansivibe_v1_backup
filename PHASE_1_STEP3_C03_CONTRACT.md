# PHASE 1 STEP 3 — C-03 preferred_item_ids Locked Contract

> Status: LOCKED (owner-approved 2026-09-27). CONTRACT ONLY — nothing wired, no API/Flutter/
> ranking/source changes, no commit/push. Audit: `PHASE_1_STEP3_C03_PREFERRED_ITEM_IDS_AUDIT.md`
> (stands unchanged; no addendum needed). C-02 untouched.

## Exact contract
**`preferred_item_ids` is an explicit preference signal, not a learned preference signal.**
It represents EXPLICIT user-selected preferred wardrobe items. It is NOT: favorites-derived,
saved looks, implicit behavioral inference, palette/fit/mood preference, or
`HairstylePreferences.preferredLookIds` (catalog codes, separate namespace).

### FACT (current repository behavior — unchanged by this lock)
- Mechanism live in code, dead in production: candidate +5/item cap 15, OI +0.05/item cap 0.15.
- ALL production call sites pass empty (`outfits.py:392`, `events.py:389`, `today.py:188` literal
  `frozenset()`; `main.py:310` omits the engine kwarg). Flutter sends nothing. No wire field.
- Resolver `resolve_preferred_item_ids` tested, uncalled. Empty/None = byte-identical baseline.

### LOCKED rules
1. **Identifier:** `wardrobe_items` UUIDs only. UUID canonicalization stays; non-UUID never matches;
   duplicates deduplicated (set semantics, existing).
2. **Ownership/security:** resolve ONLY against the authenticated user's own wardrobe items (owner-scoped
   candidates — no separate auth subsystem; OW-1 fail-degrade preserved). Client-supplied IDs can never
   exert cross-user influence. Foreign/nonexistent IDs → NO preference contribution (degrade, NOT 404 —
   deliberate difference from the M7 save precedent: preference is advisory, saves are authoritative).
3. **Ranking:** candidate lane +5/item cap 15 UNCHANGED; 100-point budget UNCHANGED; tie-break UNCHANGED;
   NEVER a hard constraint; generation UNTOUCHED.
4. **OI lane:** +0.05/item cap 0.15 preserved independently; never merged into candidate ranking;
   the two scales stay separate.
5. **Production semantics:** still empty/no-op. NO wiring, NO Flutter UI, NO API fields, NO caller
   changes in this step.
6. **Favorite interaction:** NEVER derive from favorites; favorite term stays separate. Double-count
   policy (may one item collect preference + favorite + palette + fit?) DEFERRED to C-05.
7. **Explanations:** unchanged. Future responses MAY expose explicit preference as a reason (wording
   deferred; no LLM behavior invented).
8. **Large input:** caps bound all effects (15 / 0.15); no unbounded scoring. Validation ceiling is
   UNDECIDED — adjacent conventions only: wears per-action cap 10, candidate width 5, page bound 100.
   Owner picks the cap at implementation; nothing invented here.
9. **Empty input:** empty/null ≡ no preference (byte-identical baseline, tested).
10. **Compatibility:** palette +5, fit +5, mood 0, compatibility 70, preference 15, favorite 15,
    total 100 — ALL UNCHANGED.

### FUTURE IMPLEMENTATION (not this step)
- **Wire shape (proposed, from repo conventions):** `POST /v1/outfits/generate` gains optional
  `preferredItemIds?: UUID[]` (camelCase C-4; Pydantic UUID list; absent/null ≡ empty; `[]` ≡ empty;
  malformed → 422 per DEC-010 shape precedent; unknown/foreign → IGNORED to 0 per rule 2, not 404).
  Threaded request → `GenerateOutfit.derive_with_reason` → `_derive_outfit` → `score_outfit_candidate(
  ..., preferred_item_ids=frozenset(canonical))`. No new tables, no migration, no taxonomy.
- **Flutter (future):** builder multi-select over OWNED wardrobe UUIDs only; explicit user action per
  request (never implicit, never persisted as profile state without a separate decision).
- **Call sites eventually needing wiring decisions (NOT wired now):** `outfits.py:392` (from request
  field — primary); `events.py:389` + `today.py:188` (no request preference input exists — scope
  decision required: leave empty vs extend); `main.py:310` → `engine.handle()` kwarg (assistant path —
  resolve + pass-through decision required).
- **Tests at implementation:** UUID/foreign/malformed/empty/cap matrices; ranked-delta assertions
  (not HTTP-200-only); idempotency/retry (read-only derive — naturally safe); guest/authed.

### DEFERRED (explicitly not this step)
- Favorite double-count policy → C-05. Explanation wording → future (no LLM). Any learning/inference
  use of explicit picks → forbidden without a separate contract. Mood-style taxonomy analogies → none.
