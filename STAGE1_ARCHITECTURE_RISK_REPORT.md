# Fansivibe Stage 1 — Architecture Risk Report

**Document Type:** Architecture, Data Integrity, Concurrency, and Privacy Risk Assessment  
**Date:** 2026-10-31  
**Repository:** `/home/tony/projects/fansivibe_v1_backup`  
**Committed Baseline:** Commit `97f6ded99d3f3e67b477616380320058cd396f48` (`main`)  
**Methodology:** Comprehensive static architectural inspection across backend, database, client, and security boundaries.

---

## 1. Executive Summary

This report identifies architectural risks, structural duplications, data integrity hazards, and privacy concerns in Fansivibe Stage 1. 

While the platform demonstrates strong engineering foundations—including deterministic recommendation scoring, clean repository port isolation, and robust transaction handling—several structural risks must be managed before scaling Stage 1.

Top architectural risks:
1. **Split-Brain Person Model**: Client-local storage and backend PostgreSQL both act as uncoordinated profile authorities.
2. **Silent Guest Data Loss**: Onboarding appearance scans are permanently discarded during guest-to-authenticated conversion.
3. **Unprotected Concurrency**: Profile updates lack Compare-And-Swap (CAS) optimistic locking.
4. **Architectural Duplication**: AI assistant tools bypass the Decision Engine with hardcoded rules and fallback shapes.
5. **Privacy Copy Ambiguity**: Permissions copy does not distinguish raw image bytes from persisted derived biometric attributes.

Below is an evidence-backed assessment of each risk area with severity, impact, and mitigation direction.

---

## 2. In-Depth Risk Assessment

### 2.1 Duplicate or Overlapping Business Logic
- **Evidence**:
  - `backend/app/ai/tools.py:23-42` implements hardcoded recommendation functions (`recommend_hairstyle`, `recommend_outfit`, `recommend_grooming`) that directly access catalog look constants (`catalog.CASUAL_LOOK`, `catalog.REFINED_OFFICE`, `catalog.OCCASION_TO_LOOK`).
  - Line 36 of `tools.py` contains: `face = (user.face.faceShape.lower() if user and user.face and user.face.faceShape else "oval")`, silently fabricating an oval face shape when none exists.
  - Meanwhile, `backend/app/domain/services/analysis_rules.py` implements the canonical 9-stage Decision Engine with multi-term scoring, deterministic ranking, and tie-breaking.
- **Severity**: **HIGH**
- **Impact**: Inconsistent user experience. The AI Assistant chat provides recommendations based on hardcoded rules that diverge from the AI Stylist and Hairstyle Scan results for the exact same user context.
- **Mitigation Direction**: Refactor `backend/app/ai/tools.py` into a thin wrapper that invokes the canonical application use cases (`GenerateOutfit`, `CreateHairstyleImageRun`), ensuring identical scoring and honesty rules apply across all surfaces.

---

### 2.2 Conflicting Architecture Documentation
- **Evidence**:
  - `docs/backend/KNOWLEDGE_ARCHITECTURE.md` (§3.2) specifies separate repositories for each vocabulary domain: `CategoryRepository`, `ColorRepository`, `OccasionRepository`, `ItemRepository`. The codebase implements a single unified `VocabularyRepositorySQL` in `backend/app/infrastructure/db/repositories.py:650-750`.
  - `docs/api/PROFILE_ONBOARDING_API.md` specifies `POST /v1/users/me/sync`, but the backend implements `PATCH /v1/users/me` (`users.py:111-128`); `sync` is not mounted.
  - `docs/backend/DECISION_ENGINE_ARCHITECTURE.md` (§7) describes a file decomposition under `domain/services/` (`engine.py`, `intent.py`, `recommendations.py`), whereas logic was concentrated into `analysis_rules.py`.
- **Severity**: **MEDIUM**
- **Impact**: Contradictions between design documentation and code lead to mistaken implementation assumptions during autonomous development.
- **Mitigation Direction**: Update architecture documentation to document the implemented single `VocabularyRepositorySQL` and `PATCH /v1/users/me` contract.

---

### 2.3 Data Ownership and Persistence Risks
- **Evidence**:
  - In `newproject/flutter_application_1/lib/features/profile/presentation/profile_screen.dart:358-375`, the UI reads `skinTone`, `faceShape`, `bodyType`, and `styleType` from `LocalStorage.userProfile` and `LearningService.instance.face`.
  - The backend maintains `user_state.style_profile` and serves it via `GET /v1/users/me` (`ProfileView.styleProfile` in `backend/app/api/routers/users.py:96-109`). Flutter never calls or deserializes `ProfileView.styleProfile`.
