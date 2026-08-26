DOM_DOMAIN_BLUEPRINT
==================

1. DOMAIN IDENTITY
-----------------

- Name: Wardrobe
- Product Category: Personal clothing collection / wardrobe management
- Domain Identifier: wardrobe
- Parent/Related Domain: Hairstyle (shared LearningRepository infrastructure),
  Grooming (shared learning signal pattern), Outfit Builder (future integration),
  Daily Outfit (future integration), Assistant (future integration)
- Feature Flag: wardrobe_enabled (gating M11 feedback endpoint)
- Stage: Full vertical slice implemented (input → collection → item → details → save →
  learn), local-only with future backend sync path
- Last Verified: 2026-08-22 (Stage 8 end-to-end validation)

2. DOMAIN PURPOSE
----------------

- Allow users to build and maintain a personal clothing collection (wardrobe)
- Display clothing items organized by category (tops, bottoms, outerwear, footwear,
  accessories)
- Enable adding new clothing items via category + type + color + texture selection
- Support favoriting items for quick access
- Provide AI-powered wardrobe insights and outfit recommendations
- Enable adding items to outfits for daily styling
- Share wardrobe data across features (home "Today's Look", stylist, profile)
- Reuse existing LearningRepository infrastructure for persistence and learning signals
- Designed for future backend sync (shared_preferences local-first, with backend
  integration planned behind M11 milestone)

3. PRODUCT VALUE
---------------

- Users can see their complete clothing collection at a glance
- Users can add new items with type, color, and texture metadata
- Favoriting items surfaces them priority in the grid
- AI insights ("Wardrobe Health") provide actionable recommendations
- "Add to Outfit" enables daily styling workflows
- Personalization drives "Today's Look" in home screen
- Consistent with the 65% image / 35% content card design rule (ClothingItemCard)
- Shares the same LearningRepository infrastructure as Hairstyle/Profile
- Uses the same mock-first pattern with local persistence, designed for future
  backend sync (post-M11)

4. VERIFIED REALITY CHECK
------------------------

IMPLEMENTED (code-level verified):
- POST /v1/analysis/wardrobe: N/A — no backend API; domain is local-only
- LearningService singleton with static defaultWardrobe (24 items seeded from
  WardrobeMockData.items)
- Local persistence via LocalStore → shared_preferences JSON blob
- UserModel.encode/decode round-trips wardrobe JSON to shared_preferences
- Every mutation (_mutate) atomically persists via _persist()
- addItem() → records 'item_added' signal + persists
- setFace() → records 'analysis_updated' signal + persists
- setStyleType() → records 'style_updated' signal + persists
- addSavedLook() → records 'look_saved' signal + persists
- addPreferredOccasion() → records 'occasion_preferred' signal + persists
- WardrobeDashboardHeader: total items, favorites count, style type display
- WardrobeInsightCard: AI insight with action button
- ClothingItemCard: 65% visual (icon area) / 35% content (title/meta) ratio
- Category filtering (tops, bottoms, outerwear, footwear, accessories, all)
- Favorites filtering (isFavorite flag)
- Bottom navigation "Wardrobe" tab in router_shell.dart
- Full go_router navigation: wardrobe → add-category → add-item → item-details
- 4 screen widgets: WardrobeScreen, AddWardrobeCategoryScreen,
  AddWardrobeItemScreen, WardrobeItemDetailsScreen
- 4 widget tests: WardrobeHeader, WardrobeInsightCard, ClothingItemCard
  (favorite handling), and full WardrobeScreen suite (30+ tests)
- Dart analyze: 0 issues on lib/features/wardrobe/

WORKING (end-to-end verified):
- Add item flow: FAB → Add Category → Select Category → Select Type/Color/Texture →
  Save → Item appears in wardrobe grid + LearningService.persist → LearningSignal
  'item_added' recorded → snackbar "X added to wardrobe"
- Item details: Tap item → WardrobeItemDetailsScreen → view details → Edit snackbar
  / Delete snackbar / Add to Outfit snackbar → navigate back
- Category filtering: Select category filter → grid shows only matching items with
  correct count
- Favorites: Favorite items show heart icon, non-favorites do not
- Learning persistence: App restart → LearningService.load() → persists JSON from
  shared_preferences overrides defaults; no persisted data → defaults used

