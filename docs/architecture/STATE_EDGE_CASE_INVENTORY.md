# Fansivibe — State & Edge-Case Inventory

> Companion to `DATA_MODEL_INVENTORY.md`, `FEATURE_DATA_MATRIX.md`,
> `DATA_OWNERSHIP.md`, `AI_DATA_FLOW.md`, `STORAGE_INVENTORY.md`, and
> `ACTION_API_INVENTORY.md`.
>
> For each major feature this document identifies the 10 UI states (initial /
> loading / success / empty / error / offline / unauthorized / permission
> denied / partial data / retry), plus the camera/AI-specific edge cases. For
> each edge case it records current UI behavior, required future backend
> behavior, and whether a UI change is necessary.
>
> **This is analysis only — no redesign, no implementation.** It only identifies
> required changes. Current behavior is verified against source; future behavior
> is derived from the companion docs.

---

## Verified current-state baseline (applies across features)

| State | Current reality in the app |
| --- | --- |
| Initial | Most screens render static mock content immediately (no fetch). Only `OutfitScanScreen` has an explicit `initial` camera state (`_CameraUiState.initial`). |
| Loading | Only where timers run: `*ProcessingScreen`s, `AiAnalysisScreen`, and the `OutfitScanScreen` camera `loading` state. Everything else has **no loading state** (static mocks). |
| Success | Static content rendered; local writes (wardrobe/event/save-look) succeed silently with SnackBar. |
| Empty | Only Discover (no filter matches), Wardrobe grid (empty category), EventList (no events). Everything else renders hardcoded content. |
| Error | `FansiErrorView` for 7 routes when `state.extra` is null (router `app_router.dart:57,67`); OutfitScan camera `error` state; Add Wardrobe Item inline error. Most screens have **no error state**. |
| Offline | Only Assistant handles it (falls back to `OfflineAssistant`, `assistant_service.dart:71`). All other data is local/mock, so "offline" is effectively N/A today. |
| Unauthorized | No auth exists. Account creation just navigates home (`account_creation_screen.dart:74`). No 401 handling anywhere. |
| Permission denied | Only the OutfitScan camera (`permissionDenied` state). Hairstyle FaceScan and onboarding PhotoCapture have **no real camera** (placeholders / simulated capture), so no permission flow. |
| Partial data | Missing route `extra` → `FansiErrorView` fallback (7 routes). `FaceProfile` never written → hairstyle/grooming/assistant always see empty/defaults. Profile dashboard shows `ProfileData.mock`, disconnected from the persisted `UserModel`. |
| Retry | No explicit retry UI. Camera re-initializes on capture when the controller is null (`outfit_scan_screen.dart:189`); everything else has no retry path. |

---

## Part 1 — Per-feature states

Legend: **C** = current UI behavior; **F** = required future backend behavior;
**UI?** = whether a UI change is necessary (Y/N/– n/a).

