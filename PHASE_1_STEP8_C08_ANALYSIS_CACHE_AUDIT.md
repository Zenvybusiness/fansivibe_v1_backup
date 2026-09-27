# PHASE 1 STEP 8 — C-08 analysisCached / Analysis Blob Audit

> **Status:** AUDIT ONLY. No source code, tests, schemas, APIs, migrations, or ranking behaviors modified.  
> **Date (UTC):** 2026-09-27  
> **Prior Contracts Guard:** C-01 through C-07 are untouched. C-08 is NOT implemented.

---

## Executive Summary & Verification of Known Facts

Prior investigation established four core claims regarding C-08. All four have been verified against the active codebase:

1. **`analysisCached` is a photo-taken / onboarding milestone flag, NOT an authoritative "analysis completed" flag.**  
   *Verified:* Its sole production writer is `YourAnalysisScreen._onContinueWithoutAccount()` (`lib/features/onboarding/presentation/screens/your_analysis_screen.dart:82`), where the user is an unauthenticated guest viewing mock static data (`_mockScore = 82`, static palette, static insight cards). No real analysis has executed.
2. **The local `analysisResult` blob setter is deprecated, dead, and has zero callers.**  
   *Verified:* `LocalStorage.analysisResult` setter (`lib/shared/utils/local_storage.dart:103-110`) was marked `@Deprecated` in Step 1. A repo-wide grep confirms zero callers in `lib/` and zero callers in `test/`.
3. **There is no currently established authoritative analysis blob consumed by recommendation.**  
   *Verified:* Outfit generation (`GenerateOutfit` / `score_outfit_candidate` in `backend/app/domain/services/analysis_rules.py`), Today's Look, Event looks, hairstyle recommendations, and grooming recommendations read either structured owned `wardrobe_items` columns (`category`, `color_id`, `material_id`, `fit`, `fit_confidence`), user state (`user_state.style_profile`), or catalog knowledge sources. None consume a generic analysis blob.
4. **The system already has authoritative analysis runs/results and provenance.**  
   *Verified:* The PostgreSQL `analysis_runs` table (`backend/app/infrastructure/db/models.py:175-211`) tracks lifecycle `('pending', 'completed', 'failed')` and stores the authoritative result in `result` (JSONB). Wardrobe items persist `source_run_id` (FK to `analysis_runs.id`) and `image_ref` (MediaRef JSONB). Polling endpoints (`GET /v1/analysis/runs/{run_id}`) already supply authoritative run status and snapshot payloads to Flutter clients.

---

## A. analysisCached Write/Storage/Read/Consumer Map

