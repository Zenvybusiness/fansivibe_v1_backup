# Phase 1 Step 2A — AI Stylist Product-Contract Specification

> Status: SPECIFICATION ONLY. No source modified, no tests written, no migration, no API change, no commit/push.
> Date (UTC): 2026-09-27. Sources: `PHASE_1A_P0_CORRECTNESS_AND_CONTRACT_AUDIT.md` (§§1–20),
> `PHASE_1_STEP1_P0_IMPLEMENTATION_REPORT.md`, `CURRENT_STATE.md`, `DECISIONS.md`, current code (read-only spot-checks).
> Legend: FACT (cited) · PRODUCT DECISION (owner must choose — never chosen here) · PROPOSED (sketch only, post-approval) · UNKNOWN (labeled).

Pre-verification (this step): `git status --short` empty + `git diff --stat` empty (clean tree);
Step 1 intact spot-checked (`outfit_scan_client.dart:32,37,40` Map-safe error getter,
`grooming_client.dart:115,118` `is String` date guards, `local_storage.dart:98` `@Deprecated` setter,
`hairstyle_mock_data.dart:92` num-safe convention). Skills: `.agents/skills/` inspected —
no skill matches spec-doc authoring (all are code/test skills); none loaded.

---

## CONTRACT C-01 — GUEST / AUTH

STATUS: **LOCKED** (spec = current gated behavior + conversion flow; any relaxation needs D-01).

FACT — which surfaces are guest-available:
- Guests reach the AI Stylist tab (`/stylist` exactly) with no session token (DEC-GUEST-01, Accepted).
- Phase 1 guard: whole shell guest-safe except `/assistant` + `/reasoning` (blocked → `/entry`).
- Phase 2: every protected fetch skipped + button-level `promptGuestSignIn` — analysis submits,
  `POST /v1/outfits/generate`, saves, events, feedback, wear all gated. Zero 401s by design.
- Phase 2.1: guests get REAL local capability — wardrobe CRUD (`local-*` non-UUID ids, wear hidden
  by existing UUID gate), Discover Clothes over local wardrobe, local prefs, on-device style score.
  Server AI stays account-only: all analyses, generate, Today Look, Discover feeds, events, feedback, wear.

FACT — gated-operation behavior: point-of-action sign-in prompt with specific reason; no fake data,
no successful save claimed. Analysis screens gate pre-submit (Analyze button); Generate gates at button.

FACT — captured input / conversion (guest→auth implementation entry):
- Pending intent: `{action, route(path only), params(string-only), createdAt}`, single-use, 24h expiry.
- Return/resume is class-D (return-to-origin + guidance): the user explicitly replays the action —
  NEVER auto-POSTed, never faked (no replayable server payload exists).
- Migration moves wardrobe (server UUIDs, content-dedup, favorites via follow-up update) +
  `preferredOccasions` (additive/idempotent). NON-transferable, kept local: face, signals (M10 sole-writer),
  saved-look titles (no IDs), styleType, vibe, analysis blob.
- Logout preserves device data (established semantics); login flips `isGuestUser` via `AuthSession` only.

PROPOSED CONTRACT (locked):
- Guest transition: Capture (local/camera) → Analyze: AnalyzeMyStyle yields the honest local
  "photo ready" handoff (no analysis performed, no mock result) → server analyses blocked pre-submit →
  Sign in → user explicitly replays Save/Generate. Result before sign-in is LOCAL-ONLY; nothing is
  server-backed until authenticated; post-sign-in only wardrobe + preferredOccasions persist server-side.
- Anonymous server analysis is EXPLICITLY OUT: no-user rows violate every FK/owner scope; TRX-6/signals/runs
  are all user-keyed; no session-scoped run concept exists (Phase 1A §10).

PRODUCT DECISION REQUIRED (only to change behavior): D-01 — keep gates vs anonymous server runs
(per-feature costings in Phase 1A §10; anon-derive additionally needs an ownerless-wardrobe read model).

DEPENDENCIES: none (documentation of shipped behavior).
IMPLEMENTATION FILES: none (no code change; Step 2.1 = contract tests pinning gate matrices if ordered).
TEST PLAN: guest-matrix widget tests (gated surfaces render prompt, zero repo calls), conversion tests
(20/20 exist), logout/login isolation, replay-never-auto-POST assertion.

