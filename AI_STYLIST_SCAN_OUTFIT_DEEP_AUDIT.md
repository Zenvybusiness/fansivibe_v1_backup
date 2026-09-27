# AI Stylist → Scan My Outfit — Deep Audit (INVESTIGATION ONLY)

> Status: INVESTIGATION COMPLETE. No application source modified. No fixes implemented.
> Date (UTC): 2026-09-27. Repo: `fansivibe_v1_backup` (Flutter app at `newproject/flutter_application_1`, backend at `backend`).
> Method: source code as source of truth. Docs/comments/route names verified against code; conflicts reported, not reconciled.
> Git baseline at start: dirty (pre-existing modifications incl. `CURRENT_STATE.md`, auth/hairstyle/onboarding/profile/learning/guest files + 5 untracked); no investigation-created source changes at end (only this doc + `CURRENT_STATE.md` entry).

Color legend: GREEN = working · YELLOW = partial/risk · RED = broken/blocked · GRAY = UI-only, no capability · BLUE = intentional local-only/nav/display.
Connection classes: A already-connected · B connected-but-partial · C disconnected-existing-components · D blocked-by-runtime-dependency · E UI-exists-but-no-backend · F data-exists-but-not-consumed · G backend-exists-but-UI-not-consuming · H intentional-local-only · I not-supported-by-current-architecture.

---

# 1 Executive Summary

The Scan My Outfit pipeline is **genuinely end-to-end connected at the code-path level** (A) for the authenticated happy path: Stylist tile → `OutfitScanScreen` → `OutfitScanClient POST /v1/analysis/outfit` (multipart `image`, Bearer, 30 s) → FastAPI `CreateOutfitRun` (sync, 202 `{run_id}`) → `OllamaVisionAppearanceAdapter` → deterministic `recommend_hairstyle` → `analysis_runs` completed + TRX-6 `user_state.style_profile` + 2 `learning_signals` + styled-day → `GET /v1/analysis/runs/{id}` poll → `OutfitAnalysisScreen`.

Three load-bearing qualifications:

1. **"Outfit" result is an appearance/hairstyle snapshot, not garment detection.** `CreateOutfitRun` (`backend/app/application/analysis.py:269-296`) feeds the vision output into `recommend_hairstyle` and stores `HairstyleResult.to_snapshot()` (`{appearance:{faceShape,skinTone,bodyType,styleType,sourceRunId},confidence,needs_more_data,recommendations:{top,alternatives}}`). The garment adapter (`OllamaVisionGarmentAdapter`) is wired ONLY to `POST /v1/analysis/garment` (`backend/app/api/routers/analysis.py:243-268`), never to `/outfit`. The result screen renders `Your Appearance Profile` chips + hairstyle recommendation, with a static `Analysis Details` placeholder (`outfit_analysis_screen.dart:511-530`) and dead mock types (`outfit_scan_mock_data.dart`, `DetectedClothingItem` etc. — never `fromJson`).
2. **Result-screen persistence actions are not connected.** `Save Profile` (`outfit_analysis_screen.dart:537-562`) shows `Appearance profile saved` snackbar with zero HTTP/DB/`LocalStorage` write (GRAY for authed; RED-by-design guest gate). `Share` is a `coming soon` snackbar (GRAY). No `Save`/`Retry`/`Retake` buttons exist on the result. `See Recommendations` navigates to `dailyOutfit` WITHOUT forwarding the snapshot (YELLOW context loss). (Server-side profile persistence already happened via TRX-6 at completion — the button adds nothing.)
3. **Runtime provider is a separate, unverified layer.** Code path exists (verified) ≠ provider available (not verified — requires reachable Ollama at `FANSIVIBE_VISION_HOST` with a vision-capable `FANSIVIBE_VISION_MODEL` inside 20 s; defaults are `http://localhost:11434` / `llama3.2-vision`, kill-switch `FANSIVIBE_DISABLE_VISION`). No live calls were made per instructions; real-result-verified, persisted, and consumed-by-recommendations states remain unproven live.

Best future connection-only opportunities (no redesign): wire `Save Profile` to existing `POST /v1/looks/saved` / `PATCH /me` (G); forward snapshot/run_id into `dailyOutfit` (C); add the Retake pattern that already exists in hairstyle/wardrobe flows (C); consume already-written `style_profile`/signals/wardrobe where product wants it (F).

# 2 Exact User Flow

```
USER
 ↓ (tap Scan My Outfit hero, stylist_screen.dart:434 pushNamed(scanOutfit))
AI Stylist (/stylist)
 ↓ (route /stylist/scan-outfit, app_router.dart:209, no params)
SCAN-001 OutfitScanScreen (camera init / gallery pick / preview / Analyze)
 ↓ (authed: _submitSelected → OutfitScanClient.submitOutfitAnalysis → 202 run_id → pushNamed(scanProcessing, extra:runId))
    (guest: promptGuestSignIn, no POST · upload-fail/empty/test-mode: pushNamed(scanProcessing) with null)
SCAN-002 OutfitProcessingScreen (runId only, never bytes; null → honest 'No run ID available')
 ↓ (poll GET /runs/{id} 3 s base, exp backoff, 30 attempts → completed → pushNamed(scanAnalysis, extra:snapshot))
SCAN-003 OutfitAnalysisScreen (raw-Map parse: appearance/confidence/recommendations.top)
 ↓ (Save Profile = snackbar-only GRAY · See Recommendations → dailyOutfit w/o context YELLOW · Share = stub GRAY · Back = pop BLUE)
Persistence (server, at completion — NOT via result buttons):
 analysis_runs completed + user_state.style_profile (TRX-6) + learning_signals ×2 (analysis_updated, outfit_selected) + activity_days styled-day
 ↓
Future personalization: style_profile readable by hairstyle/grooming runs + GET/PATCH /me; signals/wardrobe NOT consumed by this flow.
```

# 3 Click-by-Click UI Map

