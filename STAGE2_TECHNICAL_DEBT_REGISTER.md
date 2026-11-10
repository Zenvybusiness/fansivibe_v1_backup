# Fansivibe — Stage 2 Technical Debt & Production Readiness Register
## Verified Technical Debt, Architectural Limitations & Remediation Plan Post P0-4 Phase 4

**Document Version:** 1.0.0  
**Audit Date:** November 1, 2026  
**Status:** Authoritative Technical Debt Register  
**Auditor:** Antigravity AI  

---

## 1. Classification Taxonomy

Items in this register are classified according to strict engineering impact criteria:
- **P0 (Critical / Blockers):** Security vulnerabilities, privacy policy violations, data corruption, or application-breaking crashes. *(Zero P0 defects remain in the codebase).*
- **P1 (High / Functional):** Functional regressions, user-facing inconsistencies, broken user journeys, or schema/environment migration gaps that affect core production usage.
- **P2 (Medium / Reliability & Performance):** Lifecycle edge cases, cache management, offline synchronization gaps, performance optimizations, or missing automated operational cleanup.
- **P3 (Low / Polish & Platform):** Platform integration polish, cosmetic placeholders, informational controls, or future convenience features.

Every item in this register is categorized as either a **VERIFIED DEFECT** (empirically proven by inspection or test failure) or an **ARCHITECTURAL RECOMMENDATION** (best practice for scaling and operational resilience).

---

## 2. Technical Debt Summary Table

| Debt ID | Priority | Type | Subsystem | Title / Summary | Verified File Evidence |
|:---|:---:|:---:|:---|:---|:---|
| **DEBT-01** | **P1** | Verified Defect | Database | Shared Database Migration Lag (`0032` vs `0036`) | `backend/alembic/versions/0033_*.py`–`0036_*.py` |
| **DEBT-02** | **P1** | Verified Defect | Saved Looks | Saved Look Garment Hydration & Missing Wear Action | `lib/features/profile/presentation/saved_looks_screen.dart:431` |
| **DEBT-03** | **P2** | Recommendation | Media Lifecycle | Phase 13 Storage Orphan Reconciliation Worker | `backend/app/application/media.py:650`, Decisions Doc §10 |
| **DEBT-04** | **P2** | Recommendation | Storage | Live Cloudflare R2 Staging Verification | `backend/tests/test_storage_adapter.py:27` |
| **DEBT-05** | **P2** | Recommendation | Client Storage | Local Device Original Storage Management (Option B) | `lib/features/media/domain/original_file_manager.dart:18` |
| **DEBT-06** | **P2** | Recommendation | Offline Sync | Offline Queuing for Multi-Item Wears & Media Uploads | `lib/features/wardrobe/presentation/ensemble_wear_confirmation_sheet.dart:180` |
| **DEBT-07** | **P2** | Verified Defect | AI Assistant | Conversational Chat History Transient in Flutter | `lib/features/ai_assistant/presentation/screens/stylist_screen.dart:45` |
| **DEBT-08** | **P2** | Verified Defect | Gamification | Style Streak & Score Calculation Split Across Local/DB | `lib/features/learning/data/learning_service.dart:12` |
| **DEBT-09** | **P2** | Recommendation | AI Latency | Ollama Local Inference Timeout Bounds Under Heavy Load | `backend/app/infrastructure/external/ollama.py:42` |
| **DEBT-10** | **P3** | Recommendation | Settings | Native Push Token Registration & Hardware Haptics | `lib/features/profile/presentation/settings_screen.dart:79` |
| **DEBT-11** | **P3** | Recommendation | Settings | Dynamic Theme Switching & Units Conversion | `lib/features/profile/presentation/settings_screen.dart:110` |
| **DEBT-12** | **P3** | Recommendation | Auth | Social OAuth Stubs (HTTP 502) | `backend/app/api/routers/auth.py:82` |

---

## 3. Detailed Debt Analysis & Remediation Plans

### DEBT-01: Shared Database Migration Lag (Revision 0032 vs 0036)
- **Priority:** **P1**
- **Type:** **VERIFIED DEFECT**
- **Subsystem:** Database / Alembic Migrations
- **Evidence:**
  - Alembic linear migration head is `0036_media_upload_lease_token.py`.
  - Shared developer databases `fansivibe` and `fansivibe_test` are currently at revision `0032_offer_click_attribution.py`.
  - Migrations `0033` (idempotency ledger), `0034` (completion & canonical metadata), `0035` (processing leases), and `0036` (fencing lease tokens) were verified only on disposable isolated test databases.
- **Operational Impact:**
  If a developer or staging server runs the application without applying migrations `0033 -> 0036`, any call to `POST /v1/media/uploads` or `POST /v1/media/uploads/{id}/complete` will fail with an SQL error (`relation "media_upload_authorizations" does not exist`).
- **Remediation Plan:**
  Run `alembic upgrade head` on the shared development databases when founder authorizes deploying media cloud features to shared dev environments. (Strictly prohibited during read-only audits).

---