- **Severity**: **HIGH**
- **Impact**: Split-brain state. A user who logs in on a new phone, uses a web client, or clears local app cache loses their profile attributes, even though the backend database still holds them.
- **Mitigation Direction**: Designate `backend/app/infrastructure/db/models.py::UserState.style_profile` as the sole authority. Update Flutter `ProfileScreen` to fetch and render `GET /v1/users/me`, treating local storage strictly as a transient cache.

---

### 2.4 Provenance and Stale-Data Risks
- **Evidence**:
  - In `backend/app/infrastructure/db/repositories.py:265-306`, `update_style_profile` merges incoming non-empty fields and updates `source_run_id` to the latest run ID.
  - If Run A sets `face_shape="oval"` with `source_run_id="run-1"`, and Run B subsequently sets `body_type="athletic"` with `source_run_id="run-2"`, the stored `source_run_id` becomes `"run-2"`. The provenance of `face_shape` is permanently corrupted.
  - Furthermore, individual attributes in `style_profile` have no timestamps or TTLs.
- **Severity**: **MEDIUM-HIGH**
- **Impact**: Loss of auditability; reasoning algorithms cannot determine the age or origin of individual physical attributes, risking outdated recommendations.
- **Mitigation Direction**: Store attribute provenance at the field level within the JSONB payload (e.g. `{"face_shape": {"value": "oval", "source_run_id": "run-1", "observed_at": "..."}}`).

---

### 2.5 Concurrent Update Risks
- **Evidence**:
  - `models.py:130` defines `version: Mapped[int]` with `server_default=text("0")` on table `user_state`.
  - `UserStateRepositorySQL.update_style_profile` (`repositories.py:265-306`) executes:
    ```python
    update(UserState)
    .where(UserState.user_id == user_id)
    .values(style_profile=func.coalesce(UserState.style_profile, cast({}, JSONB)).op("||")(cast(patch, JSONB)))
    ```
  - It does NOT check or increment `UserState.version`.
- **Severity**: **MEDIUM**
- **Impact**: Concurrent requests (e.g. simultaneous hairstyle and outfit analysis submissions) execute blind last-writer-wins overwrites without conflict detection.
- **Mitigation Direction**: Implement optimistic locking: require expected version in update queries (`WHERE user_id == :user_id AND version == :expected_version`) and increment version (`version = UserState.version + 1`).

---

### 2.6 API Compatibility Risks
- **Evidence**:
  - Backend models use snake_case (`face_shape`, `skin_tone`), while API schemas output camelCase (`faceShape`, `skinTone` in `schemas/users.py:ProfileView`).
  - Telemetry endpoint `POST /v1/discovery/events` enforces `ConfigDict(extra="forbid")`.
- **Severity**: **MEDIUM**
- **Impact**: If backend routers omit explicit field translation, Flutter JSON deserialization fails silently or crashes. Adding unversioned fields to telemetry payloads causes 422 errors on older clients.
- **Mitigation Direction**: Maintain strict schema regression tests and ensure API versioning or additive schemas for telemetry contracts.

---

### 2.7 Guest-to-Authenticated Conversion Risks
- **Evidence**:
  - In `newproject/flutter_application_1/lib/features/auth/data/guest_data_migration.dart:52-57`:
    ```dart
    /// Explicitly NOT transferred (no backend upload contract exists —
    /// kept local and documented, never fabricated):
    /// face profile (server derives it from real scans), learning signals
    /// (M10 sole-writer rules), saved-look title strings (no IDs), style
    /// type, vibe, and the legacy analysis blob.
    ```
  - "Save My Progress" on `your_analysis_screen.dart:83-96` records only a `PendingAuthIntent` with route `/home`.
- **Severity**: **HIGH**
- **Impact**: High churn and user frustration. Users complete an onboarding scan, believe their progress is saved, create an account, and discover their face analysis was discarded.
- **Mitigation Direction**: Update the guest conversion modal to explicitly state that the initial scan is an ephemeral preview, or implement a secure, authenticated replay mechanism for the stashed onboarding snapshot.

---

### 2.8 Database Migration Divergence Risks
- **Evidence**:
  - `CURRENT_STATE.md` records that the development database migration head is frozen at `0029 (head)`.
  - Migrations `0030_discovery_interaction_events.py`, `0031_multi_retailer_offers.py`, and `0032_offer_click_attribution.py` have been executed and tested against `fansivibe_test`, bringing the test DB to head `0032`.
