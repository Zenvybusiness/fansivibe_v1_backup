# Fansivibe — Stage 2: Product Feature Inventory

**Document Type:** Product Feature Inventory & Classification  
**Status:** Canonical Active Baseline  
**Date:** October 31, 2026  
**Audited Against:** Git Working Tree (commit `19c35b4`, Stage 1D completion)

---

## 1. Classification Methodology & Taxonomy

This inventory audits every major feature of the Fansivibe platform against actual Flutter UI implementations, backend FastAPI endpoints, PostgreSQL database tables, domain rules, and local AI model pipelines. Features are classified into one of six mutually exclusive operational statuses:

1. **IMPLEMENTED AND WORKING:** Fully functional end-to-end (UI, API, database persistence, and AI/domain logic). Proven by integration tests or manual verification.
2. **IMPLEMENTED BUT NEEDS IMPROVEMENT:** Core functional loop executes, but contains functional gaps, UX friction, incomplete data synchronization, or architectural limitations.
3. **PARTIALLY IMPLEMENTED:** Scaffolded across UI and backend, but significant logic, screen transitions, or error handling are missing or disconnected.
4. **UI ONLY / PLACEHOLDER:** Visual presentation exists in Flutter, but buttons perform no operations, show static mock data, or lack backend endpoints and schema models.
5. **NOT IMPLEMENTED:** Planned or documented feature with no substantial code in either Flutter or backend.
6. **BLOCKED BY A DEPENDENCY OR DECISION:** Implementation cannot proceed until an external dependency, architectural decision, or commercial agreement is resolved.

---

## 2. Feature Classification Matrix

| Feature ID | Feature Name | Primary Domain | Operational Status | Key Gap / Deficiency |
| :--- | :--- | :--- | :--- | :--- |
| **FEAT-01** | User Authentication & Session Management | Auth | **IMPLEMENTED AND WORKING** | Session refresh token rotation not yet implemented |
| **FEAT-02** | Guest Mode & Ephemeral Session Isolation | Auth / Guest | **IMPLEMENTED AND WORKING** | None (Fully adheres to D10 Option A & DEC-028) |
| **FEAT-03** | Post-Auth Guest Data Migration Flow | Auth / Onboarding | **IMPLEMENTED AND WORKING** | None (Merge/Keep/Discard dialogs verified) |
| **FEAT-04** | Wardrobe Inventory & Filtering | Wardrobe | **IMPLEMENTED AND WORKING** | Item photos persist locally; remote cloud image sync pending |
| **FEAT-05** | Wardrobe Item Creation & Editing | Wardrobe | **IMPLEMENTED AND WORKING** | Photo file upload endpoint (`POST /v1/wardrobe/items/upload`) missing |
| **FEAT-06** | Single-Item Wear Logging | Wardrobe | **IMPLEMENTED AND WORKING** | Only accessible from individual item details screen |
| **FEAT-07** | Multi-Item Outfit Wear Logging | Wardrobe / Looks | **PARTIALLY IMPLEMENTED** | Backend endpoint ready; Flutter UI has no multi-item wear action |
| **FEAT-08** | AI Stylist Canonical Recommendation Engine | Recommendations | **IMPLEMENTED AND WORKING** | None (12-term candidate scoring canonicalized in `analysis_rules.py`) |
| **FEAT-09** | AI Stylist Conversational Chat & Assistant | Assistant / LLM | **IMPLEMENTED AND WORKING** | None (Harmonized response structure with dual cards & metrics) |
| **FEAT-10** | Outfit Builder (Context-Driven Assembly) | Outfit Builder | **IMPLEMENTED AND WORKING** | Occasion transparency notice active; component swapping missing |
| **FEAT-11** | Outfit Scan & Garment Attribute Extraction | Vision / Wardrobe | **IMPLEMENTED AND WORKING** | Ollama vision active; "Add to Wardrobe" prefill operational |
| **FEAT-12** | Hairstyle & Face Scan Analysis | Hairstyle / Grooming | **IMPLEMENTED AND WORKING** | Ollama face detection active; 8 canonical looks; save style active |
| **FEAT-13** | Grooming & Facial Hair Analysis | Grooming | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Authenticated bypass bug: manual inputs not sent to backend |
| **FEAT-14** | Today's Look (Daily Outfit Curation) | Daily Looks | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | "Wear This Look" button only displays snackbar, no API wear log |
| **FEAT-15** | Saved Looks & History Archive | Saved Looks | **IMPLEMENTED AND WORKING** | Items stored as raw UUIDs; requires frontend wardrobe join |
| **FEAT-16** | Event & Calendar Style Planning | Events / Calendar | **IMPLEMENTED AND WORKING** | Standalone CRUD works; no sync with native device calendar |
| **FEAT-17** | User Appearance & Profile Preferences | Profile / Identity | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Only occasion preferences sync to backend; style archetype local |
| **FEAT-18** | Style Evolution & Gamification Metrics | Learning / Stats | **IMPLEMENTED BUT NEEDS IMPROVEMENT** | Style Score and Streak computed locally; server sync partial |
| **FEAT-19** | Virtual Try-On (VTO) Scaffolding | Try-On | **UI ONLY / PLACEHOLDER** | Stage F0 mockup; displays synthetic SVG watermarked "TEST DATA" |
| **FEAT-20** | Subscription & Plan Management | Billing / Profile | **UI ONLY / PLACEHOLDER** | Static plan cards; empty `onPressed` callbacks; no Stripe/IAP |
| **FEAT-21** | In-App Help & Customer Support | Support / Profile | **UI ONLY / PLACEHOLDER** | Static FAQ lists; non-functional action buttons; no ticketing |
| **FEAT-22** | Settings & Application Preferences | Settings | **UI ONLY / PLACEHOLDER** | In-memory switches; does not persist to `user_state.settings` |
| **FEAT-23** | Fashion Reasoning Ontology (FFO Engine) | AI / Reasoning | **IMPLEMENTED AND WORKING** | Standalone query endpoint ready; not hooked to direct UI tab |
| **FEAT-24** | Discovery Commerce & Affiliate Shopping | Commerce | **BLOCKED BY A DEPENDENCY OR DECISION** | Blocked by Decision M14; external affiliate agreements required |

