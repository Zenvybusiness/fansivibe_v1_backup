# Fansivibe — UI/UX Gap Report

> Reviewed the real Fansivibe UI/UX against the discovered Feature + Data
> Inventory (`FEATURE_INVENTORY.md`, `SCREEN_DATA_INVENTORY.md`,
> `DATA_MODEL_INVENTORY.md`, `FEATURE_DATA_MATRIX.md`, `DATA_OWNERSHIP.md`,
> `AI_DATA_FLOW.md`, `STORAGE_INVENTORY.md`, `ACTION_API_INVENTORY.md`,
> `STATE_EDGE_CASE_INVENTORY.md`).
>
> **This is a gap report only — nothing is changed, nothing is redesigned.** It
> identifies genuine gaps that could prevent the real product from working
> correctly. Every claim is verified against source.
>
> **Strict rule applied:** local component/screen changes are recommended
> wherever sufficient; full-app restructuring is never recommended.

---

## Priority legend

| Code | Meaning |
| --- | --- |
| **UI_CHANGE_REQUIRED** | Prevents the real product from working correctly today (or breaks the moment real data arrives). Must change. |
| **UI_CHANGE_RECOMMENDED** | Real gap that degrades the product; change should be planned (often tied to the future backend). |
| **NO_UI_CHANGE** | Works correctly; improvement would be architecture/content, not a UI defect. |

Scope: **C** = component-level fix, **S** = whole-screen (single feature), **M** = multiple screens (same feature family).

---

## Summary table

| # | Screen | Component | Problem (short) | Priority | Scope |
| --- | --- | --- | --- | --- | --- |
| 1 | Outfit Scan | Capture handler | Capture failure silently continues without the image | UI_CHANGE_REQUIRED | C |
| 2 | Outfit Builder | Save Outfit | Save is a SnackBar; user intent lost | UI_CHANGE_REQUIRED | C |
| 3 | Hairstyle / Grooming result | Save Style | Save is a SnackBar; user intent lost | UI_CHANGE_REQUIRED | M |
| 4 | Wardrobe | Item edit/delete | Actions are SnackBar stubs | UI_CHANGE_REQUIRED | C |
| 5 | Event details | Edit/Delete | "Coming soon" stubs | UI_CHANGE_REQUIRED | C |
| 6 | Profile | Dashboard | Shows mock stats disconnected from persisted UserModel | UI_CHANGE_REQUIRED | S |
| 7 | Profile | Saved Looks | Shows mock list, not the persisted savedLooks | UI_CHANGE_REQUIRED | C |
| 8 | Hairstyle | FaceScan | "Face Scan" has no camera (placeholder) | UI_CHANGE_REQUIRED | S |
| 9 | Onboarding | PhotoCapture | Capture is simulated; fake photoPath | UI_CHANGE_REQUIRED | C |
| 10 | Hairstyle | Details route | Missing extra → blank SizedBox (no error view) | UI_CHANGE_REQUIRED | C |
| 11 | Home | Cards | Weather/insight are fake literals; no slot for real data | UI_CHANGE_RECOMMENDED | M |
| 12 | Discover / Wardrobe | Image slot | FansiImageWell placeholder cannot render imageUrl | UI_CHANGE_RECOMMENDED | M |
| 13 | Assistant | Chat | Offline fallback is invisible to the user | UI_CHANGE_RECOMMENDED | C |
| 14 | Home | Greeting | Assumes a display name (default 'Alex') | UI_CHANGE_RECOMMENDED | C |
| 15 | Home | First-visit branch | Keyed on session-scoped `hasSavedWardrobeItem` (lost on restart) | UI_CHANGE_RECOMMENDED | S |
| 16 | All server-bound screens | — | Missing loading/empty/error/retry states | UI_CHANGE_RECOMMENDED | M |
| 17 | Assistant / all | — | No feedback/rating action anywhere | UI_CHANGE_RECOMMENDED | M |
| 18 | Capture flows | — | No privacy explanation for captured face/outfit images | UI_CHANGE_RECOMMENDED | M |
| 19 | Home / Discover | Cards | Hardcoded "facts" (match %, insight stats) presented as real | UI_CHANGE_RECOMMENDED | M |
| 20 | 7 detail routes | FansiErrorView | Route-extra-only data blocks deep links / future fetch | UI_CHANGE_RECOMMENDED | M |
| 21 | Home / Stylist | Quick actions | Duplicated action config with identical ids | NO_UI_CHANGE | M |
| 22 | Scan/Builder/Hairstyle/Grooming | Processing stages | 4 identical stage widgets | NO_UI_CHANGE | M |
| 23 | All screens | Tokens | Design-system tokens used consistently (no violations found) | NO_UI_CHANGE | — |

