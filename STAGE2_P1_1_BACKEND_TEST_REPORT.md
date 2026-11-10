# Fansivibe — Stage 2 P1-1 Backend Test Report
## Interactive Outfit Component Swapping

**Feature:** P1-1 — Interactive Outfit Component Swapping  
**Test Suite:** `backend/tests/test_p1_1_outfit_swap.py`  
**Execution Environment:** Linux / Python 3.12.3 / pytest 9.1.1 / anyio 4.15.1  
**Execution Date:** November 2, 2026  
**Result:** 21 PASSED, 0 FAILED (100% Pass Rate)  
**Execution Duration:** 0.82 seconds  

---

## 1. Test Command & Execution Output

```bash
cd backend
.venv/bin/pytest tests/test_p1_1_outfit_swap.py -v
```

### Raw Output Log
```
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.6.0 -- /home/tony/projects/fansivibe_v1_backup/backend/.venv/bin/python3
cachedir: .pytest_cache
rootdir: /home/tony/projects/fansivibe_v1_backup/backend
plugins: anyio-4.15.1
collecting ... collected 21 items

tests/test_p1_1_outfit_swap.py::test_normalize_slot_name PASSED          [  4%]
tests/test_p1_1_outfit_swap.py::test_swap_top_slot_success PASSED        [  9%]
tests/test_p1_1_outfit_swap.py::test_swap_bottom_slot_success PASSED     [ 14%]
tests/test_p1_1_outfit_swap.py::test_swap_footwear_slot_success PASSED   [ 19%]
tests/test_p1_1_outfit_swap.py::test_swap_outerwear_and_accessory_slot_success PASSED [ 23%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_category_mismatch PASSED [ 28%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_duplicate_garment_in_different_slot PASSED [ 33%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_pinned_slot PASSED     [ 38%]
tests/test_p1_1_outfit_swap.py::test_swap_preserves_other_pinned_garments PASSED [ 42%]
tests/test_p1_1_outfit_swap.py::test_candidates_retrieval PASSED         [ 47%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_foreign_replacement_garment PASSED [ 52%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_foreign_current_garment PASSED [ 57%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_nonexistent_garment_id PASSED [ 61%]
tests/test_p1_1_outfit_swap.py::test_api_swap_slot_endpoint PASSED       [ 66%]
tests/test_p1_1_outfit_swap.py::test_api_candidates_endpoint PASSED      [ 71%]
tests/test_p1_1_outfit_swap.py::test_api_unauthenticated_requests_fail PASSED [ 76%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_blank_preference_fields PASSED [ 80%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_empty_current_garment_ids PASSED [ 85%]
tests/test_p1_1_outfit_swap.py::test_swap_rejects_pinned_garment_not_in_outfit PASSED [ 90%]
tests/test_p1_1_outfit_swap.py::test_api_swap_slot_validation_error_on_malformed_uuid PASSED [ 95%]
tests/test_p1_1_outfit_swap.py::test_api_swap_slot_pinned_conflict_status_409 PASSED [100%]

======================== 21 passed, 1 warning in 0.82s =========================
```

---

## 2. Test Case Breakdown and Verification Coverage

### 2.1 Slot Normalization & Whitelist Verification
- `test_normalize_slot_name`:
  Verifies that `tops`, `top`, `bottoms`, `bottom`, `pants`, `shoes`, `footwear`, `outerwear`, `jacket`, `accessories`, `accessory` map cleanly to canonical categories. Verifies that invalid names (`hat`, `random_slot`, empty string) raise `ApiError(400, "INVALID_SLOT")`.

### 2.2 Individual Slot Swapping Success
- `test_swap_top_slot_success`:
  Swaps a white shirt with an oxford shirt. Verifies resulting outfit contains the replacement top, original bottoms, original shoes, recalculated match score, and verified reasons.
- `test_swap_bottom_slot_success`:
  Swaps navy chinos with dark jeans. Verifies bottom slot is replaced while top and shoes are retained.
- `test_swap_footwear_slot_success`:
  Swaps brown oxfords with white sneakers. Verifies footwear slot replacement and score recalculation.
- `test_swap_outerwear_and_accessory_slot_success`:
  Verifies 4-piece (outerwear) and 5-piece (accessories) outfits correctly replace outerwear and accessory slots.

