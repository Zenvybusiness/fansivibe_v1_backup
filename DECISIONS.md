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