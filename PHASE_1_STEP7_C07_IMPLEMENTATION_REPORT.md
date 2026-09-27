# PHASE 1 STEP 7 — C-07 Implementation Report (Option A)

> Executed 2026-09-27. Backend-only. History event, zero recommendation
> effect. C-02…C-06 untouched. No commit/push.

## What was built

`item_added` = "a wardrobe item was successfully persisted as a
server-owned row." One append-only `learning_signals` row per successful
`POST /v1/wardrobe/items`, written post-commit. No weight, no ranking
read, no C-03 derivation; like/favorite/save/wear semantics untouched.

## Files changed

- `backend/alembic/versions/0024_item_added_signal_type.py` (new) — seeds
  `('item_added', 'Wardrobe item added', 5)` (`ON CONFLICT DO NOTHING`,
  0008/0015 precedent); downgrade deletes only that code. Head is now 0024.
- `backend/app/application/wardrobe.py` — `AddWardrobeItem` takes optional
  `signals` (default None = exact pre-C-07 behavior); on success emits one
  `insert_look_saved(signal_type="item_added", label=<name>,
  context={"wardrobe_item_id": <uuid>})` + commit in a separate unit AFTER
  the item commit (TRX-7 style); signal-write failure rolls back only the
  signal unit. Failures/422s raise before reaching the emit. Updates
  untouched (no signal surface). Aspired docstring now true.
- `backend/app/api/routers/wardrobe.py` — passes
  `LearningSignalRepositorySQL(db)`; response contract unchanged.
- Tests: new `backend/tests/test_c07_item_added.py` (10: single emit with
  exact type/label/context; DB-failure and validation-failure emit
  nothing; `signals=None` preserves legacy; update path has no surface;
  append-only retry semantics; writer contract + scoring signatures
  pinned signal-free; PG-gated seed/downgrade round-trip). Required
  baseline maintenance: `test_db_session.py` seed list + `test_c02_fit.py`
  head assertion now include 0024.

## Validation

- New: 9 pass / 1 PG-skip (sqlite env; PG suites skip by design).
- Neighbors (C-02/C-03/scoring/use-case/db): 279 pass / 27 PG-skip.
- Full backend: 977 pass / 416 skip / 3 fail + 6 collection-errors — the
  Step-3 baseline class (psycopg blocked, no PG; sqlite-override
  artifacts: 2× trending seed 500s, 1× soak PG-pool API) + 9 new passes.
- Flutter: untouched by this step; C-04 regression suites re-ran green
  (garment flow + add-item + outfit api, 51/51). Analyze n/a (no Flutter
  changes).

## Control

- C-02 (palette/fit/gate), C-03 (field/caps), C-04 (save→UUID→Build),
  C-05 (feedback persistence/semantics): all re-verified green, zero
  behavior change. C-06 untouched. Guest `local-*` path never reaches the
  server writer (Flutter-side only). No new event system, no ML, no
  refactor. Database change = one seed row. Nothing committed or pushed.
