# PHASE 1 STEP 2 — OWNER DECISIONS

> Status: DECISION DOCUMENT ONLY. No source modified, no tests written, no migration, no API change,
> no Flutter behavior change, no commit/push. Date (UTC): 2026-09-27.
> Sources: `PHASE_1_STEP2_AI_STYLIST_CONTRACTS.md`, `CURRENT_STATE.md`, `DECISIONS.md`, read-only code checks.
> C-01 and C-08 are reproduced LOCKED and were not re-opened.

## C-01 Guest/Auth
STATUS: LOCKED

Decision:
Keep current architecture:
- authenticated server-side AI surfaces remain authenticated
- guest AI uses the existing local-first guest flow
- pending intent is converted after authentication
- do not introduce anonymous server AI in this phase

No implementation required.

---

## C-02 Mood / Fit / Palette

Current behavior:
- values are request-scoped
- currently echoed into prose
- they do not currently affect ranking/filtering

### A. Keep as explanation-only context
- Runtime: unchanged — validated 1–200 free strings, echoed verbatim into `colorHarmony`/`bodyFit`/prose.
- Candidate generation: no effect (wardrobe + occasions only).
- Ranking: no effect (scoring signature takes occasions only).
- Database: none. Existing data: none stored, nothing invalid.
- Complexity: zero ( status quo).
- Risks: users may read echo as influence — needs honesty copy so prose never claims an effect.

### B. Make them deterministic recommendation constraints
- Runtime: mood/fit/palette become validated vocabulary with filter/score terms.
- Candidate generation: palette/fit could exclude candidates (hard filter).
- Ranking: new sub-terms with weights (weight-change stop condition fires — owner must also approve weights).
- Database: needs a vocab home (table or versioned backend config per K9.1 precedent); BLOCKER: fit needs
  item-fit data that DOES NOT EXIST (garment fit lost at save — see C-06); mood has no scoring data anywhere.
- Existing data: request-scoped only, nothing invalid; but past prose echoes become retroactively misleading.
- Complexity: high (vocab + sidecar dependency + engine terms + tests).
- Risks: largest blast radius; noisy/unsupported terms silently change recommendations; contradicts DEC-015/018
  AI-0 omission precedent unless explicitly superseded.

### C. Remove/drop the controls
- Runtime: pickers removed from builder; API ignores/422s the fields per deprecation call.
- Candidate generation / ranking: unchanged (they never affected either).
- Database: none. Existing data: none stored.
- Complexity: low-medium (UI removal + API field deprecation + client updates).
- Risks: removes user expression with no replacement; onboarding/builder copy churn.

### D. Relabel them as "vibe/style context" and keep them explanation-only
- Runtime: same data flow as A; only labels/copy change to "vibe" so no influence is implied.
- Candidate generation / ranking: no effect.
- Database: none. Existing data: none stored.
- Complexity: copy-only (P0-A-safe class).
- Risks: minimal; residual risk only if prose templates still imply causation (fix in copy review).

OWNER DECISION: B — LOCKED (owner-approved 2026-09-27)

Locked sub-contracts (Step 2.4; detail docs govern):
- C-02-P PALETTE = LOCKED as deterministic RANKING SIGNAL (not a hard filter). Monochrome = existing
  neutral set by reference; warm/cool = frozen subsets of the 17 `colors` codes (proposed sets +
  versioned weight: IMPLEMENTATION INPUT, OWNER APPROVAL REQUIRED). No migration, no new column,
  `_color_points` unchanged. Doc: `PHASE_1_STEP2_C02_P_PALETTE_CONTRACT.md`.
- C-02-F FIT = LOCKED as deterministic EVIDENCE-GATED RANKING SIGNAL (not a hard filter; mismatch never
  auto-removes). Evidence = `GarmentProfile.fit` + sidecar only, threshold confidence >= 0.6 LOCKED,
  missing/below = neutral; controlled request map proposed (`tailored` ruling OPEN) + deterministic
  weight: IMPLEMENTATION INPUT, OWNER APPROVAL REQUIRED. No column, no migration.
  Doc: `PHASE_1_STEP2_C02_F_FIT_CONTRACT.md`.