---

## 3. Detailed Feature Breakdown

### FEAT-01: User Authentication & Session Management
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/auth/presentation/screens/login_screen.dart`
  - `lib/features/auth/presentation/screens/register_screen.dart`
  - `lib/features/auth/data/auth_service.dart`
  - `lib/core/auth/auth_guard.dart`
  - `lib/core/auth/session_manager.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/auth/login` (`app/api/routers/auth.py`)
  - `POST /v1/auth/register` (`app/api/routers/auth.py`)
  - `POST /v1/auth/logout` (`app/api/routers/auth.py`)
  - `GET /v1/users/me` (`app/api/routers/users.py`)
- **Database Tables:** `users` (id, email, hashed_password, is_active, created_at, updated_at).
- **External / AI Dependencies:** None (Argon2 / bcrypt password hashing; standard JWT tokens).
- **What Already Works:** User registration, email/password validation, credential login, JWT token issuance and persistence in Flutter `FlutterSecureStorage`, automatic auth state restoration on app boot, zero-network declarative routing via `AuthGuard`.
- **What Remains to Be Built:** Refresh token rotation pipeline, social OAuth logins (Apple ID, Google Sign-In), password reset/recovery flow.
- **Dependencies:** Foundation for all authenticated features.

---

### FEAT-02: Guest Mode & Ephemeral Session Isolation
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/auth/presentation/screens/guest_screen.dart`
  - `lib/features/home/presentation/screens/guest_home_screen.dart`
  - `lib/features/wardrobe/data/ephemeral_wardrobe_item_repository.dart`
  - `lib/features/profile/data/ephemeral_user_state_repository.dart`
  - `lib/core/data/guest_preview_disclosure.dart`
- **Backend Endpoints & Services:** None (Zero-network by design under Decision D10 Option A).
- **Database Tables:** None (Strictly zero backend database writes; guest data kept in memory and device-local SQLite).
- **External / AI Dependencies:** Local mock generators and client-side ephemeral caches.
- **What Already Works:** One-tap guest entry into app shell (`/home`, `/discover`, `/stylist`, `/wardrobe`, `/profile`), full exploration of UI tabs, client-side ephemeral wardrobe additions, guest preview disclaimer dialog, zero database pollution, zero biometric capture.
- **What Remains to Be Built:** None for Stage 2 baseline; adheres 100% to DEC-028.
- **Dependencies:** None.

---