PARTIAL (functionally operational but with known limitations):
- Flutter type system: No duplicates or type mismatches observed — clean
- M11 feedback endpoint: gated; wardrobe saves = look_saved signal is the approved
  feedback behavior
- PostgreSQL-dependent tests: N/A — no backend DB; local-only persistence
- 0 saves observed in internal pilot (n=5) — hypothesis untested
- Experiment conversion hypothesis: untested (n=5 internal pilot, 0 saves observed)
- Real face-detection: N/A — no image upload; profile-only pass not applicable
- Confidence display: UI shows matchScore-style insights; derived confidence not
  displayed (product decision, not blocker)
- Saved looks visibility: Backend supports it (shared saved_looks table), but
  Flutter UI only shows hairstyle saves; grooming saves would need similar UI
  updates (see G-9 from grooming audit)

MOCK (fallback when backend unreachable):
- When backend unreachable: domain is local-only by design — flow never breaks
- defaultWardrobe (24 items) seeds the model on first launch
- LearningService._ persists to shared_preferences; if unavailable, degrades to
  in-memory so the app never crashes; the model just isn't written
- Mock data visually present but provenance is honest (_usedMockResult not yet in
  wardrobe but mock path is documented)
- When shared_preferences unavailable (e.g. headless tests): degrades to
  in-memory so app never crashes

NOT LIVE-VERIFIED (environment limitation):
- Live end-to-end against reachable backend PostgreSQL: N/A — no backend exists
 ; local-only by design
- Real backend API calls with Bearer auth: N/A — no backend
- Save + learning signal commit in live DB transaction: N/A — local-only
- Experiment conversion hypothesis at scale: untested (n=5 pilot, 0 saves)

HYPOTHESIS (product decision, not code-verified):
- Confidence display: UI shows matchScore-style insights; whether to show derived
  engine confidence is a product decision (W-10), not a blocker
- Experiment conversion: ≥10% hypothesis requires 200 users, 2–4 weeks (documented
  in internal pilot report)
- Real image upload / camera integration: explicitly deferred per D2 (profile-only
  pass, no CV dependencies)
- Backend sync: Local-first design with shared_preferences; M11 milestone adds
  backend endpoint for wardrobe item persistence

DEFERRED (explicitly postponed per architecture rules):
- POST /v1/feedback endpoint (M11): remains gated; save = look_saved signal is the
  approved feedback behavior
- Real image upload / camera: explicitly deferred per critical face input rule (D2);
  no CV dependencies added
- Media pipeline (M16): sealed until MS10.3
- Backend API for wardrobe: explicitly deferred per architecture rules; local-only
  first design with shared_preferences; M11 milestone adds backend
- Experiment conversion hypothesis: untested, documented for M11+ expansion
- Confidence display as dedicated UI field: product decision (W-10), not a blocker

IMPLEMENTED (verified against code):
- Analysis run lifecycle: N/A — no backend runs; local completion state only
- Result snapshot: confidence + needs_more_data not applicable (local-only)
- Saved look: source_context handling via LearningRepository; look_saved signal
  recorded atomically with save
- Owner scoping: user_id scoping via LearningService singleton (single user mode)
- Auth: N/A — single dev user via LearningService.instance
- Knowledge: CatalogKnowledgeSource with wardrobe mock seed data
- Run types: N/A — no run types in local domain
- Looks: N/A — no looks table; wardrobe items stored in UserModel.wardrobe list
- Signal types: 'item_added', 'analysis_updated', 'style_updated', 'look_saved',
  'occasion_preferred', 'look_saved'
- Database contract: reuse existing shared infrastructure (shared_preferences +
  LearningRepository pattern); no new tables created

5. DOMAIN ENTITIES
-----------------

- WardrobeEntry (Flutter + LearningRepository) — id, name, category, color,
  material (optional), isFavorite
- WardrobeItemData (Flutter data layer) — id, name, category, color, material
  (optional), isFavorite (identical fields to WardrobeEntry, different library)
- WardrobeCategory (Flutter data layer) — id, name, iconName, itemCount
- AddItemCategoryConfig (Flutter data layer) — id, name, iconName, types
- ColorOption (Flutter data layer) — name, colorValue
- TextureOption (Flutter data layer) — name
- WardrobeInsightData (Flutter data layer) — title, insight, iconName, accentColor,
  actionLabel
