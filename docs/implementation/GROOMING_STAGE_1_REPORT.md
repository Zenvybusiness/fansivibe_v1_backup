# Grooming Stage 1 Report — Database + Knowledge Foundation

**Stage:** 1 (of 8) — DATABASE + KNOWLEDGE FOUNDATION  
**Status:** Completed and verified  
**Date:** 2026-08-13  

---

## 1. Files Created

| File | Purpose |
|---|---|
| `backend/alembic/versions/0003_grooming_knowledge.py` | Alembic migration 0003 — adds grooming run type and 4 look seed rows to existing tables |
| `docs/implementation/GROOMING_STAGE_1_REPORT.md` | This report |

No Flutter, routing, or screen changes were made (per strict rules).

---

## 2. Migration Details

**Migration file:** `backend/alembic/versions/0003_grooming_knowledge.py`  
**Revises:** `0002_analysis_runs_error.py`  
**Upgrade generates:** Adds `grooming` run type row + 4 grooming look rows into existing `run_types` and `looks` tables with `content_version = '1.1'`.

### SQL executed during upgrade (key portions):

```sql
-- Add grooming run type (sort_order=1, alongside existing hairstyle)
INSERT INTO run_types (code, label, sort_order) VALUES ('grooming', 'Grooming analysis', 1);

-- Add 4 grooming look rows with content_version '1.1'
INSERT INTO looks (code, title, content_version, payload, published_at) VALUES ('structured_goatee', 'Structured Goatee', '1.1', CAST(...) AS jsonb), now();
INSERT INTO looks (code, title, content_version, payload, published_at) VALUES ('classic_stubble', 'Classic Stubble', '1.1', CAST(...) AS jsonb), now();
INSERT INTO looks (code, title, content_version, payload, published_at) VALUES ('full_beard', 'Full Beard', '1.1', CAST(...) AS jsonb), now();
INSERT INTO looks (code, title, content_version, payload, published_at) VALUES ('goatee_with_mustache', 'Goatee with Mustache', '1.1', CAST(...) AS jsonb), now();
```

### Downgrade script (0003 -> 0002):

```sql
DELETE FROM run_types WHERE code = 'grooming';
DELETE FROM looks WHERE code IN ('structured_goatee', 'classic_stubble', 'full_beard', 'goatee_with_mustache');
```

### Table reuse (per rules):

- **`run_types`** — existing table, no schema change; only adds new `('grooming', 'Grooming analysis')` row
- **`looks`** — existing table, no schema change; only adds 4 new rows with `content_version = '1.1'`
- **No new tables created** — reuses existing `analysis_runs`, `saved_looks`, `learning_signals` infrastructure
- **`analysis_runs`**, **`saved_looks**`, **`learning_signals`** — untouched

### Offline verification:

- `alembic upgrade --sql head` — clean, all SQL generated successfully
- `alembic downgrade --sql 0003:0002` — cleanly removes only grooming entries

---

## 3. Knowledge Details

**Catalog file:** `backend/app/data/catalog.py`

### GROOMING_LOOKS (4 entries, mirror hairstyle cardinality)

| Code | Title | scoreSeed |
|---|---|---|
| `structured_goatee` | Structured Goatee | 0.92 |
| `classic_stubble` | Classic Stubble | 0.85 |
| `full_beard` | Full Beard | 0.75 |
| `goatee_with_mustache` | Goatee with Mustache | 0.71 |

Each entry contains: `code`, `title`, `description`, `reasons` (list), `stylingTips`, `maintenance`, `bestFor`, `scoreSeed`.

### GROOMING_VOCAB (stable identifiers)

```python
GROOMING_VOCAB: dict[str, str] = {
    "structured_goatee": "structured_goatee",
    "classic_stubble": "classic_stubble",
    "full_beard": "full_beard",
    "goatee_with_mustache": "goatee_with_mustache",
}
```

Used by the decision engine and the save-layer `look_id` field. Mirrors the hairstyle code mapping (PR-3).

### Validation