### FEAT-03: Post-Auth Guest Data Migration Flow
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/auth/presentation/screens/post_auth_flow.dart`
  - `lib/features/wardrobe/presentation/dialogs/post_auth_conversion_dialog.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/wardrobe/items` (`app/api/routers/wardrobe.py` batch creation)
  - `PATCH /v1/users/me` (`app/api/routers/users.py` preferences sync)
- **Database Tables:** `wardrobe_items`, `user_state`.
- **External / AI Dependencies:** None.
- **What Already Works:** Upon registering or logging in from guest mode, `handlePostAuthConversion` inspects local ephemeral repositories for guest items and styling preferences. Presents users with an explicit triple-option modal (Merge Data, Keep Cloud Only, Discard Local). Under Merge, pushes local items to PostgreSQL via authenticated API. Strictly purges face biometrics from migration payload.
- **What Remains to Be Built:** Visual progress indicator for large batch migrations (>20 items).
- **Dependencies:** FEAT-01, FEAT-02, FEAT-04.

---

### FEAT-04: Wardrobe Inventory & Filtering
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/wardrobe/presentation/screens/wardrobe_screen.dart`
  - `lib/features/wardrobe/presentation/widgets/wardrobe_item_card.dart`
  - `lib/features/wardrobe/presentation/widgets/category_selector.dart`
  - `lib/features/wardrobe/data/wardrobe_repository.dart`
  - `lib/features/wardrobe/data/authenticated_wardrobe_item_repository.dart`
- **Backend Endpoints & Services:**
  - `GET /v1/wardrobe/items` (`app/api/routers/wardrobe.py`)
  - `GET /v1/wardrobe/wear-summary` (`app/api/routers/wardrobe.py`)
- **Database Tables:** `wardrobe_items` (user_id, category, subcategory, color_code, fit, occasions, image_ref).
- **External / AI Dependencies:** None.
- **What Already Works:** Displaying wardrobe grid adhering to the 65% image / 35% content card rule; category filtering (`tops`, `bottoms`, `outerwear`, `footwear`, `accessories`); subcategory filtering; wear count display badges; search by name/tags; pulling authenticated data via `AuthenticatedWardrobeItemRepository`.
- **What Remains to Be Built:** Remote image persistence. Images attached on device are currently stored as local file paths (`file:///data/...`) in Flutter SQLite (`learning_items`). The backend stores JSONB metadata in `image_ref` but does not host an image blob storage server (S3 / Cloud Storage / MinIO).
- **Dependencies:** FEAT-01.

---

### FEAT-05: Wardrobe Item Creation & Editing
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/wardrobe/presentation/screens/add_garment_screen.dart`
  - `lib/features/wardrobe/presentation/screens/edit_garment_screen.dart`
  - `lib/features/wardrobe/presentation/screens/wardrobe_item_details_screen.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/wardrobe/items` (`app/api/routers/wardrobe.py`)
  - `PATCH /v1/wardrobe/items/{id}` (`app/api/routers/wardrobe.py`)
  - `DELETE /v1/wardrobe/items/{id}` (`app/api/routers/wardrobe.py`)
- **Database Tables:** `wardrobe_items`.
- **External / AI Dependencies:** Optional camera/gallery image picker.
- **What Already Works:** Manual creation with standard controlled attributes (name, category, subcategory, color, formality, fit, season, occasion tags, brand). Updates and deletion with immediate optimistic UI updates and backend synchronization.
- **What Remains to Be Built:** Dedicated multipart binary upload endpoint (`POST /v1/wardrobe/items/upload`) for uploading photos directly to cloud object storage.
- **Dependencies:** FEAT-04.

---

### FEAT-06: Single-Item Wear Logging
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/wardrobe/presentation/screens/wardrobe_item_details_screen.dart`
  - `lib/features/wardrobe/data/wardrobe_repository.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/wardrobe/wears` (`app/api/routers/wardrobe.py`)
  - `GET /v1/wardrobe/wear-summary` (`app/api/routers/wardrobe.py`)
- **Database Tables:** `wardrobe_wear_groups`, `wardrobe_wear_events`.
- **External / AI Dependencies:** None.
- **What Already Works:** Tapping "Log Wear Today" on `WardrobeItemDetailsScreen` constructs a UUIDv4 idempotency key, posts single `itemIds: [itemId]` to `POST /v1/wardrobe/wears`, increments the item wear counter in PostgreSQL, records an event in `wardrobe_wear_events`, and updates the UI wear count badge.
- **What Remains to Be Built:** Surfacing this action from list cards without opening the full details view.
- **Dependencies:** FEAT-04.

---

