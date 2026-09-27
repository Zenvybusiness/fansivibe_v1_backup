# PHASE 1 STEP 5 — C-05 Feedback Locked Contract

> Status: LOCKED (owner-approved 2026-09-27). CONTRACT ONLY — no source/
> tests/schema/API/Flutter/ranking changes, no commit/push. Audit:
> `PHASE_1_STEP5_C05_FEEDBACK_AUDIT.md` (stands unchanged; no addendum
> needed). C-01…C-04 untouched.

## Locked semantics

1. **LIKE = outfit-level positive evidence.** The user positively evaluated
   the recommended look. It does NOT like every garment in the outfit, does
   NOT modify wardrobe-item preference, does NOT modify C-03
   `preferredItemIds`, and stays distinct from save/favorite.
   Source event: existing `feedback_events` rows. **Ranking weight:
   UNASSIGNED.**
2. **DISLIKE = outfit-level negative evidence.** The user negatively
   evaluated the recommended look. It does NOT permanently blacklist the
   outfit, does NOT mark every garment disliked, does NOT alter C-03, and
   stays distinct from skip. Source event: existing `feedback_events` rows.
   Decay/recency policy: NOT YET IMPLEMENTED. **Ranking weight: UNASSIGNED.**
3. **SKIP = "not interested right now", distinct from dislike. DOES NOT
   EXIST — NO IMPLEMENTATION.** A future Skip contract requires: event
   type, producer, persistence, dedup/idempotency, scope, expiration/decay,
   and consumption semantics.
4. **WEAR = behavioral evidence, not explicit preference.** wear ≠ save,
   like, favorite, or `preferredItemIds`. The existing wear ledger
   (`wardrobe_wear_events/groups`) remains the canonical wear history. **No
   ranking score derived yet.**
5. **SHARE = dormant/no-op ("coming soon").** No preference signal is
   derived from share. No implementation.
6. **No C-03 derivation, no double counting.** Liked, favorite, saved, and
   worn items MUST NEVER flow into `preferredItemIds`; C-03 stays
   explicitly user-selected only. preferredItemIds, favorites, saves,
   likes, dislikes, and wear remain independent signals.

## Ranking rule

No new feedback weights are approved. LIKE / DISLIKE / WEAR / SKIP / SHARE
weight = not assigned. The 0–100 formula is unchanged: palette +5, fit +5,
preference +15, favorite +15, compatibility budget and tie-break untouched.

## Persistence preserved (no new events, no migration)

`feedback_events` (#35, idempotent) stays the like/dislike source;
`saved_looks` + `look_saved` stay the save source; the wear ledger stays
the wear source. Save remains the only feedback with live recommendation
effect (ForYou +0.03, score counts).

## Future work (not this step)

Assigning any weight, dislike decay/recency, the Skip contract, and any
wear-derived scoring each need a separate implementation contract. None
are approved here.
