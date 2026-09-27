# AI Stylist → Outfit Analysis — Complete OSI-Style Deep Audit (INVESTIGATION ONLY)

> Status: INVESTIGATION COMPLETE. No application source modified. No fixes, no refactoring, no APIs, no migrations, no installs, no commit/push.
> Date (UTC): 2026-09-27. Repo: `fansivibe_v1_backup` (Flutter `newproject/flutter_application_1`, backend `backend`).
> Method: current source as source of truth (spot-verified file:line). Builds on Domain 1 (Scan My Outfit) + Domain 2 (Garment Analysis) audits; new ground here: Generate/Build Outfit, Saved Looks, TodayLook save, learning-consumer analysis, guest-gate positions, doc-vs-code conflicts.
> Definitions: "Outfit Analysis" in this doc = the Scan My Outfit flow (`POST /v1/analysis/outfit` → `OutfitAnalysisScreen`). Garment Analysis (`POST /v1/analysis/garment`) is the separate M11 path — relations traced, not conflated.

Legend: GREEN connected/verified · YELLOW partial/questionable · RED broken/fake · GRAY not implemented · BLUE external/provider-blocked.
Classes: A connected · B partial · C disconnected-existing · D runtime-dep · E UI-without-backend · F data-not-consumed · G backend-not-consumed · H intentional-local · I unsupported.

---

# 1 Executive Summary

**Verdict (§2 scale): B — Appearance/hairstyle analysis (proven), with E (partially implemented) aspects.** `POST /v1/analysis/outfit` → `OllamaVisionAppearanceAdapter` (face_shape ONLY) → `recommend_hairstyle` → appearance/style-profile snapshot. It analyzes the FACE, not the outfit: no garment, color, pattern, material, fit, coordination, or occasion capability exists anywhere on this path (proof §6). The name "Outfit Analysis" is a mislabel inherited from stale docs (which describe `sections[]/detectedItems[]` that the code never produces — conflicts §19S).

What IS real (authed): capture/gallery → multipart upload → 202 run → exp-backoff poll → appearance chips + hairstyle recommendation → runs persisted + TRX-6 profile + 2 signals + styled-day. What is NOT real: `Save Profile` (snackbar-only, RED), `Share` (stub), Retake/Retry on capture+result, any garment/wardrobe/prefs read-back, any consumption of the stored signals, guest analysis (blocked BEFORE analysis at Flutter button + 401 behind it).

Guest answer: **CANNOT analyze, CANNOT see result, CANNOT save, CANNOT persist** — first gate is the Flutter button (`_submitSelected:258`), second is FastAPI 401. Intended behavior (analyze+see, gate-on-save) IS supportable without new architecture: the pipeline is user-agnostic until the `user_id` FK insert; supporting it needs a policy decision + an anonymous-run or deferred-save mechanism (evaluated §21 — the only item that is genuinely new, everything else is connection-only).

Biggest correctness items: untyped Flutter parse with two latent cast crashes (P0); `Save Profile` fake-success copy (P1); `item_added` signal documented but never emitted (P0-data); OpenAPI 413/503 declarations unreachable (P4); ~12 stale doc claims (P4).

# 2 Exact User Flow

```
USER → AI Stylist (/stylist) → tap Scan My Outfit hero [stylist_screen.dart:434 pushNamed(scanOutfit)] (BLUE nav, no guard)
→ SCAN-001 /stylist/scan-outfit [OutfitScanScreen: camera medium/jpeg rear-first | gallery 1024² | preview Image.memory]
→ [Analyze Photo] (bytes required) → guest? prompt+return (NO http) : OutfitScanClient.submitOutfitAnalysis (multipart `image`, Bearer, 30s)
→ 202 {run_id} → pushNamed(scanProcessing, extra: runId) | fail/null → snackbar, stay
→ SCAN-002 processing [runId ONLY; null → 'No run ID available', no poll] → poll GET /runs/{id} (3s base, ×2^ backoff cap 48s, 30 tries)
→ completed → pushNamed(scanAnalysis, extra: result-snapshot) | failed → inline + Back to Scan | 401 → /entry | timeout → honest msg
→ SCAN-003 /stylist/scan-outfit/processing/analysis [raw-Map parse: appearance/confidence/recommendations.top]
→ Save Profile (snackbar-only RED) | See Recommendations → /home/daily-outfit w/o context (YELLOW) | Share stub (GRAY) | Back (BLUE)
→ persistence ALREADY happened server-side at completion: analysis_runs completed + user_state TRX-6 + signals×2 + styled-day
```