---

## CONTRACT C-02 — MOOD / FIT / COLOR PALETTE

STATUS: **LOCKED — OWNER APPROVED** (Option B, 2026-09-27; was PRODUCT DECISION REQUIRED).
Sub-contracts (all LOCKED Step 2.4, implementation NOT started):
- C-02-P Palette = ranking signal (`PHASE_1_STEP2_C02_P_PALETTE_CONTRACT.md`; warm/cool sets + weight pending).
- C-02-F Fit = evidence-gated ranking signal, threshold 0.6 (`PHASE_1_STEP2_C02_F_FIT_CONTRACT.md`; map + weight pending).
- C-02-M Mood = context/explanation-only, NOT a ranking signal (`PHASE_1_STEP2_C02_M_MOOD_CONTRACT.md`).
Matrix: `PHASE_1_STEP2_C02_SUBCONTRACT_MATRIX.md`.
FINAL C-02 contract (Step 2.7; C-02-P IMPLEMENTED Step 2.8; C-02-F IMPLEMENTED Step 2.11; C-02-M CLOSED Step 2.12): PALETTE deterministic +5 soft signal
(never filter); FIT deterministic +5 soft signal, gate conf ≥ 0.6, NO multiplier (never filter),
persistence OPTION B LOCKED (nullable `fit` + `fit_confidence` on `wardrobe_items`, slot `0023` not created);
MOOD 0 context/explanation-only; TAILORED unsupported; COMPATIBILITY 0–70
(35+5+5+5+5+5+5+5, Option A LOCKED); FULL SCORE 0–100 (caps/tie-break/hard constraints untouched).

FACT: originate as 16 fixed `BuilderOption` ids (5 occasion / 4 mood / 3 fit / 3 palette);
backend validates 1–200 free strings (NO vocab table); stored NOWHERE (request-scoped);
`POST /v1/outfits/generate` body → `_to_recommendation` PROSE ONLY (scoring signature takes occasions;
mood/fit/palette absent). Score NO · filter NO · explanation YES (verbatim echo displayed as if meaningful).
Persisted NO. Reaches engine as prose only.
Supporting precedent: DEC-015/DEC-018 freeze OMISSION of `selectedMood`/`selectedColorPalette`/`colorHex`
from event/today DTOs (AI-0 honesty: uncomputed fields absent, never fabricated).

PRODUCT DECISION REQUIRED — D-02, OPTIONS:
A. Real terms (palette→color-term map needs a palette↔color vocab call; fit→item-fit needs item-fit data
   that DOES NOT EXIST — garment fit lost at save → needs sidecar or I-unsupported; mood has NO data
   anywhere for scoring without a new taxonomy).
B. Drop controls.
C. Relabel as display-only "vibe" (copy-only, P0-A-safe).
CURRENT CODE: prose echo, zero ranking influence — do NOT present it as influence.
IMPACT: A changes ranking inputs (+ vocab/sidecar work); B removes UI; C is copy-only.

DEPENDENCIES: D-06 if option A touches garment attributes.
IMPLEMENTATION FILES (post-decision): builder pickers, `#41` schema/router, engine terms, prose templates.
TEST PLAN: unit (term maps/bounds), integration (request → ranked reasons assert REAL score delta, not HTTP 200),
negative (unknown palette string behavior per chosen option).

---

## CONTRACT C-03 — PREFERRED ITEM IDS

STATUS: **LOCKED + IMPLEMENTED** (explicit user-selected preferred wardrobe items, owner-approved 2026-09-27; implemented 2026-09-27).
Contract: `PHASE_1_STEP3_C03_CONTRACT.md` (audit: `PHASE_1_STEP3_C03_PREFERRED_ITEM_IDS_AUDIT.md`; implementation: `PHASE_1_STEP3_C03_IMPLEMENTATION_REPORT.md`).
Wire: optional `preferredItemIds?: UUID[]` on #41 (absent/null/`[]` ≡ empty baseline; malformed → 422; unknown/foreign → ignored to 0, never 404).
Ranking: existing +5/cap-15 soft term, OI +0.05/cap-0.15 independent; no filter/generation/tie-break/budget change.
Wired ONLY on the outfit generate path; events/today/assistant stay empty (no explicit source). No length cap (undecided — scoring caps bound effects).
Double-count → C-05; wording deferred.

