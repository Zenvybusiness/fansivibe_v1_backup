# Fansivibe — Stage 2 P1-1 Security & Privacy Audit
## Interactive Outfit Component Swapping

**Feature:** P1-1 — Interactive Outfit Component Swapping  
**Audit Date:** November 2, 2026  
**Auditor:** Antigravity Autonomous Security Subsystem  
**Security Verdict:** PASSED — ZERO SECURITY DEFECTS IDENTIFIED  

---

## 1. Security Scope & Threat Model

The interactive outfit component swapping feature introduces two new authenticated API endpoints:
- `POST /v1/outfits/swap-slot`
- `POST /v1/outfits/candidates`

The primary threat vectors evaluated include:
1. **Broken Object Level Authorization (BOLA / IDOR):** An attacker attempting to substitute garments owned by User B into User A's outfit, or inspecting User B's wardrobe items via candidate generation.
2. **Cross-Tenant Information Leakage:** Probing foreign UUIDs to ascertain whether specific garments exist in other users' wardrobes.
3. **Privilege Escalation & Identity Spoofing:** Supplying forged client-side `user_id` or ownership claims in request payloads.
4. **State Poisoning & Pinned Bypass:** Silently mutating pinned garments, bypassing compatibility rules, or forcing invalid garment categories into incompatible outfit slots.
5. **Data Protection & Privacy Violations:** Storing guest outfit data in authenticated database tables, logging presigned media URLs, or persisting unconfirmed wear events.

---

## 2. Authentication and Authorization Controls

### 2.1 Authenticated Identity Resolution
- Both endpoints resolve the caller's identity strictly through FastAPI dependency injection:
  ```python
  user_id: UUID = Depends(get_current_user_id)
  ```
- The JWT Bearer token is validated against active cryptographic secrets.
- Neither endpoint accepts a `user_id` in the request body, path, or query parameters. The authenticated JWT subject is the sole source of identity.
- Unauthenticated requests receive HTTP 401 Unauthorized immediately.
  - *Evidence:* Tested via `tests/test_p1_1_outfit_swap.py::test_api_unauthenticated_requests_fail` (PASSED).

### 2.2 OW-1 Wardrobe Ownership Verification
- Every garment involved in a swap operation is validated against the authenticated user's ownership before any processing occurs:
  ```python
  # In SwapOutfitSlot.execute:
  current_items = await self._wardrobe.get_by_ids(
      user_id=user_id,
      item_ids=all_garment_ids,
  )
  if len(current_items) != len(all_garment_ids):
      raise ApiError(
          status_code=404,
          code="GARMENT_NOT_FOUND",
          message="One or more specified garments were not found in user wardrobe",
      )
  ```
- The replacement garment is similarly verified:
  ```python
  replacement_item = await self._wardrobe.get_by_id(
      user_id=user_id,
      item_id=req.replacement_garment_id,
  )
  if not replacement_item:
      raise ApiError(
          status_code=404,
          code="REPLACEMENT_GARMENT_NOT_FOUND",
          message="Selected replacement garment was not found in user wardrobe",
      )
  ```
- **Fail-Closed Existence Masking:** If an attacker passes a valid UUID belonging to another user, the query filters by `AND user_id = :user_id`, returning `None`. The API responds with generic HTTP 404 `NOT_FOUND`, preventing an attacker from learning whether the garment exists in the system.
  - *Evidence:* Tested via `tests/test_p1_1_outfit_swap.py::test_swap_rejects_foreign_replacement_garment` and `test_swap_rejects_foreign_current_garment` (both PASSED).

---

## 3. Input Validation & Domain Boundaries

### 3.1 Slot Whitelist and Normalization
- The domain accepts only verified outfit slots. The helper `normalize_slot_name` enforces a closed set:
  ```python
  ALLOWED_SLOTS = {"tops", "bottoms", "footwear", "outerwear", "accessories"}
  ```
- Any malformed, unsupported, or unexpected slot identifier is rejected with HTTP 400 `INVALID_SLOT`.
  - *Evidence:* Tested via `test_normalize_slot_name` (PASSED).

### 3.2 Category-to-Slot Compatibility
- A replacement garment must belong to the exact category of the slot being replaced.
- If a user attempts to replace a `tops` slot with `bottoms` or `footwear`, the backend rejects the request with HTTP 400 `CATEGORY_MISMATCH`.
  - *Evidence:* Tested via `test_swap_rejects_category_mismatch` (PASSED).