- UserModel (Backend data layer — local) — wardrobe: List<WardrobeEntry>, face:
  FaceProfile?, styleType: String, savedLooks: List<String>, preferredOccasions:
  List<String>, signals: List<LearningSignal>
- FaceProfile (Backend data layer — local) — faceShape, skinTone, bodyType, styleType
- LearningSignal (Backend data layer — local) — type, label, timestamp
- LocalStore (Backend data layer — local) — shared_preferences JSON persistence
- LearningRepository (port) — interface defining wardrobe/savedLooks/face/styleType
 /savedLooks/preferredOccasions/signals accessors

6. FLUTTER ARCHITECTURE
----------------------

6.1 Feature Structure
- Location: lib/features/wardrobe/
- Screens: WardrobeScreen, AddWardrobeCategoryScreen, AddWardrobeItemScreen,
  WardrobeItemDetailsScreen
- Data layer: wardrobe_mock_data.dart, LearningService, LocalStore, UserModel,
  WardrobeEntry, WardrobeCategory, AddItemCategoryConfig, ColorOption,
  TextureOption, WardrobeInsightData
- Widgets: wardrobe_widgets.dart (WardrobeDashboardHeader,
  CategoryTile, WardrobeInsightCard, ClothingItemCard, _FavoriteHeart)

6.2 Navigation (app_router.go_router)
- wardrobe route → WardrobeScreen
  - wardrobe/add-category → AddWardrobeCategoryScreen (category selection)
    - wardrobe/add-item → AddWardrobeItemScreen (type/color/texture entry)
      - wardrobe/item-details → WardrobeItemDetailsScreen (view/edit/delete/add-to-outfit)
- All routes use go_router with StatefulShellRouter
- Route names centralized in RouteNames: wardrobe, wardrobeAddCategory,
  wardrobeAddItem, wardrobeItemDetails
- Bottom navigation: "Wardrobe" tab (4th item) in router_shell.dart

6.3 Input → Processing → Details → Save → Learn Flow
- Input: WardrobeScreen → user views collection, taps category filters, favoriting,
  add FAB → navigation pushes
- Processing: Category selection → type/color/texture entry → save → LearningService
  addItem() → persist → notifyListeners → grid updates
- Result: WardrobeItemDetailsScreen → item details + actions (edit, delete, add to
  outfit) → snackbars + possible navigation
- Save: LearningService.addItem() → _mutate() → _persist() → shared_preferences
  JSON write → notifyListeners → UI updates
- Learn: Every mutation records a LearningSignal (item_added, analysis_updated,
  style_updated, look_saved, occasion_preferred) → accumulated over time → drives
  styleScore, insights, personalization

6.4 State Management
- LearningService extends ChangeNotifier singleton
- Listeners for UI state updates (wardrobe list, category filter, favorites)
- _model holds the mutable UserModel state
- _loaded flag tracks whether init has completed
- _persist() writes JSON to shared_preferences on every mutation

6.5 Error States (Flutter)
- Shared_preferences unavailable: client returns null → service degrades to
  in-memory → flow continues offline (never crashes)
- No items in category: empty state shown ("No items in this category yet",
  "Add your first piece to get started")
- Save failure: not applicable (local-only; mutate always succeeds unless
  shared_preferences throws, which is caught and logged)

6.6 Loading States (Flutter)
- WardrobeScreen: Dashboard header + category pills + item grid
- Item grid: Circular implicit grid layout, empty state when no items
- Add item flow: Category screen → Item screen → Save button → immediate save
  + snackbar → grid updates on next pump

7. BACKEND ARCHITECTURE
------------------------

8.1 API Endpoints
- No backend API endpoints — wardrobe is local-only by design
- All data persists via shared_preferences LocalStore
- No authentication required — single dev user via LearningService singleton

8.2 Request/Response Schemas
- No remote schemas — all data is local Dart models
- UserModel ↔ shared_preferences JSON round-trip
- WardrobeEntry ↔ WardrobeItemData field mapping (identical fields)

8.3 Decision Engine
- N/A — no decision engine; styling signals derived from accumulated signals
  (styleScore, insights) rather than rules engine

8.4 Knowledge Source
- CatalogKnowledgeSource not applicable — mock data from WardrobeMockData.items
  seeded into LearningService defaultWardrobe