FACT — full trace: Flutter sends NEVER (zero `preferredItemIds` refs in lib) → API exposes NO field
(no schema on #41/Today/Event) → resolver EXISTS (`resolve_preferred_item_ids`: wardrobe-ID frozenset
from outfit saves, unit-tested incl. failure-degrade) → ranking SUPPORTS (`score_outfit_candidate`,
+5/cap-15, tested) → production callers pass literal `frozenset()` ×3 (outfits:392, events:389, today:188);
assistant engine accepts it but `main.py:310` passes only `preferred_occasions` — BOTH live paths unwired.
Tests cover mechanism, never liveness.

PRODUCT DECISION REQUIRED — D-03 meaning, OPTIONS:
A. Explicit-request ids (request-field, NEW-ish).
B. Favorites-derived (already scored separately — double-count risk).
C. Hard constraints (filter semantics, NEW).
D. Saved-taste boost (wire existing resolver — recommended READING, still owner call).
CURRENT CODE: dead mechanism, zero recommendation effect.
IMPACT: each option changes different files (API schema vs resolver call-site vs filter stage) and
double-count/override semantics; weights MUST NOT change silently (stop condition).

DEPENDENCIES: D-05 if feedback-derived (no).
IMPLEMENTATION FILES (post-decision): per option — schema/router/client/derive call-sites (3 frozenset sites).
TEST PLAN: unit (resolver/meaning mapping), integration (request ids → actual ranked-order delta asserted),
negative (unknown/foreign ids → 404/422 per existing validation, never stored).

---

## CONTRACT C-04 — SCAN → GENERATE

STATUS: **OPTION A IMPLEMENTED** (post-save "Build with this item",
2026-09-27; audit: `PHASE_1_STEP4_C04_SCAN_GENERATE_AUDIT.md`; report:
`PHASE_1_STEP4_C04_IMPLEMENTATION_REPORT.md`).
Garment save → wardrobe UUID → builder (`preferredItemId` extra) →
generation `preferredItemIds: [uuid]` (existing C-03 field) → regenerate
preserves. Ephemeral/unsaved generation NOT implemented (needs its own
contract). Backend/ranking/vision/DB untouched; C-02/C-03 untouched.
NOTE: the Step-2 D-04 A–D below framed the appearance-scan namespace and
stay as recorded; the implemented garment path is additive, not a
selection among them.

STATUS (Step-2 framing): **PRODUCT DECISION REQUIRED** (D-04).

FACT: Scan output = appearance/hairstyle snapshot (`recommend_hairstyle`, face_shape-only vision;
skin/body/style `""` by design) — it is NOT garment data. Generate reads wardrobe rows ONLY; Scan
produces NO wardrobe rows today. M7 outfit validation REQUIRES `components[]` with owned UUIDs —
scan output FAILS `#42` validation by shape. DIRECTLY REUSABLE: snapshot JSON as display context;
`run_id` as `source_run_id` (extractor `saved_looks:182` exists); `outfit-N` seeds for variety;
wardrobe confirm-save via #42. NOT COMPATIBLE: hairstyle-rec ≠ outfit components (needs a
product-defined transform). PARTIAL: face_shape → occasion/style bias (no term exists — needs weight call).

PRODUCT DECISION REQUIRED — D-04 shape, OPTIONS:
A. Display-context only (snapshot shown alongside builder; no data flow into generator).
B. Component-transform (product-defined mapping scan→wardrobe/components — heaviest, validation risk).
C. Run-link (source_run_id provenance on saves; display + audit, no ranking effect).
CURRENT CODE: zero Scan↔Generate wiring.
IMPACT: A = UI-only; B = new mapping + validation surface; C = provenance-only.

