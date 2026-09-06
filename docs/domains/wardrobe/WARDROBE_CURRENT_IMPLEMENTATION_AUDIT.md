# Wardrobe Current Implementation Audit

## 1. Executive Summary

The Wardrobe domain has a **fully implemented local-first vertical slice** with a clear upgrade path to backend sync. The Flutter layer provides 4 screens with go_router navigation, mock data with 24 pre-seeded items, category filtering, favorites, and a 65/35 card design rule. The backend has no wardrobe-specific API endpoints — wardrobe data stays on-device via `shared_preferences` using the existing `LearningRepository` infrastructure shared with Hairstyle and Profile domains. No PostgreSQL tables exist for wardrobe items. The domain is functionally complete for local use but has no live backend API, no real image upload, and no backend-backed save flow.

**Classification: IMPLEMENTED (local-only) with known deferred capabilities.**

---

## 2. Repository Evidence

**Flutter feature dir:** `lib/features/wardrobe/`
**Blueprint doc:** `docs/domains/wardrobe/WARDROBE_DOMAIN_BLUEPRINT.md`
**Backend app dir:** `backend/app/` — no wardrobe routers, no wardrobe-specific SQL tables
**Migrations:** `backend/alembic/` — 8 tables (users, user_state, looks, run_types, signal_types, analysis_runs, saved_looks, learning_signals); none are wardrobe-specific
**Image components:** `lib/shared/components/fansi_image_well.dart`, `lib/shared/components/fansi_mini_card.dart`
**Learning infrastructure:** `lib/features/learning/` — `LearningService`, `LocalStore`, `UserModel`, `WardrobeEntry`, `LearningSignal`

---

## 3. Flutter Implementation

### Screens (4 implemented)
- `WardrobeScreen` — dashboard header + category pills + item grid with category filtering + favorites + bottom-fab add flow
- `AddWardrobeCategoryScreen` — category selection grid (tops, bottoms, shoes/layers, leads to item config)
- `AddWardrobeItemScreen` — type/color/texture configuration with validation, saves item via Navigator.pop
- `WardrobeItemDetailsScreen` — item details view with edit/delete/add-to-outfit actions

### Navigation
- go_router with `RouteNames.wardrobe`, `wardrobeAddCategory`, `wardrobeAddItem`, `wardrobeItemDetails`
- Bottom navigation "Wardrobe" tab in `router_shell.dart`
- Full path: `wardrobe → add-category → add-item → item-details`

### Data Layer
- `WardrobeMockData` — 24 items with categories (tops/8, bottoms/5, outerwear/4, footwear/4, accessories/3), colors (16), textures (15)
- `WardrobeCategory` — id, name, iconName, itemCount
- `AddItemCategoryConfig` — maps config IDs to `WardrobeItemData.category` values
- `LearningService.instance.wardrobe` — returns `List.unmodifiable(_model.wardrobe)`, seeded with `defaultWardrobe` = 24 items mirroring `WardrobeMockData.items`
- `LocalStore` — `shared_preferences` JSON persistence; degrades to in-memory if unavailable
- `UserModel` — `wardrobe: List<WardrobeEntry>`, `savedLooks: List<String>`, `preferredOccasions: List<String>`, `signals: List<LearningSignal>`
- `WardrobeEntry` — id, name, category, color, material (optional), isFavorite

### State Management
- `LearningService` extends `ChangeNotifier` singleton
- Listeners update UI on wardrobe list, category filter, favorites changes
- `_mutate()` + `_persist()` pattern: mutate model → notify listeners → write shared_preferences JSON atomically
- `load()` reads persisted JSON on first launch; if persisted data exists and has items, it overrides defaults

### Category Filtering
- pills: All Items, Tops, Bottoms, Outerwear, Footwear, Accessories
- `(_selectedCategory == 'all') ? _items : _items.where((item) => item.category == _selectedCategory)`

### Favorites Filtering
- `isFavorite` flag on each `WardrobeEntry`
- `_favoritesCount => _items.where((item) => item.isFavorite).length`
- Heart icon shown on card for favorite items

### 65/35 Card Design Rule
- `ClothingItemCard` uses `FansiMiniCard` with `FansiImageWell` (icon + color swatch = ~65% visual) + badge (favorite heart) + title + meta (color) = ~35% content

