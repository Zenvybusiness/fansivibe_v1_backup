# Fansivibe Agent Rules

These rules apply to every AI coding agent working in this repository.

The repository is the shared source of truth. Do not rely on previous
agent chat history.

## Mandatory Workflow

Before modifying code:

1. Read `CURRENT_STATE.md`.
2. Read only task-relevant project documentation.
3. Inspect the actual code and Git status.
4. Inspect `.agents/skills/`.
5. Select relevant skills.
6. Read the selected `SKILL.md` files.
7. Identify existing project patterns.
8. Plan the smallest safe change.
9. Implement.
10. Format, analyze, and test relevant code.
11. Review the diff.
12. Update `CURRENT_STATE.md` after meaningful work.

Do not start coding before inspecting relevant skills and existing code.

## Documentation Selection

Read only what the task requires:

- Product behavior → `docs/PRODUCT_BLUEPRINT.md`
- Architecture → `docs/ARCHITECTURE.md`
- Screens/navigation → `docs/SCREEN_MAP.md`
- UI/design → `docs/DESIGN_SYSTEM.md`
- Major accepted decisions → `DECISIONS.md`
- Product identity → `PROJECT_CONTEXT.md`

Do not read every document for every small task.

## Architecture Rules

- Use feature-first modular architecture.
- Keep feature-specific code inside its feature.
- Do not access another feature's internal data or presentation code.
- Use public contracts for cross-feature communication.
- Do not put business logic in UI widgets.
- Screens must not call APIs directly.
- Flutter must not directly depend on AI providers.
- AI responses must use typed structured data.
- Prefer configuration-driven expandable systems.
- Do not hardcode backend-controlled categories.
- Use the existing state-management and routing approach.
- Do not migrate architecture without explicit approval.
- Do not add dependencies without checking existing solutions.
- Do not create empty architecture layers without real need.

## Design Rules

- Follow `docs/DESIGN_SYSTEM.md`.
- Reuse existing theme tokens and components.
- Do not invent random colors, spacing, typography, radius, or shadows.
- Keep layouts responsive.
- Prevent overflow and support text scaling.
- Feature widgets stay in their feature.
- Move widgets to `shared/` only when reuse is real.

## Safety

Never:

- expose secrets or API keys
- log authentication tokens
- log private user images
- delete or overwrite unrelated user work
- run destructive Git commands without approval
- claim tests passed without running them
- hide errors to make validation appear successful

Fansivibe processes appearance and image data. Treat it as
privacy-sensitive.

Do not shame users or present subjective appearance judgments as facts.

## Scope

Implement the requested task only.

Do not perform unrelated refactors, redesigns, package replacements, or
architecture migrations.

If a decision significantly affects architecture, privacy, authentication,
data storage, or product behavior and the repository does not answer it,
ask the user.

## Completion

After meaningful work report:

- what changed
- skills used
- files changed
- validation run
- remaining issues

Update `CURRENT_STATE.md`.

Update `DECISIONS.md` only for accepted major decisions.

Never fake completion.

## Agent Efficiency

Do not produce a separate implementation plan and wait for approval unless
the task has a real blocker, destructive action, or major architectural
decision.

For well-defined tasks:

inspect → plan internally → implement → validate → report

Keep reports concise.

Read only task-relevant documentation and skills.

Avoid repeating repository documentation in responses.