# C-02-P PALETTE — Proposed Contract (NOT implemented)

> Status: OWNER DECISION: PENDING. Documentation + repository analysis only. No taxonomy created,
> no mapping created, no code/schema/API/ranking change. Date (UTC): 2026-09-27.

## Verified existing facts (read-only)
- Color vocabulary: `colors` table, 17 FK-guarded codes seeded by `0005_wardrobe_reference_tables.py:45-63`:
  `black, white, navy, charcoal, grey, beige, burgundy, olive, khaki, cream, light_blue, blush,
  tan, silver, gold, indigo, stone` (17 codes).
- `color_id` representation: `WardrobeItems.color_id` FK → `colors.code` RESTRICT (`models.py:427`);
  user-confirmed at save (422 on unknown); surfaced as `record.color` in `_to_recommendation`
  (`application/outfits.py:203`) and as member `color` in `_candidate_members`
  (`analysis_rules.py:1486-1514`, unknown → None → neutral, nothing fabricated).
- `_color_points` logic (`analysis_rules.py:1522-1536`, +10/−10/0): pairwise gate over an EXISTING
  neutral set `_NEUTRAL_COLOR_CODES = {black, white, charcoal, grey}` (`:866-874`); <2 known colors
  → neutral 0. No hue-family/analogous rules exist and none are invented.
- Garment color storage: first-class `color_id` per item; sidecar `image_ref` JSONB passthrough
  (`routers/wardrobe.py:62,168-179`).
- Candidate color representation: member color-code strings from `items_by_id` (codes, never labels).
- Palette constants/mappings in backend: NONE — `monochrome`/`warm`/`cool` appear only in Flutter
  (`outfit_builder_mock_data.dart:98-117`, descriptions name member colors informally).

## Proposed deterministic mapping (smallest, from existing data — NOT created)
- `monochrome` = `{black, white, charcoal, grey}` — equals the existing `_NEUTRAL_COLOR_CODES`; strongest
  grounding, no invention.
- `warm` / `cool` sets: NO repo constant exists; sets must be frozen by owner as subsets of the 17 codes
  (candidate reading from Flutter descriptions: warm ⊂ earth/cream family, cool ⊂ blue/grey family —
  NOT selected here).

## Contract answers
1. Selectable values: `monochrome`, `warm`, `cool` (existing Flutter ids; backend normalizes to these,
   unknown → 422 per taxonomy pattern).
2. Color IDs per palette: monochrome fixed above; warm/cool PENDING owner freeze (subsets of the 17).
3. Hard constraint or ranking signal: PROPOSED ranking signal (new sub-term beside `_occasion_points`),
   NOT a hard filter — hard filtering risks empty candidates (204) on sparse wardrobes and expands the
   frozen hard-constraint set (tops+bottoms+skeletons) without approval.
4. Garment with no usable color: member contributes nothing to the palette term (existing unknown-neutral
   convention); never assumed into/out of the palette.
5. Palette with no matching colors: term scores neutral 0 for every candidate (existing
   `_occasion_points`-style neutral default); recommendation still returns best occasion candidate.
6. Confidence: persisted `color_id` is user-confirmed data — no AI confidence applies. Vision-extracted
   color evidence (sidecar only) is OUT OF SCOPE until the C-06 gate lands.
7. Explanation provenance: term records intersected member `color_id`s per winner; `color_harmony` prose
   cites those actual codes (pattern already exists at `outfits.py:250-255`) — never the palette name alone.
8. Migration: NO (codes, columns, vocab all exist).
9. API change: NO (request fields exist; values constrain to 3 known ids).
10. New ranking weights: YES — one sub-term + weight, owner-approved (weight stop condition stands).

OWNER DECISION: C-02-P = LOCKED (owner-approved 2026-09-27)

Locked contract:
1. Palette is a deterministic RANKING SIGNAL (not a hard candidate filter — a hard filter could
   zero-result sparse wardrobes).
2. Monochrome = repository neutral set exactly (`_NEUTRAL_COLOR_CODES` = {black, white, charcoal, grey},
   `analysis_rules.py:866`); no new neutral taxonomy.
3. Warm / Cool = explicitly frozen subsets of the 17 existing `colors` codes (proposed below; freeze
   required before implementation).
4. Missing/unknown garment color → palette contribution neutral; never fabricate a color.
5. Deterministic; LLM output never decides palette membership.
6. Requires an explicit versioned weight (see Weight contract below).
7. No migration, no new column; existing `_color_points` behavior unchanged unless implementation
   explicitly requires it.

### PALETTE COLOR SET FREEZE — IMPLEMENTATION INPUT, OWNER APPROVAL REQUIRED (not implemented)
Base: the 17 codes in `0005_wardrobe_reference_tables.py:45-63`. No ID invented; DB unchanged.
- Monochrome (FROZEN by reference): {black, white, charcoal, grey}.
- Warm (PROPOSED): {beige, burgundy, olive, khaki, cream, tan, gold} — earth/cream/warm-metallic reading
  of the Flutter "Browns, creams, and earth tones" description, restricted to existing codes.
- Cool (PROPOSED): {navy, light_blue, indigo, silver} — blue/grey/cool-neutral reading of "Blues, greys,
  and cool neutrals" (grey itself stays in monochrome; sets kept disjoint for determinism).
- Unassigned (PROPOSED neutral): {blush, stone} — match no palette; contribution neutral, never forced.
  Owner may reassign or leave unassigned.

### WEIGHT CONTRACT
Palette weight: +5 — LOCKED (versioned sub-term beside `_occasion_points`; budget Option A).
Palette mapping version MUST be recorded during implementation (version pin + snapshot provenance).
No existing ranking code modified by this lock.
