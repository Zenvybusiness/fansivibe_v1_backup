# Fansivibe — Stage 2: First Feature Proposal

**Feature ID:** P0-1 (FEAT-07)  
**Feature Name:** Multi-Item Outfit Wear Logging & Wardrobe Wear Tracking Integration  
**Status:** Recommended First Stage 2 Implementation (Pre-Implementation Proposal)  
**Date:** October 31, 2026  
**Audited Against:** Git Working Tree (commit `19c35b4`, Stage 1D completion)

---

## 1. Executive Recommendation

It is recommended that **Multi-Item Outfit Wear Logging & Wardrobe Wear Tracking Integration** be the **first feature implemented in Stage 2**.

Fansivibe’s core product premise is that of an intelligent personal stylist that helps users look their best every day. That premise collapses into an open loop if the user cannot acknowledge wearing the outfits recommended to them. 

Currently:
- The backend API (`POST /v1/wardrobe/wears`), database tables (`wardrobe_wear_groups`, `wardrobe_wear_events`), and idempotency mechanisms are **100% implemented, tested, and operational**.
- However, the Flutter client **fails to connect to this API** during outfit flows. On `DailyOutfitScreen`, tapping "Wear This Look" triggers an empty mock snackbar. On `OutfitRecommendationScreen` (Outfit Builder) and `LookDetailsScreen` (Saved Looks), no wear logging action exists at all.
- To log a worn outfit, a user must manually navigate to the Wardrobe tab, find each garment individually, open each details screen, and tap "Log Wear Today" multiple times.

Connecting multi-item wear logging across `DailyOutfitScreen`, `OutfitRecommendationScreen`, and `LookDetailsScreen` will immediately activate the platform's core daily active engagement loop with **zero backend changes, zero database migrations, and zero architectural risk**.

---

## 2. Why This Feature Must Be First

### 1. Closes the Core Daily Retention Habit Loop
A personal styling platform succeeds on daily recurring engagement. The primary daily habit is:
1. Open Fansivibe in the morning.
2. View "Today's Look" or generate an outfit for an occasion.
3. Put on the outfit.
4. Confirm "I'm wearing this today".
5. Receive positive feedback (+1 Style Streak, updated wardrobe wear analytics).

Currently, step 4 is broken in the UI. Closing this loop transforms Fansivibe from a static catalog into a living daily habit.

### 2. Zero Backend Risk & 100% Infrastructure Reuse
Unlike features that require new API contracts, new database migrations, or third-party integrations, the backend infrastructure for multi-item wear logging is already built, audited, and verified:
- `POST /v1/wardrobe/wears` in `app/api/routers/wardrobe.py` accepts `itemIds: List[UUID]` (1..10 items) and creates a single atomic wear group.
- `wardrobe_wear_groups` and `wardrobe_wear_events` tables exist in PostgreSQL (migration `0032_wear_groups_and_events.py`).
- Idempotency is enforced via `idempotency_key` (UUIDv4) preventing duplicate submissions.

### 3. Immediately Unlocks Recommendation Intelligence
Fansivibe's canonical 12-term recommendation engine (`analysis_rules.py`) features a dedicated wear decay penalty (`term_wear_decay`):
- Items worn recently receive a penalty score so the AI doesn't recommend the exact same outfit two days in a row.
- Items never worn or neglected receive freshness boosts.
Because outfit wear logging was disconnected in the UI, wear counts remained zero, causing the recommendation engine to operate on incomplete wear history. Activating this feature immediately improves recommendation variety and accuracy.

### 4. Drives Style Evolution & Gamification
The `learning/` subsystem tracks user Style Streaks and wardrobe utilization percentages. When outfits are logged as worn, users immediately see tangible progress in their style analytics, driving long-term retention.

### 5. High Perceived Value for Minimal Engineering Effort
This feature requires no backend development, no new database fields, and no model fine-tuning. It is an entirely frontend integration that delivers an immediate, visible product upgrade.

---

## 3. Target User Experience

### Flow A: Today's Look (Daily Engagement Flow)
1. User opens Fansivibe and taps "Today's Look" on the Home tab.
2. The user sees their curated daily outfit with weather context and match percentage.
3. At the bottom of the screen, the user taps the prominent primary button: **"Wear This Look Today"**.
4. The client disables the button, generates a client-side idempotency key, and issues `POST /v1/wardrobe/wears` with the item IDs of the top, bottom, outerwear, footwear, and accessories.
5. Upon 201 response, a sleek modal bottom sheet or banner appears:
   - *"Look logged for today!"*
   - Displays updated Style Streak badge (*"🔥 4-Day Streak!"*).
   - Displays affected wardrobe items with updated wear badges.
6. The "Wear This Look Today" button transitions to a disabled/checked state: **"✓ Worn Today"**.

### Flow B: Outfit Builder Recommendation Flow
1. User builds an outfit for a specific occasion (e.g., "Dinner Date").
2. On `OutfitRecommendationScreen`, after viewing the recommended ensemble and component breakdown, the user taps a secondary action: **"Wear This Outfit Today"**.
3. The outfit items are logged to the backend with context `"outfit_builder"`.
4. A celebratory toast confirms the wear log, and the outfit is automatically archived into `Saved Looks` if not already saved.

### Flow C: Saved Looks Detail Flow
1. User navigates to `SavedLooksScreen` and opens a previously saved favorite look.
2. On `LookDetailsScreen`, a dedicated **"Log as Worn Today"** button allows logging the look directly from the archive.

---

## 4. Existing Infrastructure to Reuse