### Widget Tests
- `wardrobe_screen_test.dart` — 30+ tests covering screen rendering, category filtering, item grid, add flow, item tap, View Analysis snackbar
- `add_wardrobe_category_screen_test.dart` — 7 tests for category selection flow
- `add_wardrobe_item_screen_test.dart` — 13 tests for type/color/texture selection + validation + save
- `wardrobe_item_details_screen_test.dart` — 16 tests for details view, metadata, action buttons
- `wardrobe_widgets_test.dart` — WardrobeHeader, WardrobeInsightCard, ClothingItemCard tests
- **Total: ~60+ widget tests passing**

### Design System Compliance
- 65/35 card rule preserved in `ClothingItemCard`
- FansiButton, FansiInsightCard, FansiMiniCard reusable components used
- fansivibe_colors, fansivibe_spacing, fansivibe_typography, fansivibe_radius tokens used

---

## 4. Backend Implementation

### API Endpoints
- **No wardrobe-specific API endpoints** — domain is local-only by design (blueprint §8.1)
- `POST /v1/looks/saved` and `GET /v1/looks/saved` exist but are for hairstyle/grooming saved looks, not wardrobe items
- Router `app/api/routers/looks.py` mounted in `app/main.py` alongside analysis, users routers

### Models
- `WardrobeItem` in `app/models/schemas.py` — used for AI context payload only, not a API endpoint
- `UserContext` in `app/models/schemas.py` — `wardrobe: List[WardrobeItem]` field sent with AI requests
- `SavedLooks` ORM model in `app/infrastructure/db/models.py` — has `user_id`, `look_id`, `title`, `snapshot` (JSONB), `idempotency_key`, `source_run_id`
- No `WardrobeItems` or similar table — wardrobe data not stored in PostgreSQL

### AI/Engine Integration
- `app/ai/engine.py` — references `user.wardrobe` for generating wardrobe summary line and `tools.wardrobe_summary()` cards
- `app/ai/tools.py` — `wardrobe_summary(user)` returns suggestion cards based on user wardrobe
- `app/ai/intent.py` — `INTENT_WARDROBE = "wardrobe"`, classifies "show my wardrobe", "what do I own"
- `app/intents.py` — wardrobe intent recognized, navigates to `/wardrobe` route
- Catalog knowledge source: `app/data/catalog.py` — `kind="wardrobe"` entries (KN-10 access paths: `lookup_hairstyle_look`, `retrieve_hairstyle_looks`)

### Authentication
- `deps.py` — `get_current_user_id` reads Bearer token, validates `dev` token, returns seeded `user_id`
- Owner scoping (OW-1) enforced in SQL repositories on every read
- Single dev user mode; wardrobe uses same auth seam as hairstyle/grooming

### Database
- No wardrobe tables — reuses existing `LearningRepository` pattern (shared_preferences)
- `users` table has `auth_provider`, `auth_subject`, `display_name`; no wardrobe columns
- `saved_looks` table is for hairstyle/grooming saves, not wardrobe items
- Indexes: `ix_saved_looks_user_id_created_at` — not applicable to wardrobe

---

## 5. PostgreSQL Implementation

- **No wardrobe-related tables, columns, relationships, constraints, or indexes**
- Wardrobe data does not persist to PostgreSQL — local-only via `shared_preferences`
- The existing 8 migration tables do not include any wardrobe item storage
- Alembic schema: `0001_initial_schema.py` creates 8 slice tables; no wardrobe table added
- Offline DDL verification: `alembic upgrade --sql head` exits 0 — confirms no wardrobe tables
- **Verdict: PostgreSQL involvement = N/A — domain is local-only by design**

---

## 6. Image Pipeline

### Image Handling
- **No camera/gallery/image upload** in wardrobe — explicitly deferred per D2 (critical face input rule, no CV dependencies)
- `ClothingItemCard` uses `FansiImageWell` with category-based icons and solid color swatches (not user photos)
- Color mapping: `_colorFromName()` maps color strings to `Color` objects via switch statement
- Material displayed as text badge under the image
- No `Image.network`, `Image.file`, or `Image.picker` usage in wardrobe screens