### FEAT-07: Multi-Item Outfit Wear Logging
- **Status:** PARTIALLY IMPLEMENTED
- **Flutter Screens & Files:**
  - `lib/features/home/presentation/screens/daily_outfit_screen.dart` (Contains static "Wear This Look" button that shows a snackbar)
  - `lib/features/outfit_builder/presentation/screens/outfit_recommendation_screen.dart` (Missing wear logging CTA)
  - `lib/features/saved_looks/presentation/screens/saved_looks_screen.dart` (Missing wear logging CTA)
- **Backend Endpoints & Services:**
  - `POST /v1/wardrobe/wears` (`app/api/routers/wardrobe.py` supports 1..10 `itemIds` in a single transactional wear group)
- **Database Tables:** `wardrobe_wear_groups` (id, user_id, worn_date, wear_context, idempotency_key), `wardrobe_wear_events` (id, wear_group_id, wardrobe_item_id).
- **External / AI Dependencies:** None.
- **What Already Works:** Backend API and transactional database ledger are 100% complete and tested. Accepts multi-item batches, guarantees atomic wear counts, updates last worn timestamps, and applies wear decay calculations.
- **What Remains to Be Built:** Flutter UI integration: Connecting the "Wear This Look" button on `DailyOutfitScreen` and adding wear logging buttons to `OutfitRecommendationScreen` and `SavedLooksScreen` that call `POST /v1/wardrobe/wears` with all garment item IDs in the outfit.
- **Dependencies:** FEAT-04, FEAT-06, FEAT-10, FEAT-14.

---

### FEAT-08: AI Stylist Canonical Recommendation Engine
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/ai_assistant/presentation/screens/stylist_screen.dart`
  - `lib/features/outfit_builder/presentation/screens/outfit_generation_screen.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/outfits/generate` (`app/api/routers/outfits.py`)
  - Canonical domain service: `app/domain/services/analysis_rules.py`
  - Use case: `app/application/use_cases/outfits.py` (`GenerateOutfit`)
- **Database Tables:** `wardrobe_items`, `user_state`.
- **External / AI Dependencies:** Local algorithmic 12-term candidate scoring (color harmony, formality matching, temperature/weather fit, style archetype alignment, wear decay penalty).
- **What Already Works:** Complete deterministic ranking of wardrobe candidates based on user preferences, occasions, and weather parameters. Returns structured JSON containing top recommendations, match score percentage, component breakdown, color harmony explanation, and grounded styling advice. Fully tested under `tests/test_analysis_rules.py`.
- **What Remains to Be Built:** Real-time external weather API integration (currently consumes mock/passed weather parameters).
- **Dependencies:** FEAT-04.

---

### FEAT-09: AI Stylist Conversational Chat & Assistant
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/ai_assistant/presentation/screens/stylist_screen.dart`
  - `lib/features/ai_assistant/presentation/widgets/chat_message_bubble.dart`
  - `lib/features/ai_assistant/presentation/widgets/outfit_carousel_card.dart`
  - `lib/features/ai_assistant/presentation/widgets/floating_assistant_button.dart`
  - `lib/features/ai_assistant/data/assistant_service.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/assistant/chat` (`app/api/routers/assistant.py`)
  - Canonical tool delegation: `app/domain/services/tool_registry.py` -> `GenerateOutfit`
- **Database Tables:** `ai_conversations`, `ai_messages`.
- **External / AI Dependencies:** Local Ollama `qwen2.5vl:3b` with fallback to deterministic prompt responses.
- **What Already Works:** Interactive chat conversation with natural language comprehension. When users ask for outfit recommendations, assistant invokes canonical `GenerateOutfit` tool, producing a single harmonized response containing both `reply.cards` and `reply.outfitIntelligence` metrics (`% Ensemble Match`). Rendered in Flutter as rich horizontal outfit carousels directly inside the chat stream.
- **What Remains to Be Built:** Chat history persistence in Flutter (currently resets when app is restarted); voice input transcription.
- **Dependencies:** FEAT-01, FEAT-08.

---

