# AI Stylist Domain 2 — Garment Analysis Deep Audit (INVESTIGATION ONLY)

> Status: INVESTIGATION COMPLETE. No application source modified. No fixes implemented.
> Date (UTC): 2026-09-27. Repo: `fansivibe_v1_backup` (Flutter `newproject/flutter_application_1`, backend `backend`).
> Method: current source as source of truth; doc claims verified against code, conflicts reported.
> Prior finding (Domain 1): Scan My Outfit (`POST /v1/analysis/outfit`) is appearance/hairstyle analysis (face_shape → `recommend_hairstyle`). This audit traces the SEPARATE garment capability (`POST /v1/analysis/garment`, M11) and answers whether Scan can reuse it without new architecture.

Legend: GREEN working · YELLOW partial/risk · RED broken/blocked · GRAY UI-only · BLUE intentional local-only/nav.
Classes: A connected · B partial · C disconnected-existing · D runtime-dep · E UI-without-backend · F data-not-consumed · G backend-not-consumed-by-UI · H intentional-local · I unsupported.

---

# 1 Executive Summary

Garment Analysis (M11) is a **complete, honest, authenticated pipeline living inside the Wardrobe add-item flow** — NOT inside AI Stylist. Chain: `/wardrobe` → `add-category` → `add-item` (`AddWardrobeItemScreen` + `WardrobePhotoScreen`) → `GarmentClient POST /v1/analysis/garment` (multipart `image`, Bearer, 30 s) → `CreateGarmentRun` (sync, 202 `{run_id}`, `run_type="garment"`) → `OllamaVisionGarmentAdapter` (category/subcategory/color/pattern/material/style/fit/confidence) → completed/failed run (observation snapshot verbatim, `sourceRunId` anchored) → client poll (1 s × 30, stops on 404) → strict typed `GarmentAnalysisResult.fromJson` (throws on malformed — never fakes) → suggestion card (`Not detected` for nulls) → exact-match chip prefill (never overwrites user picks) → `Save Item` → `POST /v1/wardrobe/items` 201 with `imageRef` provenance → pop. Retake + Analyze Again exist. **Zero code connection to Scan My Outfit** (no garment import anywhere under `features/outfit_scan` — verified).

Architecturally it is the inverse of Scan: Scan = engine + profile + signals, NO garment observation; Garment = observation ONLY — **deliberately NO decision-engine step, NO `user_state` write, NO signals, NO wardrobe write** (`analysis.py:645-658` docstring + deps prove it: constructor takes only `runs` + REQUIRED `garment_port`, no default so the hash adapter can never silently back it).

Answer to the architecture question: **YES — reusable without new architecture (reuse, not rebuild).** Reusable as-is: `GarmentClient` (submit+poll), `POST /garment` + shared `GET /runs/{id}`, `OllamaVisionGarmentAdapter`, `GarmentProfile.to_snapshot`, `GarmentAnalysisResult.fromJson`, suggestion-review-prefill-save pattern, `POST /wardrobe/items` with `imageRef`. Genuine gaps (not blockers for connection, but product must decide): (a) single-subject semantics — overlapping garments → `ambiguous_subject`, so a full-outfit photo does NOT yield multi-item breakdown (I for multi-item; single worn-outfit photo would likely fail or single-classify); (b) no outfit-level recommendation on garment path — but `POST /v1/outfits/generate` (Build Outfit, reads wardrobe+prefs, proven by `test_m11_p3`) already exists for that; (c) guest gate sits BEFORE analysis, while intended behavior is analyze+see then gate-on-save (policy delta, connection-only to move); (d) same runtime vision-provider dependency as Scan (D).

# 2 Exact Click-by-Click Flow

```
/wardrobe → [+] → add-category → pick category (e.g. tops)
 → pushNamed(wardrobeAddItem, extra: category) [wardrobe_screen:418, add_wardrobe_category_screen:90-92]
AddWardrobeItemScreen [Photo (optional) section:441-445]
 → Take Photo → WardrobePhotoScreen (camera medium/jpeg | permission cards)
    → capture → preview → Retake / Use Photo (pops WardrobePhoto bytes) [photo_screen:189,350-352]
 → OR Choose from Gallery (1024²) → preview
 → Analyze Item → guest? prompt (NO post) : submit → Analyzing… (20 s still-analyzing notice)
 → 202 → Analyzing clothing… → poll 1 s×30
 → completed → AI suggestion card + exact-match prefill (type/color/texture only)
 → Retake | Analyze Again | edit chips manually (canonical)
 → Save Item → (guest: LocalRepo imageless | authed: POST /wardrobe/items 201 + imageRef) → pop(item)
failed/unreadable/timeout → honest inline error, stage back to selected, retry available
```

