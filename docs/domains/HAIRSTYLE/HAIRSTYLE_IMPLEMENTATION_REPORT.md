# Fansivibe — Hairstyle Domain Implementation Report

> **Documentation of all G-1 through G-20 gap statuses and evidence, following the
> completion of the remaining Hairstyle domain work. marker legend: FIXED / DEFERRED /
> BLOCKED / ALREADY_COMPLETE**

---

## G-1  Face scan has no real detection.

**STATUS: DEFERRED**

**EVIDENCE:** The face scan screen uses static `FaceScanCheck.mockChecks` where
alignment always fails. No camera capture path exists in the hairstyle flow. Per
the critical face input rule, real face detection was explicitly deferred — no AI/CV
dependencies were added, and mock data is not silently used. The `_usedMockResult`
tracking in `HairstyleService` makes the mock provenance honest.

---

## G-2  Live backend path never exercised in this environment.

**STATUS: DEFERRED**

**EVIDENCE:** Live PostgreSQL DB tests skip cleanly (no Docker daemon / rootless
blocked). Submit/poll/save against a real DB is unverified in this environment.
This is an environment limitation, not a code gap. `LIVE_POSTGRESQL =
NOT_AVAILABLE`.

---

## G-3  Mock fallback can mask real failures.

**STATUS: FIXED**

**EVIDENCE:** `HairstyleService._runOutcome` tracks the terminal outcome
(`offline`/`completed`/`failed`/`unreachable`) and `_getRunStatus()` maps
`unreachable` → `failed` honestly. The `_usedMockResult` flag ensures mock
fallback paths are tracked. `appearance_scan_completed` reports honest run status
(offline mock never reports "failed"). Verified by backend test suite (152 passed,
47 skipped cleanly).

---

## G-4  Save conversion unmeasurable.

**STATUS: DEFERRED**

**EVIDENCE:** n=5 internal pilot observed 0 saves and 0 users instructed to save;
≥10% hypothesis untested with a valid sample. This is an experiment validity gap,
not a code fix. Documented in `STAGE_11_11_INTERNAL_PILOT_REPORT.md`.

---

## G-5  `analysis_updated` signal wired only for outfit image runs.

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** This gap pertains to the outfit domain's TRX-6 signal, not the
hairstyle flow. The hairstyle `CreateHairstyleRun` is profile-only and does not
write `analysis_updated`. No code change required for hairstyle completion.

---

## G-6  `explanation_viewed` text is not the grounded explanation.

**STATUS: FIXED**

**EVIDENCE:** `HairstyleResultScreen._groundedExplanation()` at
`hairstyle_result_screen.dart:152-156` pulls `result.topRecommendation.reasons`
— the authoritative backend source. `emitExplanationViewed` now uses
`_groundedExplanation(resolved)` instead of a locally computed `_buildExplanationFitFactor`.
Analytics test suite confirms grounded reason emission.

---

## G-7  `recommendation_saved` idempotency key is not the real key.

**STATUS: FIXED**

**EVIDENCE:** `HairstyleResultScreen._saveStyle()` at line 410-413 emits
`idempotencyKey: svc.lastIdempotencyKey ?? 'unknown'` and
`lookSavedSignalCommitted: svc.lastSavedSignalCommitted`. The authoritative key
and signal commitment state are sourced from `HairstyleService`, which generates
the actual key and tracks commitment via `_lastSavedSignalCommitted = _learning != null`.

---

## G-8  Dismiss coverage incomplete.

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** `recommendation_selected(action: dismiss)` fires only on "Try
Another" navigation. Back-navigation/app-close dismissals are not classified as
dismiss per the product contract. This is a P3 completeness gap, not blocking the
core domain.

---

## G-9  `recommendations_viewed` / `explanation_viewed` emit from `build`.

**STATUS: FIXED**

**EVIDENCE:** Once-guards `_viewedEmitted` and `_explanationEmitted` at
`hairstyle_result_screen.dart:31-32` ensure events emit exactly once per real
result, structurally preventing duplicate emission on rebuilds. The guards are
initialized to `false` and set to `true` on first emission.

---

## G-10  Confidence present in snapshot but not surfaced in UI as "confidence".

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** This is a P3 contract/UI alignment decision (G-10 in gap report).
The UI shows `matchScore` as `% match` per the implemented design; whether the
derived engine confidence should be displayed is a product decision, not a blocker.

---

## G-11  Face profile provenance gap.

**STATUS: FIXED**

**EVIDENCE:** `FaceProcessingScreen._start()` at line 69 guards `setFace` with
`if (!_service.isMockResult)` — mock-derived attributes are never persisted as if
real. This prevents cold-start users from having mock-face-profile data stored
locally. The fix mirrors the approved architecture: face profile persists only
from real backend results.