### Backend & Database (No Modifications Required)
- **Endpoint:** `POST /v1/wardrobe/wears` (`app/api/routers/wardrobe.py`)
  ```json
  // Request Schema (WardrobeWearBatchRequest)
  {
    "itemIds": ["uuid-1", "uuid-2", "uuid-3"],
    "wornDate": "2026-10-31",
    "context": "daily_outfit",
    "idempotencyKey": "c4b96b42-d6f7-4a0e-bc21-7299a91a92e1"
  }
  ```
  ```json
  // Response Schema (WardrobeWearBatchResponse)
  {
    "groupId": "7fa1bc82-...",
    "wornDate": "2026-10-31",
    "itemsLogged": 3,
    "items": [
      {"id": "uuid-1", "wearCount": 4, "lastWorn": "2026-10-31"},
      {"id": "uuid-2", "wearCount": 2, "lastWorn": "2026-10-31"},
      {"id": "uuid-3", "wearCount": 7, "lastWorn": "2026-10-31"}
    ]
  }
  ```
- **Database Tables:**
  - `wardrobe_wear_groups` (`infrastructure/db/models.py`)
  - `wardrobe_wear_events` (`infrastructure/db/models.py`)
  - `wardrobe_items` (`wear_count` and `last_worn` columns)
- **Domain Service:**
  - `WardrobeService.log_wear_group()` in `app/application/use_cases/wardrobe.py`.

### Flutter Frontend (Assets & Patterns to Reuse)
- `WardrobeRepository` (`lib/features/wardrobe/data/wardrobe_repository.dart`): Already contains single-item wear method `recordWear()`. Needs an ensemble wear method.
- `Design System Tokens`: `AppColors`, `AppSpacing`, `AppTypography` adhering to the Digital Atelier system.
- `65/35 Card Proportion Rule`: Visual presentation of the outfit items remains untouched.

---

## 5. What We Need to Build

### Frontend Additions (Flutter)

1. **Repository & Service Layer:**
   - Add `logEnsembleWear` to `lib/features/wardrobe/data/wardrobe_repository.dart` and `authenticated_wardrobe_item_repository.dart`:
     ```dart
     Future<WardrobeWearBatchResult> logEnsembleWear({
       required List<String> itemIds,
       String? wearContext,
       DateTime? wornDate,
     });
     ```
   - In `EphemeralWardrobeItemRepository`, implement local in-memory/SQLite wear recording so guest users can also test the wear interaction without errors (complying with D10 Option A).

2. **DailyOutfitScreen Integration:**
   - Update `lib/features/home/presentation/screens/daily_outfit_screen.dart`:
     - Replace the mock snackbar in `_onWearLookTapped()` with a call to `wardrobeRepository.logEnsembleWear(...)`.
     - Manage loading state (`isLoggingWear`) and success state (`isWornToday`).
     - Display the celebration bottom sheet upon success.

3. **OutfitRecommendationScreen Integration:**
   - Update `lib/features/outfit_builder/presentation/screens/outfit_recommendation_screen.dart`:
     - Add a "Log Wear Today" action in the actions bar alongside "Save Look" and "Regenerate".

4. **Celebration Feedback Widget:**
   - Create `lib/features/wardrobe/presentation/dialogs/wear_logged_dialog.dart`:
     - A polished bottom sheet displaying the logged items, confirmation checkmark, and current streak update, styled according to the Digital Atelier design tokens.

### Backend Additions
- **None.** The backend endpoint is complete and fully functional.

---

## 6. Testing Strategy & Validation Plan

### 1. Unit & Repository Testing
- Test `WardrobeRepository.logEnsembleWear()` with mock HTTP client:
  - Verify that request payload includes valid ISO date, list of UUIDs, and UUIDv4 idempotency key.
  - Verify error handling for network timeouts or 400 Bad Request.
  - Verify ephemeral repository increments local counts for guests without network calls.

### 2. Widget Testing
- Test `DailyOutfitScreen`:
  - Verify tapping "Wear This Look Today" invokes repository with correct item IDs.
  - Verify button renders loading indicator while asynchronous request is in flight.
  - Verify button text changes to "✓ Worn Today" and becomes disabled after successful logging.
- Test `OutfitRecommendationScreen`:
  - Verify "Log Wear Today" button renders and responds to user interaction.

### 3. End-to-End Integration Testing
- Start local backend (`make run` or `uvicorn`).
- Perform authenticated login.
- Fetch `GET /v1/wardrobe/items` to record baseline wear counts for items A, B, C.
- Open "Today's Look" and tap "Wear This Look Today".
- Verify `POST /v1/wardrobe/wears` returns `201 Created` with `itemsLogged: 3`.
- Fetch `GET /v1/wardrobe/items` and verify wear counts for items A, B, and C have incremented by 1.
- Immediate re-tap test: Tap "Wear This Look Today" again; verify idempotency key prevents duplicate incrementing.

---

## 7. Definition of Done & Success Metrics

### Acceptance Criteria
- [ ] User can log an entire outfit as worn from `DailyOutfitScreen` with one tap.
- [ ] User can log an outfit as worn from `OutfitRecommendationScreen` with one tap.
- [ ] Backend records single wear group in `wardrobe_wear_groups` and individual events in `wardrobe_wear_events`.
- [ ] All garment cards in the Wardrobe tab reflect the incremented wear count immediately.
- [ ] Rapid double-taps do not create duplicate wear events.
- [ ] Guest users experience a smooth client-side simulation without network errors or backend persistence.
- [ ] All existing and new Flutter widget/unit tests pass with 0 errors.
- [ ] `flutter analyze` and `dart analyze` report 0 issues.

### Success Metrics
- **Core Loop Completion:** 100% of generated daily looks can be marked as worn.
- **Data Integrity:** 0 duplicate wear groups created due to client-side idempotency keys.
- **Wear Tracking Coverage:** Wear decay scoring in `analysis_rules.py` accurately reflects real user usage.