Per-action: Take Photo GREEN · Gallery GREEN · Retake GREEN · Use Photo GREEN · Analyze Item GREEN authed / RED-by-design guest · Analyze Again GREEN · Save Item GREEN (real 201 / local) · Back BLUE · permission cards GREEN.

# 3 Flutter Architecture

Feature-first (`features/wardrobe/`), no new layers: `presentation/add_wardrobe_item_screen.dart` (914 lines, `StatefulWidget+setState`, `_PhotoStage{none,selected,analyzing,result}`) + `wardrobe_photo_screen.dart` (camera sheet) → `data/garment_client.dart` (`GarmentClient`, injectable `http.Client` + `pollInterval`, HAS `dispose` — unlike outfit client) + `data/garment_models.dart` (typed result) + `data/wardrobe_repository.dart` contract (`createItem{…,imageRef}` :148-153) with `WardrobeRepositoryImpl` (server) / `LocalWardrobeRepository` (guest, imageless, `local-*` ids) → `data/wardrobe_client.dart` (12 s timeout, Bearer) → `data/wardrobe_api_models.dart` (`MediaRef`, `WardrobeItemData`, imageRef verbatim). Routes: `/wardrobe` → `add-category` → `add-item` (extra `AddItemCategoryConfig?`, null→`_missingDataScreen`) — `app_router.dart:450-477`, names `route_names.dart:17,48-50`. Guests browse all `/wardrobe/*` (`auth_guard.dart:82-95`). Test overrides injectable (`repository`, `garmentClient`, `photoGalleryPick` constructor params — tests-only seams).

# 4 Image Pipeline

- Camera (`wardrobe_photo_screen.dart:102-147`): `availableCameras()` → `CameraController(medium, jpeg)`; capture `takePicture→readAsBytes` (:147); preview → **Retake** (`_retake:189`) / **Use Photo** (pops `WardrobePhoto{bytes,filename}`); permission mapping by `denied/accessdenied/permission` substring (:123-126) → denied/unavailable/error cards; injectable `pickImage` gallery fallback (:167-175, 1024²); Take Photo never falls back to gallery by itself.
- Gallery (`add_wardrobe_item_screen.dart:190-217`): `pickImage(1024²)`; cancel→silent return; bytes→`_photoBytes/_photoFilename`, stage reset (result/media/run cleared); fail→`Could not open the gallery.`
- Bytes retained in `_photoBytes` (memory) until retake/new-photo/save/screen-dispose; preview `Image.memory` 220 h (`:586-594`).
- Validation: UI pre-check `bytes.length > 20 MB → truthful message, no upload` (:245-251); client refuses empty/oversized (`garment_client.dart:82-85`); backend authoritative (type + declared-size + readable → 422).
- Backend stores hash+metadata only (`key,mediaType,sizeBytes,contentHash,isGenerated,uploadedAt,analyzer`); bytes never persisted/logged/echoed. Wardrobe save stores backend's OWN `input_media` values verbatim as `imageRef` + `sourceRunId` (`_buildImageRef:149-167` — null key/mediaType → null, manual saves stay imageless).

# 5 HTTP Contract

- `POST {base}/v1/analysis/garment` · `Bearer <session|dev>` · multipart field **`image`** (`fromBytes`, filename default `wardrobe_item.jpg`, suffix→content-type) · 30 s (send+collect) → `202 {run_id}` else null (all-non-202→null + debugPrint — same collapse pattern as outfit, B).
- `GET {base}/v1/analysis/runs/{run_id}` → `200 {status, result?, input_media?, error?{code,message,details{reason}}}` else bare code, `0` unreachable.
- Poll `pollGarmentRun(runId, attempts=30)`: 1 s fixed interval; **`0/404 → null` (stops — BETTER than outfit which retries 404 to exhaustion)**; completed/failed return promptly; exhaustion→null (retryable, never duplicate analysis — fresh read).
- `POST {base}/v1/wardrobe/items` JSON `{name,category,color,material?,isFavorite?,imageRef?{key,mediaType,sizeBytes,contentHash,isGenerated,uploadedAt,sourceRunId}}` → `201 WardrobeItem`; 401/409/422/413/429 declared; vocab enforced server-side (422 on unknown codes).
- Wardrobe CRUD client timeout 12 s (vs 30 s analysis).

