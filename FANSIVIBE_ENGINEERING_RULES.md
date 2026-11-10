# FANSIVIBE — PERMANENT ENGINEERING RULES

You are working on Fansivibe, an AI-powered fashion ecosystem.

Before implementing any task, read:
- `CURRENT_STATE.md`
- `FANSIVIBE_ENGINEERING_RULES.md`
- `FANSIVIBE_TASK_CHECKLIST.md`
- Relevant architecture documents and previous audit reports.

## 1. Protect the existing application

- Understand the current architecture before changing code.
- Never assume a feature is missing without inspecting its implementation.
- Never replace working architecture unnecessarily.
- Preserve existing API contracts, database schemas, authentication, authorization, guest-mode behavior and frontend compatibility.
- Follow established repository patterns.
- Do not introduce duplicate business logic or competing recommendation engines.
- Never silently remove functionality to make tests pass.

## 2. Mandatory planning before implementation

Every implementation task requires an appropriate architectural plan and test plan before coding begins.

Before coding, provide:
- Current implementation findings.
- Exact files and modules affected.
- Proposed architecture and execution flow.
- Dependencies and prerequisites.
- Potential regressions and security risks.
- Database and migration impact.
- Testing strategy and test plan: unit, integration, E2E, regression, and break testing selected according to applicability.
- Multi-user load testing and GPU stress testing evaluated conditionally based on affected functionality and risk.
- Explicit documentation and justification for any test categories deemed inapplicable.
- Rollback strategy.

Stop and request approval if the proposed work exceeds the authorized scope.

## 3. Mandatory testing

Every implementation task requires an appropriate test plan. Unit, integration, and end-to-end tests must be selected according to applicability to the affected subsystem and task scope. Any inapplicable test category must be explicitly documented with a clear reason.

### Unit tests
Test individual functions, classes, business rules, validation and error handling when changing logic, calculations, or models.

### Integration tests
Test API endpoints, databases, repositories, external adapters, authentication, storage and service interactions when modifying interfaces, persistence, or integrations.

### End-to-end tests
Test complete user workflows across frontend and backend when implementing or altering multi-step cross-tier user journeys.

### Documentation of inapplicable tests
If unit, integration, or E2E tests are not applicable to the task scope (e.g., pure documentation corrections, configuration updates without execution logic), this must be explicitly documented with a justified reason in the test plan and completion report.

Do not claim a test passed unless it was actually executed. Report skipped tests separately, including why they were skipped.

## 4. Mandatory regression and break testing

Every implementation task must incorporate regression and break testing selected according to applicability to the affected functionality and operational risk. Where specific checks are not applicable, document the reason.

After every implementation task:

- Attempt to break the feature.
- Test invalid inputs, missing data, duplicate requests and boundary conditions.
- Test expired authentication and unauthorized access.
- Test network failures, timeouts and unavailable dependencies.
- Test empty states, loading states and recovery behavior.
- Test guest and authenticated user isolation.
- Test concurrent requests and conflicting operations.
- Check that unrelated existing features still work (regression testing).

Use controlled fault injection and isolated test environments. Never run destructive experiments against production or shared user data. Document any inapplicable checks with a reason.

## 5. Concurrency and multi-user load testing

Multi-user load testing is conditional on the affected functionality and risk.

When a task impacts shared state, concurrent access, high-throughput endpoints, connection pools, or multi-user flows, simulate multiple users operating simultaneously.

Test (when applicable):
- Concurrent logins and requests.
- User data isolation.
- Simultaneous wardrobe updates.
- Simultaneous outfit generation.
- Duplicate and retried requests.
- Database connection pool behavior under load.
- Storage upload collisions.
- Rate limits and resource exhaustion.
- GPU job scheduling and memory contention.

Measure latency, throughput, errors, resource usage and recovery.

Never report a concurrency test as completed unless the load was actually generated and measured. If multi-user load testing is not applicable to the task scope (e.g., isolated client UI styling, non-concurrent local helpers, documentation), explicitly document the rationale.

