# Fansivibe Decisions

This file records accepted major product and architecture decisions.

Do not record trivial implementation choices.

## DEC-001 — Flutter Frontend

Status: Accepted

Fansivibe uses Flutter as its primary application frontend.

Changing frontend technology requires project-owner approval.

---

## DEC-002 — Feature-First Architecture

Status: Accepted

Major product capabilities are organized as independent features.

Example:

features/
├── home/
├── discover/
├── wardrobe/
├── outfit_scan/
└── hairstyle/

New features should be addable without restructuring unrelated features.

---

## DEC-003 — Backend Direction

Status: Accepted Direction

Python FastAPI is the intended backend technology.

Flutter must not directly depend on individual AI providers.

---

## DEC-004 — Database Direction

Status: Accepted Direction

PostgreSQL is the intended primary relational database.

---

## DEC-005 — Primary Navigation

Status: Accepted

Primary navigation:

- Home
- Discover
- Stylist
- Wardrobe
- Profile

---

## DEC-006 — Repository Memory

Status: Accepted

AI agents do not share chat history.

Repository documentation and actual code are the shared source of truth.

`CURRENT_STATE.md` tracks current development state.

---

## DEC-007 — Incremental Development

Status: Accepted

Fansivibe is built feature by feature.

Ordinary feature tasks must not perform unrelated architecture migrations.

---

## DEC-008 — Declarative Routing with go_router

Status: Accepted

Routes are declared centrally using `package:go_router` with
`StatefulShellRoute.indexedStack` for persistent tab navigation.

- All route name strings are centralized in `lib/app/router/route_names.dart`.
- The single `GoRouter` config lives in `lib/app/router/app_router.dart`.
- Cross-feature screen imports are eliminated — screens navigate by name only.
- Screen data is passed through `state.extra` as typed objects or `Map<String, String>`.
- Route builders null-check `state.extra` to handle GoRouter 17 eager evaluation.

This replaces raw `Navigator.push(MaterialPageRoute(...))` calls spread across
all screen files.

---

## DEC-009 — STEP 7 Hairstyle Vertical Slice: Mounting + Gating Decisions (D1–D5)

Status: Accepted

The first production vertical slice (hairstyle recommendation) is implemented
end-to-end (Flutter → FastAPI → PostgreSQL → rules engine → save → feedback
signal) per `docs/implementation/STEP_7_HAIRSTYLE_IMPLEMENTATION_PLAN.md`. The
five gating decisions were approved before implementation:

- **D1 — Dev auth seam.** Until D-AUTH-1 lands, `app/api/deps.py` maps a Bearer
  token (`FANSIVIBE_DEV_TOKEN`, default `dev`) to the seeded dev user. Owner
  scoping (404-not-403) is fully enforced; real auth swaps in additively behind
  the same seam.
- **D2 — Profile-only pass.** Analysis submits `faceProfileRef` only; face-image
  upload is deferred behind sealed MS10.3. No fake analysis: no stored face
  shape → `422 INSUFFICIENT_USER_DATA` (client falls back to the offline mock).
- **D3 — Database layer.** SQLAlchemy 2.0 + `psycopg` (binary) + Alembic; a
  `postgres` service was added to `docker-compose.yml`. Minimal STEP-4 table
  subset (8 models) with a server-side `complete_analysis_run` SQL function
  (TRX-5 write-once guard).
- **D4 — AI enrichment scope.** The rules-only decision engine is the
  deliverable; optional LLM wording enrichment of `description` reuses the
  `llm_backend.py` seam (never structure/scores) and degrades safely.
- **D5 — Save behavior.** "Save Style"/"Try This Style" POST `#23`
  (`POST /v1/looks/saved`) with an `Idempotency-Key` (replay → original/409);
  TRX-3 commits save + `look_saved` signal together; the existing snackbar
  confirmation is preserved.

Also accepted (documented deviations kept honest): mounting analysis before
D-AUTH-1/MS10.3 is a documented, dev-seam-only deviation (no fake 200s); the
analysis run contract, `{error:{code,message,details}}` taxonomy, and the
202-`{run_id}` never-idempotent submit follow
`docs/api/FANSIVIBE_API_CONTRACT_V1.md`.
## DEC-010 — Saved-Look Domain Discriminator (STEP 11.16)

Status: Accepted

`saved_looks.source_context` (`hairstyle`/`grooming`/`outfit`, CHECK-guarded,
NULL = legacy row written before the contract) is the authoritative
backend-owned answer to "is this save an outfit, hairstyle, or grooming
save". `look_id IS NULL`, title text, `learning_signals.context`, and
unvalidated snapshot inspection must never be used as domain discriminators.
Outfit `snapshot.selectedItemIds` is validated (UUID list), ownership-checked
against the owner's wardrobe via the existing owner-scoped lookup, and
persisted canonically (sorted unique UUID strings). Unknown/foreign item IDs
reject the save (404, nothing stored); malformed IDs are 422.
