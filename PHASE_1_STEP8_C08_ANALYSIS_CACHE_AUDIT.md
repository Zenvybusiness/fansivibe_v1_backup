# PHASE 1 STEP 8 — C-08 analysisCached / Analysis Blob Audit

> Status: AUDIT ONLY. No source/tests/schema/API/Flutter changes, no
> commit/push. Date (UTC): 2026-09-27. All findings read from current code.
> C-01…C-07 untouched. Prior claims VERIFIED (with one namespace warning).

## A. analysisCached write/read map

- WRITE (sole production): `your_analysis_screen.dart:82`
  (`_onContinueWithoutAccount` — guest path, no analysis ran) + test setup
  (`guest_phase2_test.dart:159`). Extra key `'analysis_cached': true`
  forwarded in navigation maps (`your_analysis_screen.dart:88`,
  `create_account_screen.dart:229` — "maybe later" path, display only).
- STORAGE: `LocalStorage.analysisCached` ↔ SharedPreferences bool
  (`local_storage.dart:65-69`); `UserSession.analysisCached` mirror
  (`user_session.dart:66-70`, **zero callers**).
- READ: `first_time_home_screen.dart:60` + `first_time_light_path_home_
  screen.dart:62` (`_hasScannedOutfit`); `home_screen.dart:179`
  (`_hasAnalysis` onboarding-done signal) + `:144` (diagnostics map);
  `profile_screen.dart:280` (color-achievement OR-clause).
- CONSUMER: first-time vs established gating + achievement/display copy.
  No ranking, scoring, polling, retry, save, or generation reader.

## B. Actual semantics

**Photo-capture/onboarding-taken — NOT analysis proof.** Set exactly where
no analysis ran (guest continue / maybe-later). Name is misleading; value
is load-bearing for first-time gating. Classification: **A (valid as a
photo-taken flag) + D (rename candidate, never a silent meaning change).**

## C. analysisResult/blob map

- `LocalStorage.analysisResult` getter (`local_storage.dart:89-94`) read
  ONLY by profile DNA fallbacks (`profile_screen.dart:309-329`, all
  null-safe `??` chains) — always null in production.
- Setter (`:103-110`) is `@Deprecated` with **zero callers** (verified:
  no `LocalStorage.analysisResult =` hit repo-wide) — dead, kept only as
  a key-clear.
- WARNING — separate namespace, do NOT conflate: `OutfitAnalysisScreen.
  analysisResult` (route `extra`, in-memory, live) is unrelated to the
  dead local blob.
- Backend/wire: **zero hits** for `analysis_cached`/`analysis_result`
  under `backend/app` — purely Flutter-local, never persisted server-side.
- Classification: **B (dead state) + E (safe removal candidate).**

## D. Authoritative analysis state (already exists — reuse it)

`analysis_runs.status` CHECK `pending/completed/failed`
(`models.py:179`) + `result` JSONB snapshot + `style_profile` writes on
completion (`application/analysis.py:154+`). Poll clients
(`GarmentClient`/`OutfitScanClient`, 30×600ms) already decide
completed/failed/result-available from run state. "Analysis completed
successfully" = run `completed` — no new flag, blob, or state machine
needed. No new analysis-storage system.

## E–G. Dependencies

- Flutter decisions today: photo-exists (in-memory bytes, not the flag);
  run/poll/continue/reuse (run state + `onboardingComplete`); first-time
  gating (the ONLY analysisCached consumer class). Nothing else branches
  on it.
- API: none (no schema/DTO/router reference). Database/storage: none
  (SharedPreferences bool + dead string-list key; no columns, no tables).
- Dead/duplicate: blob setter + getter (dead); `UserSession` mirror (dead);
  no duplication of run state anywhere.

## H–J. Safety, decisions, path

- Breaking risk: redefining/removing the flag without replacing its
  first-time-gating reads breaks guest onboarding routing; garment
  polling, retry, outfit generation, and C-04 do NOT depend on it.
- Product decisions (all small): 1. rename to `photoCaptured`-class
  (copy + read updates, zero behavior); 2. delete dead setter/getter
  (callers already null-safe); 3. keep as-is (documented, zero risk).
  No new field (A/B/C questions): run state covers completion, the flag
  covers photo-taken, the blob covers nothing — answer: keep A, delete
  the blob, add nothing.
- Safest path: (i) remove dead setter + getter (profile fallbacks
  already handle null), (ii) optionally rename the flag with all reads,
  (iii) never treat it as analysis proof. No migration (local prefs
  only), no renames on the wire (nothing exposed), no behavior change.

## Control

- Tests inspected (read-only, none run): `guest_phase2_test.dart:159`
  (flag setup), `your_analysis_screen_test.dart`, photo-capture suites,
  profile suites. Baselines stand.
- C-02…C-07: untouched (zero edits outside the two docs). Migration:
  none required. Nothing committed or pushed. STOP — C-08 NOT implemented.
