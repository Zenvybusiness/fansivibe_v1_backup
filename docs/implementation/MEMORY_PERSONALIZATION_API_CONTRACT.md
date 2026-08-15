# Memory + Personalization API Contract

## Overview

This document defines the minimum APIs required for reading user memory, updating explicit preferences, retrieving appearance profile, retrieving saved/history information, and retrieving derived personalization context. It reuses existing APIs wherever possible and only proposes new endpoints where the current contract cannot satisfy the requirement.

The API contract follows the existing Fansivibe conventions: `GET /v1/users/me` is the primary user endpoint, Bearer token auth with dev seam (D-AUTH-1), owner-only read (OW-1, 404-not-403), and additive-only API changes (API-2).

---

## 1. Existing APIs — Reuse Assessment

### 1.1 `GET /v1/users/me` (Endpoint #06)

**METHOD**: GET  
**PATH**: `/v1/users/me`  
**AUTH**: Bearer token (D-AUTH-1); dev seam `FANSIVIBE_DEV_TOKEN` default `user_id`  
**OWNERSHIP**: OW-1 — returns only the authenticated user's own profile (404 if profile missing)  
**STATUS CODES**: 200, 401 (no/invalid token), 404 (profile not found — OW-1)  
**IDEMPOTENCY**: Safe (GET never mutates)

**Current Response** (`ProfileView`):
```json
{
  "displayName": "string",
  "styleProfile": {
    "faceShape": "optional string",
    "skinTone": "optional string",
    "bodyType": "optional string",
    "styleType": "optional string",
    "sourceRunId": "optional string"
  },
  "preferences": {
    "preferredOccasions": ["string"]  // camelCase wire format
  },
  "settings": {"key": "value"},  // sparse JSONB, passed through
  "flags": {"key": "value"},     // sparse JSONB, passed through
  "version": int                   // optimistic lock version
}
```

**Reuse**: Full — this is the primary vehicle for all user memory reads. Extend with `memorySummary` field (API-P0-1).

**Enhancement**: Add `memorySummary` field (see API-P0-1 below). No breaking change if optional.

---

### 1.2 `POST /v1/looks/saved` (Endpoint #23)

**METHOD**: POST  
**PATH**: `/v1/looks/saved`  
**AUTH**: Bearer token (D-AUTH-1); `Idempotency-Key` header required  
**OWNERSHIP**: OW-1 — enforcement in SQL repos (404-not-403 on foreign user)  
**STATUS CODES**: 201 (created), 409 (conflicting idempotency key), 404 (unknown look_id), 422 (validation), 401 (auth)  
**IDEMPOTENCY**: Yes — `Idempotency-Key` header; replay returns original `created=False`

**Current Request**:
```json
{
  "lookId": "optional string",      // catalog look code
  "title": "string",                  // user-provided title
  "sourceContext": "string",          // e.g. "hairstyle", "outfit"
  "snapshot": {"dict"}                // full run result at save time
}
```

**Current Response** (`SavedLook`):
```json
{
  "id": "UUID",
  "lookId": "optional string",
  "title": "string",
  "snapshot": {"dict"},
  "sourceRunId": "optional UUID",
  "createdAt": "datetime"
}
```

**Reuse**: Full — save look is the primary behavioral event that feeds memory. The `look_saved` learning signal is emitted atomically (TRX-3).

**Enhancement**: None required for P0/P1. P1-G-P1-4 would add `POST /v1/looks/passed` as a complementary endpoint.

---

## 2. New APIs — Minimum Required

### 2.1 `GET /v1/users/me` — Extended with `memorySummary` (API-P0-1)

**METHOD**: GET  
**PATH**: `/v1/users/me` (same as existing, response extended)  
**AUTH**: Bearer token (D-AUTH-1)  
**OWNERSHIP**: OW-1 — same as existing  
**STATUS CODES**: 200, 401, 404  

**New Response Field**: `memorySummary` (optional, additive)

```json
{
  "memorySummary": {
    "appearanceVerified": true,          // bool: whether style_profile has all 4 attributes non-empty
    "savedLooksCount": 4,                // int: count of user-saved looks
    "preferredOccasions": ["work", "date"], // List<String>: user-stated preferred occasions
    "appearanceConfidence": 0.75         // float 0-1: completeness × decisiveness
  }
}
```