---

## Detail

### 1. Outfit Scan — capture failure silently continues

- **Screen:** OutfitScanScreen.
- **Component:** capture handler (`_handleCapture`, `outfit_scan_screen.dart:181-206`).
- **Problem:** on `takePicture()` failure the catch block **still navigates to
  the processing screen** without the image (`:204`), so the "scan" runs on no
  input. Also, when the controller isn't initialized it re-inits and proceeds
  anyway (`:189-194`).
- **Why it matters:** the real product's scan is meaningless without a photo; the
  user believes their outfit was analyzed when nothing was captured.
- **Required change:** block navigation on capture failure; show a retry dialog
  with the camera state machine; only navigate when `localPath` is present.
- **Scope:** component (capture flow within the scan screen).
- **Affects:** component only (not the whole screen).
- **Priority:** UI_CHANGE_REQUIRED.

### 2. Outfit Builder — Save Outfit is a SnackBar

- **Screen:** OutfitRecommendationScreen.
- **Component:** "Save Outfit" button (verified: no `addSavedLook`/persistence
  call — unlike Discover/Home/Scan which do save).
- **Problem:** tapping Save shows a transient SnackBar; nothing is written.
- **Why it matters:** user intent to keep an outfit is silently lost; inconsistent
  with the rest of the app where "save look" actually persists.
- **Required change:** wire Save to the same save path as Discover/Home (future
  `POST /looks/saved` or `POST /outfits/saved`); show saved confirmation with an
  entry point to view it.
- **Scope:** component.
- **Affects:** component only.
- **Priority:** UI_CHANGE_REQUIRED.

### 3. Hairstyle / Grooming — Save Style is a SnackBar

- **Screen:** HairstyleResultScreen, GroomingResultScreen.
- **Component:** "Save Style" buttons.
- **Problem:** same as #2 — transient SnackBar, nothing persisted, and the
  chosen style is never written to the (unused) `FaceProfile`.
- **Why it matters:** the user's chosen style is the core learning signal for the
  real product; losing it breaks personalization.
- **Required change:** persist the selected recommendation (future save endpoint)
  and record a feedback signal.
- **Scope:** two screens, same family.
- **Affects:** component on each screen.
- **Priority:** UI_CHANGE_REQUIRED.

### 4. Wardrobe — edit/delete are stubs

- **Screen:** WardrobeScreen (item detail).
- **Component:** item edit/delete actions.
- **Problem:** edit/delete show SnackBars and do nothing; only favorite toggle
  actually mutates (`copyWith(isFavorite)`).
- **Why it matters:** wardrobe management is core functionality; a real user
  cannot correct mistakes or remove items.
- **Required change:** implement edit and delete against the item row (future
  `PUT`/`DELETE /wardrobe/items/{id}`) with confirm/undo.
- **Scope:** component.
- **Affects:** component only.
- **Priority:** UI_CHANGE_REQUIRED.

### 5. Events — edit/delete "coming soon"

- **Screen:** EventDetailsScreen.
- **Component:** "Edit Event" (`event_details_screen.dart:320`) and delete.
- **Problem:** explicit "coming soon" stubs; events are also not persisted
  (widget state only).
- **Why it matters:** events are a user-created entity that must be editable and
  durable; today they vanish on restart.
- **Required change:** persist events and enable edit/delete (future
  `PUT`/`DELETE /events/{id}`).
- **Scope:** component (within the events feature).
- **Affects:** component only.
- **Priority:** UI_CHANGE_REQUIRED.

### 6. Profile — dashboard shows mock data disconnected from the model

