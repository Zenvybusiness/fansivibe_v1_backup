# FANSIVIBE — TASK EXECUTION CHECKLIST

This checklist must be followed by every engineer and AI agent before, during, and after implementing any task in the Fansivibe repository. It translates the 10 permanent engineering rules into mandatory, verifiable gates.

---

## Gate 1: Pre-Task Inspection & Context Acquisition
- [ ] Read `CURRENT_STATE.md` to identify active milestone, recent tasks, and current database/environment state.
- [ ] Read `FANSIVIBE_ENGINEERING_RULES.md`.
- [ ] Read task-relevant documentation (`docs/PRODUCT_BLUEPRINT.md`, `docs/ARCHITECTURE.md`, `DECISIONS.md`, `docs/DESIGN_SYSTEM.md`, etc.).
- [ ] Check `.agents/skills/` and read relevant `SKILL.md` files.
- [ ] Inspect existing codebase implementations — never assume a capability is missing without verifying code.
- [ ] Perform read-only Git inspection (`git status`, `git diff`, etc.) and review all existing uncommitted modifications before taking any action.

## Gate 2: Mandatory Planning Before Implementation
- [ ] Document current implementation findings.
- [ ] List exact files and modules to be modified or created.
- [ ] Formulate proposed architecture and execution flow.
- [ ] Identify dependencies and prerequisites.
- [ ] Assess potential regressions and security risks (including OW-1, guest mode, and data leaks).
- [ ] Verify database impact: confirm whether schema migrations are required (migrations require explicit authorization).
- [ ] Define testing strategy: every implementation task requires an appropriate test plan where unit, integration, E2E, regression, and break tests are selected according to applicability.
- [ ] Evaluate multi-user load testing and GPU stress testing conditionally based on affected functionality and risk.
- [ ] Explicitly document the rationale and reason for any test categories deemed inapplicable.
- [ ] Define rollback strategy.
- [ ] Verify production and deployment boundaries: confirm no production changes or deployments are included without explicit authorization.
- [ ] **STOP & REQUEST APPROVAL** if the scope exceeds authorization, introduces architectural migrations, unapproved dependencies, or touches production without authorization.

## Gate 3: Implementation & Core Testing
- [ ] Implement the smallest safe, focused change adhering to established project patterns.
- [ ] Preserve single canonical engines (e.g., single 12-term outfit scoring engine in `analysis_rules.py`).
- [ ] Preserve existing API contracts, database schemas, authentication, authorization, and guest-mode behavior.
- [ ] Execute an appropriate test plan with tests selected according to applicability:
  - **Unit Tests**: write and execute for functions, domain models, value objects, validation, and error handling when applicable.
  - **Integration Tests**: write and execute for API endpoints, repositories, storage adapters, and external seams when applicable.
  - **End-to-End Tests**: write and execute for complete multi-step user workflows when applicable.
- [ ] Document explicit reasons for any inapplicable test categories in the plan and completion report.
- [ ] Ensure all applicable tests actually executed. Explicitly document and justify any skipped tests.

## Gate 4: Mandatory Regression & Break Testing
Select regression and break testing checks according to applicability to the affected functionality and operational risk (document reasons for any inapplicable checks):
- [ ] **Invalid Inputs**: Malformed JSON, out-of-range coordinates, unexpected types, missing fields.
- [ ] **Boundary Conditions**: Empty lists, maximum length payloads, boundary values.
- [ ] **Auth & Permission Boundaries**: Unauthenticated requests, expired tokens, cross-user access attempts (OW-1).
- [ ] **Network & Upstream Failures**: Provider outages, HTTP 500/503 from external services, timeouts (verify fail-open behavior).
- [ ] **State & Lifecycle**: Empty states, loading states, error presentation, recovery paths.
- [ ] **Guest vs. Authenticated Isolation**: Verify guest data stays strictly local/ephemeral and never writes to DB.
- [ ] **Concurrency & Conflict**: Duplicate requests, rapid retry clicks, idempotent mutations.
- [ ] **Regression Suite**: Execute existing test suites to confirm unrelated features remain unbroken.