### DEBT-02: Saved Look Garment Hydration & Missing Wear Action
- **Priority:** **P1**
- **Type:** **VERIFIED DEFECT**
- **Subsystem:** Saved Looks / Presentation
- **Evidence:**
  - In `lib/features/profile/presentation/saved_looks_screen.dart:429-450`, saved looks are rendered using generic icons (`FansiImageWell(icon: _icon, color: _color)`).
  - Look cards display only the title and source run ID; they do not render the photos, names, or categories of the garments in the outfit.
  - Tapping a saved look does not navigate to a hydrated outfit detail screen.
  - Unlike `DailyOutfitScreen` and `OutfitRecommendationScreen`, `SavedLooksScreen` has no "Wear This Look Today" action button.
- **User Impact:**
  Users cannot visually review what clothing items compose a saved look from their history, cannot drill into individual items, and cannot record wearing a saved look.
- **Remediation Plan:**
  Scheduled as milestone **P1-2 (Enriched Saved Look Hydration & Wardrobe Linking)**:
  1. Add an optional query parameter `?include_items=true` to `GET /v1/looks/saved` to return populated item objects with presigned URLs.
  2. Update `SavedLooksScreen` to render garment thumbnails and drill into `LookDetailsScreen`.
  3. Wire the "Log Wear Today" button on `LookDetailsScreen` via `logEnsembleWear`.

---

### DEBT-03: Phase 13 Storage Orphan Reconciliation Worker
- **Priority:** **P2**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Media Lifecycle / Storage Maintenance
- **Evidence:**
  - `STAGE2_P0_4_FINAL_ARCHITECTURAL_DECISIONS.md` §10 codifies the orphan cleanup requirements.
  - If a user requests an upload authorization (`POST /v1/media/uploads`) but drops their network connection before uploading bytes, a staging record expires.
  - If a worker crashes during publication, candidate attempt objects (`users/{user_id}/wardrobe/{upload_id}/attempts/{lease_token}.webp`) may reside in Cloudflare R2 without being adopted as the canonical object.
- **Operational Impact:**
  Unreferenced attempt objects and uncompleted staging files accumulate in the private R2 bucket over months of operation, incurring minor storage costs.
- **Remediation Plan:**
  Implement the Phase 13 operational cron job as scheduled:
  - Query `media_upload_authorizations` where `status = 'published'` and sweep attempt keys where `key != auth.canonical_key` after a 24-hour grace period.
  - Delete expired staging objects older than 24 hours.

---

### DEBT-04: Live Cloudflare R2 Staging Verification
- **Priority:** **P2**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** External Storage Adapter
- **Evidence:**
  - In `backend/tests/test_storage_adapter.py:27`, live Cloudflare R2 tests are skipped when `CLOUDFLARE_R2_BUCKET_NAME` is unset.
  - All CI/local tests execute against `FakeStorageAdapter`.
- **Operational Impact:**
  Production-specific edge behaviors (TLS handshake latency, Cloudflare edge clock skew, network timeouts during multi-megabyte streaming PUTs) have not been empirically baselined against a live Cloudflare edge endpoint.
- **Remediation Plan:**
  Provision an isolated, private Cloudflare R2 staging bucket (`fansivibe-staging-wardrobe`) and execute the automated live storage test suite prior to public production launch.

---

### DEBT-05: Local Device Original Storage Management (Decision Option B)
- **Priority:** **P2**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Flutter Client Storage Sandbox
- **Evidence:**
  - Under approved Decision Option B, original camera photos are stored in `ApplicationDocumentsDirectory/originals/` and are **never automatically deleted**.
  - `OriginalFileManager.saveOriginal` retains raw images indefinitely.
- **Operational Impact:**
  A power user with 500+ wardrobe items captured at high resolution (12MP) could accumulate 1.5GB–2.5GB of local disk storage.
- **Remediation Plan:**
  Introduce a "Manage Storage" screen under `SettingsScreen` in a future release, allowing users to view total local cache size and manually purge verified cloud-backed original photos if device storage is constrained.

---

### DEBT-06: Offline Queuing for Wear Logs & Media Uploads
- **Priority:** **P2**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Client Offline Synchronization
- **Evidence:**
  - In `lib/features/wardrobe/presentation/ensemble_wear_confirmation_sheet.dart:180`, if the network is disconnected, wear logging displays an error view with a "Try Again" button.
  - It does not save the pending wear event into a persistent local SQLite queue for background dispatch upon network restoration.
- **Operational Impact:**
  Users with intermittent cellular connectivity in underground locations (e.g. changing rooms) must manually retry once their connection is restored.
- **Remediation Plan:**
  Implement a local offline synchronization queue using `sqflite` for pending wear events and image uploads.

---

### DEBT-07: Conversational Chat History Transient in Flutter
- **Priority:** **P2**
- **Type:** **VERIFIED DEFECT**
- **Subsystem:** AI Stylist Assistant
- **Evidence:**
  - Backend models `ai_conversations` and `ai_messages` exist in PostgreSQL.
  - In `lib/features/ai_assistant/presentation/screens/stylist_screen.dart`, messages are held strictly in widget/service memory (`List<ChatMessage> _messages`).
  - Closing the app or switching accounts completely clears previous conversation turns and recommendation carousels.