## 6. Security and privacy

- Enforce ownership checks on user-owned resources.
- Never trust client-supplied user IDs or ownership claims.
- Never expose private media or signed URLs across users.
- Keep guest data ephemeral according to established project decisions.
- Never log passwords, tokens, private images or sensitive personal data.
- Validate all inputs and external responses.

## 7. Database, Git, and Production safety

### Git operations and repository governance
- **Read-only Git inspection is permitted:** Commands such as `git status`, `git diff`, `git log`, `git show`, and `git branch` may be executed freely at any time to inspect repository state, history, and working tree modifications.
- **Non-destructive Git operations must remain within the authorized task scope:** Any non-destructive Git operation (such as creating a scoped working branch or staging task-specific files) must remain strictly within the authorized task scope.
- **Destructive Git operations must not be performed without explicit authorization:** Commands that discard work, overwrite changes, alter commit history, or delete untracked files (such as `git reset --hard`, `git clean -f/-fd`, `git restore .`, `git checkout -- .`, or `git branch -D`) must never be performed without prior explicit authorization. Always preserve uncommitted user changes.
- **Commits and pushes always require explicit authorization:** Never execute `git commit` or `git push` without prior explicit authorization.

### Production changes and deployments
- **Production changes and deployments require explicit authorization:** No changes may be made to production environments, production infrastructure, live cloud configurations (e.g., Cloudflare R2 buckets, production DNS, production secrets), nor may any deployment pipelines or production releases be triggered without explicit authorization.

### Database safety
- Inspect migrations before execution.
- Never migrate a database without explicit authorization.
- Never run destructive database tests against development or production databases.
- Preserve uncommitted user changes.

## 8. AI and GPU infrastructure

GPU stress testing and AI infrastructure validation are conditional on the affected functionality and risk (e.g., tasks introducing or modifying model inference, diffusion pipelines, VRAM allocation, or Ollama/VTON orchestration). If GPU testing is inapplicable to the task, document the reason.

When applicable:
- Measure actual RAM and VRAM usage.
- Do not assume a model fits based on parameter count alone.
- Measure cold-start and warm-start latency under load.
- Test model unloading and recovery from CUDA out-of-memory errors (stress testing).
- Coordinate GPU usage between Ollama and VTON.
- Do not unload generation-network weights repeatedly during diffusion denoising.
- Use model registries, dependency resolution and memory-aware scheduling where appropriate.

## 9. Mandatory completion report

After every task, report:

1. Objective and scope.
2. Files changed.
3. Architecture and implementation decisions.
4. Unit-test results (or documented reason if inapplicable).
5. Integration-test results (or documented reason if inapplicable).
6. End-to-end test results (or documented reason if inapplicable).
7. Regression-test results (or documented reason if inapplicable).
8. Break-testing results (or documented reason if inapplicable).
9. Multi-user/load-testing and GPU stress results (conditional on functionality and risk; documented reason if inapplicable).
10. Security findings.
11. Database, migration, and deployment status (confirming zero unauthorized migrations, production changes, or deployments).
12. Performance and resource measurements.
13. Known limitations and unresolved issues (including documented reasons for any skipped or inapplicable tests).
14. Git status and uncommitted changes (confirming read-only inspection, preservation of changes, and zero unauthorized commits or pushes).
15. Acceptance recommendation: PASS, PASS WITH LIMITATIONS, or FAIL.

Never fabricate test results, measurements or verification.

## 10. Stop conditions

Stop implementation and report the problem if:
- Existing production behavior is broken.
- A security boundary is weakened.
- A database migration is required but unauthorized.
- Destructive Git operations, unauthorized commits, or unauthorized pushes are requested.
- Production changes or deployments are requested without explicit authorization.
- The requested scope conflicts with existing architecture.
- Tests expose a genuine production defect.
- The task requires an unapproved dependency or infrastructure change.

**Final principle:** Protect the existing application first. Improve it incrementally. Prove changes with tests and measurable evidence.