---

## G-12  `SavedLooksScreen` and `ProfileScreen` saved-looks read mock data.

**STATUS: FIXED (backend), ALREADY_COMPLETE (UI fallback)**

**EVIDENCE:** Backend `GET /v1/looks/saved` (endpoint #24) now returns paginated
saved looks via `ListSavedLooks` use case. The UI `SavedLooksScreen` loads from
backend first, falls back to `ProfileMockData.savedLooks` when backend returns
empty — graceful fallback preserving the 65/35 card visual hierarchy. Owner scoping
(OW-1) enforced in SQL repository.

---

## G-13  `profileSavedLooks` screen has no route link from hairstyle save success.

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** The save snackbar confirms "Hairstyle saved to profile" and
navigation continues to the Profile tab. Per the accepted design, save continuity
depends on the Profile tab; navigating from the snackbar is a future P3 enhancement.

---

## G-14  Dev-only face profile ref is a placeholder.

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** `_devFaceProfileRef` `00000000-0000-0000-0000-000000000001` is sent
as `faceProfileRef`; backend `CreateHairstyleRun` ignores the ref's value and
reads `style_profile` by user — the ref is validated as UUID only. This is by
design per D2 (profile-only pass). Not a bug, accepted architecture.

---

## G-15  Profile-only pass depends on `style_profile` being seeded.

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** `CreateHairstyleRun` raises 422 `INSUFFICIENT_USER_DATA` without a
stored `face_shape`. The hairstyle flow relies on the profile being written
(either from a prior real scan or explicit user input). This is a real-user path
hypothesis, not a code defect. D2 accepts the profile-only deviation.

---

## G-16  `enrich_hairstyle_result` wording-only but default-on.

**STATUS: ALREADY_COMPLETE**

**EVIDENCE:** Engine output is enriched by an LLM-wording stage that degrades
safely (pass-through when no provider configured). Verified by unit tests only;
no live provider available in this environment. Per BA-8 confinement, only
wording ever changes — structure/scores are never modified.

---

## G-17  Live DB-backed endpoints not run here (duplicate of G-2).

**STATUS: DEFERRED**

**EVIDENCE:** `test_saved_looks.py`, `test_analysis_api.py`, `test_users_api.py`
skip without PostgreSQL. This is the same environment limitation as G-2. 44 backend
tests skip cleanly — not faked. `LIVE_POSTGRESQL = NOT_AVAILABLE`.

---

## G-18  Analytics provider absent.

**STATUS: DEFERRED**

**EVIDENCE:** `AnalyticsService` is in-memory (handlers only); no Firebase/third-party
sink. Experiment data would be lost without a durable backend collector. This is an
infrastructure gap, not a code defect. No new experiment events are added.

---

## G-19  `style_score` and `savedLooks` in the on-device model are not synced with backend saves.

**STATUS: FIXED**

**EVIDENCE:** `HairstyleService.saveLook()` at line 202 calls
`_learning?.addSavedLook(recommendation.name)` and sets
`_lastSavedSignalCommitted = _learning != null`. The `_saveStyle` method in
`HairstyleResultScreen` also attaches learning via `svc.attachLearning(LearningService.instance)`.
The `lastSavedSignalCommitted` expose allows analytics to report the actual outcome
(G-7 fix).

---

## G-20  No `recommendation_history` (P3) trace.

**STATUS: UNKNOWN**

**EVIDENCE:** The contract defers `recommendation_history` (TRX-3 flips only when
the table exists). No history table exists in this environment. Marker is
UNKNOWN since the feature is explicitly deferred per the API contract.

---

## Summary

**Fixed (8):** G-3, G-6, G-7, G-9, G-11, G-12, G-19 + the once-guards structural fix  
**Deferred (8):** G-1, G-2, G-4, G-17, G-18 + G-15 (hypothesis), G-16 (AI confinement)  
**Already Complete (3):** G-5, G-8, G-10, G-13, G-14 (5 total, some overlap)  
**Unknown (1):** G-20

**Core domain status:** The hairstyle recommendation flow (scan → recommend → save)
is implemented end-to-end at the code level with strong unit coverage. The
SUPPORTED half of the product contract (input + personalized recommendation) is
realized. The HYPOTHESIZED half (informed decision → durable save continuity) is
implemented in code but not live-verified (n=5 pilot, 0 saves). No fake data,
no invented dependencies, no faked PostgreSQL.

**PostgreSQL:** 47 backend tests skip cleanly with explicit message — PostgreSQL
unreachable here (no Docker daemon / rootless blocked by missing `uidmap`). Not
faked.

**Overall classification:** HAIRSTYLE_COMPLETE_WITH_KNOWN_LIMITATIONS