- C-02-M MOOD = LOCKED — CONTEXT/EXPLANATION ONLY (no backend mood data; style_type/occasions/FFO
  aesthetics/GarmentProfile.style explicitly NOT mood sources). Mood weight NOT APPLICABLE. Future
  ranking needs a separate contract. Doc: `PHASE_1_STEP2_C02_M_MOOD_CONTRACT.md`.
- Matrix + order (Palette → Fit → Mood): `PHASE_1_STEP2_C02_SUBCONTRACT_MATRIX.md` (all LOCKED).
- C-02 Budget Rebalance: OPTION A — LOCKED (owner-approved 2026-09-27). Approved future formula:
  Coverage 35, Color 5, Material 5, Season 5, Formality 5, Occasion 5, Palette 5, Fit 5 = 70.
  Global contract unchanged (0–70 / 0–15 / 0–15 = 0–100); caps, tie-break, hard constraints untouched.
  Detail: `PHASE_1_STEP2_C02_BUDGET_REBALANCE_PROPOSAL.md`.
- C-02-F Fit persistence: OPTION B — LOCKED (owner-approved 2026-09-27). Persist `fit` (nullable
  Text) + `fit_confidence` (nullable Float 0–1) as structured attributes on the existing
  `wardrobe_items` row (model `WardrobeItems`, `models.py:410`; table by `0006`; future slot `0023`
  NOT created). Fit +5, gate ≥ 0.6, no multiplier, missing/unknown = 0, tailored unsupported,
  no LLM, no filter — all re-confirmed. No backfill, no inference. Implementation dependencies:
  migration → model → write path → read path → scoring term → fit tests → regression.
  Detail: `PHASE_1_STEP2_C02_F_BLOCKER.md`.
- C-02-M Mood: CLOSED — CONTEXT/EXPLANATION ONLY (verified Step 2.12: mood reaches validation +
  prose echo only; zero scoring/filter/weight/taxonomy/LLM influence; no source change required).
- C-02 status: P + F shipped (Steps 2.8/2.11); M closed context-only (Step 2.12). Future mood
  ranking needs a separate contract. No further C-02 implementation pending.

Locked contract (concise):
1. Mood/fit/palette are genuine AI Stylist recommendation inputs, not prose-only values.
2. They enter the eventual UserContext/request-context (reuse existing; no parallel state) as
   normalized controlled values before engine use.
3. They influence recommendation behavior deterministically; ranking architecture stays intact
   (no engine replacement; sub-terms/weights, never LLM verdicts).
4. A dimension filters/ranks ONLY where repository data reliably supports it; unsupported dimensions
   degrade honestly (no fabricated properties, no hallucinated matches, no false "perfect match" claims).
5. AI-generated garment attributes are evidence, never truth; LLM output never decides fit/mood/palette
   satisfaction.
6. Initial semantics: PALETTE via deterministic color data (mapping documented, not arbitrary); FIT only
   where reliable fit data exists (never inferred from prose); MOOD as normalized vibe context, ranking
   only through an explicit deterministic repo-supported mapping.
7. Explanation reflects actual deterministic signals used — describes the decision, never invents it.
8. Implementation NOT started; weights, schema, APIs unchanged by this lock.

---

## C-03 preferred_item_ids

Current behavior:
- API mechanism exists
- resolver exists
- ranking supports a boost
- production callers currently send empty frozenset()
- mechanism is effectively inactive

### A. Preferred items = items the user explicitly wants included/considered
- AI Stylist behavior: request carries explicit wardrobe UUIDs; engine boosts (existing +5/cap-15 term)
  or constrains to them; response states which preferred items were used.
- Generation vs ranking: ranking boost (reuse as-is); inclusion-guarantee would ALSO touch candidate
  generation (new filter semantics).
