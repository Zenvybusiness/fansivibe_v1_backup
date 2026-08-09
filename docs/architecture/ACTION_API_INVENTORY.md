# Fansivibe — Action → Backend API Inventory

> Companion to `DATA_MODEL_INVENTORY.md`, `FEATURE_DATA_MATRIX.md`,
> `DATA_OWNERSHIP.md`, `AI_DATA_FLOW.md`, and `STORAGE_INVENTORY.md`.
>
> Maps the important USER ACTIONS in the real Fansivibe app to the **future**
> backend operations they will need. For each action: screen, user action,
> required input, data read, data written, backend responsibility, expected
> response, error conditions, and authentication requirement.
>
> **This is requirements derivation only.** No APIs are implemented, no routes
> are modified, no Flutter UI changes, no backend endpoints are created.
> Everything below is derived from existing product behavior and the verified
> data facts in the companion docs.
>
> **Ground truth today:** the app has exactly ONE remote call —
> `POST /v1/assistant/chat` (`assistant_client.dart:38`). All other "save /
> generate / update" actions are local-only (LearningService / SharedPreferences)
> or snackbar stubs. Auth does not exist (account creation just navigates home,
> `account_creation_screen.dart:74`).

---

## Current-state annotations used below

| Tag | Meaning |
| --- | --- |
| **NOW = local** | action currently persists only locally (`LearningService`/UserModel blob) |
| **NOW = stub** | action shows a SnackBar / does nothing durable (no data written) |
| **NOW = mock** | action renders static data (no computation) |
| **AUTH: none today** | no authentication exists; the future requirement is stated |
| **AUTH: future-required** | the future backend operation must require the user token |

---

## Part 1 — Master matrix

| # | User action | Screen | Current state | Future backend operation | Auth |
| --- | --- | --- | --- | --- | --- |
| 1 | Create account | AccountCreation | NOW = mock (navigates home) | `POST /auth/register` (email+password+name) | public → token |
| 2 | Social sign in (Google/Apple) | AccountCreation | NOW = mock | `POST /auth/social` (provider token) | public → token |
| 3 | Sign in (existing user) | Entry | NOW = mock | `POST /auth/login` | public → token |
| 4 | Save locally (maybe later) | AccountCreation | NOW = mock | offline/anonymous mode; sync later | none (anonymous) |
| 5 | Add wardrobe item | Wardrobe Add Item | NOW = local (`addItem`) | `POST /wardrobe/items` | future-required |
| 6 | Favorite wardrobe item | Wardrobe | NOW = local (`copyWith(isFavorite)`) | `PATCH /wardrobe/items/{id}` | future-required |
| 7 | Edit / delete wardrobe item | Wardrobe item detail | NOW = stub (SnackBar) | `PUT` / `DELETE /wardrobe/items/{id}` | future-required |
| 8 | View wardrobe analysis / insight | Wardrobe | NOW = stub (SnackBar) | `GET /wardrobe/insight` | future-required |
| 9 | Create event | Add Event | NOW = local (occasion signal only; event lost) | `POST /events` | future-required |
| 10 | Edit / delete event | Event details | NOW = stub ("coming soon") | `PUT` / `DELETE /events/{id}` | future-required |
| 11 | Generate outfit for event | Event details | NOW = navigation to builder | `POST /events/{id}/outfit` (or reuse builder) | future-required |
| 12 | Save today's look | Daily Outfit | NOW = local (`addSavedLook`) | `POST /looks/saved` | future-required |
| 13 | Generate another look | Daily Outfit | NOW = stub (regenerates mock) | `POST /looks/today` (regen) | future-required |
| 14 | Save look from Discover | Look Details | NOW = local (`addSavedLook`) | `POST /looks/saved` | future-required |
| 15 | Filter Discover looks | Discover | NOW = local (widget state) | `GET /looks?filters=` | future-required (personalized) |
| 16 | Scan outfit | Outfit Scan | NOW = mock + transient image | `POST /analysis/outfit` (multipart image) | future-required |
| 17 | Generate Look from scan | Outfit Analysis | NOW = local (`addSavedLook`) | `POST /looks/saved` (from analysis) | future-required |
| 18 | Build outfit (preferences) | Outfit Builder | NOW = mock (route extra prefs) | `POST /outfits/generate` | future-required |
| 19 | Save generated outfit | Outfit Recommendation | NOW = stub (SnackBar) | `POST /outfits/saved` | future-required |
| 20 | Regenerate outfit | Outfit Recommendation | NOW = stub (same mock) | `POST /outfits/generate` (same prefs) | future-required |
| 21 | Generate hairstyle recommendation | Hairstyle result | NOW = mock | `POST /analysis/hairstyle` (face image/profile) | future-required |
| 22 | Save hairstyle style | Hairstyle result | NOW = stub (SnackBar) | `POST /looks/saved` (style ref) | future-required |
| 23 | Generate grooming recommendation | Grooming result | NOW = mock | `POST /analysis/grooming` | future-required |
| 24 | Save grooming style | Grooming result | NOW = stub (SnackBar) | `POST /looks/saved` (style ref) | future-required |
| 25 | Send assistant message | Assistant | NOW = remote (`POST /v1/assistant/chat`) + offline fallback | keep/extend `POST /v1/assistant/chat` | future-required |
| 26 | Open assistant suggestion card | Assistant | NOW = local signal | `POST /assistant/feedback` (card interaction) | future-required |
| 27 | Navigate via assistant | Assistant | NOW = local signal | (server-driven nav already in reply) | future-required |
| 28 | Update profile / preferences | Profile / Preferences / Settings | NOW = stub (ephemeral widget state) | `PATCH /users/me` + `PUT /users/me/preferences` | future-required |
| 29 | Sign out | Profile menu | NOW = stub (SnackBar) | `POST /auth/logout` (revoke token) | required |
| 30 | Subscribe / upgrade | Subscription / Upgrade | NOW = mock plans | `POST /subscriptions` (purchase) | future-required |
| 31 | Submit feedback / rating | (none exists) | NOW = missing feature | `POST /feedback` | future-required (public or user) |
| 32 | Sync local data to account | (post-account) | NOW = n/a (only local store) | `POST /users/me/sync` (upsert UserModel) | future-required |