### 3.3 Duplicate Garment Defense
- A garment cannot be used in more than one slot within the same outfit.
- If `replacementGarmentId` matches any other active garment in the outfit, the backend rejects the request with HTTP 400 `DUPLICATE_GARMENT`.
  - *Evidence:* Tested via `test_swap_rejects_duplicate_garment_in_different_slot` (PASSED).

### 3.4 Pinned Slot Conflict Handling
- If the garment occupying the slot being replaced is marked as pinned by the user, the backend enforces preservation by raising HTTP 409 `PINNED_SLOT_CONFLICT`.
- In the Flutter UI, pinned garments display a gold push-pin badge and an icon button, and their "Replace" button is converted to a disabled `'Pinned'` indicator.
- If unpinning is intended, the user must explicitly tap the pin icon before replacing.
  - *Evidence:* Tested via `test_swap_rejects_pinned_slot` and `test_api_swap_slot_pinned_conflict_status_409` (both PASSED).

### 3.5 Pinned Garment Preservation
- Any other garment listed in `pinnedGarmentIds` is verified to be present in the resulting outfit components.
- The canonical scoring engine is executed on the candidate with unchanged pinned items preserved.
  - *Evidence:* Tested via `test_swap_preserves_other_pinned_garments` (PASSED).

---

## 4. Privacy, Media & Data Protection

### 4.1 Decision D10 Option A (Guest Mode Isolation)
- Guests never contact `/v1/outfits/swap-slot` or `/v1/outfits/candidates`.
- In `OutfitSlotSwapSheet`:
  ```dart
  if (isGuestUser || !AuthSession.isAuthenticated) {
    final allItems = await _wardrobeRepository.listItems(
      category: widget.targetComponent.category,
    );
    ...
    return;
  }
  ```
- Guest candidate retrieval reads from `LocalWardrobeRepository` (backed by on-device SQLite / shared preferences).
- Swapping an outfit component for a guest updates the ephemeral state in memory on the device.
- Zero guest rows, zero guest UUIDs, and zero guest telemetry records are written to PostgreSQL.
  - *Evidence:* Tested via `newproject/flutter_application_1/test/outfit_slot_swap_test.dart` (2 dedicated guest isolation tests PASSED).

### 4.2 Temporary Media URL Credentials (PR-8 Invariant)
- Candidate retrieval generates 15-minute presigned GET URLs via:
  ```python
  await storage.generate_presigned_get_url(object_key, expires_in_s=900)
  ```
- These temporary transport URLs are enriched only on the wire.
- Invariant PR-8 is preserved: presigned URLs are never stored in PostgreSQL or logged.

### 4.3 Zero Unintended State Mutations
- Neither `/v1/outfits/swap-slot` nor `/v1/outfits/candidates` modifies the wardrobe repository, wear history, or user profile.
- Wear events are NOT logged when swapping or previewing an outfit.
- Outfit derivation is strictly ephemeral. Saving an updated look requires the user to explicitly tap "Save Outfit", triggering `POST /v1/outfits/saved` with an idempotency key.

---

## 5. Security Test Summary

| Test Case | Vulnerability Checked | Result |
|:---|:---|:---:|
| `test_api_unauthenticated_requests_fail` | Missing JWT auth rejection | **PASSED (401)** |
| `test_swap_rejects_foreign_replacement_garment` | BOLA / IDOR on replacement garment | **PASSED (404)** |
| `test_swap_rejects_foreign_current_garment` | BOLA / IDOR on current outfit piece | **PASSED (404)** |
| `test_swap_rejects_nonexistent_garment_id` | Non-existent UUID rejection | **PASSED (404)** |
| `test_swap_rejects_category_mismatch` | Incompatible category insertion | **PASSED (400)** |
| `test_swap_rejects_duplicate_garment_in_different_slot` | Multi-slot duplication | **PASSED (400)** |
| `test_swap_rejects_pinned_slot` | Overwriting pinned garment | **PASSED (409)** |
| `test_api_swap_slot_validation_error_on_malformed_uuid` | SQL/Type injection on UUIDs | **PASSED (422)** |
| `test_swap_rejects_blank_preference_fields` | Unchecked whitespace strings | **PASSED (400)** |
| `test_swap_rejects_empty_current_garment_ids` | Empty outfit candidate crash | **PASSED (400)** |
| `Guest mode loads alternatives from local wardrobe` | Guest cloud leak | **PASSED (0 HTTP calls)** |
| `Guest mode swap recalculates locally` | Guest cloud persistence | **PASSED (0 HTTP calls)** |

---

## 6. Audit Verdict

**PASSED.**  
No security, authorization, privacy, or multi-tenancy vulnerabilities were found. All security boundaries comply with Fansivibe architecture rules and Stage 1/Stage 2 security requirements.