### FEAT-10: Outfit Builder (Context-Driven Assembly)
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/outfit_builder/presentation/screens/build_outfit_screen.dart`
  - `lib/features/outfit_builder/presentation/screens/outfit_generation_screen.dart`
  - `lib/features/outfit_builder/presentation/screens/outfit_recommendation_screen.dart`
  - `lib/features/outfit_builder/data/outfit_service.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/outfits/generate` (`app/api/routers/outfits.py`)
  - `POST /v1/looks/saved` (`app/api/routers/saved_looks.py`)
- **Database Tables:** `wardrobe_items`, `user_state`, `saved_looks`.
- **External / AI Dependencies:** `GenerateOutfit` domain use case.
- **What Already Works:** Multi-step wizard: select target occasion (Casual, Work, Formal, Date Night, Active), mood, and weather. Displays context transparency notice when occasion matches style profile. Passes criteria to backend, renders generated 3-outfit options with component cards, formality badge, match score, and allows saving to Saved Looks.
- **What Remains to Be Built:** In-place component swapping (e.g. "Keep this top, but give me a different pair of shoes").
- **Dependencies:** FEAT-04, FEAT-08, FEAT-15.

---

### FEAT-11: Outfit Scan & Garment Attribute Extraction
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/outfit_scan/presentation/screens/outfit_scan_screen.dart`
  - `lib/features/outfit_scan/presentation/screens/outfit_processing_screen.dart`
  - `lib/features/outfit_scan/presentation/screens/outfit_analysis_screen.dart`
  - `lib/features/outfit_scan/data/outfit_scan_service.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/analysis/outfit-scan` (`app/api/routers/analysis.py`)
- **Database Tables:** `user_state` (`profile_persistence: "persisted"`), `wardrobe_items` (via prefill).
- **External / AI Dependencies:** Local Ollama `qwen2.5vl:3b` vision adapter (`vision_appearance_adapter.py`).
- **What Already Works:** Camera/gallery image capture of worn outfit; vision analysis extracting upper garment, lower garment, footwear color, style, patterns, and estimated face shape; AI estimate badge; prefilled "Add to Wardrobe" button transferring detected attributes into `AddGarmentScreen`; authenticated profile appearance persistence.
- **What Remains to Be Built:** Multi-item automatic segmentation (splitting a single full-body photo into separate individual wardrobe item catalog photos).
- **Dependencies:** FEAT-04, FEAT-05.

---

### FEAT-12: Hairstyle & Face Scan Analysis
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/hairstyle/presentation/screens/face_scan_screen.dart`
  - `lib/features/hairstyle/presentation/screens/face_processing_screen.dart`
  - `lib/features/hairstyle/presentation/screens/hairstyle_result_screen.dart`
  - `lib/features/hairstyle/data/hairstyle_service.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/analysis/face-shape` (`app/api/routers/analysis.py`)
  - `POST /v1/analysis/hairstyle` (`app/api/routers/analysis.py`)
  - `POST /v1/analysis/hairstyle/save` (`app/api/routers/analysis.py`)
- **Database Tables:** `user_state` (`style_profile.face_shape`, `grooming_profile`).
- **External / AI Dependencies:** Local Ollama vision model; algorithmic hairstyle compatibility matrix (`grooming_rules.py`).
- **What Already Works:** Single and multi-angle face image upload; AI classification of face shape (Oval, Square, Round, Diamond, Heart, Oblong); confidence badge; ranked list of 8 canonical hairstyles with maintenance rating and face shape compatibility explanation; "Save Style" button updating `user_state` in PostgreSQL.
- **What Remains to Be Built:** AR / camera preview overlay showing hairstyle silhouettes over the user's live camera feed.
- **Dependencies:** FEAT-01, FEAT-17.

---

### FEAT-13: Grooming & Facial Hair Analysis
- **Status:** IMPLEMENTED BUT NEEDS IMPROVEMENT
- **Flutter Screens & Files:**
  - `lib/features/grooming/presentation/screens/grooming_input_screen.dart`
  - `lib/features/grooming/presentation/screens/grooming_processing_screen.dart`
  - `lib/features/grooming/presentation/screens/grooming_result_screen.dart`
  - `lib/features/grooming/data/grooming_service.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/analysis/grooming` (`app/api/routers/analysis.py`)
  - Domain service: `app/domain/services/grooming_rules.py`
- **Database Tables:** `user_state`.
- **External / AI Dependencies:** Algorithmic grooming rules engine.
- **What Already Works:** Presentation screens with face shape, beard style, density, and skin sensitivity inputs. Rule engine computes beard-to-face shape compatibility score and grooming maintenance tips.
- **Defects & Broken Journey:** **CRITICAL DEFECT.** When authenticated users enter grooming details in `GroomingInputScreen`, `GroomingProcessingScreen._runAuthenticated()` calls `_service.runAnalysis()` with empty parameters, posting `{}` to `POST /v1/analysis/grooming`. The backend use case `CreateGroomingRun` inspects `user_state.style_profile` for `face_shape`. If the user has not previously completed a Face Scan, the backend raises `422 INSUFFICIENT_USER_DATA`, causing the analysis to fail despite the user explicitly selecting their face shape on screen.
- **What Remains to Be Built:** Forwarding user-selected manual parameters in the HTTP request body when no saved face shape exists in user profile.
- **Dependencies:** FEAT-01, FEAT-12, FEAT-17.

---

### FEAT-14: Today's Look (Daily Outfit Curation)
- **Status:** IMPLEMENTED BUT NEEDS IMPROVEMENT
- **Flutter Screens & Files:**
  - `lib/features/home/presentation/screens/daily_outfit_screen.dart`
  - `lib/features/home/presentation/widgets/outfit_preview_card.dart`
  - `lib/features/home/data/today_service.dart`
- **Backend Endpoints & Services:**
  - `GET /v1/looks/today` (`app/api/routers/today.py`)
  - `POST /v1/looks/today` (`app/api/routers/today.py` regenerate with seed)
  - `POST /v1/looks/today/save` (`app/api/routers/today.py` save with `sourceContext: "daily"`)
- **Database Tables:** `wardrobe_items`, `saved_looks`.
- **External / AI Dependencies:** `GenerateOutfit` use case.
- **What Already Works:** Daily outfit generated on demand using a deterministic daily seed; component cards with image and metadata; regenerate outfit option; save to saved looks.
- **Defects & Broken Journey:** The "Wear This Look" button on `DailyOutfitScreen` currently only triggers a local `ScaffoldMessenger` snackbar ("Logged wear for today!"). It does not call `POST /v1/wardrobe/wears`, meaning daily outfit engagement is completely disconnected from the wardrobe wear tracking ledger and wear decay scoring.
- **What Remains to Be Built:** Multi-item wear logging integration (FEAT-07).
- **Dependencies:** FEAT-04, FEAT-07, FEAT-08.

---

### FEAT-15: Saved Looks & History Archive
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/saved_looks/presentation/screens/saved_looks_screen.dart`
  - `lib/features/saved_looks/presentation/screens/look_details_screen.dart`
  - `lib/features/saved_looks/data/saved_looks_service.dart`