DEPENDENCIES: none for A/C; B depends on D-02/D-06 vocabulary.
IMPLEMENTATION FILES (post-decision): A — builder/result screens; B — transform + #42 path + engine;
C — save snapshot wiring.
TEST PLAN: A — context-forward render tests; B — transform unit + validation negative (UUID/ownership);
C — provenance round-trip save→list.

---

## CONTRACT C-05 — FEEDBACK

STATUS: **LOCKED SEMANTICS** (owner-approved 2026-09-27; contract:
`PHASE_1_STEP5_C05_FEEDBACK_CONTRACT.md`; audit:
`PHASE_1_STEP5_C05_FEEDBACK_AUDIT.md`). Like = outfit-level positive
evidence; dislike = outfit-level negative evidence; skip = not
implemented; wear = behavioral evidence; share = dormant. ALL weights
UNASSIGNED; 0–100 formula untouched; no C-03 derivation, no double
counting. Save stays the only feedback with live effect. Any weight,
decay, Skip-contract, or wear-scoring work needs a separate contract.

FACT (code meaning today):
| Action | Stored where | Affects recs? | Affects personalization? |
|---|---|---|---|
| LIKE | `feedback_events{rating,reason?}` via #35 | NO (zero consumers) | NO |
| DISLIKE | same table, negative rating | NO — dislike ≠ negative preference anywhere (NOT ESTABLISHED) | NO |
| SAVE | `saved_looks` + `look_saved` signal (TRX-3) | YES — sole reaction with effect: ForYou +0.03 boost; counts feed score formula | YES (strongest input, DEC-019 §G) |
| WEAR | wear ledger/groups | NO (no UI → no rows) | NO (`worn` excluded, DEC-012) |
| SKIP | NOT FOUND (no control/field) | n/a | n/a |
| SHARE | stubs/no-ops | NO | NO |