# 3 Flutter Trace

- Screen: `features/outfit_scan/presentation/outfit_scan_screen.dart` (StatefulWidget+setState, `_CameraUiState` 6 states, lifecycle dispose/re-init), `outfit_processing_screen.dart` (runId-only, single-Timer backoff, mounted guards, dispose-cancel), `outfit_analysis_screen.dart` (621 lines, copies extra in initState, no didUpdateWidget; static `Analysis Details` placeholder :511-530; dead mock types in `outfit_scan_mock_data.dart`/`outfit_scan_widgets.dart` never parsed).
- Routes (`app_router.dart:206-235`, names `route_names.dart:25-27`): full paths `/stylist/scan-outfit[/processing[/analysis]]`; extras typed `String?`/`Map?`; null-run pushes from 4 sites (test/capture-fail/empty/guest) land on honest error.
- State: no Provider/Riverpod/Bloc (deps prove it); singletons `AuthSession/LocalStorage/SecureTokenStorage/guest_mode`.
- Per-button ACTION→CODE→SERVICE→HTTP→BACKEND→DB→FAILURE: §2 table + Domain 1 §3 (verified). Retake/Clear: ABSENT on SCAN-001 (RED vs wardrobe/hairstyle precedent); Save/Retry/Retake: ABSENT on SCAN-003 (RED); static Lighting/Framing/Posture checks hardcoded (YELLOW); `AI Analysis Active` badge display-only (BLUE).
- Save: zero HTTP/DB/`LocalStorage` writes in file (verified: no `addSavedLook|looks/saved|outfits/saved|LearningService` refs — grep empty). Share: snackbar only.

# 4 HTTP Trace

- `POST {base}/v1/analysis/outfit` multipart `image` (suffix-derived content-type; empty→client-null; NO size pre-check) · Bearer `effectiveToken('dev')` · 30s+30s · 202→`run_id`, else null (ALL codes collapse — B). `GET {base}/runs/{run_id}` same auth → 200 envelope else bare code / 0.
- Mismatches vs FastAPI/OpenAPI: OpenAPI declares 413+503 — backend NEVER raises either on this path (oversize→422; vision-fail→failed RUN). Contract docs claim `multipart (image + typed fields)` (`API_CONTRACT_RULES:527`) and `sections[]/detectedItems[]` result (`RECOMMENDATION_API:443`, `API_INVENTORY:875`, `SCAN_API:170`) — code takes image-only, returns appearance snapshot. 404/500 polled to exhaustion (garment path stops on 404 — inconsistency, B).

# 5 FastAPI Trace

`routers/analysis.py:195-229` (`def`, sync, no queue — 202 semantic) → `get_current_user_id` (`deps.py:58-85`, 401+`WWW-Authenticate`) → type+20MB validation (422, duplicated in use-case) → `CreateOutfitRun(runs, knowledge, OllamaVisionAppearanceAdapter [always injected], user_state, signals, days)` (`application/analysis.py:169-341`) → `read_image_bytes`+`build_media_ref` (SHA-256, bytes dropped) → `runs.create(outfit, vision-v1, provenance 1.1+1.0, pending)` → `port.analyze` → fail taxonomy → `recommend_hairstyle` (NO outfit recommender) → `complete(snapshot)`/`fail` (write-once `WHERE pending`) → TRX-6 5-key profile replace → 2 signals + styled-day, one commit → `202 {run_id}`. GET shared owner-scoped (foreign→404). No background/async worker exists (vs `BACKGROUND_JOB_ARCHITECTURE` async claims — conflict).

# 6 AI/Adapter Trace