### Image Components Used
- `FansiImageWell` — renders icon + color swatch in a card layout
- `FansiMiniCard` — container card with 65/35 visual/content split
- Icons from `icon_from_name()` mapping (e.g., 'person_rounded' → `Icons.person_rounded`)

### Image Pipeline Flow
```
User selects type/color/texture → ClothingItemData created with color name →
_ colorFromName() maps to Dart Color → FansiImageWell shows color swatch + icon →
ClothingItemCard renders with 65/35 split
```
**No real image capture or retrieval at any point.**

### Status: ❌ MISSING — No image upload/camera/gallery handling. Explicitly deferred.

---

## 7. Real Data Flow

### Flutter → Local Persist → (No backend API) ← PostgreSQL: NEVER

The actual data flow paths are:

**✅ UI → API → DB: N/A** (no backend API exists for wardrobe items)

**⚠️ UI → mock repository: YES** — complete flow
```
WardrobeScreen → LearningService.instance.wardrobe (from shared_preferences or defaultWardrobe)
→ _onLearningChanged() → setState → grid rebuild
Add Item: WardrobeScreen._handleAddItem() → context.pushNamed(wardrobeAddCategory)
→ AddWardrobeCategoryScreen → category selected → context.pushNamed(wardrobeAddItem)
→ AddWardrobeItemScreen → type/color/texture selected → _saveItem() → Navigator.pop(result)
→ WardrobeScreen._handleAddItem() → LearningService.instance.addItem(_toEntry(result))
→ _mutate() → _model = _model.copyWith(wardrobe: [..._model.wardrobe, item])
→ notifyListeners() → _persist() → _store.save(_model) → shared_preferences JSON write
→ Grid updates on next build → snackbar "X added to wardrobe"
```

**❌ UI exists but no backend: YES** — WardrobeScreen, Add screens all exist but make no external API calls

**❌ Backend exists but endpoint not mounted: YES** — No `POST /v1/wardrobe` or similar endpoint; `looks.router` is for saved looks (hairstyle/grooming), not wardrobe items

**Complete flow stoppage point:** The data flow stops at the `LearningService`/`LocalStore` boundary. There is no HTTP client call, no router mapping, no FastAPI endpoint, no PostgreSQL table for wardrobe items. The flow is intentionally local-only.

---

## 8. Google-Wardrobe-Inspired Capabilities

| Capability | Status | Evidence | Real/MOCK | Notes |
|---|---|---|---|---|
| Clothing catalog from photos | ❌ MISSING | No camera/gallery integration; icon-based representations only | MOCK | Explicitly deferred per D2 |
| Clothing categories (tops/bottoms/accessories) | ✅ IMPLEMENTED | categories: tops(8), bottoms(5), outerwear(4), footwear(4), accessories(3) | REAL | 24 default items from WardrobeMockData |
| Tops/bottoms/accessories attributes | ✅ IMPLEMENTED | color + material fields on each item | REAL | 16 colors, 15 textures configured |
| Visual clothing understanding | ⚠️ PARTIAL | Hardcoded AI insights (WardrobeInsightData.mock); no CV/visual analysis | MOCK | Insights are pre-written, not AI-derived |
| Filtering/search | ✅ IMPLEMENTED | Category pills filter grid; favorites filter by isFavorite flag | REAL | 6 category filters + "all" |
| Mix-and-match / outfit creation | ❌ MISSING | "Add to Outfit" button shows snackbar only; no actual outfit builder integration | MOCK | Described as future feature |
| Wardrobe intelligence (styleScore) | ✅ IMPLEMENTED | `LearningService.styleScore = 60 + min(wardrobe.length, 20) + min(savedLooks.length * 2, 20)` | REAL | Derived from accumulated signals |
| AI understanding of wardrobe items | ⚠️ PARTIAL | `WardrobeInsightData.mock` hardcoded insights; no per-item AI analysis | MOCK | Insights are generic, not item-specific |
| Virtual try-on preparation | ❌ MISSING | No try-on, fitting, or rendering pipeline | MOCK | Not applicable to current design |
| Shopping/product discovery | ❌ MISSING | No product links, catalog lookups, or shopping prep | MOCK | Explicitly deferred |
| Mix-and-match combination counting | ❌ MISSING | No combination calculation or outfit suggestion logic | MOCK | Mentioned as "future: Today's Look" |

---