| # | UI | Handler | State → service → next | Verdict |
|---|---|---|---|---|
| 1 | Stylist `Scan My Outfit` hero (`stylist_screen.dart:429-434,510`) | `onTap: pushNamed(scanOutfit)` | No params, no guard → `OutfitScanScreen` | BLUE (nav) |
| 2 | SCAN-001 Camera preview area (`outfit_scan_screen.dart:449-566`) | `_initializeCamerasAndController:105-161` (rear-first, medium, jpeg, no audio) | `ready` → live `CameraPreview` + `AI Analysis Active` badge (display-only) | GREEN device; RED terminal cards (denied/unavailable/error) w/ Retry |
| 3 | `Choose from Gallery` (`796-816`) | `_pickImage:204-245` (1024², cancel→silent return, empty→silent return) | bytes → `XFile.fromData` → preview + `Photo selected` | GREEN |
| 4 | `Switch Camera` (`807-812`) | `_switchCamera:163-202` | re-init next lens; no-op if none | GREEN device / GRAY single-cam |
| 5 | `Capture Photo` (`779-785`) | `_handleCapture:327-385` dual-use (capture OR submit-if-selected; test-mode→processing w/ null) | real capture stays on preview (2nd tap needed); guest w/o selection→prompt | YELLOW (test/real divergence) |
| 6 | `Analyze Photo` (only when bytes, `430-433,788-794`) | `_submitSelected:252-325` (guest→prompt, no POST; authed→multipart→202→processing) | fail→snackbar, stay | GREEN authed / RED guest-by-design |
| 7 | AppBar back (`391-402`) | `Navigator.pop` | back to Stylist | BLUE |
| 8 | Retry (error cards `679-683`) | `_initializeCamerasAndController` | re-init | GREEN |
| 9 | SCAN-002 `View Results` (`246-259`) | `pushNamed(scanAnalysis, snapshot??status)` | forwards live snapshot | GREEN |
| 10 | SCAN-002 `Back to Scan` (`263-270,276-294`) | `context.pop` | back to SCAN-001 | BLUE |
| 11 | SCAN-003 back (`44-50`) | `Navigator.pop` | back to processing | BLUE |
| 12 | SCAN-003 share (`52-69`) | snackbar `Share feature coming soon` | nothing | GRAY |
| 13 | SCAN-003 `Save Profile` (`537-562`) | guest→prompt; authed→snackbar `Appearance profile saved` | NO repo/client/DB write | GRAY (authed) / RED (guest gate) |
| 14 | SCAN-003 `See Recommendations` (`565-573`) | `pushNamed(dailyOutfit)` (`/home/daily-outfit`) | no extra forwarded | GREEN nav / YELLOW context loss |
| — | Retake/Clear on SCAN-001 | DOES NOT EXIST (grep: only wardrobe/hairstyle/onboarding have `_retake`) | overwrite-only | RED gap |
| — | Save/Retry/Retake on SCAN-003 | DO NOT EXIST | system-back ×2 to rescan | RED gap |
| — | Static `Lighting/Framing/Posture` checks (`703-714`) | hardcoded, unwired to vision | always same | YELLOW |

# 4 Flutter Navigation

- Names (`route_names.dart:25-27`): `scanOutfit='scan-outfit'`, `scanProcessing='scan-processing'`, `scanAnalysis='scan-analysis'`.
- Routes (`app_router.dart:206-235`): `/stylist` → `scan-outfit` (`OutfitScanScreen`, no params/extra) → `processing` (`OutfitProcessingScreen(runId: extra as String?)`) → `analysis` (`OutfitAnalysisScreen(analysisResult: extra as Map?)`).
- Other entries: `home_screen.dart:493`, `first_time_home_screen.dart:120`, `first_time_light_path_home_screen.dart:122`, `profile_screen.dart:1041` (all `pushNamed(scanOutfit)`).
- Handoff shapes: processing receives `runId` ONLY (never bytes); analysis receives `result` snapshot (`processing_screen.dart:103 snapshot=data?['result'] ?? data`), not the envelope.
- Null-run pushes (guest-gate/fail/empty/test-mode → `processing` with null) land on honest `No run ID available` + `Back to Scan` (no request/timer).
- `401` during poll escapes to `goNamed(entry)`; `failed` stays with `Back to Scan`; `completed` auto-pushes AND offers `View Results` (duplicate path).
- No deep-link params; no `didUpdateWidget` on result (stale-extra risk, YELLOW).

# 5 State Management

No Provider/Riverpod/Bloc/GetX (`pubspec.yaml:30-43` deps: `go_router,camera,http,http_parser,image_picker,shared_preferences,flutter_secure_storage`; `main.dart` no `ProviderScope`). Outfit flow = `StatefulWidget+setState` + constructor-injected `OutfitScanClient` + static singletons (`AuthSession`, `LocalStorage`, `SecureTokenStorage`, `guest_mode`). Only `ChangeNotifier` in repo (`learning_service.dart:197`) is unused in this journey. Local UI state: `_isUploading/_statusMessage/_selectedImageBytes` (SCAN-001), `_runId/_runStatus/_isLoading/_errorMessage/_pollTimer` (SCAN-002), copied `analysisResult` (SCAN-003).

# 6 Image Input Pipeline

- Camera: `availableCameras()` → empty→`unavailable`; rear-first; `CameraController(medium, jpeg, enableAudio:false)`; `CameraException` code-substring `denied/accessdenied/permission`→`permissionDenied` else `error`; lifecycle disposes on inactive/paused, re-inits on resumed (preview bytes survive, live preview re-inits — YELLOW).
- Gallery: `pickImage(maxWidth/Height 1024)` (UX sizing only); cancel→silent return; empty→silent return; `XFile.fromData(bytes, name, mimeType:'image/jpeg')` — hardcoded jpeg even for `.png` (upload type later re-derived from filename, so preview/upload MIME can diverge — YELLOW).
- Capture: `takePicture→readAsBytes`; empty→null-run push; else preview (NOT auto-navigate — 2nd tap on Analyze required; test-mode diverges by navigating immediately — YELLOW).
- Preview: `Image.memory(bytes)` (web-safe, no `dart:io`); null/empty→placeholder.
- Validation (client): `bytes.isEmpty→null` only; NO max-size, NO format enforcement (filename→content-type mapping `jpg→jpeg/png→png/webp→webp/else jpeg` is transport hint only; server authoritative). Backend enforces `content_type ∈ {jpeg,png,webp}` + `size ≤ 20 MB` (declared-size) + non-empty/readable → 422.
- Failures: permission/unavailable/error cards w/ Retry (GREEN truthful); picker fail→snackbar w/ `connectionHint`; upload fail→snackbar, stay (no fake %).

# 7 Flutter Client/Service

`lib/features/outfit_scan/data/outfit_scan_client.dart` (`OutfitScanClient:27`; injectable `http.Client`, no `dispose` — cf. hairstyle/garment/grooming have one):

- `submitOutfitAnalysis(XFile):57-68` → `readAsBytes` → `submitOutfitAnalysisBytes`; catch→`debugPrint unreachable` + null.
- `submitOutfitAnalysisBytes:72-112`: empty→null; `POST $baseUrl/v1/analysis/outfit` multipart field **`image`** (`fromBytes`, filename, `MediaType` from suffix); `Authorization: Bearer <AuthSession.effectiveToken('dev')>` always (even logged-out → `Bearer dev`); `send(...).timeout(30 s)` + `fromStream(...).timeout(30 s)`; `noteStatus(code)`; `202→jsonDecode→run_id`, else `debugPrint code+body` → null. ALL non-202 (401/403/404/413/422/500/timeout/network/JSON) collapse to null.
- Sole production caller: `outfit_scan_screen.dart:271` in `_submitSelected`.
- `getAnalysisRun:117-140`: `GET $baseUrl/v1/analysis/runs/{id}` same Bearer, 30 s; `noteStatus`; `200→(200, decoded Map?)`, else bare `(code)`; catch→`(0)` + debugPrint.
- Peer divergences: grooming POSTs JSON (no image) with 12 s timeout; garment enforces 20 MB client-side (+ UI pre-check); hairstyle allows profile-only empty multipart; garment/hairstyle/grooming have typed run parsers, outfit is bare `(code,data?)`.

# 8 HTTP Contract

- `POST {base}/v1/analysis/outfit` · `Authorization: Bearer <session|dev>` · `Content-Type: multipart/form-data` · field `image=@file (jpeg/png/webp)` → `202 {run_id: string}`; non-202 → client null (no per-code copy).
- `GET {base}/v1/analysis/runs/{run_id}` · same auth → `200 {run_id,run_type?,status: pending|processing?|completed|failed, result?:{appearance:{faceShape?,skinTone?,bodyType?,styleType?},confidence?,needs_more_data?,recommendations?:{top?:{name?,description?,matchScore?,reasons?[],stylingTips?,maintenance?,bestFor?}}}, error?: string|{code,message,details}}`; else bare code; `0` = unreachable.
- `baseUrl = AppConfig.apiBaseUrl` (default `localhost:8000`); `connectionHint` distinguishes emulator loopback vs generic.
- Timeouts: Flutter 30 s (send+collect) > backend vision 20 s > provider call; proxy/nginx 90 s (per Phase 4A).