- **Backend Endpoints & Services:**
  - `GET /v1/looks/saved` (`app/api/routers/saved_looks.py`)
  - `POST /v1/looks/saved` (`app/api/routers/saved_looks.py`)
  - `DELETE /v1/looks/saved/{id}` (`app/api/routers/saved_looks.py`)
  - `POST /v1/feedback` (`app/api/routers/feedback.py`)
- **Database Tables:** `saved_looks` (id, user_id, name, occasion, match_score, items JSONB, tags JSONB, source_context, created_at).
- **External / AI Dependencies:** None.
- **What Already Works:** Listing saved outfits, filtering by occasion, deleting saved outfits, submitting feedback reactions (like/dislike/favorite).
- **What Remains to Be Built:** Frontend item name resolution: `saved_looks.items` stores garment UUIDs; `LookDetailsScreen` displays IDs unless hydrated against active wardrobe cache.
- **Dependencies:** FEAT-01, FEAT-04, FEAT-10.

---

### FEAT-16: Event & Calendar Style Planning
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:**
  - `lib/features/events/presentation/screens/events_screen.dart`
  - `lib/features/events/presentation/screens/event_details_screen.dart`
  - `lib/features/events/presentation/screens/create_event_screen.dart`
  - `lib/features/events/data/event_service.dart`
- **Backend Endpoints & Services:**
  - `GET /v1/events` (`app/api/routers/events.py`)
  - `POST /v1/events` (`app/api/routers/events.py`)
  - `GET /v1/events/{id}` (`app/api/routers/events.py`)
  - `PATCH /v1/events/{id}` (`app/api/routers/events.py`)
  - `DELETE /v1/events/{id}` (`app/api/routers/events.py`)
  - `POST /v1/events/{id}/outfit` (`app/api/routers/events.py`)
- **Database Tables:** `user_events` (id, user_id, title, event_type, date, time, location, formality, dress_code, notes).
- **External / AI Dependencies:** `GenerateOutfit` use case parameterized by event formality.
- **What Already Works:** Creating upcoming calendar events (Weddings, Job Interviews, Dinners, Parties), generating bespoke event-tailored outfit recommendations from wardrobe items, attaching selected outfit to event record.
- **What Remains to Be Built:** Device calendar integration (iOS EventKit / Android CalendarProvider); multi-day trip packing list generator.
- **Dependencies:** FEAT-01, FEAT-04, FEAT-08.

---

