# PHASE 1 STEP 5 — C-05 Feedback Audit (trace + classification)

> Status: AUDIT ONLY. No source/tests/schema/API/Flutter changes, no
> commit/push. Date (UTC): 2026-09-27. All findings read from current code.
> C-01…C-04 untouched. Verdict: **no implementation — every activation path
> needs a pending D-05 product decision and/or a new ranking weight.**

## End-to-end traces

### SAVE — class A (implemented + consumed; nothing to do)

- Flutter: builder/outfit screens save via `OutfitBuilderClient.saveOutfit`
  (`sourceContext: "outfit"`, fresh `Idempotency-Key`); wardrobe/event/today
  saves via their own M7 paths.
- API: `#42 POST /v1/outfits/saved` (+ `#23` looks-saved) → `SaveOutfit` →
  M7 `SaveRecommendation` (TRX-3: one `saved_looks` row + one `look_saved`
  signal; DEC-010 fail-closed IDs; replay→original, clash→409).
- Persistence: `saved_looks` row + `learning_signals{look_saved}`.
- Consumers (live): ForYou reorder (`application/discover.py:292-351`,
  +0.03 per saved catalog code, cap 1.0); score formula counts
  (`application/learning.py:144-152`, saved×2); `resolve_preferred_item_ids`
  reads outfit-save snapshots (C-03 resolver, production-uncalled by lock).
- ForYou: YES. AI Stylist ranking: indirectly (C-03 resolver is wired-empty
  by lock; favorite term is separate). No change proposed.

### LIKE / DISLIKE (#35) — class B persisted, consumption = E (decision required)

- Flutter producer: `saved_looks_screen.dart:304-305` (`onLike`/`onDislike` →
  `_reactToLook` → `FeedbackRepository.submitFeedback(rating:
  like|dislike, targetSavedLookId, fresh key)`; guest-gated, pending-guard,
  truthful retry; no local signal either way).
- API: `#35 POST /v1/feedback` → `SubmitRecommendationFeedback`
  (`application/feedback.py:55`): exactly one `feedback_events` row, no
  signal/activity/wear/save mutation (M10 sole-writer); targets fail closed
  (catalog code 404; saved-look UUID 422/404-not-403); `Idempotency-Key`
  required, replay→original, clash→409.
- Persistence: `feedback_events{rating,reason?,target,dup-key}`.
- Consumers: **ZERO**. Verified: no reader of the table outside
  insert + idempotency check (`feedback.py:86` only other touch);
  `discover.py` has no feedback reference; `learning.py:122-125`
  explicitly never reads feedback/wear/favorites into score math
  (DEC-019 §B); AI Stylist scorer has no feedback parameter.
- ForYou: NO. AI Stylist ranking: NO.
- Activation needs: D-05 Like-A/B/C + Dislike-A/B/C (scope, magnitude,
  decay/undo) + a new ranking weight (stop condition). NOT done here.

### SKIP — class D (stub/absent) + E (decision + new event required)

- Flutter: no skip control, no skip field (only unrelated "skip" words in
  comments). Backend: zero `skip` hits in application/routers. No storage,
  no event, no consumer. Needs owner call (Skip-A/B/C) first.

### WEAR — class B persisted + display-consumed; ranking use = E

- Flutter producer: `wardrobe_item_details_screen.dart:302 _logWear` →
  `logWear` seam (guest-gated); summary slot reads `getWearSummary`
  (display only, `mapWearSummaryToUi`).
- API: `POST /v1/wardrobe/wears` → `LogWearEvents`
  (`application/wardrobe.py:401`; cap 10 canonical IDs, idempotent
  groups, replay-safe) → `wardrobe_wear_events/groups` ledger;
  `GET wears` / `GET wear-summary` (W-9, counts/recency display).
- Consumers: `ListWearEvents`, `GetWearSummary` (history/display only).
  Ranking: NONE — `learning.py` excludes `worn` (DEC-012); discover and
  AI Stylist never read the ledger.
- ForYou: NO. AI Stylist ranking: NO.
- Activation needs: D-05 Wear-A/B/C (recency weight + save≠wear scoping)
  + a new ranking weight (stop condition). NOT done here.

### SHARE — class D (stub)

- Flutter: `look_details_screen.dart:415 _handleShare` → "Share feature
  coming soon" snackbar; no share path on outfit/hairstyle surfaces beyond
  documented stubs. Backend: no share endpoint/event/signal. Nothing to
  activate.

### Adjacent (already settled, not C-05 work)

- Assistant card interactions (`opened`/`navigated` → `suggestion_opened`/
  `assistant_navigation` signals, `application/assistant.py:23-24`) are
  evidence-only by DEC-019 §G; not score inputs. Untouched.
- C-03/C-05 double-count policy (preferred + favorite on one item) stays
  deferred — it needs the same D-05 scope call.

## Classification summary

| Signal | Class | Consumed today | Needs |
|---|---|---|---|
| save | A | ForYou +0.03, score counts | nothing |
| like/dislike | B → E | nowhere | D-05 scope + weight |
| skip | D → E | n/a | D-05 + new control/event |
| wear | B (ledger+display) → E for ranking | history/display | D-05 scope + weight |
| share | D | nowhere | product surface first |

## Product decisions required (exact)

1. Like: item- vs outfit-level meaning; personalization vs
   recommendation-only vs stored-only (Like-A/B/C).
2. Dislike: historical-only vs negative boost/suppression; scope (For You
   vs AI Stylist); accidental-tap/undo/decay policy (Dislike-A/B/C).
3. Skip: neutral vs weak-negative; needs a new control + event definition
   (Skip-A/B/C).
4. Wear: history-only vs recency-weighted ranking; save≠wear scoping
   (Wear-A/B/C).
5. Share: whether it exists at all before any preference meaning.
6. C-03 double-count: may one item collect preferred + favorite (+
   palette + fit)? (deferred here from C-03).

## Smallest implementable C-05

NONE without an owner call. Everything already-contracted (save) is
already live; every dormant signal needs D-05 semantics and/or a new
weight. Per STEP 6, implementation STOPS here. No migration is required
for the audit conclusion itself; any future activation needs weights
first, schema only for Skip-A (new event).

## Tests inspected (read-only, none run — nothing changed)

Backend: `test_m11_feedback_api.py`, `test_assistant_feedback_api.py`,
`test_wardrobe_wears_api.py`, `test_wardrobe_wear_summary*.py`,
`application/discover.py` boost + `learning.py` exclusion (cited, not
re-run). Flutter: `feedback_api_test.dart`, `feedback_screens_test.dart`,
`assistant_card_feedback_test.dart`, `wardrobe_wear_*_test.dart`. Known
baselines stand (backend 968/415/3+6-env; Flutter 1086/19-pre-existing).

## Change control

- Files changed: `PHASE_1_STEP5_C05_FEEDBACK_AUDIT.md` (new) +
  `CURRENT_STATE.md` (entry). No other files touched.
- Source/schema/migration changes: NONE. C-02/C-03/C-04 untouched
  (verified: no edits outside the two docs). C-06…C-10 untouched.
- Nothing committed or pushed. STOP — C-05 NOT implemented.