---

## Part 2 — Per-action detail

### 1. Create account

- **Screen:** AccountCreationScreen (`account_creation_screen.dart`).
- **User action:** tap "Create Account".
- **Required input:** email, password, display name (optional). Client-side
  validation: email has `@` and `.`, length > 5 (`_validate`, :100). No
  password-strength or server validation today.
- **Data read:** none (fresh session).
- **Data written:** today none (navigates home with `onboarding_complete` +
  `display_name` extra). Future: `users` row (auth + name), initial empty
  UserModel, seed wardrobe.
- **Backend responsibility:** register, hash/verify credentials, issue session
  token, create `users` + default `user_model` row.
- **Expected response:** 201 + token + profile (name) + sync token for local
  data upload.
- **Error conditions:** email taken (409), invalid email (422), weak password
  (422), rate-limit (429). Today: **none surfaced** (always navigates home).
- **AUTH:** public; returns a token (future). **None today.**

### 2. Social sign in (Google / Apple)

- **Screen:** AccountCreationScreen (`_onSocialSignIn`, :86).
- **User action:** tap "Google" or "Apple".
- **Required input:** provider + provider token (future; today just a provider
  string in the route extra).
- **Data read / written:** same as register (new or existing user).
- **Backend responsibility:** exchange provider token, upsert `users` by
  provider subject id, issue app token, return/refresh profile.
- **Expected response:** 200 (existing) / 201 (new) + token + profile.
- **Error conditions:** provider unavailable (502), invalid/expired provider
  token (401), account-linking conflict (409).
- **AUTH:** public (OAuth callback); app sessions authenticated thereafter.
  **None today.**

### 3. Sign in (existing user)

- **Screen:** EntryScreen ("Sign In", `entry_screen.dart:363`).
- **User action:** tap "Sign In".
- **Required input:** email + password (future; today the button is a
  placeholder with no credential flow).
- **Data read:** `users` (credentials) → `user_model` for the session.
- **Data written:** refresh token / session.
- **Backend responsibility:** verify credentials, issue token, return the
  user's stored profile + model snapshot.
- **Expected response:** 200 + token + profile (+ last UserModel snapshot for
  device restore).
- **Error conditions:** wrong credentials (401), not found (404),
  rate-limit/brute-force (429).
- **AUTH:** public (credentials exchange).

### 4. Save locally (maybe later)