### FEAT-17: User Appearance & Profile Preferences
- **Status:** IMPLEMENTED BUT NEEDS IMPROVEMENT
- **Flutter Screens & Files:**
  - `lib/features/profile/presentation/screens/profile_screen.dart`
  - `lib/features/profile/presentation/screens/edit_profile_screen.dart`
  - `lib/features/profile/presentation/screens/style_preferences_screen.dart`
  - `lib/features/profile/data/user_profile_repository.dart`
- **Backend Endpoints & Services:**
  - `GET /v1/users/me` (`app/api/routers/users.py`)
  - `PATCH /v1/users/me` (`app/api/routers/users.py`)
  - `GET /v1/users/me/appearance` (`app/api/routers/users.py`)
  - `PATCH /v1/users/me/appearance` (`app/api/routers/users.py`)
- **Database Tables:** `users`, `user_state` (`style_profile`, `appearance`, `preferred_occasions`).
- **External / AI Dependencies:** None.
- **What Already Works:** Profile display; appearance biometrics display (face shape, skin undertone, contrast level); saving occasion preferences to `preferred_occasions`.
- **Defects & Broken Journey:** In `StylePreferencesScreen`, only "Occasion Focus" syncs to backend `PATCH /v1/users/me`. Archetype selectors (Minimalist, Classic, Streetwear, Bold) and color palette exclusions are only kept in device memory and do not update `user_state.style_profile`.
- **What Remains to Be Built:** Complete bi-directional sync of all style archetypes and fit preferences to `user_state`.
- **Dependencies:** FEAT-01.

---

### FEAT-18: Style Evolution & Gamification Metrics
- **Status:** IMPLEMENTED BUT NEEDS IMPROVEMENT
- **Flutter Screens & Files:**
  - `lib/features/learning/presentation/screens/learning_insights_screen.dart`
  - `lib/features/learning/presentation/widgets/style_score_card.dart`
  - `lib/features/learning/data/learning_service.dart`
- **Backend Endpoints & Services:**
  - `GET /v1/learning/insights` (`app/api/routers/learning.py`)
  - `POST /v1/learning/feedback` (`app/api/routers/learning.py`)
- **Database Tables:** `learning_feedback`, `style_evolution_snapshots`.
- **External / AI Dependencies:** Algorithmic score aggregator.
- **What Already Works:** Style insights dashboard displaying Style Score (0–100), active logging streak, wardrobe utilization percentage, and color palette distribution.
- **Defects & Broken Journey:** Style Streak and Score calculation in Flutter primarily reads from local `learning_service.dart` SQLite database rather than computing deterministically from the authoritative PostgreSQL `wardrobe_wear_groups` ledger.
- **What Remains to Be Built:** Unified backend-driven score aggregation connecting wear logs and outfit feedback directly into user learning metrics.
- **Dependencies:** FEAT-04, FEAT-06, FEAT-07.

---

### FEAT-19: Virtual Try-On (VTO) Scaffolding
- **Status:** UI ONLY / PLACEHOLDER
- **Flutter Screens & Files:**
  - `lib/features/try_on/presentation/screens/try_on_screen.dart`
  - `lib/features/try_on/presentation/widgets/try_on_canvas.dart`
- **Backend Endpoints & Services:**
  - `POST /v1/try-on/generate` (Scaffold endpoint in `app/api/routers/try_on.py` returning synthetic test payload)
- **Database Tables:** None.
- **External / AI Dependencies:** None connected (Requires diffusion model / warp model pipeline).
- **What Already Works:** Entry banner on HomeScreen; selection of outfit items; rendering a static placeholder preview canvas with a watermarked "TEST DATA" synthetic SVG.
- **What Remains to Be Built:** Real diffusion/warping virtual try-on pipeline (IDM-VTON / CatVTON / ComfyUI integration), user avatar photo upload, garment warping, backend inference queue.
- **Dependencies:** FEAT-04, FEAT-10.

---

### FEAT-20: Subscription & Plan Management
- **Status:** UI ONLY / PLACEHOLDER
- **Flutter Screens & Files:**
  - `lib/features/profile/presentation/screens/subscription_screen.dart`
  - `lib/features/profile/presentation/widgets/plan_tier_card.dart`
- **Backend Endpoints & Services:** None.
- **Database Tables:** None (`users.tier` enum exists in models, but no subscription billing tables).
- **External / AI Dependencies:** Stripe / RevenueCat / Apple StoreKit / Google Play Billing.
- **What Already Works:** Static presentation displaying Free, Pro ($9.99/mo), and Atelier ($19.99/mo) cards with feature bullet lists.
- **What Remains to Be Built:** Complete payment processing infrastructure, webhook listener, entitlement gating middleware, StoreKit/Google Play integration.
- **Dependencies:** FEAT-01.