**Field Details**:
- `appearanceVerified`: `true` if `user_state.style_profile` has all of `faceShape`, `skinTone`, `bodyType`, `styleType` non-empty. Labeled AI-inferred with confidence attribution.
- `savedLooksCount`: `SELECT count(*) FROM saved_looks WHERE user_id = current_user_id`
- `preferredOccasions`: Pulled from `user_state.preferences.preferred_occasions` (snake_case in DB, camelCase on wire). Labeled as user-stated/explicit.
- `appearanceConfidence`: Derived from `_completeness()` logic: fraction of non-empty appearance signals / 4 (0.0–1.0). Same formula as `DecisionContext.completeness`.

**Reason**: Single endpoint extension; no new path needed. Additive only (API-2 compatible). Existing clients that don't see the field ignore it; new clients can read it.

**Existing endpoint reuse**: `GET /v1/users/me` already queries `user_state` and maps to `ProfileView`. The `memorySummary` field is added to the response mapper (`_record_to_schema` in `routers/users.py`).

---

### 2.2 `POST /v1/looks/passed` — Emit `look_passed` learning signal (API-P1-1)

**METHOD**: POST  
**PATH**: `/v1/looks/passed`  
**AUTH**: Bearer token (D-AUTH-1)  
**OWNERSHIP**: OW-1 — enforcement in SQL repos; only the authenticated user can emit signals for their own account  
**STATUS CODES**: 202 (accepted), 400 (validation), 401 (no auth), 409 (conflicting idempotency)  
**IDEMPOTENCY**: Yes — optional `Idempotency-Key` header; if provided, replay returns original response

**New Request**:
```json
{
  "lookId": "string",     // catalog look code being passed
  "title": "string",      // user-provided or catalog title
  "sourceContext": "string",  // e.g. "hairstyle", "outfit"
  "idempotencyKey": "optional string"  // for dedup
}
```

**New Response**:
```json
{
  "status": "passed",
  "lookId": "string",
  "signalId": "UUID",
  "createdAt": "datetime"
}
```

**Reason**: Complementary to `POST /v1/looks/saved`. Emits `look_passed` learning signal (DB-P1-1: add to `signal_types` enum). Decision engine filtering stage (G-P1-1, G-P1-4) will use `excludedLookIds` expanded from `look_passed` history. No existing endpoint emits this signal type.

**Alternative**: Extend `POST /v1/looks/saved` with a `signalType` discriminant. Rejected: keeping save and pass as separate endpoints is cleaner for API contract clarity and UI/UX (users distinguish "save" vs "pass/not interested").

---

### 2.3 `PATCH /v1/users/me/appearance` — Update appearance profile (API-P1-2)

**METHOD**: PATCH  
**PATH**: `/v1/users/me/appearance`  
**AUTH**: Bearer token (D-AUTH-1)  
**OWNERSHIP**: OW-1 — only the authenticated user can update their own profile  
**STATUS CODES**: 200 (updated), 400 (validation), 401 (no auth), 422 (invalid values)  
**IDEMPOTENCY**: No — PATCH is mutative; not idempotent by design

**New Request**:
```json
{
  "faceShape": "optional string",        // vocabulary: oval/round/square/heart/diamond/rectangle
  "skinTone": "optional string",          // vocabulary: dark/medium/light
  "bodyType": "optional string",          // vocabulary: slim/average/athletic/plus
  "styleType": "optional string"          // vocabulary: modern_minimalist/classic_elegance/street_style/bohemian/athleisure
}
```

**New Response**:
```json
{
  "styleProfile": {
    "faceShape": "string",
    "skinTone": "string",
    "bodyType": "string",
    "styleType": "string",
    "sourceRunId": "optional string"
  },
  "memorySummary": {
    "appearanceVerified": true,
    "appearanceConfidence": 0.75
  }
}
```

**Reason**: Currently no mechanism to correct appearance profile if analysis was wrong (G-P2-2 gap). This endpoint fills that gap. Validation against vocabulary values. On success, emits `style_updated` learning signal (consumed by decision engine for preference drift tracking).

**Note**: This is listed as P2 gap (G-P2-2) in the gap report, but is included in the API contract as a minimum requirement for the personalization system to be functional. The implementation plan may gate this to P3.

---

## 3. API Reuse Summary