### 1. Declarations
- [local_storage.dart:65-69](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/shared/utils/local_storage.dart#L65-L69):
  ```dart
  static bool get analysisCached => _prefs?.getBool('analysis_cached') ?? false;
  static set analysisCached(bool value) { _prefs?.setBool('analysis_cached', value); }
  ```
- [user_session.dart:66-70](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/shared/utils/user_session.dart#L66-L70):
  ```dart
  static bool get analysisCached => LocalStorage.analysisCached;
  static set analysisCached(bool value) { LocalStorage.analysisCached = value; }
  ```
  *(Dead mirror: zero callers repo-wide).*

### 2. Writes
- [your_analysis_screen.dart:82](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/onboarding/presentation/screens/your_analysis_screen.dart#L82):
  ```dart
  void _onContinueWithoutAccount() {
    LocalStorage.onboardingComplete = true;
    LocalStorage.savedLocally = true;
    LocalStorage.analysisCached = true;
    context.goNamed(RouteNames.stylist, extra: {
      'onboarding_complete': true,
      'display_name': null,
      'vibe': null,
      'saved_locally': true,
      'analysis_cached': true,
    });
  }
  ```
- [create_account_screen.dart:229](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/auth/presentation/screens/create_account_screen.dart#L229):
  ```dart
  void _onMaybeLater() {
    context.goNamed(RouteNames.home, extra: {
      'onboarding_complete': true,
      'saved_locally': true,
      'analysis_cached': true,
    });
  }
  ```
- [guest_phase2_test.dart:159](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/test/guest_phase2_test.dart#L159):
  `LocalStorage.analysisCached = true;` (test mock setup).

### 3. Storage
- **Platform:** Device-local `SharedPreferences` (key `'analysis_cached'`).
- **Wire/Backend:** NEVER stored, transmitted, or queried on the backend. Zero occurrences in database schemas, models, or backend application code.

### 4. Reads
- [home_screen.dart:144](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/home/presentation/home_screen.dart#L144): Packaged into fallback onboarding map `_onboardingDataFromLocalStorage()`.
- [home_screen.dart:179](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/home/presentation/home_screen.dart#L179): Read in `_hasAnalysis` getter:
  ```dart
  bool get _hasAnalysis {
    final data = widget.onboardingData ?? _onboardingDataFromLocalStorage();
    return data?['onboarding_complete'] == true ||
        LocalStorage.analysisCached ||
        (data?['display_name'] != null && (data!['display_name'] as String).trim().isNotEmpty);
  }
  ```
- [first_time_home_screen.dart:60](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/home/presentation/first_time_home_screen.dart#L60):
  `bool get _hasScannedOutfit => LocalStorage.analysisCached;`
- [first_time_light_path_home_screen.dart:62](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/home/presentation/first_time_light_path_home_screen.dart#L62):
  `bool get _hasScannedOutfit => LocalStorage.analysisCached;`
- [profile_screen.dart:280](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart#L280):
  `bool get _colorAchievementUnlocked => LocalStorage.analysisCached || LocalStorage.analysisResult != null || ...`

### 5. Consumers
- **`HomeScreen` Routing:** Decides whether a first-time visitor sees `FirstTimeHomeScreen` (if `_hasAnalysis` is true) or `FirstTimeLightPathHomeScreen` (if false).
- **`FirstTimeHomeScreen` / `FirstTimeLightPathHomeScreen` Milestone Card:** Passes `hasOutfitScanned: _hasScannedOutfit` into `StyleJourneyCard`.
- **`ProfileScreen` Badge:** Evaluates whether `_colorAchievementUnlocked` is true.

---

## B. Actual Semantics

| Question | Value / Behavior |
| :--- | :--- |
| **Does it mean photo exists in memory?** | **No.** In-memory photo bytes are tracked via ephemeral screen state (`_capturedImageBytes`). |
| **Does it mean analysis started?** | **No.** No analysis request is created or dispatched when set. |
| **Does it mean analysis completed?** | **No.** It is written on guest bypass where no backend analysis ran. |
| **Does it mean analysis was cached?** | **No.** No analysis payload or inference output is saved. |
| **Does it mean analysis succeeded/failed?** | **No.** Unrelated to backend vision/LLM success/failure. |
| **What does it ACTUALLY mean?** | **"Guest user completed the onboarding photo-capture screen and continued."** |

**Semantic Verdict:** The flag name `analysisCached` is misleading. In reality, it functions strictly as an **onboarding milestone / photo-capture flow completion flag**.

---

## C. analysisResult / Blob Map

### 1. `LocalStorage.analysisResult` (Device Blob)
- **Producer / Setter:** [local_storage.dart:103-110](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/shared/utils/local_storage.dart#L103-L110). Marked `@Deprecated`. **Zero callers exist in the entire codebase.**
- **Storage:** `SharedPreferences.getStringList('analysis_result')`.
- **Readers / Getter:** [local_storage.dart:89-94](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/shared/utils/local_storage.dart#L89-L94). Read only in [profile_screen.dart:281, 309, 316, 322, 329](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart#L309-L329) as defensive fallback (`LocalStorage.analysisResult?['appearance']`). Because the setter is never called, this getter **always returns `null` in production**. All fallback chains safely coalesce to `LearningService.instance` or `LocalStorage.userProfile`.
- **Authoritative:** **No.**
- **Status:** **Dead code.**

### 2. `OutfitAnalysisScreen.analysisResult` (In-Memory Route Parameter — SEPARATE NAMESPACE)
- **WARNING:** Do not confuse this with `LocalStorage.analysisResult`.
- **Producer:** [outfit_processing_screen.dart:103-107](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_processing_screen.dart#L103-L107) extracts `data?['result']` from the polled `AnalysisRun` returned by `GET /v1/analysis/runs/{run_id}`.
- **Transport:** GoRouter extra parameter: `context.pushNamed(RouteNames.scanAnalysis, extra: snapshot ?? data);`.
- **Consumer:** [outfit_analysis_screen.dart:20-25](file:///c:/Users/shivu/OneDrive/Pictures/Desktop/fansivibe/fansivibe_v1_backup/newproject/flutter_application_1/lib/features/outfit_scan/presentation/outfit_analysis_screen.dart#L20-L25) displays appearance attributes, confidence score, and top recommendation cards.
- **Authoritative:** Yes, for transient UI rendering of the completed run. It does NOT write to `LocalStorage`.

### 3. Server Database Storage (`analysis_runs.result`)
- **Producer:** `CreateOutfitRun`, `CreateHairstyleImageRun`, `CreateGarmentRun`, `CreateGroomingRun` in `backend/app/application/analysis.py`.
- **Storage:** PostgreSQL `analysis_runs.result` (`JSONB`, nullable).
- **Consumer:** Polling clients (`GarmentClient`, `OutfitScanClient`, `HairstyleClient`, `GroomingClient`) via `GET /v1/analysis/runs/{run_id}`.
- **Authoritative:** **Yes.**

---

## D. Authoritative Analysis Run State

The application already possesses a complete, robust, and authoritative lifecycle for garment, outfit, hairstyle, and grooming analyses:

```
[Client POST /v1/analysis/{type}]
              ↓
   analysis_runs row created
      (status = 'pending')
              ↓
  Client polls GET /v1/analysis/runs/{run_id}
              ↓
┌────────────────────────────────────────────────────────┐
│                   Terminal State                       │
│                                                        │
│  status = 'completed'        status = 'failed'         │
│  result = <JSONB snapshot>   error = <JSONB details>   │
│  completed_at = now()        completed_at = now()      │
└────────────────────────────────────────────────────────┘
```

1. **State Machine Definition:**  
   `backend/app/infrastructure/db/models.py:178-181`:
   ```sql
   CheckConstraint("status IN ('pending', 'completed', 'failed')", name="ck_analysis_runs_status")
   ```
2. **Authoritative Completion Signal:**  
   The application knows analysis completed successfully when:
   - `AnalysisRun.status == 'completed'`
   - `AnalysisRun.result != null`  
   In Flutter, this is evaluated directly on the client models:
   - `GarmentAnalysisRun.isCompleted`
   - `OutfitAnalysisRunResult.isCompleted`
   - `AnalysisRun.isCompleted`
3. **Structured Persistence & Provenance:**
   - Appearance profile: written to `user_state.style_profile` on completion (TRX-6) with `source_run_id`.
   - Wardrobe item: user-confirmed save `POST /v1/wardrobe/items` links `source_run_id` (FK) and `image_ref` (MediaRef).
   - Saved look: links `source_run_id` (FK).
   - Learning signals: `analysis_updated` and `outfit_selected` emitted with `{run_id, run_type}` context.

**Conclusion:** **NO new state machine or analysis storage system is required or permitted.**

---

## E. Flutter Dependencies

| Decision | Mechanism Used Today | Depends on `analysisCached`? |
| :--- | :--- | :--- |
| **Photo exists** | In-memory `Uint8List` / `File` reference in active screen state | **No** |
| **Analysis should run** | User tap on Analyze/Continue; auth session check | **No** |
| **Polling continues** | Polling loop checks `run.isCompleted \|\| run.isFailed \|\| attempts >= max` | **No** |
| **Result is available** | `run.isCompleted == true && result != null` | **No** |
| **User can continue** | Navigation actions (`_onContinueWithoutAccount`, `_onMaybeLater`) | **Sets it on guest continue** |
| **Home screen variant** | `HomeScreen._hasAnalysis` evaluates `LocalStorage.analysisCached` | **Yes** |
| **Style journey milestone** | `FirstTimeHomeScreen._hasScannedOutfit` reads `analysisCached` | **Yes** |
| **Profile achievement** | `ProfileScreen._colorAchievementUnlocked` reads `analysisCached` | **Yes** (fallback term) |
| **Cached data reused** | Profile style DNA falls back to `analysisResult` (always null) | **No** (dead fallback) |

---

## F. API Dependencies

- **Request Schemas:** Zero references to `analysisCached` or `analysis_result`.
- **Response Schemas:** Zero references to `analysisCached` or `analysis_result`. (`AnalysisRun` contains `result: Optional[dict[str, Any]]`, which is the run's domain snapshot).
- **DTOs:** Zero references in Flutter API DTOs.
- **Wire Meaning:** None. Completely absent from all HTTP wire contracts.

---

## G. Database / Storage Dependencies

- **Database Tables:** Zero tables, zero columns, zero constraints for `analysis_cached` or `analysis_result`.
- **Migrations:** Zero migrations reference or define these fields.
- **Storage Scope:** Purely client-side Flutter `SharedPreferences` keys (`'analysis_cached'` and `'analysis_result'`).

---

## H. Dead / Duplicate State

1. **`LocalStorage.analysisResult` setter:** **DEAD.** Deprecated, has 0 callers, stores nothing.
2. **`LocalStorage.analysisResult` getter:** **DEAD.** Always returns null in production; callers are defensive fallbacks.
3. **`UserSession.analysisCached` getter/setter:** **DEAD.** Mirror property with 0 callers repo-wide.
4. **Duplicate state:** `analysisCached` does not duplicate any backend state because backend has no concept of an unauthenticated guest onboarding photo-taking milestone.

---

## I. Product Decisions Required

1. **Keep, Rename, or Refactor `analysisCached`?**
   - *Option 1 (Safest / Zero-Risk):* Retain `LocalStorage.analysisCached` as-is, with accurate documentation that it represents guest onboarding photo capture.
   - *Option 2 (Clean Rename):* Rename `LocalStorage.analysisCached` to `LocalStorage.onboardingPhotoCaptured` across its 5 Flutter read sites and 1 test site.
   - *Option 3 (Eliminate via Routing Refactor):* Change `HomeScreen._hasAnalysis` to rely exclusively on `LocalStorage.onboardingComplete` and `LocalStorage.vibe`, removing `analysisCached` entirely. *(Requires owner sign-off on onboarding UX behavior).*
2. **Dispose of Dead `analysisResult` Local Blob:**
   - Remove the `@Deprecated` `LocalStorage.analysisResult` setter and getter.
   - Clean up the 5 fallback lines in `ProfileScreen` so they read directly from `LearningService` and `userProfile`.

---

## J. Safest Implementation Path

When C-08 is implemented in the future, the smallest and safest path consists of:

1. **Delete Dead Setter & Getter:**
   - Remove `@Deprecated static set analysisResult` in `lib/shared/utils/local_storage.dart`.
   - Remove `static Map<String, dynamic>? get analysisResult` in `lib/shared/utils/local_storage.dart`.
   - Simplify `profile_screen.dart:281, 309, 316, 322, 329` to remove the dead `LocalStorage.analysisResult` fallback.
2. **Delete Dead `UserSession` Mirror:**
   - Remove `UserSession.analysisCached` getter/setter in `lib/shared/utils/user_session.dart`.
3. **Preserve or Rename `analysisCached`:**
   - Leave `LocalStorage.analysisCached` functioning as the photo-milestone flag, or perform a clean mechanical rename to `onboardingPhotoCaptured`.
   - Update `guest_phase2_test.dart:159` to match.
4. **Add Nothing New:**
   - Do NOT introduce any new analysis cache.
   - Do NOT introduce any new database tables, columns, or migrations.
   - Do NOT modify `analysis_runs` or any ranking code.

---

## K. Migration Requirement

**NONE.** No database migrations, schema alterations, or data backfills are required or allowed.

---

## L. Tests Inspected

- `newproject/flutter_application_1/test/guest_phase2_test.dart`: verifies line 159 sets `LocalStorage.analysisCached = true;`.
- `newproject/flutter_application_1/test/your_analysis_screen_test.dart`: verifies guest handoff navigation and flag writes.
- `newproject/flutter_application_1/test/outfit_scan_screen_test.dart`: verifies route extra `analysisResult` passthrough.
- `newproject/flutter_application_1/test/outfit_processing_screen_test.dart`: verifies polling and snapshot extraction.
- `newproject/flutter_application_1/test/wardrobe_add_item_screen_test.dart`: verifies garment run observation prefill.
- `newproject/flutter_application_1/test/hairstyle_client_test.dart`: verifies analysis run polling and completion checks.
- Backend suites (`test_c02_palette.py`, `test_c02_fit.py`, `test_c03_preferred_item_ids.py`, `test_c07_item_added.py`): verified clean and unaffected.

---

## M–R. Status of Prior Contracts

- **C-01:** LOCKED (Guest mode boundaries and conversion mechanisms).
- **C-02:** LOCKED (C-02-P Palette live +5, C-02-F Fit live +5, C-02-M Mood closed/context-only).
- **C-03:** IMPLEMENTED (Optional `preferred_item_ids` soft boost in outfit generation).
- **C-04:** IMPLEMENTED (Post-save "Build with this item" navigation threading).
- **C-05:** LOCKED (Feedback semantics locked; weights unassigned).
- **C-06:** AUDITED / BLOCKED (Garment attributes audited; pattern/style blocked on vocab).
- **C-07:** IMPLEMENTED (`item_added` learning signal emitted on wardrobe item creation).

---

## S. Files Changed

- `PHASE_1_STEP8_C08_ANALYSIS_CACHE_AUDIT.md` (created/updated audit report).
- `CURRENT_STATE.md` (updated with audit completion status).
- **Source code changes:** ZERO.
- **Test changes:** ZERO.
- **Migration changes:** ZERO.

---

## T. Commit & Push Status

- **Committed:** NO.
- **Pushed:** NO.
- Working tree remains clean (only audit documentation updated).

---

> **STOP:** Audit complete. C-08 implementation has NOT started.