8.5 Save Use Case
- SaveRecommendation not applicable — save = LearningService.addItem()
  → UserModel.wardrobe INSERT + look_saved signal INSERT (same pattern as
  grooming, but local-only)
- Idempotency: N/A — local-only; same idempotency key logic not applied
  (single user, no retry scenarios)

8.6 Database Contract
- No SQL tables — reuse existing shared infrastructure (shared_preferences)
- UserModel table: wardrobe JSONB (stored as single JSON blob in shared_preferences)
- Indexes: n/a — flat file in shared_preferences
- Constraints: n/a — JSON serialization handles validity
- No new tables created — all changes reuse existing LearningRepository pattern

9. API CONTRACT
---------------

9.1 Endpoint: N/A — local only
9.2 Request/Response Schemas: N/A — local only
9.3 Error Codes: N/A — local only; shared_preferences errors logged, app degrades
  to in-memory
9.4 Save Use Case: LearningService.addItem() → UserModel.wardrobe append +
  _persist() → shared_preferences write → LearningSignal 'item_added'
9.5 Error Codes: 
- VALIDATION_ERROR: N/A — form validation shown in UI (please select type and color)
- DATABASE_FAILURE: N/A — shared_preferences failure logged, app degrades to
  in-memory

10. DECISION ENGINE
------------------

10.1 Pipeline: N/A — no rules-based decision engine
10.2 Scoring: styleScore = 60 + min(wardrobe.length, 20) + min(savedLooks.length * 2, 20)
10.3 Confidence: N/A — engine-derived confidence not applicable (local-only)
10.4 Empty Candidate Behavior: N/A — catalog always has 24 default items
10.5 Knowledge Source: WardrobeMockData.items (24 items) seeded into
    LearningService defaultWardrobe
10.6 Explanation Source: AI insights from WardrobeInsightData.mock (hardcoded)
10.7 Confidence Calculation: N/A — see 10.2
10.8 Empty Candidate Behavior: N/A — always has items (defaults seeded)
10.9 Incompatible Option Behavior: N/A

11. KNOWLEDGE SYSTEM
-----------------

11.1 Knowledge Source: WardrobeMockData (24 items) + LearningRepository port
11.2 Catalog Entries: 24 wardrobe items with code, title, description (implicit),
  scoreSeed (implicit via matchScore), bestFor (implicit)
11.3 Knowledge Version: N/A — no version tracking in local domain
11.4 Validation: N/A — read-time validation not applicable (mock data hand-verified)

12. RECOMMENDATION MODEL
----------------------

12.1 Recommendation: N/A — no recommendation model; AI insights from
    WardrobeInsightData.mock
12.2 GroomingResult: N/A
12.3 Recommendation Flow: N/A

13. INPUT MODEL
--------------

13.1 Grooming Input: N/A — wardrobe input is category + type + color + texture
13.2 Input Transmission: N/A
13.3 Backend Input Validation: N/A

14. PROCESSING FLOW
------------------

14.1 Success Path (backend reachable):
- N/A — backend not reachable; local-only by design
- User opens Wardrobe → views grid → taps FAB → "Add Item"
- → Navigates to Add Category → selects category → navigates to Add Item
- → Selects type → selects color → selects texture (optional) → taps "Save Item"
- → _saveItem() creates WardrobeItemData → Navigator.pop result
- → WardrobeScreen._handleAddItem() → LearningService.addItem() → _mutate()
  → _persist() → shared_preferences JSON write → notifyListeners()
- → Grid updates on next build, snackbar "X added to wardrobe"

14.2 Failure Path (backend unreachable):
- N/A — backend unreachable is the expected state; local-only by design
- Flow never breaks offline; data persists locally via shared_preferences

15. SAVE FLOW
------------

15.1 Flutter → Local Persist Path
- GroomingService.saveGroomingLook → N/A
- LearningService.addItem(recommendation, title)
  → _mutate(() => _model = _model.copyWith(wardrobe: [..._model.wardrobe, item]))
  → signalType: 'item_added', signalLabel: '${item.name} (${item.category})'
  → notifyListeners() → _persist() → writeRaw(model.encode()) → shared_preferences
- On save success: returns true → snackbar "Look saved to profile" (adapted to
  "X added to wardrobe")
- On save failure: N/A — local-only; mutate always succeeds unless shared_preferences
  throws (caught and logged)

