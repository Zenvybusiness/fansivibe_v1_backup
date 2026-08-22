# Fansivibe — Hairstyle Domain Gap Report

> **EXTRACTION (documentation only).** Records gaps and conflicts between the
> product contract, accepted design docs, and the current truth of the Hairstyle
> domain. Nothing here is fixed; conflicts are documented with the governing
> authority. No code, DB, API, Flutter, UI, or test changes.

> **Source authority order** (used whenever sources disagree):
> Current Truth (live code + verified behavior) → Product Contract →
> API contracts → DB/domain contracts → Architecture decisions → production
> code → tests → design system → older planning → hypotheses.

> **Marker legend:** `UNKNOWN`, `UNTESTED`, `HYPOTHESIS`, `NOT LIVE-VERIFIED`,
> `IMPLEMENTED / EXECUTION UNVERIFIED`.

---

## 1. Conflict inventory (reconciled by authority order)

| # | Conflict | Sources disagreeing | Authority ruling | Resolution |
| --- | --- | --- | --- | --- |
| C-1 | **Confidence present or FUTURE?** | `HAIRSTYLE_RECOMMENDATION_API.md` §4.3 says confidence "NOT computed today (AI-0), absent from responses"; live `analysis_rules.py` derives `confidence` in `[0,1]` and `HairstyleResult.to_snapshot()` emits it | Current Truth (live code) wins | Confidence IS derived and emitted today; the API doc is stale on this point. |
| C-2 | **Flow "works end-to-end"?** | Older planning (STEP 6 era docs) say "not implemented"; `CURRENT_STATE.md` STEP 7 final validation says end-to-end COMPLETE with 384 Flutter + 85 backend tests | Current Truth (CURRENT_STATE + MVP audit) wins | Implemented; marker `IMPLEMENTED / EXECUTION UNVERIFIED` for live-DB paths only. |
| C-3 | **`setFace` cold-start** | `docs/architecture/APPEARANCE_DOMAIN_MODEL.md` says "`setFace` has no caller (verified)"; `FANSIVIBE_STAGE_11_13_FIX_CYCLE_REPORT.md` + commit `0ec42c0` fixed it (call site in `face_processing_screen.dart`) | Current Truth (commit + report) wins | Fix landed after the older doc; APPEARANCE_DOMAIN_MODEL §3.1/§8 is stale. |
| C-4 | **Card 65/35 rule** | `AGENTS.md`/MVP audit treat "65% image / 35% content" as a binding card rule; `docs/DESIGN_SYSTEM.md` does not state a numeric proportion | MVP audit (KEEP) + implemented `FansiHeroCard` agree; DESIGN_SYSTEM silent | Treat as OBSERVATION (implemented behavior), not an explicitly documented rule. |
| C-5 | **Analytics `recommendations_viewed` duplicate protection** | Stage 11.9 report §5 says "emitted once per render, `hasMock` prevents duplicates"; current `HairstyleResultScreen.build()` calls `emit` unconditionally in `build` (a rebuild could re-emit) | Current Truth (code) wins | Emission happens in `build` on every rebuild for real results; report's "once per render" claim is not structurally enforced. Documented, not fixed. |
| C-6 | **`explanation_viewed` truthfulness** | Contract says grounded explanation; UI computes a synthetic fit factor (`_buildExplanationFitFactor`) and emits text like "+6% face-shape fit" that is **not** the backend's grounded reason string | Product Contract (grounded, never invented) vs Current Truth (UI derives its own) | GAP — see G-6. The UI text is a locally derived approximation, not the engine's `_face_match_reason`. |
| C-7 | **Save analytics key** | `recommendation_saved` contract wants the idempotency key used; `HairstyleResultScreen` emits a **fresh** `DateTime.now().microsecondsSinceEpoch` that is not the key `HairstyleService.saveLook` actually sent | Product Contract (authoritative save result) vs Current Truth (approx key) | GAP — see G-7. |
| C-8 | **`recommendation_selected` dismiss semantics** | Contract: action = save or dismiss, don't classify navigation as dismiss; code only emits `dismiss` on "Try Another", not on back-nav | Current Truth narrower than contract | IMPLEMENTED but incomplete coverage; see G-8. |
| C-9 | **Face scan = real detection?** | `CURRENT_STATE.md`/MVP audit describe "face scan"; `FaceScanScreen` uses static `FaceScanCheck.mockChecks` (alignment always fails) | Current Truth wins | GAP — see G-1. The "scan" is a mock-gated screen, not a live detector. |
| C-10 | **Pilot evidence strength** | `STAGE_11_11_INTERNAL_PILOT_REPORT.md` n=5 internal; `FANSIVIBE_REAL_USER_EXPERIMENT.md` §12 wants ≥10% conversion, 200 users, 2–4 weeks | Current Truth (n=5) → not statistically significant | Do not overstate; classification `PILOT_SUCCESSFUL_WITH_ISSUES`; save conversion unmeasurable. |
| C-11 | **Grooming parity** | MVP audit says grooming POSTPONE, "not end-to-end validated"; code has full grooming engine + API | Current Truth (hairstyle is the priority) | Out of this domain's scope; recorded for context. |