---

### FEAT-21: In-App Help & Customer Support
- **Status:** UI ONLY / PLACEHOLDER
- **Flutter Screens & Files:**
  - `lib/features/profile/presentation/screens/support_screen.dart`
- **Backend Endpoints & Services:** None.
- **Database Tables:** None.
- **External / AI Dependencies:** None (Zendesk / Intercom / Email API).
- **What Already Works:** Static FAQ accordion lists and "Contact Support" list tiles.
- **What Remains to Be Built:** Ticketing API, in-app messaging, or `mailto:` / webview redirection.
- **Dependencies:** None.

---

### FEAT-22: Settings & Application Preferences
- **Status:** UI ONLY / PLACEHOLDER
- **Flutter Screens & Files:**
  - `lib/features/settings/presentation/screens/settings_screen.dart`
- **Backend Endpoints & Services:** None.
- **Database Tables:** `user_state.settings` (JSONB column exists in DB, but no active endpoint).
- **External / AI Dependencies:** None.
- **What Already Works:** Toggle switches for Push Notifications, Dark Mode, Biometric Lock, and Account Deletion confirmation dialog.
- **Defects:** Toggles only update local widget state in memory and discard changes upon leaving screen.
- **What Remains to Be Built:** Persistence to `SharedPreferences` locally and synchronization to `user_state.settings` in backend.
- **Dependencies:** FEAT-01.

---

### FEAT-23: Fashion Reasoning Ontology (FFO Engine)
- **Status:** IMPLEMENTED AND WORKING
- **Flutter Screens & Files:** None (Internal service layer; accessible via assistant and outfit builder).
- **Backend Endpoints & Services:**
  - `POST /v1/reasoning/query` (`app/api/routers/reasoning.py`)
  - Domain service: `app/domain/services/ffo_reasoning.py`
- **Database Tables:** None (Static in-memory ontology comprising 26 formal schemas).
- **External / AI Dependencies:** Local Ollama `qwen2.5vl:3b`.
- **What Already Works:** Grounded query execution evaluating semantic fashion rules (e.g., contrasting textures, silhouette balance, color theory) with rule trace citations.
- **What Remains to Be Built:** Direct UI exposure in Stylist conversation (e.g., "Why this works" explainability breakdown expandable drawer).
- **Dependencies:** FEAT-08, FEAT-09.

---

### FEAT-24: Discovery Commerce & Affiliate Shopping
- **Status:** BLOCKED BY A DEPENDENCY OR DECISION
- **Flutter Screens & Files:**
  - `lib/features/home/presentation/screens/discover_screen.dart`
- **Backend Endpoints & Services:** None.
- **Database Tables:** None.
- **External / AI Dependencies:** External affiliate product feed APIs (ShopStyle / LTK / Rakuten).
- **Status Rationale:** Strictly blocked by Decision M14 ("Discovery Commerce Scaffolding Postponed"). Requires formal commercial affiliate network agreements and catalog ingestion pipelines.
- **Dependencies:** Commercial affiliate partnership agreements.

---

## 4. Summary Statistics & Readiness Overview

- **Total Major Features Audited:** 24
- **Implemented and Working:** 12 (50.0%)
- **Implemented but Needs Improvement:** 5 (20.8%)
- **Partially Implemented:** 1 (4.2%)
- **UI Only / Placeholder:** 5 (20.8%)
- **Blocked by Decision/Dependency:** 1 (4.2%)

### Core Takeaways:
1. **Core Recommendation & Wardrobe Foundation is Solid:** The foundational layers (Auth, Wardrobe CRUD, Canonical 12-term Recommendation, Assistant Chat, Outfit Scan, and Hairstyle) are implemented, verified, and operational.
2. **Engagement Loop Disconnection is the Primary Product Defect:** Multi-item wear logging (`POST /v1/wardrobe/wears`) is complete in the backend, but the Flutter UI fails to call it from `DailyOutfitScreen` ("Wear This Look") or `OutfitRecommendationScreen`. Fixing this will instantly close the daily active user (DAU) retention loop.
3. **Targeted Bug Fixes Required Before Expansion:** The Grooming input bypass bug (FEAT-13) and Style Preferences persistence gap (FEAT-17) require straightforward payload fixes to achieve 100% operational integrity across all existing screens.