- **User Impact:**
  Users lose the styling advice, outfit recommendations, and context from previous conversations whenever they relaunch the app.
- **Remediation Plan:**
  Add a `GET /v1/assistant/history` endpoint and hydrate previous conversation turns into `StylistScreen` upon mounting for authenticated users.

---

### DEBT-08: Style Streak & Score Calculation Split Across Local/DB
- **Priority:** **P2**
- **Type:** **VERIFIED DEFECT**
- **Subsystem:** Gamification & Style Learning
- **Evidence:**
  - Backend `GET /v1/learning/summary` computes Style Score (60 base + up to 20 wardrobe + up to 20 saved looks) and streaks from `activity_days` and `wardrobe_wear_groups`.
  - Flutter `LearningService` computes streaks independently from local SQLite records (`learning_streaks.db`).
- **User Impact:**
  Logging in on a second device or reinstalling the app resets the client-displayed streak to zero until local activity occurs, causing confusion.
- **Remediation Plan:**
  Deprecate local SQLite streak calculation and unify the client to hydrate exclusively from `GET /v1/learning/summary`.

---

### DEBT-09: Ollama Local Inference Latency Under Heavy Load
- **Priority:** **P2**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Local AI Inference Pipeline
- **Evidence:**
  - `backend/app/infrastructure/external/ollama.py` configures a 20.0s socket timeout for Ollama vision inference (`qwen2.5vl:3b`).
  - Multi-threaded or concurrent vision scans on 6GB–8GB GPU VRAM systems can trigger queuing delays, pushing latency near the 20.0s timeout ceiling.
- **Operational Impact:**
  Under concurrent load, users performing Outfit Scans may experience timeouts and require retries.
- **Remediation Plan:**
  Enforce a request concurrency semaphore (max 1 or 2 concurrent Ollama calls) on the backend worker level and implement model warm-up health checks.

---

### DEBT-10: Hardware Push Notification & Vibration Integration
- **Priority:** **P3**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Settings / Platform Hardware
- **Evidence:**
  - In `SettingsScreen`, toggles for `notifications`, `soundEffects`, and `hapticFeedback` persist to the backend profile via atomic `jsonb_set` (P0-3).
  - However, native APNs/FCM device push tokens are not registered, and `HapticFeedback.lightImpact()` is not bound to UI actions.
- **Operational Impact:**
  Informational controls only; no platform-level push notifications are dispatched to the device.
- **Remediation Plan:**
  Integrate `firebase_messaging` / APNs and bind `services/HapticFeedback` to wear confirmation and button taps in a platform integration sprint.

---

### DEBT-11: Dynamic Theme Switching & Measurement Units
- **Priority:** **P3**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Settings / Presentation
- **Evidence:**
  - In `SettingsScreen`, `Theme` displays 'Dark' and `Units` displays 'Imperial' as non-interactive list tiles.
- **Operational Impact:**
  Users cannot toggle light luxury themes or switch to metric units.
- **Remediation Plan:**
  Add theme mode provider (`ThemeMode.dark` / `ThemeMode.light`) and imperial/metric unit conversion logic.

---

### DEBT-12: Social OAuth Authentication Stubs (HTTP 502)
- **Priority:** **P3**
- **Type:** **ARCHITECTURAL RECOMMENDATION**
- **Subsystem:** Authentication
- **Evidence:**
  - Route handler `POST /v1/auth/social` in `backend/app/api/routers/auth.py:82` returns HTTP 502 intentionally.
- **Operational Impact:**
  Users must authenticate using standard email and password credentials.
- **Remediation Plan:**
  Implement Sign in with Apple (`sign_in_with_apple` plugin) and Google Sign-In with backend token validation during pre-launch auth hardening.

---

## 4. Production Readiness Gate Status

| Readiness Gate | Subsystem | Post P0-4 Status | Required Action for Production Release |
|:---|:---|:---:|:---|
| **Gate A: Security & Privacy** | Auth & Media | **READY** | Scoped M16 unsealing validated; OW-1 enforced; guest biometrics isolated. |
| **Gate B: Relational DB Schema** | PostgreSQL | **PENDING UPGRADE** | Run `alembic upgrade head` (`0032 -> 0036`) on shared production databases. |
| **Gate C: Object Storage Provider** | Cloudflare R2 | **PENDING PROVISIONING**| Provision production R2 bucket and configure backend environment secrets. |
| **Gate D: Daily Active Loop** | Wear Logging | **READY** | P0-1 wear logging operational and verified across Daily and Builder flows. |
| **Gate E: AI Stylist & Vision** | Ollama | **READY** | `qwen2.5vl:3b` vision and 12-term scoring engine verified. |
| **Gate F: Interactive Styling** | Component Swap | **NEEDS IMPLEMENTATION**| Implement P1-1 component swapping. |
| **Gate G: Saved Look Fidelity** | Saved Looks | **NEEDS IMPLEMENTATION**| Implement P1-2 saved look garment hydration and linking. |