- Persistence: none required (request-scoped); optional history via saved-look snapshots.
- UI: needs a picker (multi-select from owned wardrobe) on builder/generate surfaces.
- Reuse: resolver + ranking term reused verbatim; only the 3 `frozenset()` call-sites + API schema + client change.

### B. Preferred items = saved/favorited wardrobe items
- AI Stylist behavior: favorites auto-boost without explicit per-request selection.
- Generation vs ranking: ranking-only (favorites already scored separately — DOUBLE-COUNT risk must be resolved).
- Persistence: none new (favorites already stored).
- UI: none (implicit); explainability must disclose the favorites effect.
- Reuse: resolver exists but answers a different question (outfit-save-derived, not favorites) — needs
  redefinition, not just wiring.

### C. Preferred items = previously successful recommendation items
- AI Stylist behavior: past saved/liked look members boost future candidates (taste profile).
- Generation vs ranking: ranking-only boost; needs a success definition (save? like? wear? — see C-05).
- Persistence: derivable from existing `saved_looks` (resolver does exactly this today).
- UI: none; explanation should cite "similar to your saved looks" (ForYou precedent).
- Reuse: resolver reused VERBATIM — smallest change (wire call-sites only).

### D. Remove/deprecate the mechanism
- AI Stylist behavior: unchanged (mechanism already inactive).
- Generation vs ranking: no effect.
- Persistence: none. UI: none.
- Reuse: resolver/ranking code becomes dead — remove or mark deprecated with tests proving no live path.
- Note: kills options A–C permanently until reintroduced; cheapest if personalization stays count-based (DEC-019 §B).

OWNER DECISION: LOCKED — explicit user-selected preferred wardrobe items (owner-approved 2026-09-27;
contract: `PHASE_1_STEP3_C03_CONTRACT.md`). NOT favorites/saves/inference/palette/fit/mood/catalog-codes.
Rules: wardrobe UUIDs, UUID-canonicalized, deduped; owner-scoped only, foreign/nonexistent → 0 (degrade,
not 404); candidate +5/cap-15 and OI +0.05/cap-0.15 UNCHANGED; never a filter; generation/tie-break/budget
untouched. Double-count policy DEFERRED to C-05;
explanation wording deferred. Wire IMPLEMENTED 2026-09-27 (report:
`PHASE_1_STEP3_C03_IMPLEMENTATION_REPORT.md`): optional `preferredItemIds?: UUID[]` on #41 (absent/null/`[]` ≡
empty; malformed → 422; cap UNDECIDED — no length cap shipped, scoring caps bound effects; wears-10 vs
reasoning-20 precedents conflict, owner picks). Wired ONLY at `outfits.py` derive (primary); `events.py`/
`today.py`/`main.py` intentionally left empty (no explicit preference source). Call sites for later:
`outfits.py:392` (primary), `events.py:389`/`today.py:188`/`main.py:310` (scope decisions required).

Audit facts (2026-09-27): mechanism exists twice over (candidate +5/cap-15; OI +0.05/cap-0.15) over
wardrobe UUIDs from outfit saves; resolver tested but UNCALLED; ALL production call sites pass
empty (`outfits.py:392`, `events.py:389`, `today.py:188`, `main.py:310` omits the kwarg); Flutter
sends nothing; NO wire field; ZERO product language in `docs/`. Separate namespace warning:
`HairstylePreferences.preferredLookIds` = catalog codes +0.03 (not C-03).
Options: A explicit picks (API+UI, no scoring change) / B favorites-derived (needs anti-double-count
rule) / C wire resolver (3 call-sites, silent-shift caveat) / D remove. Unknowns U-1…U-5 recorded.
Fewest-changes = C (effort fact, NOT a selection). Do not activate preferred_item_ids.

---

## C-04 Scan → Generate

Current behavior:
- scan output shape is incompatible with outfit component shape
- there is currently no safe direct wiring