## 9. Fansivibe Feature Integrations

| Feature | Integration Status | Details |
|---|---|---|
| Outfit Builder | ⚠️ PARTIAL | "Add to Outfit" snackbar on item details; no actual outfit builder API or nav flow |
| AI Stylist | ❌ NOT CONNECTED | No AI styling recommendations from wardrobe; wardrobe insights are hardcoded |
| Assistant | ✅ CONNECTED | Assistant can navigate to `/wardrobe`, shows wardrobe summary ("Here's what I know: N items"); `intent.classify("open my wardrobe")` → `INTENT_WARDROBE` |
| Home | ✅ CONNECTED | `HomeScreen` uses `learningService.wardrobe` for "Today's Look" personalization; builds outfit suggestions from outerwear/tops items |
| Profile | ✅ CONNECTED | Wardrobe data shared via LearningRepository; saved looks screen exists for hairstyle/grooming saves |
| Hairstyle | ✅ CONNECTED | Shares `LearningRepository` infrastructure (LearningService, LocalStore, signals, styleScore pattern) |
| Grooming | ✅ CONNECTED | Shares `LearningSignal` pattern (`item_added`, `look_saved`, `analysis_updated`, `style_updated`, `occasion_preferred`) |
| Learning/signals | ✅ CONNECTED | Same `_mutate()` → `_persist()` → signal recording pattern as hairstyle/grooming |
| Analytics | ⚠️ LIMITED | In-memory `AnalyticsService` only (same as hairstyle/grooming pre-M11); no third-party sink |
| Assistant chat | ✅ CONNECTED | `/v1/assistant/chat` endpoint; wardrobe data included in `UserContext` sent to AI engine |

---

## 10. Tests and Validation

### Flutter Wardrobe Tests
- `test/wardrobe_screen_test.dart` — 30+ widget tests (screen rendering, category filtering, item grid, add flow, item tap, View Analysis)
- `test/add_wardrobe_category_screen_test.dart` — 7 widget tests (category selection, navigation)
- `test/add_wardrobe_item_screen_test.dart` — 13 widget tests (type/color/texture selection, validation, save)
- `test/wardrobe_item_details_screen_test.dart` — 16 widget tests (details metadata, action buttons, favortie status)
- `test/wardrobe_widgets_test.dart` — 6 widget tests (Header, InsightCard, Card favorite handling)
- **Total: ~72 widget tests, all pass with mock data**

### Backend Wardrobe-Related Tests
- `test/test_intent.py::test_wardrobe_intent` — classifies "show my wardrobe" → `INTENT_WARDROBE`
- `test/test_intent.py::test_wardrobe_intent` — classifies "what do I own" → `INTENT_WARDROBE`
- `test/test_engine.py::test_wardrobe_uses_user_context` — wardrobe in UserContext triggers wardrobe intent/cards
- `test/test_saved_looks.py` — references `sourceContext="wardrobe"` in saved look payload (for hairstyle/grooming saves)
- `test/test_saved_looks_use_case.py` — references `source_context="wardrobe"` in use case tests
- **No backend API tests for wardrobe items** — no endpoints to test

### Test Reality
- **Flutter tests: 100% mock-dependent** — all wardrobe data comes from `WardrobeMockData`/`LearningService.instance.wardrobe`; no real backend calls
- **Backend tests: wardrobe referenced as `sourceContext` in saved looks tests**, but no wardrobe-specific endpoint tests
- **No integration/E2E tests** with reachable PostgreSQL for wardrobe
- **No tests for image upload/camera/gallery** (because none exists)
- **Learning service tests** (`test/learning_service_test.dart`) — verify default wardrobe seeding (24 items), round-trip encode/decode

---

## 11. Documentation vs Actual Code