`OllamaVisionGarmentAdapter` is NOT on this path (garment-only). Actual: `OllamaVisionAppearanceAdapter` (`ADAPTER_ID ollama-vision-v1`; `vision_appearance_adapter.py`): `POST {FANSIVIBE_VISION_HOST}/api/chat` (default `localhost:11434`), model `FANSIVIBE_VISION_MODEL` (default `llama3.2-vision`; deployment needs vision-capable override), 20s whole-client, temp 0, single attempt. Prompt: face ONLY → `{"face_shape","confidence"}` (6 labels + no_face/ambiguous). Deterministic: alias `rectangle→rectangular`, floor 0.35, transport mapping, bool-reject. Output: `AppearanceProfile(faceShape=measured, skinTone="", bodyType="", styleType="")` — other three EMPTY by design.
WHAT IT ANALYZES: face_shape ONLY. NOT analyzed: garments, colors, patterns, material, fit, silhouette, proportions, coordination, occasion, compatibility, body, accessories, shoes, overall style (each proven absent: prompt asks face-only; output hardcodes `""`; engine reads face_shape + completeness only). Failure → terminal `failed` + `details.reason` (6 reasons); kill-switch → `analyzer_unavailable`; no fallback shape, no retry.

# 7 Database Trace

| Data | Source | Stored Where | Consumer | Actually Used? |
|---|---|---|---|---|
| run row + input_media hash/meta | `CreateOutfitRun` | `analysis_runs` (pending→completed/failed, `outfit/vision-v1`) | `GET /runs[/{id}]` (owner-only; list omits result/error) | YES (history/poll) |
| result snapshot (appearance+recs) | engine | `analysis_runs.result` | forwarded to SCAN-003 (latest only); list hides it | PARTIAL (no history UI) |
| error+reason | adapter/engine fail | `analysis_runs.error` | poll failed path (Map-vs-String client bug) | PARTIAL (B) |
| 5-key profile | TRX-6 | `user_state.style_profile` (wholesale replace) | hairstyle/grooming use-cases + `GET/PATCH /me` | YES (but NOT by outfit itself) |
| `analysis_updated` + `outfit_selected` | post-complete | `learning_signals` + styled-day (one commit) | `GetLearningSummary` labels-only; score counts | WRITE yes / CONSUMER no (stored≠personalization) |
| wardrobe items | — | — | — | NOT TOUCHED (R/W/U/D: none) |
| saved_looks | — | — | — | NOT TOUCHED (Save button writes nothing) |
| prefs/flags/events/sessions/users | — | defaults/owner-FK only | builder/event flows | NOT TOUCHED by outfit |
| image bytes | camera/gallery | memory only → hashed → dropped; never persisted/logged | — | TEMP ONLY |

Relationships: `runs.user_id→users CASCADE` (real FK); `run_type→run_types RESTRICT`; `source_run_id` on saves = UUID FK `SET NULL`; outfit→save link does not exist (no save); `sourceRunId` snapshot field = string (loose).

# 8 Personalization Trace (14 items)

1 Analyze-My-Style results: NOT READ (image-only; §9). 2 `style_profile`: NOT READ (never `get_style_profile` on outfit path). 3 face_shape: NOT READ (measured fresh; empty→`oval` default). 4 skin_tone: NOT READ (produced as `""`). 5 body_type: NOT READ (same). 6 style_type: NOT READ (same). 7 wardrobe: NOT READ (no dep/import). 8 garment results: NOT READ (zero garment refs under `outfit_scan/`). 9 preferred occasions: NOT READ. 10 user prefs: NOT READ. 11 saved looks: NOT READ. 12 learning signals: NOT READ (written, never branched on). 13 events: NOT READ. 14 previous outfit analyses: NOT READ (no list/history query; each scan independent; profile-overwrite = latest-wins, not accumulation).
Score: 0/14 connected. Writes that exist but lack consumers do NOT count as personalization.

# 9 Analyze My Style Relationship

- Forward (style→outfit): NO CODE CONNECTION (outfit never reads profile; proof: no `user_state` read calls in `CreateOutfitRun`, adapter input = pixels only).
- Reverse (outfit→profile→future): CONNECTED — TRX-6 writes 5 keys; `CreateHairstyleRun:117-118` + `CreateGroomingRun:591-592` REQUIRE `face_shape` (422 otherwise); `GET/PATCH /me` surfaces it. So Outfit feeds the profile that Analyze-My-Style/profile-only + grooming consume — shared fields `face_shape,skin_tone,body_type,style_type,source_run_id` via `UserStateRepositorySQL.update_style_profile` (wholesale replace — sibling keys dropped, YELLOW).
- Shared-function delusion check: sharing the TABLE ≠ integration; only the reverse direction is a real data dependency.

# 10 Garment Relationship