---

## 2. Gap register (current truth vs. contract/design)

| # | Gap | Severity | Category | Evidence | Marker |
| --- | --- | --- | --- | --- | --- |
| G-1 | **Face scan has no real detection.** Checks (lighting/distance/alignment) are `FaceScanCheck.mockChecks`; alignment always fails; "Face Detection Active" badge is decorative. No camera capture path in the hairstyle flow. | P1 | Input fidelity | `hairstyle_mock_data.dart`; `face_scan_screen.dart` | IMPLEMENTED / EXECUTION UNVERIFIED (mock) |
| G-2 | **Live backend path never exercised in this environment.** Live PostgreSQL DB tests skip cleanly (no Docker daemon / rootless blocked); submit/poll/save against a real DB unverified here. | P2 | Verification | `STEP_7_FINAL_REPORT.md`; `CURRENT_STATE.md` (28 live tests skip) | NOT LIVE-VERIFIED |
| G-3 | **Mock fallback can mask real failures.** Backend `failed`/`unreachable`/422 → client returns null → mock result; `appearance_scan_completed` may report `run_status: failed` even when the user sees a normal mock result. | P2 | Observability / honesty | `hairstyle_service.dart` `_getRunStatus`; `hairstyle_client.dart` null-on-failure | IMPLEMENTED |
| G-4 | **Save conversion unmeasurable.** n=5 pilot observed **0 saves** and 0 users instructed to save; ≥10% hypothesis untested with a valid sample. | P1 | Experiment validity | `STAGE_11_11_INTERNAL_PILOT_REPORT.md`; `FANSIVIBE_REAL_USER_EXPERIMENT.md` §12 | HYPOTHESIS / NOT LIVE-VERIFIED |
| G-5 | **`analysis_updated` signal wired only for outfit image runs.** `CreateHairstyleRun` (profile-only) writes no learning signal; `CreateOutfitRun` writes `analysis_updated`; on-device `setFace` writes a local `FaceProfile` with no backend signal. | P2 | Memory/provenance | `app/application/analysis.py` (CreateOutfitRun Step 6 vs CreateHairstyleRun); `learning_service.dart` `setFace` | IMPLEMENTED (partial) |
| G-6 | **`explanation_viewed` text is not the grounded explanation.** UI computes `_buildExplanationFitFactor` (a clamp of matchScore) and formats "+N% face-shape fit"; backend's `_face_match_reason` ("+0.06 face-shape fit") only appears in the run snapshot, and only when a face-shape boost exists. The analytic `explanation_text` can disagree with the engine's grounded reasons. | P2 | Analytics truthfulness | `hairstyle_result_screen.dart` (lines 48–53, 139–142); `analysis_rules.py` `_face_match_reason`; `explanation_viewed` contract | IMPLEMENTED / HYPOTHESIS on accuracy |
| G-7 | **`recommendation_saved` idempotency key is not the real key.** Emitted key is a fresh timestamp; the actual key sent to `/v1/looks/saved` is generated inside `HairstyleService.saveLook` (timestamp + random). Contract wants the authoritative key. | P2 | Analytics correctness | `hairstyle_result_screen.dart` (line 391); `hairstyle_service.dart` (line 146) | IMPLEMENTED / HYPOTHESIS (values diverge) |
| G-8 | **Dismiss coverage incomplete.** `recommendation_selected(action: dismiss)` fires only on "Try Another"; back-navigation / app-close dismissals are not recorded. | P3 | Analytics completeness | `hairstyle_result_screen.dart` `_buildActions` | IMPLEMENTED (partial) |
| G-9 | **`recommendations_viewed` / `explanation_viewed` emit from `build`.** Not gated by a once-flag in code; report claims "once per render" but rebuilds can re-emit. Duplicate protection is not structural. | P3 | Analytics robustness | `hairstyle_result_screen.dart` `build()` lines 31–53 | UNTESTED (rebuild path) |
| G-10 | **Confidence present in snapshot but not surfaced in UI as "confidence".** UI shows `matchScore` as `% match`; engine's run-level `confidence` (completeness×decisiveness) is not displayed. Product contract names a "confidence score" — the shown number is the match score, not the derived confidence. | P3 | Contract/UI alignment | `hairstyle_result_screen.dart` uses `top.matchScore`; `analysis_rules.py` `derive_confidence` | IMPLEMENTED / HYPOTHESIS (which value the user should see) |
| G-11 | **Face profile provenance gap.** `FaceProcessingScreen` writes `FaceProfile` from the resolved result even when the result was the mock fallback — a mock-attribute profile can be persisted locally as if real. | P2 | Data integrity | `face_processing_screen.dart` `_start()` (setFace after any result); `hairstyle_service.dart` mock fallback | IMPLEMENTED / UNTESTED (mock-write path) |
| G-12 | **`SavedLooksScreen` and `ProfileScreen` saved-looks read mock data** (`ProfileMockData.savedLooks`), not the backend `saved_looks`/`GET /v1/users/me`. Save (POST) works; display is disconnected. | P2 | Journey continuity (principle F) | `lib/features/profile/presentation/saved_looks_screen.dart`; `profile_mocks.dart`; `STEP_9_CORE_USER_JOURNEY_REPORT.md` gap 6 | IMPLEMENTED (UI) / NOT LIVE-VERIFIED (read path) |
| G-13 | **`profileSavedLooks` screen has no route link from hairstyle save success** — the save snackbar does not navigate to Saved Looks; continuity depends on the Profile tab. | P3 | UX continuity | `hairstyle_result_screen.dart` (snackbar only) | HYPOTHESIS |
| G-14 | **Dev-only face profile ref is a placeholder.** `_devFaceProfileRef` `00000000-…-0001` sent as `faceProfileRef`; backend `CreateHairstyleRun` ignores the ref's value and reads `style_profile` by user — the ref is validated as UUID only. Not a real profile selector. | P2 | Contract fidelity | `hairstyle_service.dart` line 27; `analysis.py` `CreateHairstyleRun` | IMPLEMENTED / HYPOTHESIS (semantics) |
| G-15 | **Profile-only pass depends on `style_profile` being seeded.** `CreateHairstyleRun` raises 422 `INSUFFICIENT_USER_DATA` without a stored `face_shape`; the hairstyle flow relies on the outfit-scan TRX-6 projection or an explicit profile write, else the client falls back to mock. | P2 | Flow reliability | `app/application/analysis.py` (line 63–65); TRX-6 in `CreateOutfitRun` | IMPLEMENTED / HYPOTHESIS (real-user path) |
| G-16 | **`enrich_hairstyle_result` wording-only but default-on.** Engine output is enriched by an LLM-wording stage in the application layer; if no provider is configured it is a pass-through — verified only by unit tests, not live provider. | P3 | AI confinement (BA-8) | `app/application/enrichment.py`; `analysis.py` default `enrich` | IMPLEMENTED / EXECUTION UNVERIFIED |
| G-17 | **Live DB-backed endpoints not run here** (duplicate of G-2 for the save/API tests): `test_saved_looks.py`, `test_analysis_api.py`, `test_users_api.py` skip without PostgreSQL. | P2 | Verification | `CURRENT_STATE.md` (149 passed, 44 skipped) | NOT LIVE-VERIFIED |
| G-18 | **Analytics provider absent.** `AnalyticsService` is in-memory (handlers); no Firebase/third-party sink; events have no durable backend collector. Experiment data would be lost without a sink. | P2 | Experiment infrastructure | `analytics_service.dart`; Stage 11.9 §11.5 | IMPLEMENTED / UNTESTED (no sink) |
| G-19 | **`style_score` and `savedLooks` in the on-device model are not synced with backend saves.** `HairstyleService.saveLook` records a `look_saved` signal via `_learning` only when learning is attached (processing-screen-owned service attaches it; temp save services in result/details screens do not). | P2 | Memory continuity | `hairstyle_service.dart` `saveLook` (line 154–157); `hairstyle_result_screen.dart` `_saveStyle` (temp service) | IMPLEMENTED / HYPOTHESIS |
| G-20 | **No `recommendation_history` (P3) trace.** Shown/saved history table is conditional/gated; the contract defers it (TRX-3 flips only when the table exists). | P3 | History | `HAIRSTYLE_RECOMMENDATION_API.md` §8.7 | UNKNOWN (no table) |