LOCKED precedents (use, don't relitigate): DEC-019 §B score inputs = wardrobe/saved COUNTS only
(feedback/reactions never score math); §G assistant/card feedback = evidence/recents only, never score;
§E recents expose typed labels only, never raw text; DEC-012 save≠wear; M11 `feedback_events` gated,
aggregation-only when built.

PRODUCT DECISION REQUIRED — D-05, OPTIONS per open item:
- Dislike: historical-only (current) vs negative-preference boost (needs semantics + scope: For You only? AI Stylist too?).
- Skip: needs a NEW control + storage (closest to new); implicit-negative vs neutral.
- Wear: needs UI first (DEC-012 capture surface exists only on WARDROBE-004 single-item); recency effect undefined.
- Scope per action: For You vs AI Stylist vs history-only.
CURRENT CODE: reactions stored, (almost) nothing consumed.
IMPACT: any consumer changes ranking/personalization inputs — weight-change stop condition applies.

DEPENDENCIES: none to document; consumers depend on D-03/D-06 weight calls.
IMPLEMENTATION FILES (post-decision): `saved_looks_screen` reactions, `#35`/M11, ForYou/engine consumers.
TEST PLAN: unit (semantics mapping), integration (reaction → next-recommendation delta asserted),
negative (duplicate reaction idempotency: keyed replay → original/409), auth (guest reactions gated).

---

## CONTRACT C-06 — GARMENT ATTRIBUTES

STATUS: **PRODUCT DECISION REQUIRED** (D-06: which attrs may influence ranking + weights).

FACT — journey: 7 AI attrs → strict typed result → review prefill (type/color/texture exact-match) →
user confirm → 3 survive as scored fields (category/color/material + name); pattern/style/fit/confidence
LOST as first-class wardrobe fields (no columns). `imageRef` JSONB + `sourceRunId` STORED, UNUSED.
Minimum safe path (NO new table): persist the subset inside the EXISTING `image_ref` JSONB verbatim
(already stored) and READ it where useful (richer prefill chips; generator side-terms).

PROPOSED CONTRACT (compatible, post-D-06 only): imageRef stays the sidecar; first-class columns are
genuinely new → migration STOP + approval required (table/columns/indexes/FKs/backfill/rollback/test plan).
Do NOT wire any attr into scoring blindly (weight-change stop condition).

PRODUCT DECISION REQUIRED: which of pattern/style/fit/confidence may influence ranking, with what weights.
CURRENT CODE: write-mostly sidecar, zero ranking reads.
IMPACT: reads without weights = display-only (safe); reads with weights = engine change (owner call).

DEPENDENCIES: D-02 option A (fit terms need item-fit data — this contract is the candidate source).
IMPLEMENTATION FILES (post-decision): garment prefill/save (`_buildImageRef`), wardrobe router:179, engine side-terms.
TEST PLAN: unit (sidecar round-trip), integration (attr → prefill/generator input asserted), migration plan if columns.

---

## CONTRACT C-07 — item_added

STATUS: **BLOCKED** (seed verification first; then owner call).

FACT: backend writers NONE (5 `insert_look_saved` sites emit only `look_saved`; sole backend hit is
`wardrobe.py:127` docstring "Emits item_added" — ASPIRATIONAL vs code). Seed NOT in `signal_types`
(DEC-019 §G: `item_added`/`style_updated`/`occasion_preferred`/`assistant_message` = doc-only, NO until
seeded, DEFERRED gap; FK RESTRICT means unseeded inserts 500 on flush). Flutter: local-only
`LearningService` record + test (device truth, never synced). ~20 doc references claim backend behavior
that does not exist.

REQUIRED (in order): 1. read-only seed check of the `signal_types` seed file (technical prerequisite).
2. If no seed: document BLOCKER (this contract), do NOT invent a seed migration without explicit approval.
3. Owner call: emit (needs seed row + writer wiring) vs docfix (correct ~20 refs + docstring).
CURRENT CODE: no emission; local-only device record.
UNKNOWN/BLOCKER: seed-file contents (verify at Step 2.7; DEC-019 says absent — re-confirm against seed file).

DEPENDENCIES: D-07 seed check → owner call.
IMPLEMENTATION FILES: none until unblocked (then: seed migration proposal + `AddWardrobeItem` writer OR docs).
TEST PLAN (post-unblock): seed-guard unit test, writer integration (add → signal row asserted), FK-negative test.

---

## CONTRACT C-08 — analysisCached / analysisResult

STATUS: **LOCKED** (document as-is; Step 1 completed the safe scope).

FACT: `analysisCached` flag writer = `your_analysis_screen:82` on guest Continue-without-account —
where NO analysis ran: flag means "photo captured locally", NOT "analyzed" (semantic drift, documented
in Step 1 via code docs). Blob setter (`local_storage:86-93`) has ZERO callers (now `@Deprecated`,
Step 1; zero warnings). Readers: profile DNA (null-safe → pending), home first-time `_hasScannedOutfit`,
diagnostics map, UserSession mirror. Flag is permanent once set, survives logout (logout preserves device
data — established). Authed flows consume DISPLAY GATING only, never content. Migration ignores both.

PROPOSED CONTRACT (locked): flag = photo-captured-locally, never analysis proof; blob = non-source-of-truth;
authoritative analysis state lives server-side (runs + `style_profile`); dead setter removal = later
zero-caller cleanup (no behavior change); NO second source of truth created.
No product decision: Step 1 verified no user-facing copy surfaced needing owner words.

DEPENDENCIES: none. IMPLEMENTATION FILES: none (Step 1 done; setter removal optional cleanup).
TEST PLAN: existing pending-state/gating tests stand; removal PR (if ordered) needs neighbor-suite rerun.

---

## CONTRACT C-09 — STYLE PROFILE

STATUS: **PRODUCT DECISION REQUIRED** (D-09).

FACT: exactly 2 writers, both wholesale REPLACE via `repositories:204-233` — `analysis.py:308`
(CreateOutfitRun) + `:497` (CreateHairstyleImageRun) — 5 keys
`{face_shape,skin_tone,body_type,style_type,source_run_id}`; sibling keys DROPPED. Non-writers verified:
garment, grooming, profile-only hairstyle (reads), `UpdatePreferences` (prefs `||` merge only),
wardrobe/saves/events. Race: last-writer-wins outfit↔hairstyle-image, no version/CAS (narrow but REAL).
Consumers (hairstyle/grooming 422-gates) silently accept stale face.

PRODUCT DECISION REQUIRED — D-09, OPTIONS:
A. REPLACE (current; document + accept last-writer-wins + stale-face).
B. MERGE (per-key merge semantics — needs field-level rules).
C. Concurrency posture: single-active-user assumption (current, document) vs CAS/versioning (redesign).
CURRENT CODE: wholesale replace, silent stale-face acceptance.
IMPACT: B/C touch TRX-6 writers + all readers; CAS = genuinely new (do NOT redesign unless required).

DEPENDENCIES: D-04 (Scan writes profile via CreateOutfitRun — shape decision interacts).
IMPLEMENTATION FILES (post-decision): `analysis.py` writers, `repositories:204-233`, 422-gate consumers.
TEST PLAN: unit (merge/replace matrix), integration (outfit→hairstyle sequence asserts surviving keys),
concurrency (dual-submit → documented winner, no corruption), negative (stale-face gate behavior per decision).

---

## CONTRACT C-10 — ANALYSIS IDEMPOTENCY

STATUS: **PRODUCT DECISION REQUIRED** (D-10).

FACT — which POSTs are non-idempotent: all 4 analysis submits (new run per POST; manual re-tap → NEW run;
double AI/provider cost risk). Keyed (safe): saves, #35 feedback, wears (UQ(user,key), replay→original,
clash→409; new-key retry = 2nd row — caller discipline). Keyless (dup-row risk): wardrobe create/update,
events CRUD. Register PARTIAL (key, no UQ — frozen race window). Migration YES (ledger + dedup).
Retry behavior: client polls/loops retry READS safely; only user re-tap re-POSTs (all submit paths have
double-tap guards — Step 1 verified — but network-retry duplicates on keyless POSTs remain).