**NOT CONNECTED** (zero shared code/imports/calls; verified by grep over `outfit_scan/`). Direction garment→outfit: none (outfit consumes no category/subcategory/color/pattern/material/style/fit/imageRef/sourceRunId). Partial/shared: ONLY infrastructure — same run table (different `run_type`), same GET endpoint, same vision host/timeout/kill-switch, same MediaRef shape, same 20MB/type validation. Adapter prompts are mutually exclusive (face vs garment; garment prompt explicitly rejects face-first portraits → a Scan selfie would `no_garment` on garment path and vice versa). Reuse is available (C/G) but nothing is shared today.

# 11 Wardrobe Relationship

NOT CONNECTED in any direction: no read (no `WardrobeItemRepository` dep/import), no write, no comparison, no missing-piece logic, no save-to-wardrobe, no photo/metadata use. Wardrobe data (incl. garment-derived items + imageRefs) exists but outfit ignores it (F). (`GenerateOutfit` DOES read wardrobe — but outfit-analysis never calls it, §12.)

# 12 Generate/Build Outfit Relationship

Neither direction exists with Outfit Analysis: `GenerateOutfit` (`outfits.py:268-397`) is READ-ONLY deterministic ranking over owned wardrobe + `preferred_occasions` (request: occasion/mood/fit/colorPalette/seed; 204-empty w/ typed reason; 503 on engine fail; NO commit, NO signals, NO profile/style reads beyond prefs); Flutter builder (`outfit_client` → `#41 generate`, `#42 saved`, guest-derivation gates) and `daily_outfit_screen` (TodayLook `#31/#32`, GuestSignInCard for guests, REAL save via `POST /v1/looks/today/save` sourceContext daily, idempotent) never touch analysis runs; `See Recommendations` navigates WITHOUT forwarding snapshot/run (context loss). `SaveOutfit→SaveRecommendation` (outfit/daily contexts, owned-UUID validation, idempotent replay, `look_saved`+day TRX-3) is consumable by outfit results (G) but unwired (C). M11 P3 proves save→generate works — the bridge exists; outfit-analysis just never steps onto it.

# 13 Saved Looks Relationship

Outfit Analysis can save NOTHING today: no `looks/saved` call, no `source_run_id` attach, no retrieval, no share (all RED/GRAY on this screen). Backend capability EXISTS and fits: `POST /v1/looks/saved` (any `sourceContext` incl. `outfit`, snapshot verbatim, idempotent-key, owned-ID validation) and `POST /v1/outfits/saved` (outfit-validated via M7) — both write look + signal + day. (G backend-ready, C unwired.) Daily/builder surfaces prove the pattern live.

# 14 Learning Relationship

- WRITES: 2 signals/run (`analysis_updated`, `outfit_selected`) + styled-day (verified); score inputs (counts) updated.
- CONSUMERS: `GetLearningSummary` surfaces label STRINGS only; style score uses counts; ranking/scoring branches on NO signal type; `resolve_preferred_item_ids`/`get_outfit_coverage` read `saved_looks`, never signals; `item_added` (wardrobe-save signal) is docstring-only — zero emits repo-wide. Feedback writes `feedback_events` (separate table, no signal). Assistant `_buildContext` ships wardrobe/face/saves/prefs to CHAT only (not into analysis/recommendation scoring).
- Verdict: WRITE EXISTS ×2, CONSUMER (personalization-driving) DOES NOT EXIST. Stored signals ≠ personalization. Learning loop is write-only history + display labels.

# 15 Guest Flow

CAN ANALYZE? NO. CAN SEE RESULT? NO. CAN SAVE? NO. CAN PERSIST? NO (zero server rows; local none for outfit).
Gates in order: (1) Flutter `_submitSelected:258` prompt+return (first, no HTTP); (2) `_handleCapture` no-selection same; (3) FastAPI 401 (behind); (4) poll-401→`/entry`; (5) Save button prompt. Browse to SCAN-001 allowed (shell guest-safe). NULL-run guard prevents 401-storms (honest error).
Vs intended (analyze+see, gate-on-save): architecture CAN support it — vision+engine+snapshot are user-agnostic until the `user_id` FK insert; TRX-6/signals/day are the persistence boundary. Options (decision, not design): ephemeral/anonymous run (genuinely NEW — no anonymous-run concept exists, I) vs deferred-save-after-signup (exists pattern: pending-intent + post-auth conversion, C). Do NOT implement; owner decides.