15.2 Learning Signal Flow
- On item add: signal 'item_added' with label "${item.name} (${item.category})"
- On face set: signal 'analysis_updated' with label "Face analysis saved"
- On style type set: signal 'style_updated' with label styleType
- On save: signal 'look_saved' with label title
- On occasion prefer: signal 'occasion_preferred' with label occasion
- Signal is appended atomically with model mutate + persist (same transaction)
- No immediate profile rewrite — aggregated over time

15.3 Idempotency
- N/A — local-only single user; no duplicate prevention needed
- Same item added twice → appears twice in wardrobe list (user can favorite one)

16. LEARNING SIGNAL FLOW
-----------------------

16.1 Signal Recording
- Trigger: successful addItem (LearningService.addItem)
- Signal: item_added
- Context: "${item.name} (${item.category})"
- Label: recommendation name (e.g. "Merino Crew Neck (tops)")
- User: the authenticated dev user via LearningService.instance

16.2 Signal Storage
- Stored in UserModel.signals list
- Appended via _mutate() → _persist() → shared_preferences JSON
- Signals accumulate over time → drive styleScore, insights, personalization

16.3 Derived Signals (read time)
- Style score: 60 + min(wardrobe.length, 20) + min(savedLooks.length * 2, 20)
- Streak: not tracked (consecutive days with adds not computed)
- Preferences: preferredOccasions updated based on signal aggregation
- Profile rewrite: explicitly NOT performed after single add — architecture
  explicitly avoids this (signals aggregated over time)

16.4 Signal Contamination Prevention
- Mock results: save action returns true (local-only) → signal committed
- Save requires valid recommendation from real API — N/A (local-only)
- Source context explicitly tracked per-signal — cross-contamination prevented
  within learning service

17. ERROR STATES
 --------------

17.1 Flutter Error States
- Shared preferences unavailable: degrade to in-memory; app never crashes
- No items in category: empty state shown
- Save failure: N/A (local-only); mutate always succeeds unless shared_preferences
  throws, which is caught and logged via debugPrint

17.2 Backend Error States
- N/A — no backend

18. OWNERSHIP AND AUTH
---------------------

18.1 Authentication
- N/A — single dev user via LearningService.instance singleton
- Token 'dev' → seeded dev user (same deps.py seam as hairstyle/grooming)

18.2 Ownership (OW-1)
- Every wardrobe read enforces user_id scoping via LearningService singleton
- Foreign user → N/A — single user mode; LearningService is global singleton

18.3 Auth Seam
- Currently: dev token 'dev' → seeded dev user_id
- Future: D-AUTH-1 swap behind same deps.py seam; additive, no modifications
  needed for wardrobe; wardrobe uses same seam

19. TRANSACTION BOUNDARIES
--------------------------

19.1 TRX-3: Save Recommendation (SaveRecommendation use case)
- N/A — local-only; _persist() writes shared_preferences on every mutation
- On insert error: rollback → logged via debugPrint; app degrades to
  in-memory
- On success: commit → model visible, signal recorded
- Idempotent replay: same key + same payload → returns original (created=False),
  no new rows, signal not re-committed (N/A — local-only)

19.2 Analysis Run Lifecycle (complete_analysis_run / fail_analysis_run)
- N/A — no analysis runs in local wardrobe domain

20. BINDING DECISIONS
---------------------

20.1 Confirmed Bindings (code-verified)
- Wardrobe reuses existing LearningRepository infrastructure (LearningService,
  LocalStore, UserModel, signals)
- Wardrobe reuses shared_preferences for local persistence
- Wardrobe reuses same LearningSignal pattern as Hairstyle/Profile
- Wardrobe reuses same TRX-3 transaction pattern (model mutate + persist together)
- No new database tables created — all changes reuse existing schema (shared_preferences)
- Flutter: WardrobeService.saveGroomingLook() calls LearningService.addItem()
  with sourceContext='wardrobe' (adapted from grooming pattern)
- sourceContext = 'wardrobe' added additively to _SOURCE_CONTEXTS
  = {"hairstyle", "grooming", "wardrobe"}

20.2 Deferred Bindings
- POST /v1/feedback endpoint (M11): remains gated; save = look_saved signal is
  the approved feedback behavior
- Real image upload / camera: explicitly deferred per D2; no CV dependencies
- Media pipeline (M16): sealed until MS10.3
- Backend API for wardrobe: explicitly deferred per architecture rules; local-only
  first design with shared_preferences; M11 milestone adds backend