# 9 FastAPI Route

`backend/app/api/routers/analysis.py:49,195-229`:

- `POST /outfit` (`response_model=AsyncAccepted`, `status_code=202`, OpenAPI declares 401/413/422/503) — `def` (sync, NOT async; no `BackgroundTasks`/queue — 202 is semantic, work completes in-request).
- Validation BEFORE anything: `content_type ∉ {image/jpeg,image/png,image/webp} → 422` (`212-215`); `image.size > 20 MB → 422` (`216-219`, declared-size only).
- Wiring (`220-227`): `CreateOutfitRun(runs, knowledge, appearance_port=OllamaVisionAppearanceAdapter() [always injected — dev/hash default unreachable in prod], user_state, learning_signal, activity_days)` → `run_id = use_case(...)` → `AsyncAccepted(run_id)`.
- `GET /runs/{run_id}` (`130-143 → GetAnalysisRun`): owner-scoped, foreign/missing→404 (not 403); `GET /runs` (`146-165`) list summaries WITHOUT `result/error`.

# 10 Authentication/Authorization

- Flutter: `AuthSession.effectiveToken('dev')` session-first; `noteStatus(401)→notifyUnauthorized` (clear token, fire expiry once). Guest = `!isAuthenticated && savedLocally` (`guest_mode.dart:19`).
- Backend: `get_current_user_id` (`deps.py:58-85`) — missing/non-`Bearer`/empty/unresolvable→401 (`errors.py:68-73` + `WWW-Authenticate`); dev-token only if `allow_dev_token`.
- Gates: Stylist tile none (browse free); `_submitSelected`/`_handleCapture`(no-selection)/`Save Profile` → `promptGuestSignIn` + return (no POST — class-D, nothing replayable); processing null-guard (no poll); poll-401→snackbar + `goNamed(entry)`; run retrieval owner-scoped (`WHERE id AND user_id`); cross-user→404 indistinguishable from missing (OW-1, by design). Guests persist only locally (`LearningService`+`LocalStorage`); post-auth merge/keep/discard, never silent.

# 11 Backend Business Flow

`CreateOutfitRun` (`backend/app/application/analysis.py:169-341`):

1. Re-validate (type + 20 MB → 422) — duplicate of router (defense-in-depth).
2. `read_image_bytes` (empty/unreadable→422) + `build_media_ref` (`media.py:66-93`: `key=users/{id}/scans/{uuid}/input.{ext}`, mediaType, sizeBytes, **SHA-256**, `analyzer="ollama-vision-v1"`; bytes hashed then discarded, never persisted/logged).
3. DB #1: `runs.create(user_id, run_type="outfit", engine_version="vision-v1", input_media, knowledge_version=provenance() "1.1+1.0")` → `status='pending'`, id = `gen_random_uuid()`.
4. AI: `appearance_port.analyze(...)` → `AppearanceAnalysisError(reason)`→`fail(PROCESSING_FAILURE+details.reason)` + return (still HTTP 202); bare `Exception`→same without reason. NEVER a stuck pending.
5. Engine: `build_context` → **`recommend_hairstyle`** (`analysis_rules.py:418`) → exception→`fail(PROCESSING_FAILURE)`. (No outfit-specific recommender — S-1 reuses face→hairstyle catalog.)
6. DB #2: `complete(run_id,user_id,'completed',result=snapshot)`; `False`→500 `DATABASE_FAILURE`. Result = `HairstyleResult.to_snapshot()`; error = `{code,message,details:{run_id,reason?}}` with `reason ∈ {no_face_detected,ambiguous_subject,analyzer_unavailable,analyzer_timeout,low_confidence,invalid_analyzer_response}`.
7. DB #3 (TRX-6): `update_style_profile(face_shape,skin_tone,body_type,style_type,source_run_id)` — wholesale 5-key replace (`repositories.py:220`).
8. DB #4-6: `insert_look_saved("analysis_updated",{run_id,run_type:outfit})` + `insert_look_saved("outfit_selected",{source_context:outfit,run_id,run_type:outfit})` (verbatim codes; comment: lifecycle, not UI selection) + `mark_styled_today` upsert — ONE `commit()`.
- Timestamps: `created_at=now()` default; `completed_at=now()` inside SQL guards; write-once `WHERE status='pending'` (TRX-5); `pending` observable only on crash between create and terminal write. Status CHECK = `{pending,completed,failed}` — no `processing` value exists.

# 12 AI/Vision Pipeline

Adapter: **`OllamaVisionAppearanceAdapter`** (`backend/app/ai/vision_appearance_adapter.py`; `ADAPTER_ID="ollama-vision-v1"`). (Garment adapter is `/garment`-only — must not be confused.)

- Config (`settings.py:66-82`): `FANSIVIBE_VISION_HOST` (default `http://localhost:11434`), `FANSIVIBE_VISION_MODEL` (default `llama3.2-vision` — deployment MUST override with vision-capable model, e.g. `qwen2.5vl:3b`), `FANSIVIBE_VISION_TIMEOUT_S` (default `20.0`, whole-client), `FANSIVIBE_DISABLE_VISION` (kill-switch → `analyzer_unavailable`, no I/O; legacy `=1` honored).
- Request (`121-141`): `POST {host}/api/chat` `{model, stream:False, format:"json", options:{temperature:0}, messages:[{role:user, content:prompt, images:[b64]}]}` via `httpx.Client(timeout)`. Single attempt — NO retry loop (cf. reasoner `1+max_retries`).
- Prompt (`83-93`): face only — STRICT JSON `{"face_shape":"<label>","confidence":0-1}`, label ∈ `{oval,round,square,heart,diamond,rectangular}`, `no_face`/`ambiguous` verdicts.
- Parse/normalize (deterministic): `_normalize_face_shape` (lower/strip, `rectangle→rectangular` alias, `no_face→no_face_detected`, `ambiguous→ambiguous_subject`, else `invalid_analyzer_response`); `_parse_confidence` (bool rejected, must be 0-1); floor `LOW_CONFIDENCE_FLOOR=0.35` → `low_confidence`; transport `Timeout→analyzer_timeout`, `Connect/HTTP→analyzer_unavailable`, other→`analyzer_unavailable`. No fallback shape.
- Output (`232-238`): `AppearanceProfile(faceShape=<measured>, skinTone="", bodyType="", styleType="", sourceRunId="")` — **only face_shape measured; other three are `""` by design** (dev/hash adapter generates all four but is never injected on this path).
- Post-AI deterministic: `build_context` + `recommend_hairstyle` (face-shape boosts `_BOOSTS`, face reason prepended, `_completeness`→confidence/`needs_more_data`); image bytes ephemeral (b64 in-memory, never logged/persisted; test asserts no leak).
- CODE EXISTS (verified) vs PROVIDER AVAILABLE (unknown — `docker-compose` points at `http://ollama:11434` with no model seed; `.env.example` defaults `DISABLE_VISION=true`; no live call per instructions) vs VERIFIED RESULT (not verified).

# 13 Processing/Polling