- **Screen:** AccountCreationScreen ("Maybe Later — Save Locally", :138).
- **User action:** continue without an account.
- **Required input:** none.
- **Data read/written:** on-device `UserModel` blob (existing behavior).
- **Backend responsibility:** none until account creation; later, an
  **anonymous → sync** operation (see #32) to merge local data.
- **Expected response:** app continues offline.
- **Error conditions:** none locally.
- **AUTH:** none (anonymous device-scoped).

### 5. Add wardrobe item

- **Screen:** WardrobeScreen → Add Item flow (route `wardrobeAddCategory`).
- **User action:** fill item form and confirm add.
- **Required input:** name, category (from config), color (from swatches),
  texture (optional), notes/material (optional).
- **Data read:** `AddItemConfig` categories/colors/textures (local vocab);
  future: knowledge config from backend.
- **Data written:** `WardrobeEntry` via `LearningService.addItem`
  (`wardrobe_screen.dart:301`); sets `UserSession.hasSavedWardrobeItem`;
  `item_added` signal.
- **Backend responsibility (future):** `POST /wardrobe/items` — validate
  category/color against controlled vocab, store row, re-derive wardrobe
  stats/insight.
- **Expected response:** created item (+ refreshed counts). Today: local
  SnackBar "added to wardrobe".
- **Error conditions:** invalid category/color (422), item limit/dup (409),
  auth (401). None surfaced today.
- **AUTH:** future-required (rows scoped by user_id). **None today.**

### 6. Favorite wardrobe item

- **Screen:** WardrobeScreen (item card).
- **User action:** toggle favorite.
- **Required input:** item id + new favorite state.
- **Data read:** the item row.
- **Data written:** `copyWith(isFavorite)` on the local `WardrobeEntry`.
- **Backend responsibility (future):** `PATCH /wardrobe/items/{id}` — partial
  update; favorites feed insight/counts.
- **Expected response:** updated item.
- **Error conditions:** not found (404), conflict (409), auth (401).
- **AUTH:** future-required.

### 7. Edit / delete wardrobe item

- **Screen:** WardrobeScreen item detail.
- **User action:** edit or delete an item.
- **Required input:** item id (+ updated fields).
- **Data read:** the item.
- **Data written:** **nothing today** — SnackBar only.
- **Backend responsibility (future):** `PUT /wardrobe/items/{id}` (replace
  fields), `DELETE /wardrobe/items/{id}` (cascade images, re-derive stats).
- **Expected response:** updated/204. Today: "coming soon" SnackBar.
- **Error conditions:** not found (404), foreign-key refs (409), auth (401).
- **AUTH:** future-required.

### 8. View wardrobe analysis / insight

- **Screen:** WardrobeScreen ("View Analysis", `_handleViewAnalysis`, :285).
- **User action:** tap "View Analysis".
- **Required input:** none.
- **Data read:** the user's wardrobe (+ catalog vocab); today the insight is
  mock/static.
- **Data written:** none (view-only).
- **Backend responsibility (future):** `GET /wardrobe/insight` — compute gaps
  from wardrobe + catalog (the assistant tool already hints at the rule:
  "consider a lightweight jacket", `tools.py:57`).
- **Expected response:** insight card (title/insight/action/route).
- **Error conditions:** empty wardrobe (204/empty insight), auth (401).
- **AUTH:** future-required.

### 9. Create event

- **Screen:** AddEventScreen.
- **User action:** fill form and tap "Add Event".
- **Required input:** event name, date (picker), time (picker), event type
  (grid). Valid only when all four are set (`_isValid`, `add_event_screen.dart:22`).
- **Data read:** `EventType.mockTypes` vocabulary.
- **Data written:** **event is NOT persisted** — returned via `pop<UserEvent>`
  into `EventListScreen` state (:118); only `addPreferredOccasion(eventType.name)`
  is durable (:116).
- **Backend responsibility (future):** `POST /events` — validate type against
  controlled vocabulary, store dated row, record occasion preference.
- **Expected response:** created event (echoed back). Today: pops event into
  list state.
- **Error conditions:** missing fields (422 — blocked client-side today),
  past date (422), invalid type (422), auth (401).
- **AUTH:** future-required. **None today.**

### 10. Edit / delete event

- **Screen:** EventDetailsScreen (`_editEvent`, `event_details_screen.dart:320`).
- **User action:** tap "Edit Event" (or delete).
- **Required input:** event id (+ fields).
- **Data read/written:** nothing today — "Edit Event coming soon" SnackBar.
- **Backend responsibility (future):** `PUT/DELETE /events/{id}`.
- **Expected response:** updated/204.
- **Error conditions:** not found (404), auth (401).
- **AUTH:** future-required.

### 11. Generate outfit for event

- **Screen:** EventDetailsScreen ("Generate Outfit", `_generateOutfit`, :316).
- **User action:** tap "Generate Outfit".
- **Required input:** event id/type (as preference seed).
- **Data read:** event (type/occasion); today none (just navigates to
  `build-outfit`, `context.pushNamed(RouteNames.buildOutfit)` :317).
- **Data written:** none today (route extra carries no event data).
- **Backend responsibility (future):** `POST /events/{id}/outfit` — generate a
  look grounded in the event occasion + wardrobe (or reuse the builder endpoint
  pre-seeded with the event's occasion).
- **Expected response:** an outfit recommendation (matches the builder output).
- **Error conditions:** event not found (404), generation failure (503/500),
  auth (401).
- **AUTH:** future-required.

### 12. Save today's look

- **Screen:** DailyOutfitScreen.
- **User action:** tap "Save Look".
- **Required input:** the displayed `DailyOutfitData` (title).
- **Data read:** current look card.
- **Data written:** `LearningService.addSavedLook` (`daily_outfit_screen.dart:1172`)
  → `look_saved` signal; saved-look title in UserModel.
- **Backend responsibility (future):** `POST /looks/saved` — store a saved-look
  reference + snapshot payload (see STORAGE_INVENTORY 1.6/1.7).
- **Expected response:** saved-look id. Today: local + SnackBar.
- **Error conditions:** look not found/expired (404), duplicate (409 — or
  idempotent), auth (401).
- **AUTH:** future-required. **None today.**

### 13. Generate another look

- **Screen:** DailyOutfitScreen ("Generate Another Look", `_handleGenerateAnother`, :1160).
- **User action:** tap "Generate Another Look".
- **Required input:** nothing new (same user model).
- **Data read:** user model (future); today reuses the same mock look.
- **Data written:** none today.
- **Backend responsibility (future):** `POST /looks/today` (regenerate) or
  `GET /looks/today?variant=N` — return a fresh daily look.
- **Expected response:** a different look card.
- **Error conditions:** no looks available (404/empty), generation failure
  (503), auth (401).
- **AUTH:** future-required.

### 14. Save look from Discover

- **Screen:** LookDetailsScreen.
- **User action:** tap Save.
- **Required input:** `DiscoverLookData` title.
- **Data read:** the look detail payload.
- **Data written:** `LearningService.addSavedLook(look.title)`
  (`look_details_screen.dart:327`); `look_saved` signal.
- **Backend responsibility (future):** `POST /looks/saved` (same as #12) — with
  the catalog look id, not just a title.
- **Expected response:** saved-look id. Today: local.
- **Error conditions:** look not found (404), auth (401).
- **AUTH:** future-required.

### 15. Filter Discover looks

- **Screen:** DiscoverScreen.
- **User action:** toggle filter chips (occasion/style/fit).
- **Required input:** active filter set (widget state).
- **Data read:** mock look catalog (static); filters filter locally.
- **Data written:** none (session-only filter state).
- **Backend responsibility (future):** `GET /looks?occasion=&style=&fit=&page=`
  — serve catalog + personalize with the user's wardrobe (match scores,
  `isOwned`).
- **Expected response:** filtered look cards (paginated).
- **Error conditions:** invalid filter values (422), auth (401 for
  personalized fields).
- **AUTH:** future-required for personalization; public catalog otherwise.

### 16. Scan outfit

- **Screen:** OutfitScanScreen.
- **User action:** capture an outfit photo.
- **Required input:** captured image (camera `XFile`); today only the local
  `xFile.path` is held (`outfit_scan_screen.dart:199`) — never uploaded.
- **Data read:** none (no analysis exists — `OutfitAnalysisData.mock`).
- **Data written:** none durable (image transient; `_ProcessingStage` timer
  state).
- **Backend responsibility (future):** `POST /analysis/outfit` (multipart
  image) — upload to object storage, run analysis, return sections + detected
  items + scores.
- **Expected response:** `OutfitAnalysisData` (sections, detected items,
  scores) + confidence.
- **Error conditions:** image too large/unsupported (413/422), no clothing
  detected (422), service/model failure (503), timeout, auth (401).
- **AUTH:** future-required (media is private). **None today.**

### 17. Generate Look from scan

- **Screen:** OutfitAnalysisScreen ("Generate Look", `outfit_analysis_screen.dart:257`).
- **User action:** tap "Generate Look".
- **Required input:** the analysis result.
- **Data read:** analysis sections/detected items.
- **Data written:** `LearningService.addSavedLook` (:260) — `look_saved` signal.
- **Backend responsibility (future):** `POST /looks/saved` — persist the
  saved look + snapshot of the analysis (link to scan image).
- **Expected response:** saved-look id. Today: local.
- **Error conditions:** analysis expired/missing (404), auth (401).
- **AUTH:** future-required.

### 18. Build outfit (preferences)

- **Screen:** OutfitBuilderScreen → OutfitRecommendationScreen.
- **User action:** select occasion/mood/fit/color-palette chips and generate.
- **Required input:** the 4 preference selections (route extra today).
- **Data read:** `BuilderOption` vocab (local); future: wardrobe + catalog.
- **Data written:** none today (`OutfitRecommendation.mock`; Save is SnackBar).
- **Backend responsibility (future):** `POST /outfits/generate` — generate an
  outfit from preferences + wardrobe, return recommendation + reasons + scores.
- **Expected response:** `OutfitRecommendation`.
- **Error conditions:** invalid preference values (422), no matching wardrobe
  (204/empty), generation failure (503), auth (401).
- **AUTH:** future-required.

### 19. Save generated outfit

- **Screen:** OutfitRecommendationScreen ("Save Outfit").
- **User action:** tap "Save Outfit".
- **Required input:** the recommendation.
- **Data read/written:** **nothing today** — SnackBar only (verified; no
  `addSavedLook` call here, unlike Discover/Home/Scan).
- **Backend responsibility (future):** `POST /outfits/saved` — persist
  recommendation + component snapshot (JSONB) as a saved outfit.
- **Expected response:** saved-outfit id.
- **Error conditions:** auth (401), duplicate (409/idempotent).
- **AUTH:** future-required.

### 20. Regenerate outfit

- **Screen:** OutfitRecommendationScreen ("Regenerate", `outfit_recommendation_screen.dart:266`).
- **User action:** tap "Regenerate".
- **Required input:** same preferences as the last generation.
- **Data read/written:** none today (same mock returned).
- **Backend responsibility (future):** `POST /outfits/generate` with
  variety/seed to yield a different result.
- **Expected response:** a different recommendation.
- **Error conditions:** generation failure (503), auth (401).
- **AUTH:** future-required.

### 21. Generate hairstyle recommendation

- **Screen:** HairstyleProcessingScreen → HairstyleResultScreen.
- **User action:** run a face scan / generate.
- **Required input:** captured face image (transient) + scan readiness
  (`FaceScanCheck`).
- **Data read:** `HairstyleAnalysisResult.mock` (static); `FaceProfile` exists
  but is **never written** (setFace uncalled) so the top pick is always the
  mock default.
- **Data written:** nothing durable today; Save Style is SnackBar-only.
- **Backend responsibility (future):** `POST /analysis/hairstyle` (face image
  or profile) — run face analysis, return recommendations + confidence +
  write `FaceProfile`.
- **Expected response:** `HairstyleAnalysisResult` (top + alternatives,
  scores, reasons).
- **Error conditions:** poor image/face not detected (422), service failure
  (503), auth (401).
- **AUTH:** future-required (face media is private). **None today.**

### 22. Save hairstyle style

- **Screen:** HairstyleResultScreen ("Save Style").
- **User action:** tap "Save Style".
- **Required input:** the recommendation id.
- **Data read/written:** nothing today — SnackBar only.
- **Backend responsibility (future):** `POST /looks/saved` (style reference) or
  `POST /profile/style` — record the chosen style.
- **Expected response:** saved reference id.
- **Error conditions:** auth (401).
- **AUTH:** future-required.

### 23. Generate grooming recommendation

- **Screen:** GroomingProcessingScreen → GroomingResultScreen.
- **User action:** select grooming inputs and generate.
- **Required input:** face shape, beard style, density, color options
  (`GroomingOption` selection).
- **Data read:** `GroomingAnalysisResult.mock` (static).
- **Data written:** nothing durable today (Save is SnackBar-only).
- **Backend responsibility (future):** `POST /analysis/grooming` — return
  grooming recommendation + reasons + scores.
- **Expected response:** `GroomingAnalysisResult`.
- **Error conditions:** invalid inputs (422), service failure (503), auth (401).
- **AUTH:** future-required.

### 24. Save grooming style

- **Screen:** GroomingResultScreen ("Save Style").
- **User action:** tap "Save Style".
- **Required input:** the recommendation id.
- **Data read/written:** nothing today — SnackBar only.
- **Backend responsibility (future):** `POST /looks/saved` (style ref) / `POST /profile/style`.
- **Expected response:** saved reference id.
- **Error conditions:** auth (401).
- **AUTH:** future-required.

### 25. Send assistant message

- **Screen:** AssistantScreen.
- **User action:** send a chat message (or tap a clarification chip).
- **Required input:** message text + history + `AssistantUserContext`
  (wardrobe/face/savedLooks/occasions) — the ONLY implemented remote call
  (`assistant_client.dart:38`).
- **Data read:** `LearningService` model snapshot; backend catalog.
- **Data written:** `assistant_message` signal locally; conversation stays in
  memory.
- **Backend responsibility:** current `engine.py` (rules + catalog + optional
  Ollama text enrichment). Future: authenticated routing + persisted context.
- **Expected response:** `AssistantReply` (intent/text/cards/clarifications/
  navigation); on failure the app falls back to `OfflineAssistant`
  (`assistant_service.dart:71`).
- **Error conditions:** backend unreachable (timeout → offline fallback, not an
  error to the user), 4xx/5xx logged, invalid context (422), auth (401).
- **AUTH:** future-required (conversations + context are private). **None today.**

### 26. Open assistant suggestion card

- **Screen:** AssistantScreen.
- **User action:** tap a suggestion card.
- **Required input:** card title.
- **Data read/written:** local `suggestion_opened` signal
  (`assistant_service.dart:91`); no backend call.
- **Backend responsibility (future):** `POST /assistant/feedback` — record
  card interaction for learning.
- **Expected response:** 204 ack.
- **Error conditions:** auth (401).
- **AUTH:** future-required.

### 27. Navigate via assistant

- **Screen:** AssistantScreen.
- **User action:** tap a navigation request / say "go to wardrobe".
- **Required input:** navigation route (in reply) or message text.
- **Data read/written:** local `assistant_navigation` signal (:95).
- **Backend responsibility:** navigation is already returned server-side
  (`NavigationRequest`); future: none beyond auth.
- **Expected response:** route handled by the router.
- **Error conditions:** unknown route (client-side guard), auth (401).
- **AUTH:** future-required.

### 28. Update profile / preferences / settings

- **Screen:** ProfileScreen / PreferencesScreen / SettingsScreen / UpgradeScreen.
- **User action:** toggle preferences/settings, edit profile fields.
- **Required input:** changed preference/setting values (switch toggles,
  option selection).
- **Data read:** mock preference/settings lists.
- **Data written:** **nothing today** — all widget state
  (`PreferencesScreen`/`SettingsScreen` render local state; the profile
  dashboard is `ProfileData.mock`, disconnected from `UserModel`).
- **Backend responsibility (future):** `PATCH /users/me` (name, avatar, style
  DNA) + `PUT /users/me/preferences` (stored JSONB) + `PUT /users/me/settings`.
- **Expected response:** updated profile/preferences.
- **Error conditions:** invalid values (422), auth (401).
- **AUTH:** future-required. **None today.**

### 29. Sign out

- **Screen:** ProfileScreen menu ("Sign Out", `profile_mock_data.dart:107`).
- **User action:** tap "Sign Out".
- **Required input:** none.
- **Data read/written:** nothing today — SnackBar only.
- **Backend responsibility (future):** `POST /auth/logout` — revoke session
  token.
- **Expected response:** 204 + local session cleared.
- **Error conditions:** already logged out (401, idempotent).
- **AUTH:** required.

### 30. Subscribe / upgrade

- **Screen:** SubscriptionScreen / UpgradeScreen.
- **User action:** choose a plan and subscribe.
- **Required input:** plan id (`ProfileMockData.plans`).
- **Data read:** mock plan list (static).
- **Data written:** nothing today.
- **Backend responsibility (future):** `POST /subscriptions` — purchase via
  external entitlement/payment service (external, STORAGE_INVENTORY cat 5),
  record `subscriptions` state.
- **Expected response:** plan activation + entitlement.
- **Error conditions:** payment failure (402/424), plan not found (404),
  store unreachable (503), auth (401).
- **AUTH:** future-required.

### 31. Submit feedback / rating

- **Screen:** **none — the feature does not exist.** Verified: no feedback
  form, no rating control anywhere (only the "Haptic Feedback" settings row,
  `profile_mocks.dart:248`, which is a settings toggle, not user feedback).
  The `LearningSignal` docstring mentions "feedback" as a concept
  (`learning/data/models.dart:79`) but no action records it.
- **User action:** n/a (missing feature).
- **Required input:** (future) rating + optional comment + feature/reference.
- **Data read/written:** today none.
- **Backend responsibility (future):** `POST /feedback` — validate, store,
  (optionally) link to a signal/look id.
- **Expected response:** 201/204 ack.
- **Error conditions:** invalid payload (422), spam/rate-limit (429).
- **AUTH:** user-scoped (or public with rate limits) — future decision.
- **Note:** flagged as a **missing concept** (DATA_MODEL_INVENTORY §19.6);
  the requirement is derived, not observed behavior.

### 32. Sync local data to account

- **Screen:** post-onboarding (implicit; "Maybe Later — Save Locally" is the
  entry point for the anonymous path).
- **User action:** continue offline, then create an account later (or sign in
  on a new device).
- **Required input:** the full local `UserModel` blob (JSONB candidate).
- **Data read:** `UserModel` from SharedPreferences.
- **Data written:** today only the local blob.
- **Backend responsibility (future):** `POST /users/me/sync` — upsert the
  UserModel snapshot (JSONB) + split relational rows (wardrobe/events/signals/
  saved-looks); conflict handling (server-vs-device timestamps).
- **Expected response:** sync receipt / merged model.
- **Error conditions:** conflicts (409 → resolution), auth (401), payload too
  large (413).
- **AUTH:** future-required.

---

## Part 3 — Error-condition summary (cross-action)

| Condition | Actions affected | Future HTTP |
| --- | --- | --- |
| Not authenticated / expired token | all user-data actions | 401 |
| Not found (item/event/look/plan/event) | 6, 7, 10, 11, 12, 13, 14, 30 | 404 |
| Invalid input (vocab, validation, dates) | 1, 5, 9, 15, 18, 21, 23, 28 | 422 |
| Duplicate / conflict | 1 (email), 5 (dup item), 12/14/17/19 (dup save), 32 (sync) | 409 |
| Backend unreachable / failure | 11, 13, 16, 18, 20, 21, 23, 30 | 503 (or client offline fallback, as assistant does) |
| Media invalid / too large | 16, 21 | 413 / 422 |
| Rate limiting | 1, 3, 31 | 429 |
| Payment failure | 30 | 402 / 424 |
| Client-side only (no server) | edit/delete stubs (7, 10), Save Outfit (19), profile (28) | n/a — no call today |

---

## Part 4 — Requirements derived, not implemented

1. **Every action that writes user data needs authentication** in the future;
   today there is none (account creation is a mock).
2. **The only existing backend contract is `POST /v1/assistant/chat`** — all
   other operations above are new, derived requirements. The assistant endpoint
   already accepts the user model (`UserContext`) and must be secured once auth
   lands.
3. **Four action clusters map to the same future endpoints:** saved looks
   (12/14/17/22/24 → `POST /looks/saved`), generation (11/18/20 → outfit
   generate), analysis (16/21/23 → analysis), and profile (28 → users/me).
   This consolidation is intentional — the UI currently duplicates the concept
   across features (see `DATA_MODEL_INVENTORY` §19.1).
4. **Several actions write nothing today** (stubs): edit/delete item and event,
   Save Outfit, Save Style, Sign Out, profile/preferences, subscribe. Their
   backend requirements are derived from UI presence, not from observed
   persistence.
5. **Feedback (#31) is a missing feature** — the task example lists it, but no
   UI or data path exists; it is documented as a requirement gap, not a claim.
6. **Event-generated outfit (#11)** currently loses the event context (routes
   to the builder with no event data) — the future endpoint must carry the
   occasion seed, fixing the current data-loss.
7. **Authentication is a prerequisite for every relational write** in
   STORAGE_INVENTORY Part 2; until then all rows live in the on-device
   `UserModel` blob (the local store remains the source of truth).