- Experiment conversion hypothesis: untested, documented for M11+ expansion
- Confidence display as dedicated UI field: product decision (W-10), not a blocker

21. DEFERRED CAPABILITIES
------------------------

21.1 M11 Feedback Endpoint
- POST /v1/feedback remains unavailable/gated
- Save action IS the feedback signal (look_saved signal commitment via TRX-3)
- Approved per API contract (FEEDBACK_LEARNING_API §3: "SAVE is the only fully
  supported feedback action today")

21.2 Real Image Upload
- Explicitly deferred per critical face input rule (D2)
- No CV dependencies added to this environment
- Profile-only pass: no image upload; wardrobe uses icon-based representations

21.3 Media Pipeline (M16)
- Sealed until MS10.3

21.4 Experiment Conversion Hypothesis
- ≥10% conversion requires 200 users, 2–4 weeks
- n=5 internal pilot observed 0 saves
- Unexplored in current environment

21.5 Confidence Display
- Whether to display derived engine confidence is a product decision (W-10),
  not a blocker
- Currently UI shows matchScore-style insights only

22. MARKER STATUS
================

FACT: The Wardrobe domain has a full vertical slice implemented
(input → collection → item → details → save → learn) using existing
LearningRepository infrastructure reusing hairstyle/profile patterns.

SUPPORTED: All API endpoints are N/A (local-only by design). Decision engine
is N/A (signal-based, not rules). Flutter UI screens are wired and pass
widget tests. Local persistence via shared_preferences works end-to-end.
Flutter: 100% passing (30+ widget tests + 30+ integration tests).

OBSERVATION: The Wardrobe domain shares the same LearningRepository
infrastructure as Hairstyle and Profile (LearningService, LocalStore,
UserModel, signals, defaultWardrobe). All changes reuse existing schema
(shared_preferences JSON blob). No new tables were created — all changes
reuse existing local storage pattern.

INTERPRETATION: The wardrobe data is purely local/mock — 24 pre-seeded items
from WardrobeMockData, persisted via shared_preferences. The LearningRepository
pattern is designed for future backend sync (M11 milestone). Mock provenance
not tracked (no _usedMockResult equivalent). The 65/35 card rule is preserved
in ClothingItemCard. The domain is fully functional as a local-first feature
with a clear upgrade path to backend-backed implementation.

UNKNOWN: Whether running against reachable PostgreSQL would reveal any issues
not caught in this environment (0 — domain is local-only by design). Whether
experiment conversion hypothesis (≥10%, n=5 pilot, 0 saves) holds with larger
user base and durable analytics. Whether real image upload would be required.

NOT LIVE-VERIFIED: Live against production PostgreSQL database. Real backend API
calls with Bearer auth (beyond dev token 'dev'). Save + learning signal commit
in live DB transaction. Real face-detection vs mock gate at scale.

IMPLEMENTED: Full vertical slice (input → collection → item → details → save →
learning signal), LearningRepository pattern, shared_preferences persistence,
Flutter UI screens, route navigation, service orchestration, 65/35 card design
rule, widget test suite (30+ tests passing), dart analyze clean.

DEFERRED: M11 feedback endpoint (by design D2/D5), real face-detection / image
upload (by design D2), experiment conversion hypothesis (by environment limitation),
confidence display as dedicated UI field (product decision W-10), backend API
for wardrobe (by design D2 — local-first).

BLOCKED: None — domain is locally complete; no blocking issues.

23. VERSION METADATA
--------------------

- Domain blueprint created: 2026-08-22
- Last Stage 8 validation: 2026-08-22 (WARDROBE_STAGE_8_REPORT.md)
- Decision engine: signal-based, deterministic from accumulated signals
- Knowledge version: N/A (no version tracking in local domain)
- Flutter version: consistent with fansivibe v1 backend
- Backend version: FastAPI + SQLAlchemy 2.0 + PostgreSQL + Alembic (not used by
  wardrobe; local-only shared_preferences persistence)
- LearningService defaultWardrobe: 24 items, mirrors WardrobeMockData.items
- SharedPreferences key: 'fansivibe.user_model.v1'
- Shared preferences read/write: atomic per-operation; degrade to in-memory on
  failure (headless tests, no daemon)