- Client `getAnalysisRun` (§7); UI `_pollRunStatus({attempts=0})` (`outfit_processing_screen.dart:63-184`): `_pollInterval=3 s`, `_maxPollAttempts=30`.
- Null/empty runId → no request/timer, `No run ID available` + `Back to Scan`.
- `attempts>=30` → `Analysis polling timed out` (honest, manual retry only).
- `200`: store `_runStatus`, `completed→pushNamed(scanAnalysis, snapshot??data)` (+ duplicate `View Results` path); `failed→SnackBar('Analysis failed: …')` + stay (`Back to Scan` owns recovery).
- `401→SnackBar('Authentication error, please re-scan')` + `goNamed(entry)` (session already cleared).
- Else: `0→connectionHint`, `429→'Too many requests…'`, `elapsed>20 s→'Still analyzing…'`, else `'Server returned X, retrying…'` (404/500 retried to exhaustion — cf. garment stops on 404; YELLOW).
- Reschedule: single `Timer?` backoff `3 s×2^min(attempts,4)` = 3,6,12,24,48,48… (ceiling undocumented in UI — YELLOW; indeterminate spinner + `>20 s` copy mitigates); `dispose→cancel`; `mounted` guards; no user-cancel button; terminal statuses `completed/failed` stop.

# 14 Result Parsing

**No typed `OutfitAnalysisResult.fromJson/toJson` exists.** Only `OutfitAnalysisRunResult(statusCode,data?)` with `isCompleted/isFailed` and brittle `error => data?['error'] as String?` (**throws `TypeError` when backend sends Map error** — cf. garment `failureReason` Map-parse; YELLOW/RED latent crash on failed-run detail read).

Real parsing = ad-hoc raw-Map (`outfit_analysis_screen.dart:32-38,140-143,249-252`):

| UI var | JSON key | Dart type | Default/transform |
|---|---|---|---|
| appearance | `appearance` | `Map?` nullable | — |
| confidence | `confidence` | `(??0.0) as double` — **throws if int** | `×100 %` |
| needsMoreData | `needs_more_data` | `bool? ?? false` | badge |
| recommendations/top | `recommendations[.top]` | `Map?` | card |
| faceShape/skinTone/bodyType/styleType | `appearance.*` camelCase | `String?` each | `Not detected` if null/empty |
| name/description | `top.*` | `String?` | `??'Recommended Look'/''` |
| matchScore | `top.matchScore` | `(??0.0) as double` | bands ≥0.9/0.8/0.7 |
| reasons | `top.reasons` | `List?` | `toString()` each |
| stylingTips/maintenance/bestFor | `top.*` | dynamic via `_notEmpty` | verbatim |

Mock types (`outfit_scan_mock_data.dart`: `DetectedClothingItem/AnalysisSection/OutfitAnalysisData`) are mock-only, never parsed. Typed peers exist (hairstyle `AnalysisRun.fromJson` + `hairstyleResultFromRun` with `??` guards; garment strict `fromJson` with vocab check) — outfit is the untyped outlier (B).

# 15 Result UI

`OutfitAnalysisScreen` (`outfit_analysis_screen.dart`, 621 lines): responsive (`>600 px → 48 px gutter/560 max`), `SingleChildScrollView`, sections — appearance-profile chips (`_buildAppearanceProfile:134-243`: face/skin/body/style + `Confidence %` + `Needs more data` badge), recommendation card (`245-367` + `_buildMatchScore:369-416`), `Detected Attributes` rows (`422-480`), **`Analysis Details` static header + `Face and appearance attributes analyzed above` + empty `SizedBox` (`511-530`) — never renders `DetectedItemChip/AnalysisSectionCard/mock`** (`outfit_scan_widgets.dart:137-445` + mock data = dead, YELLOW). Result content = appearance profile + hairstyle recommendation (NOT garment list — doc-implied outfit analysis is actually face analysis; conflict §4 vs code).

# 16 Save/Recommendation Actions

| Button | Handler → service → API → DB | Class |
|---|---|---|
| Save Profile | guest→`promptGuestSignIn`+return; authed→snackbar only. NO client/repo/HTTP/`LocalStorage` write anywhere in file | GRAY (authed fake-save) / RED gate (guest) |
| See Recommendations | `pushNamed(dailyOutfit)` (`/home/daily-outfit`, `DailyOutfitScreen` refetches independently) — snapshot NOT forwarded | GREEN nav / YELLOW context loss |
| Share | snackbar `coming soon` — no Share API/DB | GRAY |
| Back (AppBar) | `Navigator.pop` → processing | BLUE |
| Save / Retry / Retake | DO NOT EXIST | RED gap (vs hairstyle `_retake`, wardrobe `_retake`) |

Note: server profile WAS already persisted by TRX-6 at completion — `Save Profile` adds nothing even if wired; honest wiring = save the LOOK (`POST /v1/looks/saved`) or confirm it visibly.

# 17 Database Flow

Caused by one Scan (authed, success): `analysis_runs` INSERT(pending) → complete(completed+result) → `user_state` TRX-6 replace → `learning_signals` ×2 + `activity_days` upsert (one commit). Reads: `GET /runs/{id}` (owner-only), `GET /runs` (summaries w/o result/error). Untouched: `saved_looks`, `wardrobe_items`, `user_events`, `user_sessions`, `users` (owner FK only). Image bytes never persisted (hash only). Details per table §§18-22.

# 18 analysis_runs

Columns (`models.py:174-209`; `0001:203`, `0002:56`, `0010:27`): `id UUID PK gen_random_uuid()`, `user_id UUID FK users CASCADE NOT NULL`, `run_type TEXT FK run_types RESTRICT NOT NULL`, `status TEXT NOT NULL default 'pending' CHECK(pending/completed/failed)`, `engine_version TEXT NOT NULL` (repo default `rules-v1`; outfit writes `vision-v1`), `knowledge_version TEXT NULL` (NULL=unknown legacy), `input_media JSONB NULL` (`{key,mediaType,sizeBytes,contentHash,isGenerated,uploadedAt,analyzer}`), `result JSONB NULL` (snapshot §11), `error JSONB NULL` (`{code:PROCESSING_FAILURE,message,details:{run_id,reason?}}`), `created_at now()`, `completed_at NULL→now()` via SQL fns, indexes `(user_id,created_at)`, `(user_id,run_type,created_at)`.
Lifecycle: `created(pending,outfit,vision-v1)` → sync AI+engine → `completed(+result)` or `failed(+error)` (write-once `WHERE pending`; `False`→500). Scan represented as `run_type="outfit"` (seed `0021:20`), `engine_version="vision-v1"`, `knowledge_version="1.1+1.0"`. Retrieval owner-scoped; list omits result/error; retention — no TTL/purge in code/migrations (I: not visible).

# 19 user_state/style_profile

Table `user_state` (`models.py:111-124`; `0001:158`): `user_id PK FK users CASCADE`, `style_profile JSONB NOT NULL '{}'`, `preferences JSONB '{}'`, `flags JSONB '{}'`, `version INT ≥0`, `updated_at`. Profile keys are free JSON (`face_shape,skin_tone,body_type,style_type,source_run_id`) — no DB columns, nullable-by-absence.
Create: `create_account` + dev seed (empty `{}`). Update: ONLY `CreateOutfitRun:307-315` + `CreateHairstyleImageRun:496` via `update_style_profile` (wholesale 5-key replace — drops sibling keys outside the five). Read: NEVER by outfit flow; readers = `CreateHairstyleRun:117` + `CreateGroomingRun:591` (`!face_shape→422 INSUFFICIENT_USER_DATA`), `GetProfile→GET/PATCH /me` (`StyleProfile{faceShape,skinTone,bodyType,styleType,sourceRunId}`). Flutter scan never calls `GET /me`; `ProfileScreen` reads local `LearningService.face`+`LocalStorage` (`profile_screen.dart:314`).

