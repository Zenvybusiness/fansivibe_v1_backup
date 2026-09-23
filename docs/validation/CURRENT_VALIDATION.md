# Fansivibe Current Validation Baseline

Date: 2026-09-23
Flutter SDK: 3.47.4 (Channel stable)
Dart SDK: 3.13.3
Python: 3.14.5
PostgreSQL: 16.0
Host OS: Windows 11 (windows_x64)

---

## 1. Summary Baseline

| Component | Status | Metrics / Details |
|---|---|---|
| **Flutter pub get** | **PASS** | Dependencies resolved cleanly (0 conflicts) |
| **Flutter analyze** | **PASS** | 0 issues found (1.2s) |
| **Flutter test suite** | **PASS** | 978 passed, 0 failed, 0 skipped (20s) |
| **Backend test suite (pre-fix)** | **FAIL** | 896 passed, 537 skipped, 11 failed |
| **Backend API smoke** | **PASS** | Live FastAPI reverse-proxy / reasoning smoke verified |
| **Android** | **NOT TESTED** | No physical Android device or emulator connected |
| **Web** | **PASS** | Edge (web) device connected; web-safe image byte pipeline verified |
| **Camera** | **NOT TESTED** | Physical camera not available on headless host; Web picker verified |
| **Authentication Isolation** | **PASS** | Multi-user isolation verified across Auth, Wardrobe, Looks, Events |
| **AI / FFO Grounding** | **PASS** | 165/165 reasoning integration/contract tests pass; fail-closed verified |

---

## 2. Flutter Dependency Graph Audit

- **Alleged Conflict**: `test ^1.31.0` vs `flutter_test` vs `test_api 0.7.10`.
- **Verified Current State**:
  - `pubspec.yaml` direct dependencies: `flutter` (sdk), `cupertino_icons: ^1.0.8`, `go_router: ^17.2.3`, `camera: ^0.12.0+1`, `http: ^1.2.2`, `http_parser: ^4.1.2`, `image_picker: ^1.0.7`, `shared_preferences: ^2.3.3`, `flutter_secure_storage: ^11.1.1`.
  - `dev_dependencies`: `flutter_test` (sdk), `flutter_lints: ^5.0.0`.
  - `package:test` is **NOT present** in `pubspec.yaml` or `pubspec.lock`.
  - `test_api` is resolved to `0.7.12` directly bundled with the Flutter 3.47.4 SDK.
  - Conflict is **HISTORICAL / NON-EXISTENT** in the current dependency graph.
  - `flutter pub get`: PASS (code 0).
  - `flutter analyze`: PASS (0 issues found).
  - `flutter test`: PASS (978/978 passed).

---

## 3. Backend Test Suite Audit (Initial Baseline)

Running `pytest -q`:
- Total Collected: 1444 tests
- Passed: 896
- Skipped: 537 (integration / optional model-dependent tests)
- Failed: 11
- Duration: 15.93s

### Failure Breakdown

1. `tests/test_analysis_use_case.py::test_outfit_run_creates_with_development_adapter` (IMPLEMENTATION BUG)
2. `tests/test_analysis_use_case.py::test_outfit_run_profile_updated_with_image_attributes` (IMPLEMENTATION BUG)
3. `tests/test_analysis_use_case.py::test_outfit_run_learning_signal_emitted` (IMPLEMENTATION BUG)
4. `tests/test_analysis_use_case.py::test_outfit_run_with_development_adapter_full_structure` (IMPLEMENTATION BUG)
5. `tests/test_analysis_use_case.py::test_outfit_run_with_sparse_profile_sets_needs_more_data` (IMPLEMENTATION BUG)
6. `tests/test_analysis_use_case.py::test_recommendation_deterministic_with_image_appearance_profile` (IMPLEMENTATION BUG)
7. `tests/test_evidence_id_namespace.py::test_inventory_lists_exactly_supplied_ids` (STALE TEST / CONTRACT CHANGE)
8. `tests/test_ffo_reasoning_adapter.py::test_evidence_serialization_compact` (STALE TEST / CONTRACT CHANGE)
9. `tests/test_ffo_ref_namespace.py::test_evidence_ids_distinct_from_refs` (STALE TEST / CONTRACT CHANGE)
10. `tests/test_ffo_ref_namespace.py::test_3h_prompt_constraints_preserved` (STALE TEST / CONTRACT CHANGE)
11. `tests/test_ollama_prompt_hardening.py::test_system_prompt_id_fidelity_rules` (STALE TEST / CONTRACT CHANGE)

See `docs/validation/FIX_AUDIT.md` for root cause analysis and resolution details.