| Documentation Claim | Actual Code Reality | Status |
|---|---|---|
| `POST /v1/analysis/wardrobe: N/A — no backend API` | Confirmed — no such endpoint exists | ✅ VERIFIED |
| `LearningService singleton with static defaultWardrobe (24 items seeded from WardrobeMockData.items)` | Confirmed — `learning_service.dart:9-187` has `defaultWardrobe` = 24 items mirroring `WardrobeMockData.items` | ✅ VERIFIED |
| `Local persistence via LocalStore → shared_preferences JSON blob` | Confirmed — `local_store.dart` and `learning_service.dart:_persist()` | ✅ VERIFIED |
| `UserModel.encode/decode round-trips wardrobe JSON to shared_preferences` | Confirmed — `models.dart:139-170` `toJson()`/`decode()` | ✅ VERIFIED |
| `Every mutation (_mutate) atomically persists via _persist()` | Confirmed — `learning_service.dart:248-264` `_mutate()` → `change()` → `_persist()` | ✅ VERIFIED |
| `addItem() → records 'item_added' signal + persists` | Confirmed — `learning_service.dart:267-273` | ✅ VERIFIED |
| `WardrobeDashboardHeader: total items, favorites count, style type display` | Confirmed — `wardrobe_widgets.dart:12-127` | ✅ VERIFIED |
| `WardrobeInsightCard: AI insight with action button` | Confirmed — `wardrobe_widgets.dart:265-287` | ✅ VERIFIED |
| `ClothingItemCard: 65% visual (icon area) / 35% content (title/meta) ratio` | Confirmed — `wardrobe_widgets.dart:289-400` uses `FansiImageWell` (icon + color) + `FansiMiniCard` + badge + title + meta | ✅ VERIFIED |
| `Category filtering (tops, bottoms, outerwear, footwear, accessories, all)` | Confirmed — `wardrobe_screen.dart:65-69`, `_filteredItems` getter | ✅ VERIFIED |
| `Favorites filtering (isFavorite flag)` | Confirmed — `_favoritesCount` and heart icon on cards | ✅ VERIFIED |
| `Bottom navigation "Wardrobe" tab in router_shell.dart` | Confirmed — `app_router.dart:351-386` | ✅ VERIFIED |
| `Full go_router navigation: wardrobe → add-category → add-item → item-details` | Confirmed — `app_router.dart:351-386` | ✅ VERIFIED |
| `4 screen widgets: WardrobeScreen, AddWardrobeCategoryScreen, AddWardrobeItemScreen, WardrobeItemDetailsScreen` | Confirmed — all 4 exist | ✅ VERIFIED |
| `4 widget tests: WardrobeHeader, WardrobeInsightCard, ClothingItemCard (favorite handling), and full WardrobeScreen suite (30+ tests)` | Partially — there are 4 widget test files but WARDROBE_DOMAIN_BLUEPRINT.md says "4 widget tests" while actual test count is ~72 across 5 files; the claim of "4" is understated but not wrong | ⚠️ SLIGHTLY UNDERSTATED |
| `Dart analyze: 0 issues on lib/features/wardrobe/` | Need to verify; last explicit check in hairstyle audit showed 0 issues on `lib/features/hairstyle/**` | ❓ UNKNOWN (not explicitly verified in this audit) |
| `M11 feedback endpoint: gated; wardrobe saves = look_saved signal is the approved feedback behavior` | Confirmed — `POST /v1/feedback` unmounted in `main.py`; save = look_saved signal | ✅ VERIFIED |
| `PostgreSQL-dependent tests: N/A — no backend DB; local-only persistence` | Confirmed — no wardrobe DB tests exist | ✅ VERIFIED |
| `0 saves observed in internal pilot (n=5) — hypothesis untested` | Documented in blueprint; not a code claim | ⚠️ DOCUMENTED LIMITATION |
| `Real image upload / camera integration: explicitly deferred per D2 (profile-only pass, no CV dependencies)` | Confirmed — no camera/gallery/image_picker in wardrobe code | ✅ VERIFIED |
| `Confidence display: UI shows matchScore-style insights; derived confidence not displayed (product decision, not blocker)` | Confirmed — `WardrobeInsightData.mock` insights only; no confidence field | ✅ VERIFIED |
| `Saved looks visibility: Backend supports it (shared saved_looks table), but Flutter UI only shows hairstyle saves` | Partially — backend `saved_looks` table exists; Flutter UI wardrobe screen does NOT display saved looks; profile saved looks screen shows hairstyle saves | ⚠️ PARTIAL — backend supports but wardrobe UI doesn't surface saved looks |

---

## 12. Capability Status Matrix