- **Severity**: **MEDIUM**
- **Impact**: Running backend development servers against a database at migration `0029` will fail when accessing Discovery telemetry or multi-retailer offer tables (`0030`–`0032`).
- **Mitigation Direction**: Document environment-specific migration statuses and schedule a formal, isolated upgrade of the development database to head `0032`.

---

### 2.9 Privacy and Biometric Isolation Concerns
- **Evidence**:
  - Camera permission and scan screens state that "camera data / photos are not stored" (`camera_permission_screen.dart:154-169`).
  - In code, raw image bytes are indeed ephemeral and not written to disk or S3.
  - However, derived biometric and physical attributes (`face_shape`, `skin_tone`, `body_type`) are permanently written to relational database tables (`user_state.style_profile`).
- **Severity**: **HIGH**
- **Impact**: Potential regulatory violation under biometric privacy regulations (e.g. GDPR, CCPA, BIPA) if users believe all facial analysis data is discarded, whereas derived facial geometry is permanently retained.
- **Mitigation Direction**: Update privacy copy to state clearly: "Your raw photos are processed securely in memory and never stored. Derived style attributes (such as your face shape) are saved to your profile to personalize your styling recommendations."

---

### 2.10 Invariants and Functionality That Must Be Preserved

During any future refactoring or implementation, the following frozen contracts and invariants MUST be strictly preserved:

1. **Fashion Formal Ontology (FFO) Invariants**:
   - Cryptographic corpus digest: `967f891e4c91d4e9463be5ea183b62ad3f3548f35c1b1e4d8678da49bf4d2581`.
   - Reasoner admission contracts in `backend/app/ai/conclusion_admission.py`.
2. **Trending Engine Evidence Boundary**:
   - `DEMAND_SIGNAL_AVAILABLE = False` must remain strictly enforced across all trend and discovery services until authentic consumer purchase demand data is authorized.
3. **Digital Atelier Visual Standards**:
   - Strict 65% visual / 35% content card proportion rule (`FansivibeCard`).
   - Dark luxury aesthetic (`#131313` background, `#D4AF37` accent gold tokens).
4. **Deterministic Ranking Architecture**:
   - Pure domain candidate scoring and deterministic multi-stage tie-breaking in `analysis_rules.py`. Scoring weights must never be altered without founder approval.
5. **Analysis Submission Idempotency**:
   - Client-generated `Idempotency-Key` header with database unique constraint `uq_analysis_runs_idempotency` (`0025`).
6. **Multi-Retailer Offer Isolation**:
   - Separation of canonical product identity (`products`) from transient merchant commerce (`retailers`, `retailer_offers`, `offer_price_history`) (`0031`, `0032`).
7. **Knowledge Separation Boundary**:
   - Strict isolation between system-owned knowledge tables and user-generated data (`TRX-8`).

---

## 3. Summary Risk Matrix

| Risk ID | Risk Domain | Severity | Primary Affected Component | Recommended Action |
|---|---|---|---|---|
| **R-01** | Duplicate Logic | **HIGH** | `app/ai/tools.py` vs `analysis_rules.py` | Route assistant through Decision Engine use cases |
| **R-02** | Conflicting Docs | **MEDIUM** | `KNOWLEDGE_ARCHITECTURE.md`, `PROFILE_ONBOARDING_API.md` | Align architecture docs with implemented codebase |
| **R-03** | Split-Brain Person Model | **HIGH** | `ProfileScreen` vs `user_state.style_profile` | Hydrate Flutter Profile from `GET /v1/users/me` |
| **R-04** | Provenance Loss | **MED-HIGH** | `user_state.style_profile` JSONB | Introduce field-level provenance and timestamps |
| **R-05** | Unchecked Concurrency | **MEDIUM** | `UserStateRepositorySQL.update_style_profile` | Add optimistic locking (CAS on `version`) |
| **R-06** | API Deserialization | **MEDIUM** | Pydantic Schemas vs Flutter DTOs | Maintain snake_case / camelCase mapping tests |
| **R-07** | Guest Conversion Loss | **HIGH** | `GuestDataMigration` | Disclose preview nature or support post-auth replay |
| **R-08** | Migration Divergence | **MEDIUM** | Dev DB (`0029`) vs Test DB (`0032`) | Controlled upgrade of dev DB to head `0032` |
| **R-09** | Privacy Transparency | **HIGH** | Camera Permission copy vs `style_profile` | Disclose persistent derived features vs raw bytes |
| **R-10** | Invariant Degradation | **CRITICAL** | FFO Digest, 65/35 Card Rule, `DEMAND_SIGNAL=False` | Enforce frozen invariant regression checks |

---
*End of Stage 1 Architecture Risk Report.*