- **Screen:** ProfileScreen (dashboard).
- **Component:** the whole profile dashboard (`ProfileData.mock`).
- **Problem:** level/rank/XP, style DNA, stats and achievements are a static
  mock; the screen never reads the persisted `UserModel`/`styleScore`.
- **Why it matters:** the profile is presented as the user's actual status; it
  will display stale/fake values once real data exists.
- **Required change:** render from the persisted user model + computed
  aggregates (future `GET /users/me`), with loading/empty/error states.
- **Scope:** whole screen (single feature).
- **Affects:** whole screen.
- **Priority:** UI_CHANGE_REQUIRED.

### 7. Profile — Saved Looks shows mock, not the persisted list

- **Screen:** SavedLooksScreen.
- **Component:** the saved-looks list.
- **Problem:** displays `ProfileMockData.savedLooks`; the persisted
  `UserModel.savedLooks` (which Discover/Home/Scan DO write) is never read.
- **Why it matters:** user saves looks in three other features, then cannot see
  them here — the product visibly loses data.
- **Required change:** read the persisted saved looks (future saved-look
  endpoint), add empty state + details.
- **Scope:** component.
- **Affects:** component only.
- **Priority:** UI_CHANGE_REQUIRED.

### 8. Hairstyle — "Face Scan" has no camera

- **Screen:** FaceScanScreen.
- **Component:** the whole screen.
- **Problem:** it is a `StatelessWidget` showing a `FacePreviewPlaceholder`;
  "Scan Face" simply navigates to the processing screen
  (`face_scan_screen.dart:135-137`). No capture, no permission flow.
- **Why it matters:** the core hair-analysis input (a face image) is never
  captured; the feature is cosmetic.
- **Required change:** real camera capture (or gallery upload) + permission UX,
  mirroring OutfitScan's state machine, then pass the image to analysis.
- **Scope:** whole screen.
- **Affects:** whole screen.
- **Priority:** UI_CHANGE_REQUIRED.

### 9. Onboarding — PhotoCapture is simulated

- **Screen:** PhotoCaptureScreen.
- **Component:** capture interaction.
- **Problem:** tapping capture sets `_captured = true` and after a 2s timer
  navigates with a fake `photoPath: 'captured'` (`photo_capture_screen.dart:47-56`).
  No real image exists.
- **Why it matters:** onboarding promises "Style DNA, score, and analysis" from
  a photo that is never taken; the analysis screen animates over nothing.
- **Required change:** real capture (camera/gallery) + permission + retake/
  retry, and only proceed to analysis with a real image.
- **Scope:** component.
- **Affects:** component (screen flow).
- **Priority:** UI_CHANGE_REQUIRED.

### 10. Hairstyle — details route renders a blank on missing data

- **Screen:** `hairstyle-details` route.
- **Component:** route fallback.
- **Problem:** unlike the 7 other routes that render `FansiErrorView` on null
  `extra`, this route returns an empty `SizedBox` (verified in the screen
  inventory), i.e. a blank screen.
- **Why it matters:** inconsistent failure handling; users hit a dead screen.
- **Required change:** render the standard `FansiErrorView` (or fetch by id).
- **Scope:** component.
- **Affects:** component only.
- **Priority:** UI_CHANGE_REQUIRED.

### 11. Home — fake weather/insight literals with no slot for real data

- **Screen:** Home dashboard + DailyOutfit.
- **Component:** Today's Look / insight cards.
- **Problem:** `weather: '68°F • Partly Cloudy'` and insight text are hardcoded
  (`home_mock_data.dart:63`, `daily_outfit_mock_data.dart:65`); there is no
  field/state wired to accept a future weather service or computed insight.
- **Why it matters:** when weather/insight become real (external service +
  backend), the UI has no path to display them; today it fabricates values.
- **Required change:** introduce data-driven slots for weather and insight with
  a placeholder/failure fallback (future binding to `GET /looks/today` + weather).
- **Scope:** multiple cards.
- **Affects:** whole home feature.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 12. Discover/Wardrobe — image slot cannot render real images

- **Screen:** Discover cards, Wardrobe items, outfit recommendations, saved
  looks.