# 16 Error Matrix

| Case | Backend | DB | Flutter | Visible copy |
|---|---|---|---|---|
| no image (null submit) | — | — | Analyze hidden w/o bytes; guard return | none needed (GREEN) |
| invalid/unreadable | 422 | no run | generic upload-fail | honest, vague (B) |
| unsupported MIME | 422 (both layers) | no run | generic upload-fail | honest, vague (B) |
| >20MB | 422 (declared-size) | no run | generic upload-fail; NO pre-check (vs garment) | honest (B) |
| no garment (outfit path) | N/A — face prompt | — | — | N/A (outfit detects faces, not garments) |
| multiple garments | N/A (single-face `ambiguous_subject` only) | — | `Analysis failed` | honest (B) |
| no person | `failed/no_face_detected` | failed row | `Analysis failed…` + Back to Scan | honest (GREEN) |
| ambiguous subject | `failed/ambiguous_subject` | failed row | same | honest (GREEN) |
| AI unavailable/timeout | `failed/{reason}` | failed row | same (+`>20s→Still analyzing` while polling) | honest (GREEN) |
| malformed AI JSON | `failed/invalid_analyzer_response` | failed row | same | honest (GREEN) |
| low confidence | `failed/low_confidence` | failed row | same | honest (GREEN) |
| 401 | `AUTHENTICATION_ERROR`+header | — | submit: generic fail+session-clear; poll: re-scan+/entry | honest (GREEN) |
| 403 | none (→404) | — | n/a | n/a |
| 404 poll | `NOT_FOUND` | — | `Server returned 404, retrying…`→timeout (retried!) | honest outcome, wrong tactic (YELLOW) |
| 422 | validation envelope | no run | generic fail | honest, vague (B) |
| 500 | DATABASE_FAILURE/request_id | — | generic fail | honest (GREEN) |
| poll timeout (30 tries) | n/a | — | `Analysis polling timed out` | honest (GREEN) |
| network fail | n/a | — | `Upload failed + connectionHint` (emulator-aware) | honest (GREEN) |
| save failure | n/a (no save call) | — | n/a — button always "succeeds" (snackbar) | FAKE success (RED) |

# 17 Security

JWT-first (`effectiveToken` session-wins; `noteStatus(401)` clears+fires once); runs `WHERE id AND user_id` on get/complete/fail/list — cross-user theoretical retrieval: NOT possible via API (404-indistinguishable; no IDOR path found; enumeration yields 404s, no oracle beyond existence-timing — accepted OW-1). No run-ID prediction (gen_random_uuid). Images: hashed, never persisted/logged/echoed (tests assert); error payloads carry run_id only. Guests: no token, no rows. Pre-existing (report-only): register-key no-UQ race; `oval`-default via stub path; wholesale TRX-6 replace; no analysis idempotency key (double-tap→double-run billed twice).

# 18 Tests

| Area | Exist | Verify | Missing |
|---|---|---|---|
| Flutter UI render | `scan_screen/processing/analysis_screen_test` | bars/placeholders/chips/share-stub | real camera, overflow/scaling |
| Nav | `scan_screen_test` (test-mode), router tests | test-mode nav only | real chain, back-stack, dailyOutfit extra |
| Client | `outfit_scan_client_test` | multipart/auth/202→id/422→null/empty/401-clear/hygiene | timeout path, per-code mapping |
| Polling | single-GET + spinner only | fetch + loading | backoff/timeout/failed/401/429/completed-forward |
| Parse | Map-fixture render | rendering | int-confidence/Map-error robustness (P0!), typed parser |
| Backend route | `test_outfit_image_router` (fakes) | 422-no-run, failed+reason, no-leak, 404-foreign | live PG E2E here |
| Use-case | `test_analysis_use_case` | TRX-6, signal pair, SHA-256 | — |
| Adapter | `test_vision_appearance_adapter` | normalize/floor/transport | live-provider test (needs Ollama) |
| DB/persist | `test_analysis_api` (PG-gated, skipped) | 202→completed, list-contains | run in CI with PG |
| Ownership | router+api tests | foreign→404 | Flutter-side |
| Save | NONE for scan | — | no-save assertion (locks honest-noop) |
| Guest | null-run + adjacent gates + routing | honest null-run | submit/capture/save gates w/ `isGuestUser=true`; post-auth return w/o auto-POST |
| Personalization non-read | NONE | — | assert-no-read tests (lock image-only design) |