# 20 learning_signals

Columns (`models.py:247`; `0001:252`): `id PK`, `user_id FK CASCADE`, `signal_type FK signal_types RESTRICT`, `label 1..200`, `context JSONB NULL`, `occurred_at now()`; index `(user_id,occurred_at)`.
Scan writes 2 rows post-complete + 1 commit: `analysis_updated {run_id,run_type:outfit}` + `outfit_selected {source_context:outfit,run_id,run_type:outfit}` (`analysis.py:322-339`; `outfit_selected` = run-lifecycle, not UI tap). Scan reads none. Consumers: `GetLearningSummary→list_recent_labels(20)` surfaces labels only; score uses counts only; `resolve_preferred_item_ids`/`get_outfit_coverage` read `saved_looks`, never signals. Signals are write-mostly history (F).

# 21 saved_looks

Columns (`models.py:212`; `0001:229`, `0009:33`): `id PK`, `user_id FK CASCADE`, `look_id FK looks SET NULL NULL`, `title 1..200`, `source_context NULL CHECK(hairstyle,grooming,outfit,daily)` (nullable legacy; new writes must supply), `snapshot JSONB NOT NULL`, `idempotency_key NOT NULL + UQ(user_id,key)`, `source_run_id FK runs SET NULL NULL`, `created_at`. **Scan flow: zero reads/writes** (`CreateOutfitRun` has no saved_looks dep; result `Save Profile` does no HTTP — cf. `HairstyleService.saveLook→POST /looks/saved sourceContext hairstyle`, `AssistantService.saveOutfit→sourceContext outfit`). Saves live on other surfaces (`POST /v1/looks/saved→SaveRecommendation+look_saved`; `POST /v1/outfits/saved` outfit-validated). Readers of saves (hairstyle prefs, outfit coverage) never run inside scan. (G: backend save exists, scan UI doesn't consume it.)

# 22 wardrobe_items

Columns (`models.py:410`; `0006:21`): `id PK`, `user_id FK CASCADE`, `name`, `category_id FK RESTRICT`, `color_id FK RESTRICT`, `material_id NULL FK`, `is_favorite default false`, `image_ref JSONB NULL`, `created/updated`. **Scan: no import, no dep, no read, no write.** Recommendation derives from image only. (Contrast `GenerateOutfit` — Build Outfit, not Scan — reads all owned items + `preferred_occasions` read-only; `SaveOutfit` validates component IDs.) Wardrobe data exists but scan doesn't consume it (F — or I if product never intends scan↔wardrobe; owner decides).

# 23 Analyze My Style → Outfit Analysis Dependency

Verdict: **no forward dependency exists. Scan never reads the stored profile; it is image-only. The reverse (Scan→profile→future hairstyle/grooming) is the only wired direction.**

Prod adapter generates ONLY `face_shape` (others `""` by design); dev/hash adapter generates all four but is never injected (router asserts). Engine: `""→default "oval"` (`analysis_rules.py:220`) + per-shape boosts; `_completeness`→confidence/`needs_more_data`.

| Field | Generated by Scan? | Stored? | Read by Scan? | To AI / deterministic? | Display? | NULL/empty |
|---|---|---|---|---|---|---|
| face_shape | yes (measured or `failed`) | yes TRX-6 | NO | yes — lower→default `oval`, `_BOOSTS`, reason prepended | chip | empty impossible on prod success (fails `no_face/ambiguous/low_confidence/invalid/unavailable/timeout`); dev-empty silently→`oval` (no guard — cf. hairstyle-image `:446` fails) |
| skin_tone | no (prod `""`) | stores `""` verbatim | NO | completeness only | chip / `Not detected` | `""`→completeness↓, `needs_more_data`, confidence↓ |
| body_type | same | same | NO | same | same | same |
| style_type | same | same | NO | same | `Style Vibe` chip | same |
| hair/* | nowhere in models/value_objects/rules/`FaceProfile`/`StyleProfile`; beard opts are UI-only, never persisted | NO | NO | unused | unused | N/A |
| whole appearance | output echoes profile + `sourceRunId` | via TRX-6 | NO | `build_context` + `recommend_hairstyle` | snapshot→`scanAnalysis`, ad-hoc parse | sparse→banner, never blocks |

Stored Analyze-My-Style `face_shape` is a write-only sibling to Scan, never an input. Scan's write makes the profile reusable for LATER hairstyle/grooming without re-capture (docstring `:182`).

# 24 Personalization Data Inventory

- System/canonical (§25): vocab tables + versions + boost maps — never user.
- User facts (§26): `users`, `style_profile` (AI-inferred TRX-6), `wardrobe_items`, `saved_looks`, `user_events` — server truth.
- Preferences (§27): `preferences.preferred_occasions` only — user-stated.
- Observations (§28): `analysis_runs` (all statuses), `learning_signals` (incl. scan pair), `activity_days`, `feedback_events`, `wear_events/groups` — append-only history.
- Temp (never persisted): image bytes (hashed→dropped), `XFile/Uint8List` previews, multi-angle captures, `PendingAuthIntent` (single-slot LocalStorage, 24 h), in-memory `LearningService` until `LocalStore`, mock fallbacks, poll timers.
- Rule honored: no recommendation to stuff every AI observation into the permanent profile; current architecture keeps observations in run/signal history, profile to 5 keys.

# 25 Fixed/System Data

`run_types` (incl. `outfit` 0021, `garment` 0022), `signal_types` (`look_saved,analysis_updated` 0001; `outfit_selected` 0008), `looks`, `wardrobe_categories`, `colors`, `materials`, `event_types`; `engine_version` (`vision-v1` outfit), `knowledge_version` (`1.1+1.0` = catalog 1.1 + OI 1.0); `_BOOSTS/_GROOMING_BOOSTS`, `_FACE_SHAPE_ALIASES`, `LOW_CONFIDENCE_FLOOR=0.35`, canonical face-shape set. All ownerless by design (RESTRICT-vocab FK policy).

# 26 User Profile Data

`users` (identity root) + `user_state.style_profile` 5 keys (AI-inferred, TRX-6 from Scan AND HairstyleImage) + `wardrobe_items` + `saved_looks` (user-confirmed) + `user_events`. Scan WRITES profile, never reads it; reads of profile happen in hairstyle/grooming use-cases + `GET/PATCH /me`; Flutter scan/profile screens read local mirrors, not server. All profile JSON keys nullable-by-absence (`{}` default).

# 27 User Preference Data

Only `user_state.preferences.preferred_occasions` (user-stated). Writers: `PATCH /me` merge (`||`), R36 event path, Flutter `syncPreferredOccasion` append-if-absent. Reader: outfit BUILDER (`_preferred_occasions`, `_get_suitable_occasions`) — never Scan. Flutter Scan sends no prefs; prefs screen guest path is device-only. Colors/fit/saved-looks/feedback: exist as wardrobe/signal/look data but are NOT consumed by Scan (F).

# 28 Analysis Observation Data

Per-run temp→persisted-history: detected `face_shape` (+`""` skin/body/style from prod adapter), `confidence`, `needs_more_data`, `recommendations.top/alternatives[]`, `matchScore/reasons/stylingTips/maintenance/bestFor`, `input_media` hash/key/analyzer, `error{reason}` on failure. Persisted in `analysis_runs.result/error` (full) + projected 5 keys into `style_profile` (TRX-6) + 2 signal rows + styled-day. Image bytes temp-only. `pending` rows only on crash. `GET /runs` list intentionally omits result/error (summaries).

# 29 Guest vs Authenticated

`isGuestUser = !isAuthenticated && savedLocally`; shell incl. `/stylist/*` browsable; `/assistant,/reasoning` blocked; writes gated at buttons (class-D, no auto-POST).

| Action | Guest | Authed |
|---|---|---|
| Browse SCAN-001 | allowed | allowed |
| Capture/gallery | renders; no-selection capture→prompt; test-mode bypass→null-run | bytes→preview→Analyze |
| Analyze POST | BLOCKED at button (prompt, no HTTP, no run; intent recorded, no replay) | multipart→202 or error snackbar |
| Poll/result | null→`No run ID available`, no poll; 401→entry | 3 s×30 backoff; completed→analysis; failed→inline; timeout→honest |
| Save Profile | BLOCKED (prompt) | snackbar-only (no persistence call; TRX-6 already wrote server profile) |
| Profile/prefs | local-only + post-auth Merge/Keep/Discard | server `GET/PATCH /me` + local hydration |
| Signals/persistence | zero server rows | full lifecycle §§17-20 |

Hairstyle counterpart is stricter (guest `GuestSignInCard`, never-submit).

# 30 Security/Ownership

- JWT-first (`get_current_user_id`); `Bearer dev` fallback only where `allow_dev_token` (prod-false); `effectiveToken` session-wins; `noteStatus(401)` clears + fires expiry once.
- Runs: `WHERE id AND user_id` on get/complete/fail/list — cross-user→404 (indistinguishable from missing; OW-1 accepted pattern). `saved_looks` UQ `(user_id,idempotency_key)`; `looks/wardrobe_categories/colors` RESTRICT (no orphan); `user_*` CASCADE (account delete purges).
- No cross-user read path found in scan flow; no token/image/PII logging (bytes hashed, b64 ephemeral, tests assert no leak; `connectionHint` only).
- Gaps (report-only): `register_idempotency_key` no UQ (app-enforced race window — pre-existing F4…F6 class); `wear_group_id` no FK (pre-existing); `error as String?` client cast can throw on Map errors (latent crash, B); `oval`-default on empty face_shape via dev/stub path (fabrication guard absent on outfit path only).

# 31 Error Handling

| Code | Backend | Flutter surface (honest?) |
|---|---|---|
| 401 submit | `AUTHENTICATION_ERROR` + `WWW-Authenticate` | guests never POST; logged-in 401→generic `Upload failed. <hint>` + session cleared (yes) |
| 401 poll | same | `Authentication error, please re-scan` + `goNamed(entry)` (yes) |
| 403 | none by design (foreign→404) | n/a |
| 404 poll/GET | `NOT_FOUND` (foreign∨missing) | `Server returned 404, retrying…` → timeout (retried; YELLOW — garment stops) |
| 409 | none on analysis surface | n/a |
| 413 | declared-only, unreachable (oversize→422) | no pre-check (cf. garment 20 MB); oversize surfaces as generic upload-fail (B doc-bug) |
| 422 | bad type / >20 MB / unreadable-empty / bad UUID / missing part | generic `Upload failed/error + hint` (no per-code copy; B) |
| 500 | `complete False→DATABASE_FAILURE` (+request_id) | generic poll/upload fail (yes) |
| 503 | declared-only; vision fails→`failed` RUN not HTTP 503 | n/a (correct fail-closed) |
| timeout/network | n/a (sync in-request; adapter 20 s) | submit→`Upload failed + hint` (emulator loopback hint); poll `0→hint`, `>20 s→Still analyzing` (yes) |
| AI fail | terminal `failed` + `details.reason` (6 reasons) | `Analysis failed: …` + inline + `Back to Scan` (yes; NOTE Map-vs-String `error` mismatch) |
| poll timeout | n/a | `Analysis polling timed out` (yes) |
| cancelled input | n/a | silent return (yes) |
| invalid image | 422 before run | empty→null-run / upload-fail (yes) |

No mock success anywhere on this path (verified: no mock fallback in outfit client/processing/analysis; dead mocks are unused).

# 32 OSI Findings

- L7 application/business: result IS hairstyle snapshot, not outfit/garment (B — works, mislabeled); `Save Profile` fake-save (GRAY); `See Recommendations` context loss (YELLOW); no Retake/Retry (RED gap); `oval`-default via stub path (YELLOW); `outfit_selected` semantic = lifecycle not tap (YELLOW naming).
- L6 data/serialization: untyped result parse + `as double` int-throw + `error as String?` Map-throw (YELLOW/RED latent); `snapshot??envelope` forwarding (GREEN); `needs_more_data`/`confidence` degrade honestly (GREEN); preview/upload MIME diverge (YELLOW); 413-declared-never-raised / 503-declared-never-raised doc-bugs (YELLOW).
- L5 session/state: `setState` + singletons (GREEN — matches approved approach); no `didUpdateWidget` (YELLOW); single-timer poll w/ cancel + mounted guards (GREEN); backoff ceiling undocumented (YELLOW); TRX-6 wholesale replace drops extra keys (YELLOW); one-commit signals+day (GREEN).
- L4 HTTP/transport: multipart `image` + Bearer + 30 s > 20 s budget (GREEN); all-non-202→null collapse loses per-code UX (YELLOW); poll retries 404/500 to exhaustion (YELLOW); no idempotency key on analysis POST (reported pre-existing risk).
- L3 connectivity: `connectionHint` (emulator vs generic), `statusCode 0` path, `>20 s` copy (GREEN).
- L2/L1 device/input: camera/gallery/preview/permission/cancel/empty handling (GREEN); no-Retake (RED gap); static posture checklist (YELLOW); test-mode/real divergence (YELLOW).

# 33 Automated Test Coverage

Flutter (`test/`): `outfit_scan_screen_test` (render + test-mode nav), `outfit_processing_screen_test` (spinner/initial), `outfit_analysis_screen_test` (Map-fixture render incl. share stub), `outfit_scan_client_test:60-183` (multipart URL/auth, 202→run_id, 422→null, empty fail-closed, dev-fallback/session-wins, 401-clears+fires, hygiene no-localhost), `guest_phase2_test:358-374` (null-run honest, no poll), `auth_flow_regression:205-296,328` (token plumbing, `See Recommendations→dailyOutfit` nav), `router_auth_guard_test:73` (shell browsable), `photo_capture_screen_test` (Analyze-Style camera≠gallery pattern proof), `preferences_sync_test`, `guest_auth_conversion_test:476` (adjacent gates).
Backend (`backend/tests/`): `test_outfit_image_router` (contract w/ fakes: gif→422 no-run, no_face/boom→terminal `failed`+reason, no byte leak, foreign→404), `test_analysis_use_case` (TRX-6 5-field write, signal pair, gif/50 MB→422, SHA-256), `test_analysis_api` (202→completed, list contains outfit, no-token→401, foreign→404 — DB-gated, skipped w/o PG), `test_vision_appearance_adapter` (normalize/floor/transport mapping), `test_analysis_rules`, `test_garment_analysis`, `test_get_profile`, `test_update_preferences`.
What each ACTUALLY proves: shapes/contracts/fail-closed/single-fetch/loading-render/null-run honesty. What each does NOT prove: live provider, live DB E2E here, or UI wiring beyond fixtures.

# 34 Missing Test Coverage

- Widget: guest gates on `_submitSelected`/`_handleCapture`/`Save Profile` (`isGuestUser=true`); poll edge UI (backoff, 30-attempt timeout, `failed` inline, 401→entry, 429/0/`>20 s` copies, completed→analysis with snapshot-vs-envelope); failed/timeout via MockClient; `Save Profile` asserting NO HTTP (locks honest-noop or fails post-wire); int-`confidence`/Map-`error` robustness; Retake absence (locks gap until added).
- Client: 30 s timeout path; retry/idempotency (none exists — locks current).
- Backend: already strong on contract; live face-photo success unproven (needs real selfie + provider — owner live-test).
- Cross: Analyze-Style→Outfit read (asserts non-read — locks image-only design); wardrobe/prefs/signals non-consumption by scan (locks F); post-auth return to `/stylist/scan-outfit` without auto-POST.

# 35 Live Test Matrix

(Status = expected CURRENT behavior — owner to fill ACTUAL.)

| # | Action | Expected current | Actual / Status |
|---|---|---|---|
| 1 | Authed opens AI Stylist | renders hero `Scan My Outfit` | _ / _ |
| 2 | Tap Scan My Outfit | `/stylist/scan-outfit`, camera or denied-card | _ / _ |
| 3 | Camera capture | preview stays (2nd tap Analyze needed) | _ / _ |
| 4 | Gallery pick | preview + `Photo selected` | _ / _ |
| 5 | Valid face image → Analyze | `Uploading…` → processing → (provider up: completed→analysis w/ face chip + rec; down: `failed`+reason) | _ / _ |
| 6 | Processing | spinner → auto-advance or `View Results` | _ / _ |
| 7 | Polling (slow) | `>20 s→Still analyzing…`; 30 tries→timeout | _ / _ |
| 8 | Result | appearance chips + rec card; `Not detected` for skin/body/style (prod) | _ / _ |
| 9 | Retake | MISSING — system-back ×2 | _ / _ |
| 10 | Save Profile | snackbar only (verify NO new saved_look; profile already TRX-6'd) | _ / _ |
| 11 | Back | pops to processing → scan | _ / _ |
| 12 | Retry after failure | `Back to Scan` manual resubmit only | _ / _ |
| 13 | Analyze My Style first, then Outfit | both write profile; outfit does NOT read prior profile (verify second result independent of first) | _ / _ |
| 14 | Outfit after style profile exists | same as 13 (no personalization delta) | _ / _ |
| 15 | Empty profile user | works (image-only); `needs_more_data` likely true | _ / _ |
| 16 | User WITH wardrobe | no wardrobe influence on result (verify) | _ / _ |
| 17 | User WITHOUT wardrobe | same result shape | _ / _ |
| 18 | With preferences | no influence (verify) | _ / _ |
| 19 | Without preferences | same | _ / _ |
| 20 | Network unavailable | `Upload failed. <hint>` / poll `0→hint` | _ / _ |
| 21 | Vision provider down (`DISABLE_VISION=1` or host dead) | terminal `failed` + `analyzer_unavailable`, honest copy | _ / _ |
| 22 | Token expiry mid-poll | `Authentication error, please re-scan` → `/entry` | _ / _ |
| 23 | Logout/login | runs persist per-user; foreign run→404 | _ / _ |
| 24 | Repeat scan | new `run_id`, new row, profile overwritten (latest wins) | _ / _ |

# 36 Existing Architecture Connection Opportunities

(Only C/F/G — no redesign. Each maps existing→existing.)

1. **C/G-1 `Save Profile` → existing save APIs.** UI exists (GRAY), backend exists (`POST /v1/looks/saved` w/ `source_context='outfit'` + `source_run_id`; `PATCH /me` prefs). Wire button to one (product picks: look-save = snapshot archive; profile-save = already done by TRX-6, so button should be relabeled or save the LOOK). No new endpoint/table.
2. **C-2 `See Recommendations` context.** `DailyOutfitScreen`/`GetTodayLook` exist. Forward `run_id` or snapshot as route extra (already the `processing→analysis` pattern) so recommendations build on THIS analysis instead of refetching. No new API.
3. **C-3 Retake/Retry.** Pattern exists (`face_scan_screen:243`, `wardrobe_photo_screen:189`). Copy clear-and-reshoot + result-retry into SCAN-001/003. No new service.
4. **F-1 Stored `face_shape` → future personalization.** TRX-6 profile already written by Scan; hairstyle/grooming already read it. Any future outfit-personalization reads the same `GET /me` / `get_style_profile` contract — no schema change.
5. **F-2 Wardrobe/prefs/saved-looks → outfit context.** Data + reader patterns exist (`GenerateOutfit` reads wardrobe+prefs; `get_outfit_coverage` reads outfit-context saves). IF product wants scan-vs-wardrobe, the read side already exists — currently intentionally unused by Scan (confirm intent before wiring).
6. **F-3 Signals → future recommenders.** `analysis_updated`+`outfit_selected` already emitted with `{run_id,run_type,source_context}`; `GetLearningSummary` already surfaces labels. Any future consumer reads existing rows — no new signal needed.
7. **G-4 History/UI.** `GET /runs` + `GET /runs/{id}` + `GET /me` exist; scan UI consumes only the just-completed snapshot. A history/retry-from-history surface is pure UI work.
8. **B-fix (correctness, still connection-only):** type the Flutter result parse (mirror `hairstyle_models.dart`/`garment_models.dart`), fix `error as String?` Map crash + `as double` int crash, derive upload content-type from bytes not filename, stop polling 404 fast (mirror garment). No architecture change.

# 37 Blockers

- **D-1 Vision provider (runtime).** Real results require reachable Ollama (`FANSIVIBE_VISION_HOST`, default `localhost:11434`) serving a VISION-capable `FANSIVIBE_VISION_MODEL` (default `llama3.2-vision` is NOT installed per Phase 4A — override e.g. `qwen2.5vl:3b`) within 20 s. Kill-switch `FANSIVIBE_DISABLE_VISION=true` forces `analyzer_unavailable`. No code change unblocks this — owner provisions model/host or repoints env. (Phase 4A verified blank-image fail-closed live; real-face success still unverified.)
- **D-2 Live DB E2E unverified here.** `test_analysis_api` needs PostgreSQL; contract proven with fakes only in this investigation (no live POST per instructions).
- **B-1 Declared-never-raised codes (413/503)** mislead integrators; oversize→422 contradicts OpenAPI 413. Doc/annotation fix only.
- **B-2 Flutter `error as String?`** will throw on real Map errors the backend actually sends — blocks honest failed-detail display until typed.

# 38 Risks

- Mislabel risk: endpoint named "outfit" returns hairstyle recommendation — product/comms must not promise garment detection (garment path is separate `POST /garment`).
- `oval`-default on empty face via stub/dev path (no fail-closed like hairstyle-image `:446`) — prod adapter can't hit it (raises first), but any future adapter swap must preserve fail-closed.
- TRX-6 wholesale replace drops out-of-band profile keys — future writers must merge or coordinate.
- All-non-202→null collapse hides 401/413/422/500 distinctions from UX copy and diagnostics.
- Single-commit signals+day is correct; but nothing consumes signal TYPES yet — building "personalization" on label strings without a consumer contract risks placebo personalization.
- Pre-existing (not scan-caused): no idempotency key on analysis POST (double-tap→double-run); `register_idempotency_key` no UQ; `wear_group_id` no FK; model-only CHECK labels absent in DB.

# 39 What Is Already Complete

- Stylist tile → SCAN-001 → SCAN-002 → SCAN-003 navigation with typed extras (BLUE/GREEN).
- Camera/gallery/preview/permission/cancel/empty handling (GREEN).
- `POST /v1/analysis/outfit` multipart contract + auth + 202 `{run_id}` (GREEN).
- Sync `CreateOutfitRun`: validate→hash→create(pending)→vision→engine→complete/failed→TRX-6→signals+day→202 (GREEN).
- `OllamaVisionAppearanceAdapter`: prompt/normalize/floor/transport taxonomy/no-leak (GREEN code path).
- Owner-scoped `GET /runs/{id}` + write-once terminal states + honest `failed` reasons (GREEN).
- Poll with backoff/timeout/disposal/mounted-guards + honest null/timeout/failed/401 states (GREEN).
- Result render of appearance+recommendation + `Not detected` + `needs_more_data` (GREEN).
- Guest browse-free + button-gated honesty (GREEN by design).
- No mock success on path; errors surfaced (GREEN).
- Contract/use-case/adapter/client/auth tests (GREEN).

# 40 What Is NOT Complete

- `Save Profile` persists nothing (GRAY); `Share` stub (GRAY); no Save/Retry/Retake on result (RED gap); no Retake on capture (RED gap).
- `See Recommendations` drops context (YELLOW).
- Flutter parse untyped + two latent cast crashes (YELLOW/RED).
- Scan reads NOTHING back: no profile/prefs/wardrobe/saves/signals consumption (F by current design — personalization claim would be false today).
- Outfit-vs-garment: no garment detection in this flow (separate endpoint exists; this flow never calls it).
- Live layers unverified: provider availability, real-face success, live DB E2E (D).
- OpenAPI 413/503 declarations unreachable (doc-bug).
- Poll retries 404/500 to exhaustion; backoff ceiling undocumented (YELLOW).

# 41 What Must NOT Be Changed

Architecture freeze (per task): no new repos/API systems/backend services/DB models/migrations/AI providers/persistence/state-management/auth systems/duplicate pipelines. Specifically: do NOT replace `OutfitScanClient`/`CreateOutfitRun`/`OllamaVisionAppearanceAdapter`/`AnalysisRunRepositorySQL`/`UserStateRepositorySQL`/GoRouter shell/`AuthSession`/TRX-6/signal vocab/`knowledge_provenance`/Digital Atelier tokens/65-35 card rule. Do NOT install/provision Ollama, change model/prompts, add packages, create tables/columns, commit/push. Future work = connect existing components (§36) or owner-approved additions reported as "Missing / unsupported by current architecture".

# 42 Recommended Future Implementation Order

(PLAN ONLY — DO NOT IMPLEMENT without owner approval.)

1. **Correctness first (B, no product change):** type result parse (mirror hairstyle/garment models); fix `error` Map + `confidence` int casts; 404-stop poll; bytes-derived content-type; correct 413/503 OpenAPI annotations. Verify: `outfit_scan_client_test` + new parse/poll widget tests + `flutter analyze`.
2. **Honest buttons (C/G):** wire `Save Profile`→ existing look-save (or relabel to reflect TRX-6 auto-save) + assert-no-fake test; forward snapshot/run_id into `dailyOutfit`; replace `Share` stub with either real share or remove button (no dead UI). Verify: widget tests asserting HTTP + nav extras.
3. **Retake/Retry (C):** copy hairstyle/wardrobe retake into SCAN-001/003 + failed-state retry. Verify: widget tests.
4. **Read-back (G/F, product-gated):** surface `GET /me` profile + `GET /runs` history in result/history UI; ONLY then decide whether scan should consume wardrobe/prefs (confirm product intent — currently F, may be intentionally out of scope).
5. **Live verification (D):** owner provisions vision host+model → live matrix §35 (face photo, empty-profile, wardrobe/prefs variance, provider-down, token-expiry, repeat-scan) → record ACTUALs.
6. **Personalization consumer (product decision):** IF signals/profile are to drive recommendations, define the consumer contract first (which signal types, which fields, which fallback when NULL) — do NOT bulk-copy observations into profile. New-consumer design needs owner approval (may be I if unsupported).

---

## Appendix — Source index (spot-verified)

Flutter: `features/stylist/presentation/stylist_screen.dart:429-434,510` · `app/router/app_router.dart:206-235` · `route_names.dart:25-27` · `features/outfit_scan/presentation/outfit_scan_screen.dart:36,105-161,163-245,252-385,391-402,430-433,449-632,679-816` · `outfit_processing_screen.dart:13-61,63-184,187-307` · `outfit_analysis_screen.dart:10-38,44-69,134-243,245-367,369-480,511-576,579-596` · `data/outfit_scan_client.dart:27-148` · `widgets/outfit_scan_widgets.dart` · `data/outfit_scan_mock_data.dart` · `shared/utils/guest_mode.dart:19,34-62` · `shared/auth/auth_session.dart:28-79` · `app/router/auth_guard.dart:42-98` · `core/config/app_config.dart:20-23,115-123`.
Backend: `api/routers/analysis.py:49-63,130-165,195-268` · `application/analysis.py:51-186,169-341,344-522,524-748,750-772` · `application/media.py:26-93` · `ai/vision_appearance_adapter.py:50-238` · `ai/vision_garment_adapter.py` (contrast) · `ai/appearance_adapter.py:121-172` (dev-only) · `domain/services/analysis_rules.py:151,220-471,801-813` · `domain/value_objects.py:66,136-151` · `infrastructure/db/models.py:51-124,144-209,212-260,410,552` · `infrastructure/db/repositories.py:87-233,275,419,475,1237-1279` · `api/deps.py:38-85` · `api/errors.py` · `api/schemas/analysis.py:23-57` · `api/schemas/users.py:17` · `api/routers/users.py:38-129` · `config/settings.py:66-99` · `alembic/versions/0001,0002,0006,0008,0009,0010,0021,0022`.
Tests: Flutter `test/outfit_scan_{screen,processing,analysis,client}_test.dart`, `guest_phase2_test:358-374`, `auth_flow_regression:205-328`, `router_auth_guard_test`, `photo_capture_screen_test`, `preferences_sync_test`, `guest_auth_conversion_test` · Backend `tests/test_outfit_image_router.py`, `test_analysis_{api,use_case,rules}.py`, `test_vision_appearance_adapter.py`, `test_garment_analysis.py`, `test_get_profile.py`, `test_update_preferences.py`.
Docs: `docs/SCREEN_MAP.md:49-65` (conflicts §4), `docs/ARCHITECTURE.md`, `CURRENT_STATE.md` (Phase 4A vision notes).
Skills used: `flutter-apply-architecture-best-practices` (read for layer/state/routing lens; no code emitted).