## Gate 5: Multi-User Simulation & Load Testing (Conditional)
*Note: Conditional on affected functionality and risk (e.g., concurrent mutations, shared DB pools, high-throughput flows, upload concurrency). If inapplicable to the task scope, explicitly document the reason.*
- [ ] Simulate concurrent requests and multi-user load.
- [ ] Verify database connection pool stability under load.
- [ ] Verify storage upload isolation and avoid key collisions.
- [ ] Verify rate limiting and resource contention behavior.
- [ ] Measure latency, throughput, error rates, and recovery metrics.

## Gate 6: Security & Privacy Verification
- [ ] Verify owner scoping (`user_id` enforced from verified JWT; client-supplied IDs never trusted).
- [ ] Verify private media isolation: signed URLs expire (e.g., 15m), never exposed cross-user.
- [ ] Verify zero logging of tokens, passwords, private images, or sensitive facial/body measurements.
- [ ] Validate and sanitize all external inputs and provider responses.

## Gate 7: Database, Git & Production Safety Audit
- [ ] **Read-only Git inspection**: read-only Git inspection is permitted and used to verify repository and working tree state.
- [ ] **Non-destructive Git scope**: confirm all non-destructive Git operations remained strictly within the authorized task scope.
- [ ] **No destructive Git operations**: confirm no destructive Git commands (`git reset --hard`, `git clean -f/-fd`, `git restore .`, `git checkout -- .`, `git branch -D`) were executed without explicit authorization.
- [ ] **No unauthorized commits or pushes**: confirm no commits or pushes were made without explicit authorization.
- [ ] **No unauthorized production changes or deployments**: confirm no production changes or deployments were performed without explicit authorization.
- [ ] **Database safety**: confirm no database migration was executed without explicit authorization, and no destructive database tests were run against shared databases (`fansivibe`, `fansivibe_test`).
- [ ] **Preserve existing modifications**: confirm all uncommitted user files and pre-existing modifications are strictly preserved.

## Gate 8: AI & GPU Infrastructure Validation (Conditional)
*Note: Conditional on affected functionality and risk (e.g., tasks introducing or modifying model inference, diffusion denoising, VRAM allocation, or Ollama/VTON scheduling). If inapplicable to the task scope, explicitly document the reason.*
- [ ] Measure physical RAM and VRAM usage.
- [ ] Benchmark cold-start vs. warm-start latencies.
- [ ] Execute GPU stress testing: test CUDA out-of-memory handling and model recovery.
- [ ] Ensure non-disruptive scheduling between Ollama and VTON models.

## Gate 9: Stop Conditions Check
- [ ] Halt immediately and report if:
  - Existing production behavior is broken.
  - A security boundary is weakened.
  - An unauthorized database migration is required.
  - Destructive Git operations, unauthorized commits, or unauthorized pushes are requested.
  - Production changes or deployments are requested without explicit authorization.
  - Scope conflicts with existing architecture.
  - An unapproved dependency or infrastructure change is required.

## Gate 10: Mandatory 15-Point Completion Report
Produce the standardized 15-point report:
1. **Objective and scope**
2. **Files changed**
3. **Architecture and implementation decisions**
4. **Unit-test results** (or documented reason if inapplicable)
5. **Integration-test results** (or documented reason if inapplicable)
6. **End-to-end test results** (or documented reason if inapplicable)
7. **Regression-test results** (or documented reason if inapplicable)
8. **Break-testing results** (or documented reason if inapplicable)
9. **Multi-user/load-testing and GPU stress results** (conditional on functionality and risk; documented reason if inapplicable)
10. **Security findings**
11. **Database, migration, and deployment status** (confirming zero unauthorized migrations, production changes, or deployments)
12. **Performance and resource measurements**
13. **Known limitations and unresolved issues** (including reasons for skipped or inapplicable tests)
14. **Git status and uncommitted changes** (confirming read-only inspection, preservation of changes, zero unauthorized commits or pushes)
15. **Acceptance recommendation**: `PASS`, `PASS WITH LIMITATIONS`, or `FAIL`
- [ ] Update `CURRENT_STATE.md` with task outcome.