Passing tests ≠ provider works (all vision tests fake transport; Phase 4A blank-image live check is the only live evidence; real-face success unverified).

# 19 OSI Status

A UI YELLOW (flow renders; save/share fake; no retake) · B Navigation GREEN (typed extras, honest null-run) · C Flutter service YELLOW (contract ok; untyped parse + cast crashes) · D HTTP YELLOW (collapse, 404-retry, 413/503 fiction) · E FastAPI GREEN (validate→sync→terminal, write-once) · F Auth GREEN (JWT scoping, honest gates) · G AI GREEN code / BLUE runtime (provider unverified) · H Database GREEN (runs+profile+signals; bytes never stored) · I Personalization RED (0/14 reads; writes without consumers) · J Garment RED (not connected; shared infra only) · K Wardrobe RED (untouched both ways) · L GenerateOutfit RED (unwired; capability proven elsewhere) · M SavedLooks RED screen / GREEN backend (G) · N Learning YELLOW (writes real, consumers absent) · O Guest YELLOW (honest but before-analysis vs intended) · P Errors GREEN (except save-fake RED + 404-retry YELLOW) · Q Security GREEN (OW-1, no PII leak; pre-existing notes) · R Tests YELLOW (contracts strong; UI/guest/live gaps) · S Documentation RED (12 stale claims — see below).

Doc conflicts (code wins): `APPEARANCE_API:173` (outfit="clothing detection") · `RECOMMENDATION_API:174,443` (`sections[]/detectedItems[]`, `OutfitAnalysisData`) · `SCAN_API:170,191,397` (same + "history only/Generate Look") · `API_INVENTORY:875` · `API_CONTRACT_RULES:527` (typed fields) · `AI_DATA_FLOW:157` (`addSavedLook` @ screen:260 — function absent from file) · `ACTION_API_INVENTORY:55` (mock NOW) · `MVP_SCOPE:98,116` (timer-over-mocks/no model) · `SCREEN_DATA_INVENTORY:730` (future-sections) · `API_SECURITY_REVIEW:646` (413) · `BACKGROUND_JOB_ARCHITECTURE:92-151` (async workers; code sync).

# 20 Critical Findings

- P0: untyped `as double` (int-confidence crash) + `error as String?` (Map-error crash) — real backend shapes crash the UI; no idempotency key (double-charge runs); `item_added` never emitted (learning blind to wardrobe saves).
- P1: `Save Profile` fake-success; `See Recommendations` context loss; zero Scan↔garment/wardrobe/generate/saves wiring; guest blocked before (not on) save; 404 retried to exhaustion.
- P2: no Retake (capture+result), no Retry on result, static posture checklist, undocumented 48s backoff ceiling, `Not detected` trio on every prod result (skin/body/style always empty — UX presents 3 dead chips).
- P3: 0/14 personalization reads; signals write-only; profile wholesale-replace drops keys; `outfit_selected` misnomer (lifecycle≠tap); observations unaccumulated (latest-wins).
- P4: 12 stale doc claims (§19S); unreachable 413/503 in OpenAPI; missing tests §18; live face-photo + live PG E2E unverified.

# 21 Connection-Only Opportunities

| Pair | Current | Via (exists) | Missing link | New arch? |
|---|---|---|---|---|
| Outfit ↔ Garment | NOT CONNECTED | `GarmentClient`, `POST /garment`, adapter, typed model | one call + review UI in scan flow | NO |
| Outfit ↔ Wardrobe | NOT CONNECTED | wardrobe repo/read patterns, `GenerateOutfit` | read call for compare/recommend | NO |
| Outfit ↔ Analyze My Style | reverse-only | `GET /me`, `get_style_profile` | forward read (product-gated) | NO |
| Outfit ↔ style_profile | writes-only | same contracts | read where product wants | NO |
| Outfit ↔ Generate Outfit | NOT CONNECTED | `POST /generate` + M11-P3 proof | forward snapshot/runId as prefs/seed | NO |
| Outfit ↔ Saved Looks | NOT CONNECTED | `POST /looks/saved` + `/outfits/saved` | wire Save button to either | NO |
| Outfit ↔ Learning | write-only | existing signal rows + summary | define consumer contract first | NO (consumer may be I — decide) |
| Guest ↔ pipeline | blocked-before | pending-intent + post-auth conversion | reposition gate AND/OR anonymous-run decision | anonymous run YES(I); reposition NO |

