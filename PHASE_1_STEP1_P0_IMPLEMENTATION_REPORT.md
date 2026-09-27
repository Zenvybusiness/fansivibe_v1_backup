# Phase 1 Step 1 — P0-A Correctness Implementation Report

> Status: IMPLEMENTED (P0-A scope only). No product decisions implemented. No commit/push.
> Date (UTC): 2026-09-27. Plan source: `PHASE_1A_P0_CORRECTNESS_AND_CONTRACT_AUDIT.md` §§16,18.
> Method: smallest existing-pattern diffs; behavior changes limited to crash→honest-error and retry→stop.

---

# 1 Scope implemented

Parser safety (A1-01..04 + envelope verification) · outfit 404-stop polling · 401-path verification (outfit already correct; garment prompt-stop added) · analysisCached/blob doc cleanup + dead-setter deprecation · double-submit audit (all guards pre-exist → no code change) · 13 new tests. NOT implemented (per boundary): guest-anon/gates, mood/fit/palette, preferred_ids, Scan→Generate, feedback/wear learning, sidecar, item_added, analysis keys, merge/CAS, UserContext/engine/personalization, tables/migrations/APIs/providers.

# 2 Files changed

Lib (6): `outfit_scan/presentation/outfit_analysis_screen.dart` (2 lines) · `outfit_scan/data/outfit_scan_client.dart` (error getter) · `outfit_scan/presentation/outfit_processing_screen.dart` (404 branch + terminal-error block) · `wardrobe/data/garment_client.dart` (401 stop) · `grooming/data/grooming_client.dart` (date guards) · `shared/utils/local_storage.dart` (docs + deprecated setter).
Tests (5): `outfit_scan_client_test` (+5) · `outfit_analysis_screen_test` (+1) · `outfit_processing_screen_test` (+5 + scripted client/router) · `grooming_client_test` (+1) · `wardrobe_garment_flow_test` (+1).
Backend: NONE (no backend change required — all P0-A items were Flutter-side).

# 3 Exact behavior changes

1. int JSON confidence/matchScore now render (was: red-screen TypeError). 2. Failed-run Map error now surfaces typed reason/message (was: TypeError inside snackbar/debug path → generic poll-error). 3. Non-string grooming dates → null dates + honest null-run (was: throw → null via outer catch — same outcome, now explicit; my own new test caught that `as String?` alone still threw on int — fixed with `is` checks). 4. Outfit poll 404 → single GET → `Analysis not found…` + Back to Scan (was: ~30 retries → timeout). 5. Terminal-error block now shows for ANY stopped poll with a message (404/timeout; null-run output identical). 6. Garment poll 401 → immediate null (was: 30 s doomed loop; session already cleared via noteStatus). 7. Docs-only: analysisCached meaning + blob non-source-of-truth + deprecated setter. 8. Double-submit: verified `_isSubmitting/_saving/stage/once` guards on wardrobe-create, event-create, garment-analyze, outfit-submit, all saves — NO missing guard → NO change.

# 4 Parser changes

`(as num? ?? 0).toDouble()` ×2 (screen:33,251 — project convention from hairstyle_mock_data:92) · Map-safe `error` getter (mirror GarmentAnalysisRun.failureReason: reason → message → string-passthrough → null) · `is String` date guards (grooming_client:112-119) · reason lists UNCHANGED (outfit `toString` safe; hairstyle `as String` throw preserved as honest failure per A1-05) · OutfitRecommendation strict UNCHANGED (caller catches → failure; A1-06) · envelopes UNCHANGED (all four clients already try/catch decode → null/failure; proven by new malformed-body tests).

# 5 Polling changes

Outfit 404 branch (stop + message + Back; backoff/timeout/completed/failed untouched) · terminal-error display generalization (null-run identical; timeout now visible — previously spinner-forever with invisible message, same bug class) · garment 401 prompt-stop (copy unchanged — auth copy on add screen is a product-copy call, reported §13) · 401→entry on outfit VERIFIED pre-existing (no change) · hairstyle/grooming loops, intervals, timeouts (incl. justified grooming 12 s) UNCHANGED per §5 directive.

# 6 analysisCached/dead-code changes

Docs only + `@Deprecated(message)` setter (zero callers → zero warnings; analyze 0). No rename (churn/risk), no behavior change, no new source of truth, no guest change. Copy needing owner words: NONE surfaced (internal comments only) — no product-decision trigger.

# 7 Double-submit changes

NONE (code). Audit table: wardrobe `_isSubmitting` ✓ · event `_saving`+null-button ✓ · garment `_photoStage==analyzing` ✓ · outfit `_isUploading` ✓ · builder/daily/rec busy+once ✓ · saves idempotent server-side ✓. Genuine residual: network-retry duplicates on keyless POSTs (wardrobe/events/analyses) — documented, NOT changed (server keys = P0-C per boundary).

# 8 Tests added (13)

Client: Map-error reason/message/string/int shapes (outfit) · malformed `[]` → statusCode 0 · int run_id → null · grooming non-string dates → null dates. Widget: int confidence/matchScore/reason render · 404 stops (1 GET + error + Back) · completed forwards · failed-Map shows reason · 401→entry · 500 retries (2 GETs, spinner, dispose-cancel). Garment: 401 stops after 1 GET. All assert NO crash + honest path; no invented copy asserted (only implementation's own strings).

# 9 Tests run

`flutter analyze lib test` · 5-file targeted (55/55) · FULL `flutter test`. Backend suite NOT rerun (zero backend changes; §9 permits citing baseline).

# 10 Test results

Analyze: 0 issues (1 info `provide_deprecation_message` appeared mid-work → fixed with message form → clean). Targeted: 55/55 pass (incl. 13 new; 2 failures DURING work — both test-authoring bugs: settle-on-spinner, `as String?`-on-int — fixed, and the latter caught a real crash class). Full: **1076 pass / 19 fail** (+13 vs Phase 0's 1063, same 19).

# 11 Existing baseline failures

Identical file-set to Phase 0: auth_screens×5, clothes×6, for_you×4, guest_phase2×2, widget×2 — pre-existing, unrelated (no AI-stylist/builder/learning/conversion files). Backend Phase 0 baseline stands (915/537/3-CRLF-environmental) — untouched.

# 12 Unexpected regression

NONE. During-work notes (resolved, not regressions): test pumpAndSettle vs indeterminate spinner (test-only lesson: manual pumps for spinner states); misapplied edit hit wrong test block once (caught in diff review, corrected — final diff verified per-hunk §2).

# 13 Remaining P0 issues (NOT in approved scope — owner calls)

D-01…D-10 (Phase 1A §15) untouched · `item_added` seed-check pending · garment-401 user copy (vague `taking longer` on auth expiry — needs product words) · interim retry messages invisible during outfit retries (pre-existing display gap, preserved) · keyless-POST duplicates · P0 casts in files NOT touched (none known — inventory was exhaustive for analysis/builder/today/grooming paths).

# 14 Product decisions NOT implemented (explicit)

Guest-anon/gates · mood/fit/palette terms · preferred_ids · Scan→Generate · feedback/wear learning · sidecar reads · item_added emit · analysis keys · merge/CAS · UserContext/engine/personalization/ML · tables/migrations/APIs/providers/Ollama. Verified absent from diff (`git diff --stat`: 6 lib + 5 test files only; backend empty).