# 6 FastAPI Chain

- `POST /garment` (`analysis.py router:232-268`): `response_model=AsyncAccepted`, 202; same validation as outfit (type set + 20 MB declared-size → 422); wiring `CreateGarmentRun(runs, garment_port=OllamaVisionGarmentAdapter())` — REQUIRED port, no dev default; → `AsyncAccepted(run_id)`. Sync in-request (no background worker).
- `CreateGarmentRun` (`application/analysis.py:645-747`): validate → `read_image_bytes` → `build_media_ref(analyzer="ollama-garment-v1")` → `runs.create(garment, vision-v1, provenance)` → `port.analyze(...)` → `GarmentAnalysisError(reason)`→`fail(PROCESSING_FAILURE+details.reason)` / bare `Exception`→fail w/o reason / engine-N/A (no engine step) → `complete(result=replace(profile, sourceRunId=run_id).to_snapshot())` / `False`→500. **No `user_state`, no signals, no wardrobe, no activity-day deps — proven by constructor signature.**
- `GET /runs/{run_id}` + `GET /runs` shared with all run types (owner-scoped, foreign→404, list omits result/error).

# 7 Authentication

- Same substrate as Scan: `get_current_user_id` (JWT; `Bearer dev` only where allowed) → 401 otherwise; Flutter `effectiveToken('dev')` + `noteStatus(401)`.
- Guest reachability: **blocked at TWO layers.** (1) Flutter FIRST: `_analyzePhoto:233-242` → `promptGuestSignIn('Sign in to analyze clothing…')` + return, no HTTP (class-D, no replay). Guests CAN photograph/preview (no gate in `_takePhoto/_pickFromGallery`). (2) FastAPI SECOND: no/invalid token → 401 before any use-case/DB. Business/repository/DB layers add nothing (owner id comes from auth dep).
- So: guest CANNOT technically reach the endpoint today — exact gate = Flutter button (first), FastAPI auth dep (second). Intended behavior (analyze+see, gate-on-save) requires moving the existing gate, not new auth (see §24).

# 8 AI/Vision

`OllamaVisionGarmentAdapter` (`vision_garment_adapter.py:129`, `ADAPTER_ID="ollama-garment-v1"`, recorded in MediaRef): same Ollama transport (`_default_chat` `POST {host}/api/chat`, temp 0, `format:json`, single attempt, whole-client timeout `FANSIVIBE_VISION_TIMEOUT_S=20.0`, kill-switch `FANSIVIBE_DISABLE_VISION` → `analyzer_unavailable`), same `LOW_CONFIDENCE_FLOOR=0.35`, same taxonomy (`no_garment_detected, ambiguous_subject, analyzer_unavailable, analyzer_timeout, low_confidence, invalid_analyzer_response`).

- Prompt (:75-94): garment-only STRICT JSON `{category,subcategory,color,pattern,material,style,fit,confidence}`; code ∈ 5 canonical; null = not clearly visible; **face-first portrait explicitly NOT a garment photo → `no_garment`**; overlap → `ambiguous`.
- Normalization: category — None stays None, non-string→invalid, `no_garment/ambiguous`→raise, off-vocab description (e.g. "shirt")→**None (not failure)**; text attrs — None→None, non-string→invalid, blank/"null"→None; confidence via shared parser (bool rejected, 0-1); below floor→`low_confidence`.
- Deterministic `needs_review = category/color/material null OR confidence < 0.6` (:206-208) — weak/missing always routes through user confirmation.
- Output `GarmentProfile` (all-None-able + `confidence=0.0` default + `needs_review=True` default + `sourceRunId` anchored by use-case, NOT adapter).
- IMPLEMENTED: all above + `validate_result` contract (:222-254). UI-ONLY: none on this path (summary renders only parsed fields). MOCK/DEAD: `wardrobe_mock_data.dart` exists for other surfaces (not parsed here); dev/hash adapter has no garment equivalent (port REQUIRED). UNSUPPORTED: multi-item breakdown, outfit-level verdict, wearing-occasion inference, size/fit advice, price/brand ID.