- **Component:** `FansiImageWell` (`shared/components/fansi_image_well.dart`).
- **Problem:** the image slot is a gradient+icon placeholder; the `imageUrl`
  fields on Discover models are never rendered (no `Image.network`/asset wired).
- **Why it matters:** once object storage / real media exists, the UI cannot
  display it; look cards will stay empty wells.
- **Required change:** extend the image well to render a real image source with
  a loading/error fallback (component-level, reusable).
- **Scope:** component (one shared widget, many screens).
- **Affects:** multiple screens via the shared component.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 13. Assistant — offline fallback is invisible

- **Screen:** AssistantScreen.
- **Component:** chat (message list/status).
- **Problem:** when the backend is unreachable, `OfflineAssistant` answers
  silently (`assistant_service.dart:71`); the user cannot tell answers are not
  personalized.
- **Why it matters:** offline answers are rules-only; a user could mistake them
  for their personalized AI.
- **Required change:** a small offline/degraded notice (chip/banner) when the
  fallback engine is used.
- **Scope:** component.
- **Affects:** component only.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 14. Home — greeting assumes a display name

- **Screen:** HomeScreen (greeting).
- **Component:** greeting header (`GreetingData`, default name 'Alex').
- **Problem:** the greeting uses an onboarding-extras name with a hardcoded
  fallback; there is no real user-name source.
- **Why it matters:** presents a fabricated name; will be wrong once auth exists.
- **Required change:** read the name from the user model/account (future
  `GET /users/me`), keep a neutral fallback ("Welcome").
- **Scope:** component.
- **Affects:** component only.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 15. Home — first-visit branch keyed on a session flag

- **Screen:** HomeScreen (light-path branch).
- **Component:** first-visit gating (`home_screen.dart:25`).
- **Problem:** the branch is gated by `UserSession.hasSavedWardrobeItem`, a
  static in-memory flag (`shared/utils/user_session.dart`) that resets on every
  launch and is owned outside `features/learning`.
- **Why it matters:** confusing data ownership; after a restart the gate is
  wrong, so the user can flip between onboarding branches.
- **Required change:** derive the gate from the persisted user model (wardrobe
  non-empty) instead of the session flag.
- **Scope:** whole screen branch.
- **Affects:** whole screen.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 16. Server-bound screens — missing loading/empty/error/retry states

- **Screen:** Home, Wardrobe, Discover, Events, Profile, Builder, analysis
  results, Assistant.
- **Component:** screen-level state handling.
- **Problem:** verified in `STATE_EDGE_CASE_INVENTORY.md`: no loading skeletons,
  no empty states (except Discover/Wardrobe/Events), no error states, no retry.
- **Why it matters:** the moment real backend calls land, screens will flash
  mocks or blank/error with no recovery path.
- **Required change:** per-screen loading/empty/error/retry states introduced
  together with each backend binding (not before — avoids speculative UI).
- **Scope:** per screen, when its backend lands.
- **Affects:** whole screens.
- **Priority:** UI_CHANGE_RECOMMENDED (required once backend exists).

### 17. No feedback/rating action anywhere

- **Screen:** all result surfaces (Assistant, Discover, Builder, Hairstyle,
  Grooming, Scan).
- **Component:** — (feature does not exist).
- **Problem:** verified: no thumbs-up/down, no rating control; the only
  "feedback" is a settings toggle ("Haptic Feedback", `profile_mocks.dart:248`).
- **Why it matters:** the learning loop (signals) has no explicit user signal;
  recommendation quality cannot improve.
- **Required change:** add lightweight feedback actions on AI outputs
  (like/dislike/why), wired to future `POST /feedback`.
- **Scope:** new component across result screens.
- **Affects:** multiple screens.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 18. Capture flows — no privacy explanation

- **Screen:** PhotoCapture, FaceScan, OutfitScan, AccountCreation.
- **Component:** capture CTAs / account copy.
- **Problem:** captured face/outfit images are privacy-sensitive, but no screen
  explains what happens to the image (upload, retention, deletion). The account
  screen claims data "will be saved to your account" with no privacy note.
- **Why it matters:** appearance/image data is privacy-sensitive (AGENTS safety
  rules); unexplained capture erodes trust and may fail store review.