# 22 Current Data-Flow Diagram

```
Analyze My Style ──writes──▶ style_profile ──read by──▶ Hairstyle(profile-only)/Grooming [CONNECTED]
       │                              │
       │ (image pass also writes TRX-6)│
       ▼                              │  (outfit NEVER reads profile)
Outfit Analysis ──writes──▶ style_profile [CONNECTED] ──▶ future hairstyle/grooming [CONNECTED]
       │──writes──▶ analysis_runs(outfit) [CONNECTED] ──▶ GET /runs (poll+history, no history UI) [PARTIAL]
       │──writes──▶ learning_signals×2 + styled-day [CONNECTED] ──▶ summary-labels display [PARTIAL] / scoring-consumers [NOT CONNECTED]
       │──result──▶ OutfitAnalysisScreen [CONNECTED] ──▶ Save (snackbar) [NOT CONNECTED] / Share [NOT CONNECTED] / dailyOutfit w/o context [PARTIAL]
       │──▶ Garment Analysis [NOT CONNECTED] (shared: run table, GET, vision host — infra only)
       │──▶ Wardrobe (read/write/compare) [NOT CONNECTED]
       │──▶ Generate Outfit [NOT CONNECTED] (bridge proven via wardrobe-save path, unused here)
       │──▶ Saved Looks [NOT CONNECTED] (both save APIs ready, unwired)
Garment Analysis ──▶ Wardrobe (confirm-save + imageRef) [CONNECTED] ──▶ Generate Outfit (reads wardrobe+prefs) [CONNECTED]
       │──▶ style_profile / signals / saves [NOT CONNECTED]
Generate Outfit ──▶ Saved Looks (/outfits/saved, validated) [CONNECTED] ──▶ look_saved + day [CONNECTED]
TodayLook ──▶ save (/looks/today/save, idempotent) [CONNECTED]; guest GuestSignInCard [CONNECTED]
Guest ──▶ Outfit capture/preview [CONNECTED] / analyze+result+save+persist [NOT CONNECTED — gated before analysis]
```

# 23 Recommended Investigation Order

1. Vision-provider live probe (owner provisions host+model → real-face POST/poll → record ACTUAL matrix; unblocks every D).
2. Save-button decision (which existing save API `Save Profile` should call — `looks/saved` vs relabel-as-auto-saved; then P0 parse fixes against REAL payloads).
3. Guest-policy decision (reposition vs anonymous-run) — gates all O-work; needs owner product call.
4. Garment-reuse spike (read-only trace of single-item Scan→garment call shape; confirm `ambiguous` rate on worn-outfit photos before any wiring).
5. Personalization-consumer contract (which signals/fields, NULL fallbacks) BEFORE any read-wiring; else placebo personalization.
6. Doc refresh pass (12 stale claims) + OpenAPI 413/503 correction + missing-test backfill (parse robustness, guest gates, no-read locks).

---

## Appendix — Source index (new + carried)

New: `backend/app/application/outfits.py:1-60,144-230,268-397,433-530` · `application/saved_looks.py:45-205` · `routers/outfits.py` + `routers/wardrobe.py:96-181` · `outfit_builder/{outfit_client,outfit_models,outfit_repository}.dart` + `build_outfit_screen:55` + `outfit_generation_screen:62` + `outfit_recommendation_screen:20,65,110` · `home/presentation/daily_outfit_screen.dart:185-284,364,1209` + `today_look_{client,models,repository}.dart` · `events/event_details_screen:206-379` · docs conflicts listed §19S.
Carried (verified D1/D2): outfit_scan 3 screens + client; `routers/analysis.py:130-268`; `CreateOutfitRun:169-341` / `CreateGarmentRun:645-747`; both adapters; `GarmentClient/Models`; `add_wardrobe_item_screen`; `models.py` tables; `settings.py:66-82`; `guest_mode/auth_session/auth_guard/pending_intent`; test files §18.
Skills lens: `flutter-apply-architecture-best-practices` (carried; no code emitted).
