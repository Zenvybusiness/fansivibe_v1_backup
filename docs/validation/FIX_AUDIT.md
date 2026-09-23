# Fansivibe Fix Audit

Date: 2026-09-23
Auditor: Antigravity AI Agent

This document records the verification of alleged vs confirmed problems across the entire Fansivibe codebase.

---

## Confirmed Issues Register

### Issue 1: `DevelopmentAppearanceAnalysisAdapter.analyze()` parameter signature mismatch
- **Confirmed?**: YES
- **Evidence**: `TypeError: DevelopmentAppearanceAnalysisAdapter.analyze() got an unexpected keyword argument 'image_bytes'` when called from `CreateOutfitRun` (`backend/app/application/analysis.py:241`). Causes 6 unit test failures in `backend/tests/test_analysis_use_case.py`.
- **Severity**: P1
- **Root cause**: `AppearanceAnalysisPort.analyze` declared `image_bytes: bytes | None = None` in Phase 10 boundary fix, but `DevelopmentAppearanceAnalysisAdapter.analyze` in `backend/app/ai/appearance_adapter.py` omitted the parameter. Furthermore, it incorrectly called `self.validate_result(profile.__dict__)` which validates 7-field result snapshots against a 5-field `AppearanceProfile`.
- **Fix required?**: YES
- **Files affected**:
  - `backend/app/ai/appearance_adapter.py`
- **Tests required**:
  - `backend/tests/test_analysis_use_case.py` (6 tests: `test_outfit_run_creates_with_development_adapter`, `test_outfit_run_profile_updated_with_image_attributes`, `test_outfit_run_learning_signal_emitted`, `test_outfit_run_with_development_adapter_full_structure`, `test_outfit_run_with_sparse_profile_sets_needs_more_data`, `test_recommendation_deterministic_with_image_appearance_profile`)
- **Status**: PENDING FIX

---

### Issue 2: Obsolete square-bracket test assertions against frozen delimiter-free prompt
- **Confirmed?**: YES
- **Evidence**: 5 tests in `backend/tests/` assert Phase 3H square-bracket syntax (`[term-denim]` and `"square-bracketed IDs in section C"`):
  - `test_evidence_id_namespace.py::test_inventory_lists_exactly_supplied_ids`
  - `test_ffo_reasoning_adapter.py::test_evidence_serialization_compact`
  - `test_ffo_ref_namespace.py::test_evidence_ids_distinct_from_refs`
  - `test_ffo_ref_namespace.py::test_3h_prompt_constraints_preserved`
  - `test_ollama_prompt_hardening.py::test_system_prompt_id_fidelity_rules`
- **Severity**: P1
- **Root cause**: Phase 3X and Phase 3AG intentionally transitioned the reasoning prompt to delimiter-free IDs (`term-denim` without square brackets) to eliminate LLM bracket-literal hallucinations. `backend/app/ai/reasoning_prompt.py` was frozen in Phase 3AG/3AO. The 5 unit tests were historical pins that were never updated to reflect this intentional architectural decision.
- **Fix required?**: YES (Update stale test pins to assert the delimiter-free contract, strictly preserving the frozen prompt and FFO corpus unchanged).
- **Files affected**:
  - `backend/tests/test_evidence_id_namespace.py`
  - `backend/tests/test_ffo_reasoning_adapter.py`
  - `backend/tests/test_ffo_ref_namespace.py`
  - `backend/tests/test_ollama_prompt_hardening.py`
- **Tests required**:
  - `pytest -q`
- **Status**: PENDING FIX

---

## Non-Issues / Historical Claims Audited

| Alleged Issue | Confirmed? | Current Verification & Evidence | Action Required |
|---|---|---|---|
| **Flutter dependency conflict** (`test` vs `flutter_test`) | **NO** | `pubspec.yaml` and `pubspec.lock` have zero references to `package:test`. `test_api 0.7.12` is cleanly bundled by Flutter 3.47.4. `flutter pub get`, `flutter analyze` (0 issues), and `flutter test` (978/978) all pass. | None (No change). |
| **AI Evidence Grounding broken** ("0/25", "14/25", hallucinated IDs) | **NO** | Phase 3AO and 3AI verified 90% evaluable rate on held-out benchmark. Fail-closed contract enforcement in `validate_output` and `conclusion_admission.py` rejects unretrieved IDs and unpermitted references. | None (Keep frozen). |
| **Mock data masquerading as production** | **NO** | `WardrobeRepositoryImpl`, `TodayLookRepositoryImpl`, `SavedLooksRepositoryImpl`, `KnowledgeRepositoryImpl` all enforce strict real-backend data flow with explicit zero-mock-fallback contracts. | None (No change). |
| **Dev auth leaking to production** | **NO** | `backend/app/config/settings.py` enforces startup validation in production: `allow_dev_token=True` is strictly rejected; default secrets are rejected; dev credentials rejected. | None (No change). |
| **Cross-user data leakage / auth isolation** | **NO** | Strict owner-scoped database queries (`user_id == current_user_id`) verified by dedicated isolation test suites across Auth, Wardrobe, Saved Looks, Events, Learning, and Analysis. | None (No change). |
| **Rogue Trending scrapers or migrations** | **NO** | Zero unauthorized scrapers exist. Zero premature Alembic migrations for Trending exist (migrations stop at 0022). Architecture safety rules respected. | None (No change). |
| **Android Camera functionality** | **NOT TESTED** | Headless development environment has no connected physical Android device. Web device (Edge) is available and functional. Explicitly marked NOT TESTED per rules. | None (Documented). |