| Requirement | Existing Endpoint | New Endpoint | Status |
|---|---|---|---|
| Read user profile | `GET /v1/users/me` | — | Reuse (extend with `memorySummary`) |
| Update preferences | No explicit endpoint (UI state only) | — | Reuse `GET /v1/users.me` response; persistence is Flutter LocalStore + backend write path (G-P0-2) |
| Retrieve appearance profile | `GET /v1/users.me` → `styleProfile` | — | Reuse |
| Retrieve saved looks | `saved_looks` table via repo; no dedicated API | — | Reuse existing data; no new API needed for P0/P1 |
| Retrieve saved/history | `GET /v1/users/me` → preferences + saved_looks query | — | Reuse existing data |
| Derived personalization context | `DecisionContext` internal; not exposed via API | — | Reuse internally; no new public API needed |
| Emit `look_saved` signal | `POST /v1/looks/saved` (TRX-3) | — | Reuse |
| Emit `look_passed` signal | — | `POST /v1/looks/passed` (API-P1-1) | New, P1 only |
| Correct appearance profile | — | `PATCH /v1/users/me/appearance` (API-P1-2) | New, P2 gap included in contract |

**No APIs that expose internal Decision Engine structures.** The `DecisionContext` and `ScoredCandidate` types remain internal to the backend domain service layer. Only `ProfileView` and the new `memorySummary` field are exposed to clients.

**No raw learning signals exposed to client.** The `learning_signals` table and signal history are not directly queryable via API. The `memorySummary` on `GET /v1/users/me` provides aggregated, labeled summaries only.

---

## 4. Error Handling Conventions

All endpoints follow the Frozen 12-category error taxonomy (API_CONTRACT_RULES.md §12):

- **401**: Authentication required (no/invalid Bearer token)
- **403**: Not used — owner endpoints return 404-not-403 instead (OW-1)
- **404**: Profile/resource not found or ownership violation (foreign user)
- **422**: Validation error (invalid field values, vocabulary violations)
- **429**: Rate limited (inherited from infrastructure; not explicitly defined in contract)
- **500**: Database failure / unexpected error

All error bodies follow the frozen format: `{"error": {"code": "XXX", "message": "YYY", "details": {...}}}`

---

## 5. Idempotency

| Endpoint | Idempotent? | Key |
|---|---|---|
| `GET /v1/users/me` | Yes | N/A (safe method) |
| `POST /v1/looks/saved` | Yes | `Idempotency-Key` header |
| `POST /v1/looks/passed` | Yes (optional) | `Idempotency-Key` header |
| `PATCH /v1/users/me/appearance` | No | N/A (mutative) |
| `POST /v1/feedback` | Gated (M11) | — |

---

## 6. API Versioning

All endpoints reside under `/v1/` path major (API-1). The `memorySummary` field and `POST /v1/looks/passed` are additive changes under the same major version — no version bump required (API-2: additive responses OK). Clients pinning `Accept: application/json; version=1.0` receive the new fields; default clients receive latest minor superset.

---

## 7. Summary of API Changes by Priority

| Priority | Endpoint | Change | Reason |
|---|---|---|---|
| **P0** | `GET /v1/users/me` | Extend response with `memorySummary` field | P0-G-P0-3: "What Fansivibe knows" user-facing summary |
| **P1** | `POST /v1/looks/passed` | New endpoint: emit `look_passed` learning signal | P1-G-P1-4: feedback loop for incorrect recommendations |
| **P2** | `PATCH /v1/users/me/appearance` | New endpoint: update appearance profile attributes | P2-G-P2-2: appearance profile correction flow |

**No new endpoints required for P0 alone.** P0 only needs the `memorySummary` extension to `GET /v1/users/me`. P1 adds `POST /v1/looks/passed`. P2 adds `PATCH /v1/users/me/appearance`.

---

## 8. Ownership & Authorization

All endpoints enforce OW-1 (owner-only, 404-not-403):

- `GET /v1/users/me`: Returns only the caller's own profile; valid dev token with `user_id` scope
- `POST /v1/looks/saved`: SQL repo enforces `user_id` FK scoping; 404 if foreign user attempts save
- `POST /v1/looks/passed`: SQL repo enforces `user_id` FK scoping; 404 if foreign user emits signal
- `PATCH /v1/users/me/appearance`: SQL repo enforces `user_id` FK scoping; 404 if foreign user updates profile

No endpoint accepts a `user_id` path or body parameter; the authenticated `user_id` from the dev auth seam (D-AUTH-1) is used implicitly.