### A. DISPLAY CONTEXT
- Data flow: Scan snapshot → shown alongside builder/result as style context; generator input unchanged
  (owned wardrobe + occasions only).
- Source of truth: wardrobe rows (generation) + run snapshot (display); no cross-writes.
- Failure: scan failure degrades to no-context (builder works standalone, as today).
- Compatibility: full — no model changes; M7 validation untouched.
- Migrations: none.

### B. TRANSFORM
- Data flow: Scan snapshot → product-defined transform → wardrobe/outfit component candidates →
  ownership/validation → generation. ONLY valid transformed candidates enter.
- Source of truth: wardrobe rows remain authoritative; transform output is advisory until validated/persisted.
- Failure: transform miss (hairstyle-rec ≠ components) → fall back to A behavior; transform must never
  fabricate UUIDs (fail closed per #42: unknown → 404, malformed → 422).
- Compatibility: new mapping layer; M7 validation UNCHANGED (gate stays).
- Migrations: none for transform itself; persisting transformed rows uses existing wardrobe create path.

### C. RUN LINK
- Data flow: Scan creates analysis run → Generate request references `source_run_id` → generator derives
  independently; save embeds run link (extractor `saved_looks:182` exists).
- Source of truth: run snapshot (provenance) + wardrobe rows (generation); link is audit, not input.
- Failure: missing/unknown run id → ignored with logged warning, generation proceeds (link is optional).
- Compatibility: full — additive `source_run_id` field; M7 validation untouched.
- Migrations: none (snapshot JSONB already carries it).

### D. HYBRID
- Data flow: A (context display) + C (run linkage) now; B-grade transformed components admitted ONLY after
  passing the same validation as owned rows.
- Source of truth: wardrobe rows authoritative; scan is context + provenance.
- Failure: each layer degrades independently (context missing / link missing / transform miss → plain generation).
- Compatibility: full; no model bypass at any layer.
- Migrations: none.
- Note: highest complexity of the four, but each piece ships independently — no big-bang required.

OWNER DECISION: OPTION A (garment path) — LOCKED + IMPLEMENTED
(owner-approved 2026-09-27; audit:
`PHASE_1_STEP4_C04_SCAN_GENERATE_AUDIT.md`, report:
`PHASE_1_STEP4_C04_IMPLEMENTATION_REPORT.md`). Post-save "Build with this
item": saved wardrobe UUID → builder → existing C-03 `preferredItemIds`.
Unsaved/ephemeral generation explicitly OUT (needs its own contract).
Backend/ranking/vision/DB/C-02/C-03 untouched. (Options A–D above framed
appearance-scan and are superseded for the garment path only.)

---

## C-05 Feedback

Current behavior:
- save is already connected to look_saved + ForYou boost
- like/dislike are stored but largely not consumed
- wear ledger exists
- skip is absent
- share is currently a stub/no-op

### Like
#### A. Positive personalization signal
- Event: existing #35 reaction (no new event).
- Persistence: `feedback_events` (exists).
- Ranking: new positive term/weight (weight-change stop condition fires).
- Generation: none (ranking-only) unless scope says otherwise.
- Learning: counts as taste evidence (recents/personalization; score math stays count-based per DEC-019 §B unless superseded).
- Migration/API: none (M11 aggregation later is separate work).
#### B. Recommendation-only signal
- Same event/persistence as A; effect scoped to recommendation surfaces (For You / AI Stylist),
  never to profile/learning aggregates.
- Ranking: scoped boost; generation/learning: none. Migration/API: none.
#### C. Keep stored but do not consume yet
- No behavior change; events accumulate for future use. Zero risk, zero effect.

### Dislike
#### A. Negative personalization signal
- Event: existing #35 negative rating. Persistence: `feedback_events` (exists).
- Ranking: new negative term (first of its kind — semantics + magnitude need explicit approval).
- Generation: optional suppression filter (stronger than ranking; separate approval).
- Learning: negative taste evidence. Migration/API: none.
- Risk: highest — one accidental tap punishes future recs; needs undo/weight-decay policy (not designed).
#### B. Recommendation-only suppression
- Same event/persistence; effect = hide/suppress similar items on recommendation surfaces only.
- Ranking: suppression list, not a score term. Generation/learning: none. Migration/API: none.
#### C. Keep stored but do not consume yet
- No behavior change. Zero risk. (Current behavior.)

### Skip
#### A. Add explicit skip event
- Event: NEW (control + event definition required — closest-to-new surface in C-05).
- Persistence: new event type or `feedback_events` extension (schema decision at implementation).
- Ranking: neutral (position rotation) or weak-negative per owner call — NOT silently negative.
- Generation/learning: none until defined. Migration/API: likely (new event/endpoint or field).
#### B. Treat skip as neutral/no event
- No event, no persistence, no effect. Zero work; skips leave no trace.
#### C. Defer
- No control, no event. Revisit with learning/ledger work.

### Wear
#### A. Positive signal with recency weighting
- Event: existing wear ledger rows (needs UI first — no surface emits them today except WARDROBE-004 single-item).
- Persistence: `wardrobe_wear_events/groups` (exist).
- Ranking: new recency term (weight stop condition fires); generation: none.
- Learning: wear-as-taste (contradicts NOTHING yet, but DEC-012 save≠wear + DEC-019 wear-excluded-from-score
  must be explicitly scoped or superseded).
- Migration/API: none for ledger; UI work required to emit events.
#### B. History-only event
- Ledger rows persist; no ranking/generation/learning consumption. Truthful history, zero effect.
#### C. Defer
- No new capture surfaces; ledger stays dormant. (Current behavior.)

OWNER DECISION: LOCKED SEMANTICS (owner-approved 2026-09-27; contract:
`PHASE_1_STEP5_C05_FEEDBACK_CONTRACT.md`). Like = outfit-level positive
evidence; dislike = outfit-level negative evidence (no blacklist, decay
not implemented); skip = DOES NOT EXIST (no implementation; future
contract must define event/producer/persistence/dedup/scope/decay/
consumption); wear = behavioral evidence (wear ≠ save/like/favorite/
preferredItemIds; ledger canonical); share = dormant. ALL ranking weights
UNASSIGNED — 0–100 formula untouched. No C-03 derivation, no double
counting: preferredItemIds/favorites/saves/likes/dislikes/wear stay
independent. The per-action options above are superseded by this lock;
any weight/decay/Skip-contract work needs a separate implementation
contract.

---

## C-06 Garment AI Attributes

Current verified behavior:
Detected attributes include:
- category
- color
- material
- pattern
- style
- fit
- confidence

Only some currently survive as scored fields.

### A. Keep current 3 scored attributes (category + color + material)
- Storage: none (status quo). Ranking: unchanged. Explainability: unchanged (prefill chips as today).
- Migration: none. imageRef: stays write-mostly.
- Noise risk: zero (no new AI input consumed).

### B. Preserve all 7 attributes but initially use only the current 3 for ranking
- Storage: inside EXISTING `image_ref` JSONB verbatim (no new columns; write path already stores it).
- Ranking: unchanged (reads gated off). Explainability: richer prefill chips possible (display-only).
- Migration: none. imageRef: becomes the sidecar (read where useful).
- Noise risk: low — persisted but not scored; reads are display-only until C-06 scoring decision.

### C. Preserve and score category + color + material + pattern + style + fit
- Storage: sidecar (B) suffices for preservation; first-class columns NOT required to score.
- Ranking: three NEW sub-terms + weights (weight-change stop condition fires; needs pattern/style/fit
  vocabularies — none exist; AI-0 honesty applies to ungrounded attrs).
- Explainability: reasons must cite only grounded attrs (REC_API §4.5 precedent).
- Migration: none for sidecar reads; columns only if first-class chosen (STOP + approval).
- Noise risk: MEDIUM-HIGH — pattern/style/fit are the noisiest vision outputs; needs confidence gating
  (confidence attr exists but is itself currently lost — circular dependency, owner to resolve).

### D. Preserve all 7 and make scoring weights configurable/versioned
- Storage: sidecar + a weight-config home (versioned backend config per K9.1, or table).
- Ranking: same new terms as C, plus versioning/rollback machinery.
- Explainability: same grounding rule as C, plus version disclosure.
- Migration: config-table only if chosen (STOP + approval); else versioned config file.
- Noise risk: same as C, mitigated by tunability — at the cost of the heaviest implementation here.

OWNER DECISION: PENDING

Do not change ranking weights yet.

---

## C-07 item_added

Current verified behavior:
- no backend writers
- seed is absent according to current audit
- migration may be required depending on selected implementation

### Read-only seed/schema verification (performed this step, no writes)
- `backend/alembic/versions/0001_initial_schema.py:140-143` seeds exactly 2 codes: `look_saved`, `analysis_updated`.
- `0008_outfit_selected_signal_type.py:20-25` adds `outfit_selected`.
- `0015_assistant_card_signal_types.py:30-36` adds `suggestion_opened`, `assistant_navigation`.
- No other migration inserts into `signal_types` (repo-wide grep); total = exactly 5 seeded codes.
- `item_added` appears in `backend/app` ONLY as the `wardrobe.py:127` docstring ("Emits item_added" —
  aspirational, no insert call). FK `learning_signals.signal_type → signal_types.code` is RESTRICT, so an
  unseeded insert would 500 on flush.
- Corroborated by `test_db_session.py:65-78` (seed-presence test) and DEC-019 §G (DEFERRED gap).
- RESULT: **seed ABSENT confirmed — option A currently BLOCKED on a seed migration.**

### A. Emit item_added when a wardrobe garment is successfully persisted
- Payload (proposed, not implemented): `signal_type="item_added"`, label = item name (1–200, BC-12),
  context = `{wardrobe_item_id}` — M10 sole-writer rules apply (route via signal port at implementation).
- Writer location: `AddWardrobeItem` use case (`backend/app/application/wardrobe.py`) post-commit.
- Transaction boundary: separate sequential unit AFTER the item commit (TRX-7 precedent from DEC-015:
  item 201 stands even if the signal write fails — avoids failure-induced duplicates).
- Idempotency: wardrobe create is keyless (dup rows possible) — signal follows the row (no independent key
  proposed; retry-after-commit duplicates BOTH without a key — owner to accept or order keying).
- Seed/migration: REQUIRED — new migration inserting `('item_added', …)` (0008/0015 precedent verbatim) +
  downgrade; do NOT create yet.
### B. Keep item_added documentation-only and do not emit it
- No writer, no seed, no migration. Fix the ~20 doc references + `wardrobe.py:127` docstring to match code.
- Zero runtime risk; closes the doc-vs-code conflict honestly.
### C. Defer until learning/event-ledger implementation
- No decision on emit-vs-docfix now; `item_added` stays in the DEC-019 DEFERRED row with B as the interim
  truth (docs corrected or explicitly marked aspirational).

Do not create the migration yet.

OWNER DECISION: PENDING

---

## C-08 analysisCached/blob

STATUS: LOCKED

Verified meaning:
- analysisCached is a photo-taken/cached-photo state
- it is NOT the authoritative analysis result
- dead setter is deprecated
- no product decision required

No implementation.

---

## C-09 Style Profile

Current behavior:
- two writers
- wholesale replacement
- last-writer-wins behavior
- possible stale-write/concurrency problem

### A. Keep REPLACE semantics
- Conflict: last-writer-wins across outfit↔hairstyle-image; simultaneous submits lose one write silently.
- Stale clients: 422-gates keep accepting the latest stored face (stale-face accepted, documented).
- Database / API / migration: none. Client compat: full (current behavior).

### B. MERGE fields deterministically
- Conflict: per-key merge (e.g. newer `source_run_id` wins per field; explicit field rules frozen at implementation).
- Stale clients: partial staleness possible (mixed-generation profile) — merge rules must define coherence.
- Database: none (same 5-key JSONB shape). API: none (same read shape).
- Migration: none. Client compat: full reads; writers change merge fn only.
- Risk: mixed-vintage profiles ("face from run X, style from run Y") presented as one — needs coherence rule.

### C. Versioned compare-and-swap
- Conflict: concurrent writer loses with explicit conflict (409/412 class) instead of silent overwrite; client retries on fresh read.
- Stale clients: rejected on stale version (explicit, honest).
- Database: needs a version column/generation counter on `user_state` (migration STOP + approval).
- API: version echo on read + precondition on write (contract change).
- Migration: REQUIRED. Client compat: old clients break on versioned writes until updated (compat window needed).

### D. MERGE + version/CAS
- B merge rules + C optimistic concurrency: coherent merged writes that still conflict honestly.
- Stale clients: rejected, then re-merge on fresh read.
- Database / API / migration: same as C (version column + preconditions).
- Client compat: same compat window as C. Highest complexity here; only option that fixes BOTH loss and silence.

OWNER DECISION: PENDING

Do not modify the profile implementation yet.

---

## C-10 Analysis Idempotency

Current behavior:
- analysis requests are honestly non-idempotent
- saves/feedback/wears already have idempotency mechanisms

### A. No analysis idempotency for MVP
- Duplicates: every POST = new run + new provider cost (documented, accepted).
- Retry: user re-tap / network retry = second run (honest, visible in run history).
- Database/storage: none. Concurrency: independent runs, no interference.
- API: none (contract already declares never-idempotent submits).
- Migration: none. Complexity: zero. Risk: duplicate AI spend on flaky networks.

### B. Client-generated idempotency key
- Duplicates: same key + same payload → original run replayed; changed payload → 409 (C-12/API-33 precedent).
- Retry: same-key retry safe; new-key retry = second run (caller discipline, documented).
- Database: run-key UNIQUE per user (migration STOP + approval). Concurrency: same-key writers serialize.
- API: `Idempotency-Key` required/optional header on the 4 analysis POSTs (contract change).
- Migration: REQUIRED. Complexity: medium (save/feedback/wear precedent exists — copy the pattern).

### C. Server-generated request/run key
- Duplicates: server returns a submission receipt; client polls receipt → exactly one run materializes.
- Retry: receipt replay safe by construction; no client key discipline needed.
- Database: receipt/run-key store with TTL (new table or JSONB — migration decision at implementation).
- Concurrency: receipt creation serializes duplicates server-side.
- API: new request/receipt round-trip (largest contract change here).
- Migration: REQUIRED (likely). Complexity: high (new endpoint + lifecycle + expiry).

### D. Deterministic analysis identity based on photo/content hash
- Duplicates: identical bytes (+ same operation) → same identity → replay, no second provider call.
- Retry: inherently safe for identical retries; edited/cropped photo = new identity (correct).
- Database: content-hash UNIQUE per user+operation (migration STOP + approval); hash PII handling per privacy rules.
- Concurrency: same-hash writers serialize on the UNIQUE.
- API: no new headers (identity derived); contract documents replay-on-identical-bytes.
- Migration: REQUIRED. Complexity: medium-high (canonicalization rules: what counts as "same photo" across
  formats/sizes must be frozen, else replay is unpredictable).

### E. Separate idempotency strategy for each analysis operation
- Any per-operation mix of A–D (e.g. keyed garment submits, unkeyed appearance polls).
- Duplicates/retry/DB/concurrency/API/migration: per-operation sum of the chosen options.
- Complexity: highest to reason about; only justified if operations prove materially different cost/duplicate rates.
- Recommendation recorded here (not a decision): start uniform (A or B for all four); split only on measured pain.

OWNER DECISION: PENDING

---

# FINAL DECISION MATRIX

| Contract | Decision | Locked? | Migration? | API change? | Ranking impact? | Event impact? |
|---|---|---|---|---|---|---|
| C-01 | Keep gated architecture, no anon server AI | LOCKED | No | No | No | No |
| C-02 | PENDING | No | No (A/C/D); Yes-vocab if B | Only C (field deprecation) | Only if B (+weights approval) | No |
| C-03 | PENDING | No | No | Yes if A (request field) | Only if A/B/C wired | No |
| C-04 | PENDING | No | No (all options) | Additive field only if C/D | No | Run-link provenance if C/D |
| C-05 | PENDING (4 independent) | No | Only if Skip-A (new event) | Only if Skip-A | Only if Like-A/Dislike-A/Wear-A | Wear-A/Like-A/Dislike-A consume |
| C-06 | PENDING | No | No (sidecar); Yes only if first-class columns | No | Only if C/D (+weights approval) | No |
| C-07 | PENDING (A blocked on seed migration) | No | Yes only if A (seed row) | No | No | Yes if A (new signal) |
| C-08 | Photo-taken flag; blob non-authoritative, setter deprecated | LOCKED | No | No | No | No |
| C-09 | PENDING | No | Yes only if C/D (version column) | Only if C/D (preconditions) | No | No |
| C-10 | IMPLEMENTED (Option B — client-generated Idempotency-Key) | LOCKED | Yes (0025) | Yes (Idempotency-Key header) | No | No (run replay only) |

## IMPLEMENTATION ORDER

Do not implement yet.

Dependency-safe order based ONLY on the verified repository (no-migration → schema/event → ranking → learning/ledger → concurrency):

1. **C-04 Scan→Generate (A/C/D display+link layers)** — no migration, no ranking, no events; additive-only,
   each layer degrades independently; unblocks nothing else but risks nothing.
2. **C-02 option C/D/A (copy/controls)** — no migration, no ranking; settles what the builder promises
   BEFORE any term work references mood/fit/palette (C-03/C-06 depend on honest vocabulary).
3. **C-08 cleanup (dead-setter removal)** — already LOCKED, zero callers; no dependency either way, batch
   with any no-migration release.
4. **C-07 (seed migration if A, else docfix if B)** — schema/event work with zero ranking effect; the seed row
   (if ordered) must land BEFORE any writer emits (hard dependency for A); docfix path is dependency-free.
5. **C-06 sidecar reads (B, display-only)** — no migration; must precede C-06 scoring (C/D) and informs
   C-02-B feasibility (fit data availability).
6. **C-03 wiring (per chosen meaning)** — ranking-affecting; goes AFTER C-02 vocabulary settles (avoid building
   on prose fields) and AFTER C-05 scope decisions if taste-derived (option C needs success definition).
7. **C-05 consumers (Like/Dislike/Wear effects)** — learning/event-ledger affecting; after C-03 (shared ranking
   surface — order the boosts together or they stack blindly) and after M11 aggregation exists for raw reactions.
8. **C-06 scoring (C/D weights)** — ranking-affecting on noisiest inputs; last among scoring work so weight
   interactions are measured against the settled C-02/C-03/C-05 baseline, never simultaneously.
9. **C-09 (profile semantics)** — concurrency-affecting; after all readers/writers settle (C-04 links reference
   runs, not profile keys, so no inversion); version column (C/D) migrates a table every analysis touches.
10. **C-10 (analysis idempotency)** — concurrency/idempotency last: keying changes the write path of the same
    analysis writers C-09 governs; implementing keys before merge/CAS settles risks building replay on top of
    replace semantics that later change.

Why: each layer's tests assert deltas against the previous settled baseline; ranking-affecting work never
ships concurrently (weight interactions unmeasurable); schema work precedes its writers; concurrency
primitives land after the semantics they protect stop moving.

## STOP CONDITION

STOP after writing the decision document.

Do not:
- edit source code
- edit tests
- create migrations
- alter schemas
- alter APIs
- alter ranking
- alter event consumers
- commit
- push