---

## 3. What is confirmed working (no gap)

- Decision engine 7-stage pipeline, deterministic, unit-tested (18–21 tests).
- Knowledge catalog: 4 looks, read-time validation, KN-3 deprecated filter, `knowledge_version` (16 tests).
- Save TRX-3 all-or-nothing + idempotent replay/409 (9 use-case tests).
- Run lifecycle failure honesty: pipeline failure → `failed` run with PROCESSING_FAILURE, never stuck pending.
- Owner scoping (OW-1) 404-not-403 on run reads.
- Bearer dev auth seam (D-AUTH-1) with invalid-token 401.
- Analytics mock gate: mock fallback → no experiment events.
- Cold-start fix: `setFace` called after scan (commit `0ec42c0`).
- Wire DTOs mirror mock data + catalog (PR-3 stable ids).

---

## 4. Open decisions / follow-ups (carried forward, not resolved here)

1. **D-AUTH-1** — real auth provider; dev seam is Medium (0.7) placeholder.
2. **MS10.3** — media seal; face-image submission path (multipart → MediaRef) still gated; profile-only pass is the mounted path.
3. **`/v1/feedback` (#35)** — gated; save (`look_saved`) remains the slice's feedback signal.
4. **Real-user experiment** — ≥10% save conversion, 200 users, 2–4 weeks (`FANSIVIBE_REAL_USER_EXPERIMENT.md` §12); pilot was n=5 internal, not significant.
5. **Live PostgreSQL verification** — requires Docker daemon + rootless support (`uidmap`) unavailable here; 44 backend tests skip.
6. **Grooming** — implemented but POSTPONE per MVP audit; not end-to-end validated.
7. **`recommendation_history` (P3)** — shown/saved trace conditional.
8. **Confidence display** — whether the UI should show derived confidence vs. match score is a product decision (G-10).

---

## 5. Summary classification

| Area | Classification |
| --- | --- |
| Core loop (scan → recommend → save) | **IMPLEMENTED / EXECUTION UNVERIFIED** (live DB path not exercised here) |
| Decision engine + knowledge | IMPLEMENTED (unit-tested) |
| Save TRX-3 + idempotency | IMPLEMENTED (unit-tested; live DB skips) |
| Analytics six events + mock gate | IMPLEMENTED (tested) |
| Cold-start face-profile fix | IMPLEMENTED (commit `0ec42c0`) |
| Pilot evidence | n=5 internal, `PILOT_SUCCESSFUL_WITH_ISSUES`; conversion unmeasurable |
| Product contract SUPPORTED half | Realized (input + personalized recommendation) |
| Product contract HYPOTHESIZED half | Implemented in code; **NOT LIVE-VERIFIED** (informed decision → durable save continuity) |
| Real-world outcome claim | **Not made** (out of scope) |

**Overall:** the Hairstyle domain is **implemented end-to-end at the code level
with strong unit coverage**, and the SUPPORTED half of the product contract is
realized. The dominant gaps are verification (live PostgreSQL paths never run in
this environment), input fidelity (face scan is a static mock gate, not real
detection), experiment validity (n=5, 0 saves → conversion hypothesis untested),
and several analytics-fidelity items (explanation text and idempotency-key
accuracy are locally approximated rather than authoritative).