| Capability | Status | Evidence | Real/MOCK | Notes |
|---|---|---|---|---|
| Wardrobe local vertical slice | ✅ IMPLEMENTED | 4 screens, go_router navigation, LearningService, shared_preferences persist, 60+ widget tests passing | REAL | Local-only by design |
| Category filtering | ✅ IMPLEMENTED | 6 category pills filter grid items | REAL | All items, tops, bottoms, outerwear, footwear, accessories |
| Favorites filtering | ✅ IMPLEMENTED | `isFavorite` flag, heart icon on cards | REAL | Favorite count displayed in header |
| 65/35 card design rule | ✅ IMPLEMENTED | `ClothingItemCard` uses `FansiImageWell` + `FansiMiniCard` | REAL | Verified visual/content split |
| Add item flow (FAB → category → type/color/texture → save) | ✅ IMPLEMENTED | Complete navigation + `_mutate` → `_persist` → snackbar | REAL | Local persistence only |
| Item details (edit/delete/add-to-outfit) | ✅ IMPLEMENTED | `WardrobeItemDetailsScreen` with action buttons + snackbars | REAL | No actual DB mutation |
| AI wardrobe insights | ⚠️ PARTIAL | `WardrobeInsightData.mock` hardcoded; no per-item AI analysis | MOCK | Pre-written insights only |
| Category-based outfit suggestions | ❌ MISSING | No mix-and-match combination logic | MOCK | "Add to Outfit" shows snackbar only |
| Real image upload / camera | ❌ MISSING | Explicitly deferred per D2 | MOCK | No image_picker, camera, gallery |
| StyleScore derivation | ✅ IMPLEMENTED | `60 + min(wardrobe.length, 20) + min(savedLooks.length * 2, 20)` | REAL | From accumulated signals |
| Saved looks visibility | ⚠️ PARTIAL | Backend `saved_looks` table exists; wardrobe UI doesn't display them | MOCK/REAL | Backend supports, UI doesn't surface |
| Assistant wardrobe navigation | ✅ IMPLEMENTED | `intent.classify("open my wardrobe")` → navigates to `/wardrobe` | REAL | Via intent routing |
| Home "Today's Look" | ✅ IMPLEMENTED | `HomeScreen` reads `learningService.wardrobe` for personalization | REAL | Uses outerwear/tops items |
| Profile wardrobe data sharing | ✅ IMPLEMENTED | LearningRepository shares wardrobe across features | REAL | Same `LearningService.instance` |

---

## 13. Current Architecture Diagram

```
[Flutter UI]                          [LearningRepository]                          [Local Storage]
       │                                   │                                               │
       │   wardrobe tab ↓                   │ wardrobe getter                               │   shared_preferences
       ▼                                   ▼                                               ▼
  WardrobeScreen                    LearningService                                 LocalStore
       │       _items = .wardrobe           addItem() → _mutate() → _persist()          write JSON blob
       │       category filter              signals: item_added, etc.            degrade to in-memory
       │       favorites filter             load() → override defaults               on failure
       │                                   │                                               │
       │   _handleAddItem() → pushNamed      │                                               │
       ▼                                   ▼                                               ▼
  AddWardrobeCategoryScreen         │                                               │
       │         category sel. → pushNamed   │                                               │
       ▼                                   ▼                                               ▼
  AddWardrobeItemScreen         LearningSignal  ──┬─────────────────────────────────────┘
       │         type/color/texture          │   (type, label) recorded per mutation
       │         → _saveItem() → pop result  │                                               │
       ▼                                   ▼                                               ▼
  WardrobeItemDetailsScreen        UserModel.wardrobe  ──┬─────────────────────┐
                                              │  List<WardrobeEntry>│  24 default items  +
                                              │                     │  + user-added items
                                              ▼                     ▼
                                       styleScore = 60 + min(len,20) + min(saved*2,20)
                                              │
                                              ▼
                                       WardrobeDashboardHeader
                                              │
                                              ▼
                                       Category pills + favorites + item grid
```

**No backend API or PostgreSQL in the flow.** Data terminates at `LearningService` → `LocalStore` → `shared_preferences`.

---

## 14. Missing / Partial Pieces