### 2.3 Domain Validation & Safety Invariants
- `test_swap_rejects_category_mismatch`:
  Asserts that attempting to replace a `tops` slot with a `bottoms` garment raises HTTP 400 with code `CATEGORY_MISMATCH`.
- `test_swap_rejects_duplicate_garment_in_different_slot`:
  Asserts that attempting to replace a slot using a garment already active in another slot raises HTTP 400 with code `DUPLICATE_GARMENT`.
- `test_swap_rejects_pinned_slot`:
  Asserts that if the requested slot's current garment is in `pinnedGarmentIds`, the swap is rejected with HTTP 409 `PINNED_SLOT_CONFLICT`.
- `test_swap_preserves_other_pinned_garments`:
  Asserts that when a different slot is replaced, any other pinned items are verified to remain in the resulting outfit components.
- `test_swap_rejects_blank_preference_fields`:
  Asserts that empty or whitespace `occasion`, `mood`, `fit`, or `colorPalette` fields raise HTTP 400 `INVALID_PREFERENCES`.
- `test_swap_rejects_empty_current_garment_ids`:
  Asserts that an empty `currentGarmentIds` list raises HTTP 400 `INVALID_OUTFIT`.
- `test_swap_rejects_pinned_garment_not_in_outfit`:
  Asserts that specifying a pinned garment ID that is not part of the active outfit raises HTTP 400 `PINNED_GARMENT_NOT_IN_OUTFIT`.

### 2.4 Candidate Retrieval Verification
- `test_candidates_retrieval`:
  Verifies `GetOutfitCandidates.execute` returns garments matching the slot category, excludes the current garment occupying that slot, and excludes any garment already active in another slot.

### 2.5 Security, Authorization & Tenant Scoping
- `test_swap_rejects_foreign_replacement_garment`:
  User A attempts to substitute a garment owned by User B. Asserts HTTP 404 `REPLACEMENT_GARMENT_NOT_FOUND` is raised, masking the garment's existence.
- `test_swap_rejects_foreign_current_garment`:
  User A attempts to supply a garment owned by User B in `currentGarmentIds`. Asserts HTTP 404 `GARMENT_NOT_FOUND` is raised.
- `test_swap_rejects_nonexistent_garment_id`:
  Asserts non-existent random UUIDs raise HTTP 404.
- `test_api_unauthenticated_requests_fail`:
  Asserts requests without Bearer token return HTTP 401 Unauthorized for both `/v1/outfits/swap-slot` and `/v1/outfits/candidates`.
- `test_api_swap_slot_validation_error_on_malformed_uuid`:
  Asserts malformed non-UUID strings (`not-a-uuid`) in request bodies return HTTP 422 Unprocessable Entity.

### 2.6 Full FastAPI HTTP Integration
- `test_api_swap_slot_endpoint`:
  Submits an authenticated request via FastAPI `TestClient` to `POST /v1/outfits/swap-slot`. Asserts HTTP 200, valid response structure matching `OutfitSlotSwapResponse`, correct replaced slot, previous garment ID, and canonical score.
- `test_api_candidates_endpoint`:
  Submits an authenticated request to `POST /v1/outfits/candidates`. Asserts HTTP 200, valid `OutfitCandidatesResponse`, and verifies presigned GET URL enrichment via `_candidate_to_wire`.
- `test_api_swap_slot_pinned_conflict_status_409`:
  Submits an HTTP request attempting to swap a slot where the current garment is pinned. Asserts HTTP 409 status code and `PINNED_SLOT_CONFLICT` error code.

---

## 3. Test Metric Summary

| Category | Test Count | Passed | Failed | Skipped | Pass Rate |
|:---|:---:|:---:|:---:|:---:|:---:|
| Slot Normalization | 1 | 1 | 0 | 0 | 100% |
| Unit Slot Swapping | 4 | 4 | 0 | 0 | 100% |
| Domain Validation | 5 | 5 | 0 | 0 | 100% |
| Candidate Retrieval | 1 | 1 | 0 | 0 | 100% |
| Security & OW-1 Scoping | 5 | 5 | 0 | 0 | 100% |
| HTTP API Integration | 5 | 5 | 0 | 0 | 100% |
| **Total** | **21** | **21** | **0** | **0** | **100%** |