# 9 Result Parsing

`GarmentProfile.to_snapshot()` → `runs.result` → `GET` wire → `GarmentAnalysisRun` getters (`result` Map-cast, `inputMedia` Map-cast, `failureReason` = `error.details.reason` Map-path — CORRECT, cf. outfit's crashing `as String?`) → `GarmentAnalysisResult.fromJson` (strict: unknown category→throw, non-num confidence→throw, non-string attr→throw, blank→null, `needs_review ?? true`, `sourceRunId` opt) → `FormatException` caught → `unreadable` error (never fake) → summary rows (`Category…Fit`, null→`Not detected`) + review banner.
Type-safety: BEST in repo (strict-throw > hairstyle `??`-guard > outfit raw-`as`). Residual: `data?['result'] as Map?` casts throw (not caught as FormatException — uncaught TypeError risk on malformed envelope, YELLOW); `sizeBytes as int?` in `_buildImageRef` same class.

# 10 Database Writes/Reads

| Table | Garment analysis (`POST /garment`) | Wardrobe save (`POST /wardrobe/items`) |
|---|---|---|
| analysis_runs | WRITE create(pending,garment,vision-v1,media,provenance) → complete(result snapshot)/fail(error+reason); READ owner-scoped GET (no other table touched) | NOT USED (except `sourceRunId` string carried in imageRef — no FK) |
| user_state/style_profile | NOT USED (no dep, no read, no write) | NOT USED |
| wardrobe_items | NOT USED (docstring :648-654 explicit) | WRITE full row (name/category/color/material?/favorite/imageRef verbatim); READ list/get; UPDATE patch; DELETE destroy (owner-scoped, 404 foreign) |
| learning_signals | NOT USED (zero emits) | Docstring claims `item_added` (`wardrobe.py:127`) BUT **no `insert_look_saved("item_added")` call exists anywhere in `backend/app`** (sole `item_added` hit is that docstring) — doc-vs-code CONFLICT (B/E): saves currently emit NO signal |
| saved_looks | NOT USED | NOT USED |
| users | FK owner only | FK owner only |
| user_sessions | NOT USED | NOT USED |
| user_events | NOT USED | NOT USED |

Image bytes: never stored (hash/metadata only). No retention/TTL/purge visible for runs or imageRefs (I: not in code).

# 11 Personalization

Reads performed by garment flow: NONE — image-only (no profile, no prefs, no wardrobe, no saves, no runs, no signals, no events).
- A SYSTEM: 5 category codes, vocab tables (categories/colors/materials), `vision-v1`, provenance `1.1+1.0`, floor 0.35, `needs_review` rule — all code/config.
- B PROFILE FACTS: none consumed, none written.
- C PREFERENCES: none consumed (save screen's chips are manual user input at save time, not reads).
- D OBSERVATIONS: per-run `{category…fit,confidence,needs_review,sourceRunId}` + `input_media` hash/key — persisted in run row; `imageRef` copy persisted on save. Nothing derived into recommendations on this path.

# 12 Analyze My Style Relationship

**NO CODE CONNECTION FOUND — both directions.**
- Forward (profile → garment): `CreateGarmentRun` has no `user_state` dep, never calls `get_style_profile/get_profile`; adapter input = pixels only. `face_shape/skin_tone/body_type/style_type` unread.
- Reverse (garment → profile): no `update_style_profile` call; profile untouched by garment runs AND by wardrobe saves. Future hairstyle/grooming runs therefore cannot see garment results via profile.
(Evidence: constructor deps `runs + garment_port` only; zero `style_profile` references on garment path; zero `GarmentProfile` imports in hairstyle/grooming use-cases.)

# 13 Wardrobe Relationship

**CONNECTED (A) with a PARTIAL mapping (B).** `Garment Analysis → Wardrobe Item` works today via user-confirmed save: suggestion → exact-match prefill (subcategory→Type, color→Color, material→Texture; case-insensitive; never overwrites existing picks) → `Save Item` → `POST /v1/wardrobe/items` (201, vocab-422) with `imageRef` = backend's own media values + `sourceRunId`. Provenance chain run→item is traceable (`sourceRunId` string; no FK — YELLOW, string-only link).
PARTIAL gaps: observed `category` is DISPLAYED but never drives the save — save category = the category chosen on the PREVIOUS screen (`widget.category.wardrobeCategoryId`), so a mis-categorized entry + correct AI observation still saves under the wrong category (C-opportunity: cross-check/warn); `pattern/style/fit/subcategory` have no wardrobe columns and are dropped at save (I — schema has no such fields; prefill only covers type/color/texture); photo bytes local-only until save, guests imageless (H).

# 14 Scan My Outfit Comparison

| Capability | Scan My Outfit (`/outfit`) | Garment Analysis (`/garment`) |
|---|---|---|
| Route | `/stylist/scan-outfit→processing→analysis` | `/wardrobe→add-category→add-item` (photo section) |
| UI | dedicated 3-screen flow, no retake on capture, snackbar-only save | embedded photo step, Retake/Use Photo/Analyze Again, real save |
| Image input | camera(med/jpeg)+gallery 1024², no size pre-check | same camera/gallery 1024² + 20 MB pre-check |
| HTTP endpoint | `POST /v1/analysis/outfit` | `POST /v1/analysis/garment` |
| Auth | Bearer+`noteStatus`; guest gated at Analyze | identical; guest gated at Analyze |
| AI adapter | `OllamaVisionAppearanceAdapter` (face_shape only) | `OllamaVisionGarmentAdapter` (7 garment attrs) |
| Model/host/timeout | same vision settings (20 s, kill-switch) | same |
| Prompt | face JSON | garment JSON (+face-portrait guard) |
| Result | hairstyle snapshot (engine-derived) | observation snapshot verbatim (no engine) |
| analysis_run | `outfit/vision-v1` + TRX-6 + 2 signals + styled-day | `garment/vision-v1`, NO side writes |
| Profile update | YES (TRX-6, incl. `""` skin/body/style) | NO |
| Wardrobe | none | suggestion→prefill→save+imageRef |
| Recommendations | hairstyle recs in result | none (review-and-save only) |
| Learning signals | 2 per run | 0 (and save path's `item_added` is docstring-only) |
| Guest support | browse free; Analyze blocked; save fake | browse free; Analyze blocked; save real-local (imageless) |
| Persistence | runs+profile+signals | runs + (on confirm) wardrobe item |
| Error handling | per-reason fail + generic UI copy; `error as String?` crash; 404 retried | typed reasons → tailored copy; Map-safe parse; 404 stops; strict-throw parse |
| Tests | client+router+usecase+adapter+3 widget | `test_garment_analysis` 18T + `wardrobe_garment_flow_test` (parse×5/transport×5/photo×3/e2e-save) + M11 P3/P4 + wardrobe suites |

Verdict: **reusable without new architecture.** Reuse set: `GarmentClient` (+poll), `POST /garment`, shared run GET, garment adapter, `GarmentProfile.to_snapshot`, `GarmentAnalysisResult.fromJson`, photo→review→prefill→save UX, `POST /wardrobe/items`. Blockers that are GENUINE (I): multi-garment outfit decomposition (adapter is single-subject by contract); outfit-level styling verdict (no engine on garment path — but `GenerateOutfit` covers recommendations from wardrobe). Non-blockers (C/F/G/policy): Scan↔garment UI link (zero imports today), guest-before-analysis gate position, category cross-check, `item_added` docstring gap.

# 15 Guest Behavior

Guest: Wardrobe browsable → add-category → add-item → **Take Photo/Gallery + preview ALLOWED (no gate)** → Analyze Item → **prompt `Sign in to analyze clothing…`, NO post, NO result** → Save Item → local imageless item. So sign-in occurs **BEFORE ANALYSIS** — guest never sees any AI output. Intended (analyze+see, gate ONLY ON SAVING) is NOT met; current = analyze-gated AND save-degraded. (Compare Scan: identical before-analysis gate, but Scan's save is additionally fake for authed users; garment's authed save is real.)

# 16 Save Behavior

- `Save Item` (authed): `repository.createItem(name, category, color, material, imageRef)` → `POST /v1/wardrobe/items` → 201 → `pop(item)`; failure → `Failed to add item` (no fake success). Validation-first (`Please select a type and color`).
- `Save Item` (guest): `LocalWardrobeRepository.createItem` on-device, imageRef ALWAYS null (server-side analysis unreachable) — honest imageless local save, no prompt, no backend.
- `Retake`/`Analyze Again`: local state reset / re-run (no dup-save risk; poll-retry is fresh read).
- Existing APIs consume garment output TODAY: `POST /wardrobe/items` (imageRef verbatim, vocab-422). `POST /looks/saved` could archive garment looks (G, unused here).

# 17 Error States

| State | Backend | Flutter UI (honest?) |
|---|---|---|
| invalid/unreadable bytes | 422 (`read_image_bytes`) | upload-fail / unreadable-result copy (yes) |
| unsupported MIME | 422 both layers | generic upload-fail (B: no per-code copy) |
| oversized | 422 (>20 MB); UI+client pre-check | `larger than 20 MB…` pre-upload (yes, best-in-repo) |
| no garment | terminal `failed/no_garment_detected` | `No clothing item… Retake…` (yes) |
| ambiguous/overlap | `failed/ambiguous_subject` | `Photograph one item at a time` (yes) |
| low confidence | `failed/low_confidence` | `too unclear… better light` (yes) |
| AI unavailable/timeout | `failed/{reason}` (kill-switch→unavailable) | `service unavailable… try again` (yes) |
| malformed AI JSON | `failed/invalid_analyzer_response` | `Garment analysis failed…` (yes) |
| 401 | `AUTHENTICATION_ERROR` | guests never POST; (poll 401 → bare code → null → `taking longer…` — YELLOW: no entry-redirect like outfit) |
| 403 | none (foreign→404) | n/a |
| 404 poll | `NOT_FOUND` | poll STOPS → `taking longer… try again` (honest outcome, vague copy — YELLOW) |
| 422 | validation envelope | generic upload-fail (B) |
| 500 | `DATABASE_FAILURE`/unhandled+request_id | generic fail (yes) |
| poll timeout (30×1 s) | n/a (sync) | `taking longer than expected… try again` + retry (yes) |
| missing run (never submitted) | n/a | stage-gated (Analyze needs bytes; no null-run push exists here — GREEN vs outfit's null-run path) |
| result null/unparseable | n/a | `unreadable… try again` (yes; envelope Map-cast TypeError uncaught — YELLOW) |

# 18 Security

JWT-first, `Bearer dev` fallback where allowed; owner-scoped runs/items (foreign→404, indistinguishable); vocab RESTRICT / owned CASCADE; image bytes ephemeral (b64 in-memory, never logged/persisted/echoed — adapter docstring + router tests assert); `connectionHint`-only diagnostics; guest imageless-local (no orphan uploads). Gaps (report-only): `item_added` signal never emitted (analytics blind spot, not auth); `sourceRunId` string-only link (no FK); same pre-existing idempotency/413-doc issues as Scan path.

# 19 Tests

- Backend UNIT: `test_garment_analysis.py` — adapter (observation, nulls-stay-null, no_garment/ambiguous/descriptive-coerce/wrong-types/low_confidence/face-guard/no-bytes/validate_result ×10) + router/use-case (202+run_id, adapter+bytes wiring, snapshot-carry, terminal-failed, non-image reject ×5) + imageRef persistence (save-with/without-ref, patch-only-when-present ×3). SERVICE: `test_m11_p3_wardrobe_to_outfit` (DB-gated: garment-shaped save → reload → `GenerateOutfit` uses real UUIDs/values). API: `test_wardrobe_api`, `test_m13_outfits_api` (ownership, 204-empty, determinism, no-side-effects), `test_m11_p4_empty_reasons`, `test_m11_feedback_api`.
- Flutter CLIENT: `wardrobe_garment_flow_test` transport group (202→run_id, empty/oversized→null, poll completed+media, typed reasons, timeout→null ×5). UNIT parse group (verbatim, nulls, unknown-category-throws, non-num-confidence-throws, wrong-types-throw ×5). WIDGET: photo screen (buttons, preview+Retake/Use Photo, pop-bytes ×3) + add-screen e2e (prefill+save-with-imageRef …). Plus `add_wardrobe_item_screen_test`, `wardrobe_client_test`, `wardrobe_api_models_test`, `local_wardrobe_repository_test`, `clothes_test`, `assistant_outfit_wardrobe_wiring_test`.
- Missing: guest-gate widget test (Analyze prompt, no HTTP); poll-401 UI; envelope Map-cast robustness; category cross-check (none exists); multi-photo/category-mismatch; LIVE provider (real photo E2E — owner live-test); live DB E2E here (DB tests skip w/o PG).

# 20 OSI Table (12-layer)

| Layer | Garment path | Mark |
|---|---|---|
| 1 User/UI | photo step (Take/Gallery/Analyze/Retake/Save), suggestion card, `Not detected` | GREEN |
| 2 Navigation/state | `/wardrobe→add-category→add-item(extra category)`, `_PhotoStage` setState, timer-cancel dispose, client dispose | GREEN |
| 3 Image/media | med/jpeg camera, 1024², preview memory, 20 MB pre-check, bytes-never-stored (hash only) | GREEN |
| 4 Flutter client/service | `GarmentClient` submit+poll+404-stop, `WardrobeRepository` contract + local impl | GREEN |
| 5 HTTP/API | multipart `image`+Bearer 30 s; save JSON+imageRef 201; all-non-202→null collapse | GREEN (B on collapse) |
| 6 FastAPI/auth | same validation both layers, `get_current_user_id`, 202/201/422/404 shapes | GREEN |
| 7 Business service | `CreateGarmentRun` (no engine/side-writes by design) + `AddWardrobeItem` (vocab-422, verbatim imageRef) | GREEN |
| 8 AI/vision | garment adapter: prompt/normalize/floor/taxonomy/no-leak/`needs_review` | GREEN code (D runtime) |
| 9 Result/run | verbatim snapshot + sourceRunId anchor; write-once terminal; owner-scoped GET | GREEN |
| 10 DB/persistence | runs + wardrobe item + imageRef; NO profile/signals; `item_added` docstring-only | GREEN (B doc conflict) |
| 11 Personalization/learning | reads nothing; `item_added` missing = wardrobe saves invisible to learning | YELLOW (F) |
| 12 Result UI/recommendations | suggestion+prefill+real save; NO outfit-level recommendation on path (`GenerateOutfit` exists elsewhere) | GREEN (G for outfit-rec) |

# 21 A–I Classification

- A: photo→analyze→poll→suggest→prefill→save chain; adapter+use-case+run lifecycle; owner scoping; honest per-reason errors; guest browse; strict parse.
- B: error collapse (non-202→null, generic copies); envelope Map-cast risks; 404/401 poll copy vagueness; category displayed-but-unused; string-only sourceRunId link; `item_added` docstring-vs-code.
- C: Scan↔garment link (zero imports); category cross-check vs observation; guest-gate repositioning (existing prompt, new position).
- D: vision provider reachability/model (same as Scan); live DB E2E unverified here.
- E: (none structural — every garment UI has backend; only `item_added` analytics-doc gap).
- F: `style_profile`/signals/wardrobe/prefs exist but garment reads none (by design); garment observations exist but Scan/recommenders don't consume them.
- G: `GenerateOutfit` + `POST /looks/saved` exist but garment/Scan UI don't invoke them here; `GET /runs` history unconsumed by UI.
- H: guest imageless-local save; photo bytes memory-only; pending-intent single-slot.
- I: multi-item outfit decomposition; pattern/style/fit persistence (no columns); outfit-level verdict on garment path; guest anonymous analysis (no such API by design).

# 22 Blockers

- D-1 vision provider (same as Scan: host+vision-capable model+20 s; kill-switch). No code unblocks it.
- Policy (C, not D): guest-before-analysis gate vs intended analyze-then-gate-on-save — owner decision, then reposition existing prompt.
- I-1 single-subject contract: worn-outfit photos → likely `ambiguous`/`no_garment` — full-look scan via this endpoint needs product framing (one item at a time) or genuinely new multi-subject architecture (owner call).
- B-1 `item_added` never emitted: learning blind to wardrobe saves until writer added (connection-only: one insert call at existing save boundary).

# 23 Disconnected Existing Components (C/F/G)

1. C-1 Scan screen ↔ `GarmentClient`/`POST /garment` (import + call; all pieces exist).
2. C-2 Observed `category` ↔ save-category validation (warn on mismatch with chosen category).
3. C-3 Guest gate position (move existing `promptGuestSignIn` from Analyze to Save on garment path — mirrors intended behavior).
4. F-1 Garment observations (`runs.result`, `imageRef`s) ↔ Scan/recommender surfaces.
5. F-2 `style_profile` ↔ garment (intentionally unread; any future use reads existing `GET /me`).
6. G-1 `GenerateOutfit` ↔ post-scan flow (outfit recs from wardrobe incl. garment-saved items — already proven by M11 P3).
7. B-fix `item_added` emission at `AddWardrobeItem` boundary (existing signal infra, existing vocab seed needed — verify seed first).

# 24 Smallest Architecture-Preserving Solution

**Reuse, in order:** (1) Scan result/capture UI calls existing `GarmentClient.submitGarmentAnalysisBytes + pollGarmentRun` against existing `POST /garment` (no new endpoint/adapter/model); (2) parse with existing `GarmentAnalysisResult.fromJson`; (3) render with the existing suggestion-review pattern (`Not detected`, `needs_review` banner); (4) persist via existing `POST /wardrobe/items` (+`imageRef`) or archive via `POST /looks/saved`; (5) recommend via existing `GenerateOutfit` over the wardrobe the scan just enriched. **Genuinely new architecture required ONLY for:** multi-garment decomposition of one outfit photo, outfit-level styling verdicts beyond wardrobe-based generation, and anonymous-guest analysis (no such API by design). Guest analyze-then-gate = repositioning existing prompt, not new auth.

# 25 Proposed Implementation Plan (PLAN ONLY)

- P0 correctness: envelope Map-cast hardening (mirror strict `fromJson`); poll-401 → entry-redirect (mirror outfit); `item_added` writer OR docstring correction (verify `signal_types` seed first); OpenAPI 413/503 accuracy on garment+wardrobe routes. Files: `garment_client.dart`, `add_wardrobe_item_screen.dart`, `wardrobe.py` router/use-case. Connection-only.
- P1 disconnected: Scan→garment call wiring (`outfit_scan` UI + `GarmentClient`, existing endpoint/adapter/model); category cross-check warn (existing observation + existing category config); guest-gate reposition (existing prompt). Connection-only.
- P2 UX: surface `needs_review`/`Not detected` states in any Scan reuse (copy existing summary widget); keep Retake/Analyze Again (copy existing). Connection-only.
- P3 personalization: define consumer contract for garment observations (which fields, NULL fallback) BEFORE any profile/run consumer reads them; do NOT bulk-copy into `style_profile`. May be I — owner approval required.
- P4 testing: guest-gate widget tests; poll-401/envelope-robustness tests; category-mismatch test; owner live matrix (real garment photo, face-portrait guard, overlap→ambiguous, provider-down, token-expiry, repeat-scan, guest capture→prompt).

---

## Appendix — Source index (spot-verified)

Flutter: `wardrobe/presentation/add_wardrobe_item_screen.dart:19-100,109-167,169-242,270-392,402-556,558-663,666-719` · `wardrobe_photo_screen.dart:22-175,189,278-352` · `wardrobe/data/garment_client.dart:11-167` · `garment_models.dart:1-90` · `wardrobe_client.dart:34,62-137` · `wardrobe_repository.dart:148-272` · `local_wardrobe_repository.dart:27-77` · `wardrobe_api_models.dart:4-235` · `add_wardrobe_category_screen.dart:90-92` · `wardrobe_screen.dart:418,449` · `app/router/app_router.dart:450-477` · `route_names.dart:17,48-50` · `auth_guard.dart:82-95` · `outfit_scan/*` (zero garment refs — verified).
Backend: `routers/analysis.py:232-268` · `application/analysis.py:645-747` · `ai/vision_garment_adapter.py:1-261` · `domain/value_objects.py:79-117` · `domain/ports/garment_analysis.py:50` · `routers/wardrobe.py:96-181` · `application/wardrobe.py:123-170` · `infrastructure/db/models.py` (UserState 111, AnalysisRuns 174, WardrobeItems 410) · `config/settings.py:66-82`.
Tests: backend `test_garment_analysis.py` (18) · `test_m11_p3_wardrobe_to_outfit.py` · `test_m13_outfits_api.py` · `test_m11_p4_empty_reasons.py` · `test_wardrobe_api.py` · Flutter `wardrobe_garment_flow_test.dart` (parse×5/transport×5/photo×3/e2e) · `add_wardrobe_{category,item}_screen_test` · `wardrobe_{client,api_models,repository}_test` · `local_wardrobe_repository_test` · `clothes_test` · `assistant_outfit_wardrobe_wiring_test`.
Skills lens: `flutter-apply-architecture-best-practices` (carried from Domain 1; no code emitted).