### Missing
- **Real image upload / camera/gallery** — explicitly deferred per D2; no `image_picker` or platform channels
- **Backend API for wardrobe items** — `POST /v1/wardrobe` or similar endpoint not implemented; no router, no schema, no endpoint
- **Mix-and-match / outfit creation logic** — "Add to Outfit" button shows snackbar only; no actual outfit builder integration
- **Virtual try-on preparation** — no pipeline for try-on data
- **Shopping/product discovery preparation** — no product links or catalog lookups
- **Per-item AI visual understanding** — no computer vision or image analysis of user photos
- **Saved looks display in wardrobe UI** — wardrobe screen doesn't show saved looks; profile saved shows hairstyle saves only
- **Backend-supported wardrobe save with idempotency** — no `SaveRecommendation`-style use case for wardrobe items

### Partial
- **AI wardrobe insights** — hardcoded mock insights exist but are not AI-derived; `WardrobeInsightData.mock` is static
- **Assistant wardrobe integration** — navigation works but no AI-powered wardrobe analysis from backend
- **Home "Today's Look"** — uses wardrobe data but limited to showing outerwear/tops; no deep personalization
- **SharedLearningRepository infrastructure** — correctly shared with hairstyle/grooming but wardrobe mock provenance not tracked (no `_usedMockResult` equivalent)

### Risks and Technical Debt
1. **No backend sync path** — wardrobe data lives only in `shared_preferences`; no API to migrate to when M11 milestone adds backend
2. **Mock provenance untracked** — no `_usedMockResult` equivalent to distinguish mock vs real data; honest boundary not enforced
3. **Image system completely icon-based** — if real image upload ever required, would need significant new infrastructure (camera, storage, URL handling)
4. **65/35 card rule uses placeholders** — `FansiImageWell` with category icons, not user photos; switching to real images would redesign the card
5. **No error handling for shared_preferences failures** in production — degrades to in-memory but no monitoring/alerting
6. **Flat JSON blob in shared_preferences** — no migration path if schema evolves; `UserModel.encode/decode` version handling minimal
7. **Single-user mode only** — `LearningService` is global singleton; no multi-user support; `user_id` scoping via SQL repos not applicable
8. **Deprecated knowledge not filtered** — wardrobe catalog entries don't have version/deprecation tracking like hairstyle KN-3

---

## 15. Risks and Technical Debt

1. **No backend sync path** — wardrobe is local-only with no migration path to M11 backend; if M11 delivers a `POST /v1/wardrobe` endpoint, the Flutter client would need substantial changes (HTTP client, error handling, auth, idempotency)
2. **Mock/provenance boundary unclear** — no `_usedMockResult` tracking like hairstyle domain has; future developers might accidentally mix mock and real data
3. **Image system is entirely placeholder** — icon-based; any move to user photos would require: image picker, upload pipeline, storage URLs, thumbnail generation, error states, and card redesign (65/35 rule would need re-evaluation)
4. **Single user, single device** — `LearningService.instance` is a singleton with `shared_preferences`; no multi-user or roaming profile support
5. **Shared preferences version drift** — `UserModel.encode/decode` has no explicit version field; if the JSON schema changes, old persisted data could fail to decode and fall back to defaults silently
6. **No analytics for wardrobe actions** — save/scan actions recorded as `LearningSignal` but not sent to any durable collector; experiment conversion hypothesis untested (n=5 pilot, 0 saves)
7. **Deprecated catalog entries** — wardrobe `AddItemConfig` has no KN-3 equivalent; all 24 items always served, no filtering mechanism
8. **Test gap** — ~72 widget tests all pass with mocks; no tests for backend integration (because none exists); if backend is added later, test suite would need substantial expansion

---

## 16. Recommended Next Step

**Add `_usedMockResult` tracking to the Wardrobe LearningService and update the data flow to explicitly demarcate mock vs real provenance, matching the pattern established in the Hairstyle domain.**

This is the single most appropriate next engineering step because:
- It establishes the mock/real boundary that will be needed if/when a backend API is added in the M11 milestone
- It follows the exact pattern already proven in the Hairstyle domain (G-11 fix: `face_processing_screen.dart` guards `setFace` with `!_service.isMockResult`)
- It provides honest provenance tracking without requiring any backend changes
- It's a minimal, safe change that doesn't alter UI or API contracts
- It future-proofs the domain for backend sync while preserving the current local-only behavior

This step should be done before any M11 backend API work begins, so the mock/real boundary is established from the start.