### 1. Onboarding (Entry → PhotoCapture → AiAnalysis → Account → Home)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** entry screen renders immediately. **F:** check session/token on launch. **UI?:** Y (splash/session gate). |
| Loading | **C:** `AiAnalysisScreen` is a timer animation over mock capabilities. **F:** real analysis progress with status. **UI?:** Y (real progress/cancel). |
| Success | **C:** navigates home with `onboarding_complete` + name/vibe extras. **F:** create account + user model row. **UI?:** – |
| Empty | **C:** "Maybe Later — Save Locally" path works. **F:** anonymous session → sync later. **UI?:** – |
| Error | **C:** none (capture is simulated; analysis can't fail). **F:** analysis/register failures. **UI?:** Y (error + retry on account/analysis). |
| Offline | **C:** works locally. **F:** register deferred; anonymous mode. **UI?:** Y (deferred-sync banner). |
| Unauthorized | **C:** n/a (no auth). **F:** expired social token handling. **UI?:** Y |
| Permission denied | **C:** `PhotoCaptureScreen` is simulated (no camera, no permission). **F:** real capture needs camera/gallery permission. **UI?:** Y (real capture + permission UI). |
| Partial data | **C:** none. **F:** interrupted analysis (photo captured, analysis not done). **UI?:** Y (resume). |
| Retry | **C:** none. **F:** register/analysis retry. **UI?:** Y |

### 2. Home dashboard (cards + quick actions)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** cards render static mock immediately. **F:** fetch daily look + score + streak. **UI?:** Y |
| Loading | **C:** none. **F:** skeleton cards while fetching. **UI?:** Y |
| Success | **C:** cards show mock values. **F:** real values + `GET /looks/today`. **UI?:** – |
| Empty | **C:** none (mock always populated). **F:** "no look yet / add wardrobe to start" empty card. **UI?:** Y |
| Error | **C:** none. **F:** card-level error placeholders. **UI?:** Y |
| Offline | **C:** works (mock). **F:** cache last-known cards + offline notice. **UI?:** Y (subtle offline chip) |
| Unauthorized | **C:** n/a. **F:** 401 → session redirect. **UI?:** Y |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** greeting name from onboarding extras, else default 'Alex'; `UserSession.hasSavedWardrobeItem` gates first-visit branch (home_screen.dart:25). **F:** read real profile name + wardrobe flag from user model. **UI?:** Y |
| Retry | **C:** none. **F:** pull-to-refresh / retry cards. **UI?:** Y |

### 3. Wardrobe (grid + add item + detail)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** seeded `defaultWardrobe` (24 items) on first load (`LearningService.load`). **F:** fetch user wardrobe. **UI?:** – |
| Loading | **C:** none. **F:** skeleton grid. **UI?:** Y |
| Success | **C:** grid + category counts render from `LearningService.wardrobe`. **F:** server-backed wardrobe. **UI?:** – |
| Empty | **C:** empty-category empty state exists. **F:** empty + "add your first item" CTA. **UI?:** Y (CTA) |
| Error | **C:** none for the grid; add-item has inline validation error. **F:** load/save errors. **UI?:** Y |
| Offline | **C:** works locally. **F:** offline queue for add/edit/delete; sync later. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401 handling. **UI?:** Y |
| Permission denied | **C:** n/a (item images are placeholders). **F:** gallery/camera permission for item photos. **UI?:** Y (future) |
| Partial data | **C:** edit/delete are SnackBar-only stubs (no data change). **F:** PUT/DELETE + optimistic UI. **UI?:** Y (enable edit/delete) |
| Retry | **C:** none. **F:** retry failed saves (offline queue). **UI?:** Y |

### 4. Discover (feed + filters + details)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** for-you/trending mocks render immediately. **F:** `GET /looks` feed. **UI?:** Y |
| Loading | **C:** none. **F:** skeleton feed. **UI?:** Y |
| Success | **C:** static cards. **F:** personalized cards (match scores from wardrobe). **UI?:** – |
| Empty | **C:** empty state when filters match nothing. **F:** empty + reset-filters CTA. **UI?:** Y (CTA) |
| Error | **C:** none. **F:** feed error + retry. **UI?:** Y |
| Offline | **C:** works (mock). **F:** cached feed + offline notice. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** personalized fields need auth. **UI?:** Y |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** look details rely on route `extra`; 7 routes fall back to `FansiErrorView` when null (router:67). **F:** fetch by look id. **UI?:** Y (deep-link load) |
| Retry | **C:** none. **F:** retry feed/detail. **UI?:** Y |

### 5. Outfit Scan (camera + processing + analysis)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** explicit `_CameraUiState.initial`. **F:** same + permission pre-check. **UI?:** – |
| Loading | **C:** camera `loading` state; then timer-driven processing screen. **F:** real upload+analysis progress. **UI?:** Y (stage statuses from server) |
| Success | **C:** `OutfitAnalysisData.mock` renders after fixed stages; "Generate Look" saves (`addSavedLook`). **F:** real analysis result + save. **UI?:** – |
| Empty | **C:** none. **F:** "no clothing detected" empty result. **UI?:** Y |
| Error | **C:** camera `error` state with message. **F:** analysis failure state. **UI?:** Y |
| Offline | **C:** analysis is local mock, so works offline (falsely). **F:** degrade to offline hints when analysis unavailable. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401. **UI?:** Y |
| Permission denied | **C:** `permissionDenied` state exists (outfit_scan_screen.dart:278). **F:** n/a (permission is client-side). **UI?:** – |
| Partial data | **C:** capture failure still navigates to processing (silently loses image, `_handleCapture` catch). **F:** must not proceed without the image. **UI?:** Y (block + retry) |
| Retry | **C:** re-inits camera on null controller. **F:** retry capture/analysis. **UI?:** Y |

### 6. Outfit Builder (inputs + generation + recommendation)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** option chips render immediately; selection passed as route extra. **F:** load option vocabulary from config. **UI?:** – |
| Loading | **C:** timer-driven generation stages. **F:** real generation progress. **UI?:** Y |
| Success | **C:** `OutfitRecommendation.mock`; "Save Outfit" is SnackBar-only. **F:** real rec + save. **UI?:** Y (enable save) |
| Empty | **C:** none. **F:** "no wardrobe match" empty rec. **UI?:** Y |
| Error | **C:** none. **F:** generation failure. **UI?:** Y |
| Offline | **C:** works (mock). **F:** offline recommendation fallback. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401. **UI?:** Y |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** route extra prefs carry live data; null → FansiErrorView. **F:** persist prefs server-side. **UI?:** Y |
| Retry | **C:** "Regenerate" button exists but returns the same mock. **F:** true regenerate. **UI?:** – |

### 7. Hairstyle (face scan → processing → result)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** `FaceScanScreen` shows a **placeholder** (`FacePreviewPlaceholder`) + mock checks — no camera at all. **F:** real capture. **UI?:** Y |
| Loading | **C:** timer-driven processing screen. **F:** real analysis progress. **UI?:** Y |
| Success | **C:** `HairstyleAnalysisResult.mock`; Save Style SnackBar-only. **F:** real result + persist style. **UI?:** Y (enable save) |
| Empty | **C:** none. **F:** "face not detected" empty result. **UI?:** Y |
| Error | **C:** none (no capture/analysis to fail). **F:** analysis failure. **UI?:** Y |
| Offline | **C:** works (mock). **F:** offline fallback. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401 (face media is private). **UI?:** Y |
| Permission denied | **C:** none — **no camera**; `_handleScan` just navigates (face_scan_screen.dart:136). **F:** real camera + permission UI. **UI?:** Y |
| Partial data | **C:** `FaceProfile` never written (`setFace` uncalled) → result is always the mock default. **F:** persist analysis → face profile. **UI?:** Y |
| Retry | **C:** none. **F:** retry scan/analysis. **UI?:** Y |

### 8. Grooming (input → processing → result)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** option chips render; selections ephemeral. **F:** load vocab from config. **UI?:** – |
| Loading | **C:** timer-driven processing. **F:** real analysis progress. **UI?:** Y |
| Success | **C:** `GroomingAnalysisResult.mock`; Save SnackBar-only. **F:** real result + save. **UI?:** Y (enable save) |
| Empty | **C:** none. **F:** insufficient-input empty result. **UI?:** Y |
| Error | **C:** none. **F:** analysis failure. **UI?:** Y |
| Offline | **C:** works (mock). **F:** offline fallback. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401. **UI?:** Y |
| Permission denied | **C:** n/a (no media capture). **UI?:** – |
| Partial data | **C:** face profile empty → mock defaults. **F:** real face input. **UI?:** Y |
| Retry | **C:** none. **F:** retry. **UI?:** Y |

### 9. Events (list + add + details)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** `EventListScreen` state with `EventType.mockTypes`. **F:** `GET /events`. **UI?:** Y |
| Loading | **C:** none. **F:** skeleton. **UI?:** Y |
| Success | **C:** events held in widget state (created via `pop<UserEvent>`). **F:** server-backed events. **UI?:** – |
| Empty | **C:** empty state exists ("no events"). **F:** empty + create CTA. **UI?:** Y (CTA) |
| Error | **C:** none. **F:** load/save errors. **UI?:** Y |
| Offline | **C:** works locally. **F:** offline queue + sync. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401. **UI?:** Y |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** events are **not persisted** (lost on restart); only `addPreferredOccasion` is durable. Edit is "coming soon" stub. **F:** persist events + edit. **UI?:** Y |
| Retry | **C:** none. **F:** retry. **UI?:** Y |

### 10. Profile (+ preferences / settings / subscription / support / saved looks)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** `ProfileData.mock` renders instantly. **F:** `GET /users/me` + aggregates. **UI?:** Y |
| Loading | **C:** none. **F:** skeleton. **UI?:** Y |
| Success | **C:** mock stats/level/rank/style DNA/saved looks. **F:** real aggregates from user data. **UI?:** – |
| Empty | **C:** none. **F:** empty saved-looks/achievements states. **UI?:** Y |
| Error | **C:** none. **F:** profile fetch error. **UI?:** Y |
| Offline | **C:** works (mock). **F:** cached profile. **UI?:** Y |
| Unauthorized | **C:** n/a (Sign Out is SnackBar stub). **F:** 401 → sign-in. **UI?:** Y (enable sign out) |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** profile is **disconnected** from `UserModel`; SavedLooks shows `ProfileMockData.savedLooks`, not persisted `savedLooks`; preferences/settings are ephemeral widget state. **F:** read persisted user model + prefs. **UI?:** Y |
| Retry | **C:** none. **F:** retry. **UI?:** Y |

### 11. Assistant (chat)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** empty chat with suggestion chips. **F:** restore session (if retained). **UI?:** – |
| Loading | **C:** `pending` message (typing indicator) while awaiting `POST /v1/assistant/chat`. **F:** same + server status. **UI?:** – |
| Success | **C:** structured reply (text/cards/clarifications/nav). **F:** authenticated replies. **UI?:** – |
| Empty | **C:** n/a. **UI?:** – |
| Error | **C:** none surfaced to the user — backend failure → **offline fallback** (silently). **F:** distinguish offline vs error. **UI?:** Y (error notice) |
| Offline | **C:** `OfflineAssistant` mirror answers deterministically (`assistant_service.dart:71`). **F:** offline-aware hint that answers are not personalized. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** 401 (context is private). **UI?:** Y |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** context sent includes empty `face`; conversation history only in memory; `selectClarification` re-sends. **F:** server-persisted context/history (if product decides). **UI?:** Y (per decisions) |
| Retry | **C:** user re-sends manually. **F:** automatic retry on transient failure. **UI?:** Y |

### 12. Stylist hub

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** static grid renders. **F:** config-driven actions. **UI?:** – |
| Loading/Success/Empty/Error/Offline/Unauthorized/Permission/Partial/Retry | **C:** N/A (pure static navigation, no data). **F:** if actions become config-driven, standard states apply. **UI?:** – |

### 13. Learning core (persistence layer — not a screen)

| State | C / F / UI? |
| --- | --- |
| Initial | **C:** `LocalStore.load()` seeds `defaultWardrobe` on first run; degrades to in-memory when storage unavailable (tests). **F:** server sync. **UI?:** – |
| Loading | **C:** `load()` is sync-ish; screens assume data ready. **F:** async hydration. **UI?:** Y |
| Success | **C:** `ChangeNotifier` notifies listeners. **F:** sync ack. **UI?:** – |
| Empty | **C:** n/a. **UI?:** – |
| Error | **C:** storage write errors are swallowed (blob save). **F:** surfaced sync/save errors. **UI?:** Y |
| Offline | **C:** whole layer is local — inherently offline. **F:** offline queue. **UI?:** Y |
| Unauthorized | **C:** n/a. **F:** token-gated sync. **UI?:** Y |
| Permission denied | **C:** n/a. **UI?:** – |
| Partial data | **C:** empty `face`, optional `styleType` handled; missing fields default. **F:** merge/conflict resolution on sync. **UI?:** Y |
| Retry | **C:** none. **F:** sync retry with backoff. **UI?:** Y |

---

## Part 2 — Camera / AI edge cases

Verified camera reality: **only `OutfitScanScreen` uses a real camera** (full
state machine). `FaceScanScreen` (hairstyle) shows a placeholder and just
navigates; onboarding `PhotoCaptureScreen` is a simulated capture (no camera,
`photo_capture_screen.dart:47`). No AI runs anywhere (mocks — see
`AI_DATA_FLOW.md`).

| Edge case | Current UI behavior | Required future backend behavior | UI change necessary? |
| --- | --- | --- | --- |
| Camera unavailable | OutfitScan: `unavailable` state (no cameras). Others: N/A (no camera). | n/a (client-only) | Y — provide downgrade path (gallery/upload) so scan features are usable without a camera |
| Permission denied | OutfitScan: `permissionDenied` state (outfit_scan_screen.dart:278). Others: N/A. | n/a (client-only) | Y — unify permission UX; add it to the future real face/onboarding captures |
| Capture failure | OutfitScan: catch → **still navigates to processing** (`_handleCapture` :202-205), silently losing the image. Others: N/A. | n/a (client-only) | **Y — block navigation + show retry; never proceed without the image** |
| Upload failure | None — images are never uploaded today. | `POST /analysis/outfit` (and future face) must return 413/422/503 and the client must show error + retry | Y |
| AI processing failure | Impossible today — processing is a fixed timer; it cannot fail. | Analysis service errors → typed failure response; client shows error state + retry | Y |
| Invalid image | No validation; any capture "succeeds". | Backend validates (no clothing/face detected) → 422 with reason | Y — surface "no item/face detected" with retake |
| Insufficient data | Hairstyle/grooming/assistant silently use defaults/mocks when `face` is empty; assistant outfit falls back to catalog (`tools.py`). | Backend should reply "insufficient data" + ask for the missing input (face scan, wardrobe) | Y — prompt user to add missing data |
| AI confidence too low | No confidence is computed anywhere (`AI_DATA_FLOW.md` Part D.3). | If a future model returns low confidence, backend returns low-confidence + alternatives/clarification instead of a top pick | Y — UI to present alternatives when confidence is low |
| Duplicate save (save look) | Local `addSavedLook` is additive — duplicates possible. | `POST /looks/saved` idempotent (409 or upsert) | Y — dedupe feedback |

---

## Part 3 — Required-change summary (identifies changes only; no redesign)

### UI changes strictly necessary (existing features)

1. **Capture failure must not proceed silently** (Outfit Scan) — block + retry.
2. **Enable Save Outfit / Save Style** (Builder, Hairstyle, Grooming) — today
   they are SnackBar stubs; wire them to the future save endpoints.
3. **Enable edit/delete** (Wardrobe item, Event) — stubs today.
4. **Enable Sign Out / profile save** (Profile, Preferences, Settings) — stub
   today; needs 401-aware session handling.
5. **Wire persisted data to UI** (Profile dashboard, Saved Looks, Preferences)
   — read `UserModel`/server data instead of `ProfileData.mock`.
6. **Add empty + CTA states** where features can have no data once real:
   Home cards, Builder, Hairstyle, Grooming, Profile.
7. **Add loading states** (skeletons) for every future server-backed screen:
   Home, Wardrobe, Discover, Events, Profile, Builder, analysis screens.
8. **Add error + retry states** for every future server call; surface offline
   vs error in the Assistant (today both silently fall back).
9. **Add camera to Face Scan and onboarding capture** + permission UI, or
   provide gallery/upload alternatives.
10. **Persist events** and add event edit/delete UI.
11. **Add feedback/rating UI** — the feature does not exist (gap, not observed).

### Backend behaviors required (future, from `ACTION_API_INVENTORY.md`)

- Typed HTTP errors (401/404/422/409/413/429/503) with consistent error bodies.
- Idempotency for save-look/save-outfit; conflict semantics for sync.
- "Insufficient data" and "low confidence" structured signals from AI analysis.
- Offline-capable contract so the app can cache and sync later.

### Explicitly NOT changing (per task)

- No redesign of screens, navigation, or the design system.
- No API/routing/UI implementation — this inventory only records required
  changes for the design phase.