- **Required change:** short privacy explanation on each capture flow (what is
  uploaded, retained, deletable) before capture.
- **Scope:** copy + small notices across capture screens.
- **Affects:** multiple screens (same family).
- **Priority:** UI_CHANGE_RECOMMENDED.

### 19. Home/Discover — hardcoded "facts" presented as real

- **Screen:** Home insight, Discover match scores, analysis results.
- **Component:** stat/score text.
- **Problem:** strings like "unlock 12+ new outfit combinations", 94%/92% match
  scores, "3 curated alternatives" are hardcoded literals shown as the user's
  real results.
- **Why it matters:** fabricated precision presented as fact is misleading and
  conflicts with the no-subjective-judgment-as-fact rule; also duplicates
  content across codebases.
- **Required change:** derive all numbers/labels from real computed data; where
  unavailable, use honest neutral copy ("example" / "preview") rather than
  factual claims.
- **Scope:** copy + data binding across cards.
- **Affects:** multiple screens.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 20. Detail routes — route-extra-only data blocks deep links

- **Screen:** look details, event details, item details (7 routes via
  `FansiErrorView`).
- **Component:** router fallback (`app_router.dart:57,67`).
- **Problem:** detail screens require a route `extra`; there is no load-by-id
  path. A null extra yields an error view (or blank, see #10).
- **Why it matters:** future backend responses (or app restores / notifications)
  must be able to open a record by id; the UI cannot.
- **Required change:** support fetching by id with loading/error states when the
  extra is absent.
- **Scope:** route handlers + detail screens.
- **Affects:** multiple screens.
- **Priority:** UI_CHANGE_RECOMMENDED.

### 21. Home / Stylist — duplicated quick-action config

- **Screen:** HomeScreen, StylistScreen.
- **Component:** quick actions (`QuickActionData`) vs stylist actions
  (`StylistActionData`).
- **Problem:** two components model the same actions with identical ids; the
  same 5 action ids also appear in assistant `action` values and backend
  `NAVIGATION_MAP`.
- **Why it matters:** if the two lists drift, navigation inconsistencies appear.
  Today they are consistent, so no defect.
- **Required change:** none for functionality (works today). Consolidate to one
  config source when the capability/config system lands (architecture, not UI).
- **Scope:** —.
- **Affects:** —.
- **Priority:** NO_UI_CHANGE.

### 22. Four identical processing-stage widgets

- **Screen:** Outfit Scan, Outfit Builder, Hairstyle, Grooming processing.
- **Component:** `ProcessingStage`/`GenerationStage`/`HairstyleProcessingStage`/
  `GroomingProcessingStage` (identical id/label/duration shape).
- **Problem:** four duplicated stage widgets/models across features.
- **Why it matters:** maintenance duplication only; all four work correctly
  today.
- **Required change:** none for the product to work. Consolidate into one shared
  stage widget when refactoring is otherwise warranted.
- **Scope:** —.
- **Affects:** —.
- **Priority:** NO_UI_CHANGE.

### 23. Design-system compliance

- **Screen:** all audited screens.
- **Component:** theme tokens (`FansivibeColors`, `FansivibeTypography`,
  `FansivibeSpacing`, `FansivibeRadius`, `FansivibeShadows`) and shared
  components (`FansiButton`, `FansiErrorView`, `FansiImageWell`).
- **Problem:** within the audited scope, components consistently use the
  project tokens and shared components; no token misuse or ad-hoc colors/spacing
  were found.
- **Why it matters:** consistent design system = the baseline; nothing to fix.
- **Required change:** none.
- **Scope:** —.
- **Affects:** —.
- **Priority:** NO_UI_CHANGE.

---

## Grouped notes

- **Required (9):** #1–#10 (capture integrity, save actions, edit/delete, data
  binding, blank-screen fallback). These are the genuine blockers to the real
  product working correctly.
- **Recommended (11):** #11–#20 — most are explicitly tied to the future
  backend; they should be scheduled *with* each backend binding rather than
  pre-built speculatively (per the "no speculative UI" principle).
- **No change (3):** #21–#23 — duplication and design-system items work
  correctly today; improvements would be architectural, not UI defects.
- **No full-app restructuring is recommended** anywhere in this report.