- `_validate_grooming_entry()` — read-time validation raising `KnowledgeError` on missing code, empty required fields, empty reasons, or out-of-range `scoreSeed`
- `_to_grooming_recommendation()` — converts validated entry to `GroomingRecommendation` DTO
- `CatalogKnowledgeSource.lookup_grooming_look(code)` — exact keyed read
- `CatalogKnowledgeSource.retrieve_grooming_looks()` — filtered/derived reads for the Decision Engine (deprecated entries filtered, KN-3)

### Knowledge version

- `catalog.KNOWLEDGE_VERSION = "1.1"` (bumped from `"1.0"`)
- Aligns with migration's `looks.content_version` seed for grooming entries
- Exposed on the port via `CatalogKnowledgeSource.knowledge_version`

### Deterministic & reproducible

- Catalog entries are pure data (no randomization, no external state)
- Seed data is idempotent: re-running the migration inserts the same rows; downgrade removes only grooming entries
- Knowledge source methods are deterministic given the same catalog

---

## 4. Tests Executed

| Test suite | Result |
|---|---|
| `pytest -q` (all backend tests) | **85 passed, 28 skipped** |
| Knowledge tests (filter: `test_knowledge.py`) | 20 passed, 2 skipped |
| Decision engine tests (filter: `test_decision_engine.py`) | 21 passed |
| Grooming knowledge load verification | Verified: lookup, retrieve, version all load correctly |
| Migration SQL verification | `upgrade --sql head` clean, `downgrade --sql 0003:0002` clean |
| Existing Hairstyle behavior | Unchanged — 85 tests pass, same as baseline |

### 28 skipped tests

These are DB-backed tests that require a reachable PostgreSQL instance. They skip cleanly with an explicit message — not faked. This is expected in this environment.

---

## 5. Verification Checklist

| # | Requirement | Status |
|---|---|---|
| 1 | Migration applies successfully | ✅ `alembic upgrade --sql head` clean |
| 2 | Migration can be reproduced cleanly | ✅ `alembic downgrade --sql 0003:0002` clean |
| 3 | Grooming run type exists | ✅ `('grooming', 'Grooming analysis')` in `run_types` |
| 4 | All four grooming seed rows exist | ✅ 4 rows in `looks` with `content_version = '1.1'` |
| 5 | Grooming vocabulary loads correctly | ✅ `CatalogKnowledgeSource` serves all 4 looks |
| 6 | Knowledge version is 1.1 | ✅ `catalog.KNOWLEDGE_VERSION = "1.1"` |
| 7 | Existing Hairstyle behavior remains unchanged | ✅ 85 passed, 28 skipped (same as baseline) |

---

## 6. Summary of Changes

### Created

- **`backend/alembic/versions/0003_grooming_knowledge.py`** — Alembic migration 0003
  - Adds `grooming` run type to existing `run_types` table
  - Seeds 4 grooming look rows into existing `looks` table with `content_version = '1.1'`
  - Downgrade removes only grooming entries

### Modified

- **`backend/app/data/catalog.py`**
  - Bumped `KNOWLEDGE_VERSION` from `"1.0"` to `"1.1"`
  - Added `GROOMING_LOOKS` (4 look entries mirroring hairstyle cardinality)
  - Added `GROOMING_VOCAB` (stable identifier mapping)
  - Added `_validate_grooming_entry()` validation function
  - Added `_to_grooming_recommendation()` DTO converter
  - Updated `CatalogKnowledgeSource` with `lookup_grooming_look()` and `retrieve_grooming_looks()` methods

### Untouched (per strict rules)

- Flutter code — no modifications
- Routing — no modifications
- Grooming screens — no modifications
- Grooming API — not implemented yet
- Grooming decision engine — not implemented yet
- Hairstyle behavior — no modifications
- New dependencies — none added

---

## 7. Validation Gate — Pass

All verification criteria met. The migration is deterministic and reproducible. The knowledge catalog is properly structured and validated. Existing hairstyle behavior is completely unchanged (85 tests pass, 28 DB-backed tests skip cleanly). No new tables were created; all changes reuse the existing Step 4–5 infrastructure.