PRODUCT DECISION REQUIRED — D-10: is duplicate AI/provider cost acceptable now, or is keying required
now vs later? (Keying runs = product + schema call — P0-C, do NOT implement keys merely because useful.)
CURRENT CODE: analyses honestly non-idempotent per `FANSIVIBE_API_CONTRACT_V1.md` (202-`{run_id}` never-idempotent).
IMPACT: keys need schema (run-key UQ), router, client, and replay-vs-new semantics.

DEPENDENCIES: D-09 (replay + replace interaction).
IMPLEMENTATION FILES (post-decision): analysis routers/schemas, run tables (migration proposal + STOP),
all 4 clients' submit paths.
TEST PLAN: idempotency matrix (duplicate POST → same run / second run per decision), retry storms,
concurrent same-key submits, cost accounting (provider-call count asserted, not just HTTP 200).

---

## Implementation readiness (per-contract gate for Steps 2.1–2.10)

| Contract | Status | May implement (Step 2.x) when |
|---|---|---|
| C-01 | LOCKED | Anytime as documentation/tests; behavior change needs D-01 |
| C-02 | LOCKED (B, owner-approved) | Owner picked B; implementation pending |
| C-03 | PRODUCT DECISION REQUIRED | Owner picks meaning; weights frozen otherwise |
| C-04 | PRODUCT DECISION REQUIRED | Owner picks A/B/C |
| C-05 | PRODUCT DECISION REQUIRED | Owner picks semantics + scope per action |
| C-06 | PRODUCT DECISION REQUIRED | Owner picks attrs + weights (display-only reads need no weights) |
| C-07 | BLOCKED | Seed-file check → owner emit-vs-docfix |
| C-08 | LOCKED | Done (Step 1); setter removal = optional cleanup |
| C-09 | PRODUCT DECISION REQUIRED | Owner picks REPLACE/MERGE + concurrency posture |
| C-10 | PRODUCT DECISION REQUIRED | Owner accepts cost or orders keying (schema STOP first) |

STOP CONDITIONS (unchanged): missing product decision · contradiction with DECISIONS.md · migration
necessary · unknown provider behavior · ambiguous auth · weight/profile-semantic changes · unrelated
regression · out-of-scope file needed · architecture incapable. Report blocker, invent nothing.

Database rule: every contract above is implementable on existing columns/JSONB/event tables except
C-07-emit (seed row), C-06-columns (only if first-class chosen), C-09-CAS (only if versioning chosen),
C-10-keying (run-key UQ). Each triggers the migration STOP + approval report before any DDL.
