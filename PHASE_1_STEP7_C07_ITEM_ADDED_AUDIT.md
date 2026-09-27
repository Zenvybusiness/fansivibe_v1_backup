# PHASE 1 STEP 7 — C-07 item_added Audit + Implementation Readiness

> Status: AUDIT ONLY. No source/tests/schema/API/Flutter changes, no
> commit/push. Date (UTC): 2026-09-27. All findings read from current code.
> C-01…C-06 untouched. Verdict: **meaningful but owner-gated — readiness
> plan below, STOP until the emit-vs-docfix call.**

## A. All wardrobe creation paths

| Path | Entry | Persisted? | Event emitted today |
|---|---|---|---|
| Normal add (authed) | Flutter add screen → `POST /v1/wardrobe/items` → `AddWardrobeItem` (`application/wardrobe.py:134`; create + commit; IntegrityError → vocab 422) | YES (row) | NONE |
| AI scan → save (authed) | same endpoint after garment prefill (C-04) | YES (row) | NONE |
| Edit/update | `PATCH /v1/wardrobe/items/{id}` → `UpdateWardrobeItem` | YES (mutation) | NONE (`item_updated` equally doc-only) |
| Import | none exists (no import path anywhere) | n/a | n/a |
| Guest/local | `LocalWardrobeRepository` (`local-<µs>` ids, on-device only) | device only | NONE (Flutter `LearningService` local record only, never synced) |

`wardrobe.py:127` docstring "Emits item_added" is the sole backend hit —
aspirational vs code (verified: `AddWardrobeItem` has no signal call).

## B. Existing events emitted (backend writers — exhaustive)

Single writer method: `LearningSignalRepository.insert_look_saved`
(`ports/repositories.py:743`, `signal_type` default `"look_saved"`; SQL impl
`infrastructure/db/repositories.py:429`, flush → FK-validated). Call sites:
`sustenances: saved_looks.py:193` (`look_saved`), `analysis.py:323/329`
(`analysis_updated` + `outfit_selected`), `analysis.py:509`
(`analysis_updated`), `assistant.py:74` (`suggestion_opened` /
`assistant_navigation`). Wardrobe create/update: zero. An `item_added`
emit would duplicate NO existing signal.

## C. Existing signal types (exact)

`signal_types` seed = exactly 5 codes: `look_saved`, `analysis_updated`
(0001:140-143), `outfit_selected` (0008), `suggestion_opened`,
`assistant_navigation` (0015). `item_added` ABSENT. FK:
`learning_signals.signal_type → signal_types.code RESTRICT`
(`models.py:261-263`) — an unseeded `item_added` insert 500s on flush,
stores nothing. No CHECK beyond label 1–200.

## D. item_added readers/consumers

NONE. No reader, aggregation, recommendation, analytics, or UI consumer
references the code: repo-wide backend hits = the one docstring; docs
hits (~20, WARDROBE_API/domain blueprints) describe intent, not behavior.
The only ledger reader in code is `list_recent_labels`
(`learning.py:167`, labels-only recents display) — type-blind, so a new
code would surface as a label string there and nowhere else. Flutter
`LearningService` keeps a local-only record (device truth, never synced).

## E. Redundant or meaningful

MEANINGFUL-but-gated (A-leaning, E-gated): "item created" is new ledger
information — no existing signal fires on wardrobe create, and the
append-only signal survives item deletion while the row does not (the
documented history-vs-state split). It is NOT redundant (B false), NOT
analytics-only-today (no analytics reader — C overstated), and NOT mere
residue: `WARDROBE_API.md:167` marks W-3 create + `item_added` signal
"Required". But DECISIONS + C-07 owner doc keep emit-vs-docfix PENDING,
so the call stays with the owner.

## F. Idempotency mechanism (reuse, no new system)

Wardrobe create is keyless (retry-after-commit can dup rows). Readiness:
emit in a **separate sequential unit AFTER the item commit** (TRX-7
precedent: item 201 stands even if the signal write fails) via the
existing `insert_look_saved(signal_type="item_added", label=<name 1–200>,
context={"wardrobe_item_id": <uuid>})` + commit. Retry-after-commit may
dup both row and signal — owner accepts, or orders keying (new UQ =
heavier schema change, NOT recommended for a history fact). No new
idempotency infrastructure either way.

## G. Guest/local boundary

Eligibility = successful **server** row commit (`AddWardrobeItem` return).
`local-*` ids never reach the server and MUST NEVER produce ledger rows;
guest→auth migration creates fresh server rows via the normal path (each
eligible once, at creation). Update path emits nothing (keep `item_updated`
out of scope).

## H. Migration requirement (documented, NOT written)

If ordered: one migration inserting `('item_added', <label>, <sort_order>)`
into `signal_types`, following 0008/0015 verbatim, with a `downgrade`
DELETEing the code. No existing rows affected; no FK/data migration; the
RESTRICT FK is the only enforcement. Unseeded emission 500s — seed MUST
land before any writer.

## I. Recommendation impact

NONE. Effect = ledger history + recents label. Score, ranking, ForYou,
and all C-contracts untouched. Any future recommendation consumer needs
a separate product decision + weight (stop condition).

## J. Product decision required

Exactly one: **emit (A)** — create the seed migration + one post-commit
writer call as above — vs **docfix (B)** — correct the ~20 doc claims +
`wardrobe.py:127` docstring to match code (zero runtime risk). No other
call is hiding here.

## K. Smallest implementation path (on owner A only)

1. Seed migration (0008/0015 precedent) → 2. one `insert_look_saved`
   call in `AddWardrobeItem` post-commit (+ commit/rollback handling) →
   3. writer test (add → signal row asserted; FK-negative unseeded test
   already covered by RESTRICT) → 4. neighbor suite rerun. Files:
   `backend/alembic/versions/00XX_item_added_signal_type.py`,
   `backend/app/application/wardrobe.py`, one test file. Nothing else.

## L–S. Control

- L. Tests inspected (read-only, none run): `test_db_session.py`
  (seed-presence), wardrobe add/update suites, learning recents suites.
  Baselines stand (backend 968/415/3+6-env; Flutter 1086/19-pre-existing).
- M–Q. C-02/C-03/C-04/C-05/C-06: untouched (zero edits outside the two
  docs); scoring untouched; C-08…C-10 untouched.
- R. Files changed: `PHASE_1_STEP7_C07_ITEM_ADDED_AUDIT.md` (new) +
  `CURRENT_STATE.md` (entry). No other files touched.
- S. No source/schema/migration changes. Nothing committed or pushed.
  STOP — C-07 NOT implemented (owner emit-vs-docfix call pending).
