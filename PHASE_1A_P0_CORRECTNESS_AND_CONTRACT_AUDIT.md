# Phase 1A — P0 Correctness + Product-Contract Audit (INVESTIGATION ONLY)

> Status: INVESTIGATION COMPLETE. Nothing implemented. No source modified, no tests written, no commit/push.
> Date (UTC): 2026-09-27. Baseline: Phase 0 frozen. Source = current code. Prior docs D0–D5 + DECISIONS.md:893-905,1040 reused as leads, re-verified.
> Legend: FACT (cited) · PRODUCT DECISION (owner must choose — never chosen here) · PROPOSED (sketch only) · UNKNOWN (labeled).

---

# 1 Executive Summary

P0-safe without product calls: harden ~10 Flutter cast sites (2 crashing today: outfit `as double` ×2 + `error as String?`; strict models that throw into handled paths elsewhere), unify poll 404/401 handling toward the garment precedent (stop on 404; outfit retries 404 to exhaustion), correct or emit `item_added` (DECISIONS already marks it aspirational; seed presence unverified — check `signal_types` seed before emitting), fix `LocalStorage` semantic drift (`analysisCached` = photo-taken, not analyzed; blob setter dead). Everything taste-related (guest-anon, mood/fit/palette, preferred_ids meaning, scan→generate shape, feedback semantics, garment sidecar) is PRODUCT DECISION — evidence + options below, no selections made. Idempotency: saves/feedback/wears keyed (safe); analyses/wardrobe/events unkeyed (double-charge/double-row risk documented, retry behavior per surface).

# 2 P0 Correctness Findings (index; detail §§3–9)

P0-A (crash/honesty): A1-01 outfit `confidence as double` · A1-02 outfit `matchScore as double` · A1-03 outfit `error as String?` · A1-04 grooming `created_at as String` · A1-05 `e as String` reason maps (hairstyle+outfit) · A1-06 strict `OutfitRecommendation.fromJson` (safe via caller catch, but any new caller inherits throw) · A2-01 outfit poll retries 404 to exhaustion · A6-01 `analysisCached` semantic drift + dead blob setter.
P0-B (needs owner call before touch): guest-anon, mood/fit/palette, preferred_ids meaning, scan→generate, feedback, garment sidecar, `item_added` emit-vs-docfix (seed check first).
P0-C (do NOT touch yet): engine weights, profile merge semantics, any new table/API/provider, reasoning prompts, migration logic.

# 3 Parser Findings (A1 — exact implementation list)

Conventions in repo (best→worst): garment strict-throw+caller-catch (BEST) · `as X? ?? default` + tryParse (hairstyle/grooming runs — GOOD) · `(as num? ?? 0).toDouble()` (hairstyle rec — GOOD) · raw `as` with caller try/catch (outfit-client decode, builder — SAFE-BY-CALLER) · raw `as` in build() with NO catch (outfit screen — CRASHES).

| ID | File:line | Cast | Backend shape | Failure | Affected flow | Tests | Missing |
|---|---|---|---|---|---|---|---|
| A1-01 | outfit_analysis_screen:33 `(??0.0) as double` | int confidence (JSON number) → TypeError in build | HairstyleResult snapshot (float normally; int legal JSON) | red screen | SCAN-003 render | fixture-render only | int-confidence widget test |
| A1-02 | same:251 matchScore | same | same | red screen | rec card | same | same |
| A1-03 | outfit_scan_client:23 `error as String?` | Map error `{code,message,details}` (ALWAYS Map on failed runs) → TypeError when read | failed-run envelope | crash on failed-detail read | processing→failed path | none (isFailed w/o error read) | Map-error test |
| A1-04 | grooming_client:113,117 `as String` (non-null) | null-safe by `!=null` guard BUT non-string (int) → throw | ISO strings (normal) | crash inside get-call catch → null (fail-safe: outer try) | grooming poll | none | non-string date test |
| A1-05 | hairstyle_mock_data:94, outfit_models:118 `e as String` | non-string reason element → throw | string lists (normal) | throw into caller catch (hairstyle: handled? verify at impl — service maps; outfit client catches malformed-200) | rec reasons | happy-path only | mixed-type test |
| A1-06 | outfit_models:51-56,112-127 non-null `as String/List` + `(as num)` | ANY null/missing → throw | contract-stable 200 (normal) | caught → `OutfitResult.failure` (SAFE today) | builder rec | api-mapping tests | contract-drift test (missing-field) |
| A1-07 | garment_models (strict-throw + caller FormatException catch) | — | — | SAFE (reference pattern) | wardrobe suggest | 5 parse tests | none |
| A1-08 | `jsonDecode() as Map` all clients (submit+get) | top-level array/string → throw | dicts (normal) | caught → null/failure (SAFE) | all submits/polls | 422→null etc. | non-dict body test (1 per client) |
| A1-09 | `run_id as String?` all submits | int → throw→null | UUID strings | silent null → upload-fail copy (SAFE but vague) | all submits | 202→id | int-id test |
| A1-10 | processing:103 `data?['result'] as Map?` | non-map result → throw inside setState-free zone? (in async handler → caught? `_pollRunStatus` try/catch → 'Polling error' — SAFE) | dict\|null | honest poll-error | SCAN-002 | none | non-map-result test |
| A1-11 | profile_screen:309-329 blob `as Map?` chains | null-safe (`?` + pending fallback) | blob (never written!) | SAFE (always pending path) | profile DNA | pending-state tests | writer-or-remove decision (A6) |
| A1-12 | today/outfit `DateTime.tryParse(as String? ?? '')` | null-safe | ISO\|null | SAFE | saves/history | — | none |

Implementation list (for later): num-safe confidence/matchScore (`(as num? ?? 0).toDouble()`), Map-safe error getter (mirror `GarmentAnalysisRun.failureReason`), String-safe grooming dates, String-safe reason maps (`.toString()` vs throw — PRODUCT-adjacent: throw preserves honesty, toString preserves render; owner call if behavior change is feared, else safe), missing-field contract tests per model, non-dict-body tests per client. NO behavior change except crash→honest-error.

# 4 Polling Findings (A2 — 6 flows)

| Flow | Where | Interval | Attempts | Timeout(req) | 401 | 404 | 5xx/malformed | Failed | Completed | Net-exc |
|---|---|---|---|---|---|---|---|---|---|---|
| Outfit scan | processing screen Timer | 3s ×2^ cap 48s | 30 | 30s | →/entry + snackbar | RETRIED to timeout (INCONSISTENT) | retried/`Polling error` | inline+Back | auto-push + View Results dup | hint copy |
| Garment | client loop | 1s fixed | 30 | 30s | bare code→null→`taking longer` (vague, no redirect — INCONSISTENT) | STOPS→null (PRECEDENT) | null | typed copy+retry | returns run | hint |
| Hairstyle | client loop (+service multi-angle ×3 sequential + vote) | 600ms | 30 | 30s | noteStatus(clears) → null | null→null (STOPS — verify at impl: get→null on non-200) | null | mapped `_describeError` + mock fallback (mock path — flagged D1) | returns run | debugPrint |
| Grooming | client loop | 600ms | 30 | 12s (NOTE: vision N/A here — profile/rules path, fast; OK) | same as hairstyle | same | same | service flags | returns run | debugPrint |
| AnalyzeMyStyle | photo_capture→FaceProcessing (hairstyle path) | 600ms ×3 angles | 30×3 | 30s | GuestSignInCard pre-gate | same | same | honest error screen (post-fix) | result | — |
| Builder/Today/Event | NO polling (single derive) | — | — | 12s | typed failure | n/a | typed failure | honest error+retry | render | typed failure |

Inconsistencies (fix later, no product call): outfit-404-retry vs garment/hairstyle-stop; outfit-401-redirect vs garment-vague-null; outfit exp-backoff vs fixed loops (both fine; document, don't unify blindly); grooming 12s vs 30s family (justified: no vision — keep, document); mock fallback ONLY in hairstyle service (flagged, owner-aware). Missing tests: backoff/timeout/401/429/failed-forward per flow (garment has 5 transport tests — template).

# 5 Idempotency Findings (A3)

| Write | Idempotent? | Key | Server protection | Client retry | Dup risk |
|---|---|---|---|---|---|
| Analysis submit (all 4) | NO | none | none (new run per POST) | manual re-tap → NEW run | double-charge runs (documented; P0-C: keying runs = product+schema call) |
| Save look (M7 direct, #42, #33) | YES | `Idempotency-Key` (fresh UUIDv4/attempt; empty refused client-side) | UQ(user,key): replay→original, clash→409 | same-key retry safe; new-key retry = 2nd row (caller discipline) | low (documented) |
| Feedback #35 | YES | key required | UQ(user,key), tier-1 append | same as saves | low |
| Wear log/groups | YES | key (+item) | UQ keys | same | low (no UI calls at all) |
| Wardrobe create/update | NO | none | none (each POST = row) | re-tap → 2nd row | REAL on flaky net (P0-A candidate: client-side double-tap guard already? verify at impl — `_isSubmitting` guards exist on add screen; network-retry dup still possible) |
| Events CRUD | NO | none | none (retries = rows; CURRENT_STATE-flagged) | manual | REAL (P0-A candidate, owner-noted risk) |
| Auth register | PARTIAL | `register_idempotency_key` (no UQ — app-enforced race window, Phase-4A F3) | taken-email checks | — | narrow race (frozen) |
| Guest migration | YES (ledger) | `migratedGuestIds` + server-tuple dedup | content compare | ledger-safe Retry | ~none (tested 20/20) |
| Signals/activity | append-only by design | n/a (retries SHOULD append — except M7 TRX-3 replay path returns pre-insert) | — | — | by-design |

# 6 preferred_item_ids (A4 — lifecycle VERIFIED)

Flutter sends: NEVER (zero `preferredItemIds` refs in lib — FACT). API exposes: NO (no schema field on #41/Today/Event — FACT). Repository resolution: EXISTS (`resolve_preferred_item_ids(saved_looks,user)` → wardrobe-ID frozenset from outfit saves; unit-tested incl. failure-degrade — FACT). Ranking supports: YES (`score_outfit_candidate(preferred_item_ids)` + `candidate_preference_points` +5/cap-15, tested — FACT). Production callers: THREE derive paths pass literal `frozenset()` (outfits:392, events:389, today:188 — FACT, zero drift since D4). Assistant engine (`ai/engine.py:107-208,294,465`) ACCEPTS it BUT production caller `main.py:310` passes only `preferred_occasions` — so the ONLY live consumer path is also unwired (FACT). Tests cover mechanism, never liveness. DO NOT ACTIVATE (needs B3 meaning first).

# 7 item_added (A5 — full-repo verdict)

Backend writers: NONE (5 `insert_look_saved` sites: saved_looks/assistant/analysis×3 — zero `item_added`; sole backend hit = `wardrobe.py:127` docstring "Emits item_added" — ASPIRATIONAL). Seed: NOT in `signal_types` seeds per DECISIONS.md:1040 (DEFERRED, "NO until seeded" — verify seed file at impl). Flutter: local-only `LearningService` record (line 288) + `learning_service_test:62` asserts it (device truth, never synced). Docs: ~20 backend-claim references (WARDROBE_API:167,185,408,440; FEEDBACK_LEARNING_API:121; domain models; TABLE_DEFINITIONS:213 — all vs code). DECISIONS.md:893-905 ALREADY records aspirational status (established convention — cite, don't relitigate). DO NOT ADD (needs seed-check + owner call: emit-vs-docfix).

# 8 LocalStorage analysisResult (A6)

Writer of blob: NONE FOUND (setter `local_storage:86-93` exists, zero lib callers — FACT; verify once more at impl). Writer of flag: `your_analysis_screen:82` on guest Continue-without-account — where NO analysis ran (flag = "photo taken", NOT "analyzed" — SEMANTIC DRIFT, FACT). Readers: profile DNA (faceShape/styleType, null-safe→pending), home first-time (`_hasScannedOutfit`), home diagnostics map, UserSession mirror. Authoritative: NO. Stale: N/A (never populated) — but flag is PERMANENTLY true once set (no clearer found; survives logout — logout preserves device data per established entry). Authed flows consume: only display gating (never content). Migration consumes: NO. Safe scope: rename/document flag OR remove dead setter OR wire honestly (all P0-A, no product call — copy change only if labels change meaning; else owner call).

# 9 style_profile writes (A7 — exact)

Writers (ONLY 2 call sites, both wholesale REPLACE via `repositories:204-233`): `analysis.py:308` (CreateOutfitRun) + `:497` (CreateHairstyleImageRun) — 5 keys `{face_shape,skin_tone,body_type,style_type,source_run_id}`, sibling keys DROPPED (FACT). Non-writers (verified): garment, grooming, profile-only hairstyle (reads), `UpdatePreferences` (prefs `||` merge only), garment/wardrobe/saves/events. Race/loss: last-writer-wins across outfit↔hairstyle-image (no version/cas; concurrent submits → one overwrite lost — REAL but narrow; INFERRED intent: single-active-user flow, no lock design anywhere). Consumers depend on latest-wins? YES: hairstyle/grooming 422-gates assume "current face" (stale-face accepted silently — P0-A document, P0-C redesign). DO NOT REDESIGN (needs product+concurrency call).

# 10 Guest AI Stylist (B1 — per-feature CURRENT + supportability)

| Feature | Start? | See result? | Backend auth? | Flutter block | Save? | Existing-arch support for Analyze→See→(Sign-in)→Save? |
|---|---|---|---|---|---|---|
| AnalyzeMyStyle (photo_capture) | capture yes | guest mock-chain card, NO backend result | n/a (never POSTs) | Continue→stylist | n/a | SUPPORTABLE (already local-first) |
| Face/Hairstyle-image | capture yes | NO (GuestSignInCard, never submits) | 401 behind | pre-submit | prompt | needs anon-run (NEW) or same-gate-keep |
| Garment | capture+preview yes | NO | 401 behind | Analyze-button | local-imageless | needs anon-run (NEW) |
| Outfit/Scan | capture+preview yes | NO | 401 behind | Analyze-button | fake (authed too) | needs anon-run (NEW) |
| Grooming (incl. Beard/Glasses) | input gated (post-fix) | NO | 401 behind | input gate | prompt | needs anon-run (NEW) |
| Generate/Derives | inputs open | NO | 401 behind | Generate-button (+screen guard) | 401/prompt | needs anon-derive (NEW: reads OWNER wardrobe — harder than analyses) |

Anonymous server analysis = GENUINELY NEW (no-user rows violate every FK/scope; TRX-6/signals/runs all user-keyed; no session-scoped run concept). Alternative within architecture: keep gates (current), or Deferred-Save-After-Signup (pending-intent exists; runs can't pre-exist → still needs anon-run OR local-result-then-replay — replay of WHAT? no payload: class-D audit proved no replayable payload exists). PRODUCT DECISION with honest costing — no selection here. Do NOT bypass auth.

# 11 mood/fit/colorPalette (B2 — exact trace + choices)

Originate: builder pickers (16 fixed `BuilderOption` ids: 5 occ / 4 mood / 3 fit / 3 palette). Validated: backend 1–200 free strings (NO vocab table — FACT). Stored: NOWHERE (request-scoped; no column/pref — FACT). Passed: #41 body → `_to_recommendation` prose ONLY (FACT: scoring fn signature takes occasions; mood/fit/palette absent). Score/filter/explain: score NO; filter NO; explanation YES (verbatim echo in colorHarmony/bodyFit/prose — displayed as if meaningful). Choices for later (NOT selected): (a) real terms (palette→color-term map needs palette↔color vocab call; fit→item-fit needs item-fit data that DOESN'T EXIST — garment fit lost at save → needs sidecar or I-unsupported); (b) drop controls; (c) relabel as display-only "vibe" (copy-only, P0-A-safe). Mood has NO data anywhere (I for scoring without new taxonomy).

# 12 Scan → Generate (B4 — reusability verdict)

DIRECTLY REUSABLE: snapshot JSON (appearance+recs) as display context; run_id as `source_run_id` inside M7 snapshots (extractor exists `saved_looks:182`); `outfit-N` seeds accept external variety keys; wardrobe items Scan could confirm-save via #42 (owned-UUID path). PARTIALLY: face_shape → occasion/style bias (no term exists — needs weight call); garment-less snapshot → Generate reads wardrobe only (Scan produces NO wardrobe rows today). NOT COMPATIBLE: hairstyle-rec snapshot ≠ outfit components (M7 outfit validation REQUIRES components[] with owned UUIDs — scan output fails #42 validation by shape; needs transform = product-defined mapping). Do NOT connect (needs B-product shape call).

# 13 Feedback semantics (B5 — code-meaning only)

Like/Dislike (`saved_looks_screen:104-130,304-305` → #35 → `feedback_events{rating,reason?}`): stored reaction, ZERO consumers — dislike ≠ negative preference anywhere (NOT ESTABLISHED). Save → `look_saved` (+ForYou 2-context boost — the ONLY reaction with effect). Wear → ledger (no UI → no rows). Skip: NOT FOUND (no skip control/field). Share: stubs/no-ops. Possible futures (NOT selected): dislike→negative boost (needs semantics+scope call), likes→ForYou widening (code-only), wear→recency (needs UI first), skip→implicit negative (needs control+storage — closest to new).

# 14 Garment preservation (B6 — journey + minimum connection)

Journey: 7 AI attrs → strict result → prefill(type/color/texture exact-match) → user confirm → 3 survive as scored fields (category/color/material) + name; pattern/style/fit/confidence LOST (no columns); imageRef/sourceRunId STORED, UNUSED. Minimum connection reusing architecture (NO schema): persist the subset inside existing `image_ref` JSONB verbatim (already stored!) and READ it where useful (prefill richer chips; generator side-terms — needs weight call), i.e. stop treating imageRef as write-only. First-class columns = genuinely new (migration) — NOT proposed. PRODUCT-adjacent: which attrs MAY influence ranking (needs weight call) — do not wire blindly.

# 15 Product decisions required (P0-B list — owner chooses, agent must not)

D-01 guest-anon vs gates-keep (per-feature B1 table). D-02 mood/fit/palette: terms vs drop vs relabel. D-03 preferred_ids meaning (explicit-request vs favorites vs constraints vs saved-taste-boost) + consequence matrix (explicit=request-field NEW-ish; favorites=already-scored separately; constraints=filter semantics NEW; saved-boost=wire existing resolver — RECOMMENDED reading, still owner call). D-04 scan→generate shape (display-context vs component-transform vs run-link). D-05 feedback: dislike/skip/wear semantics + which surfaces they affect. D-06 garment sidecar reads (which attrs, what weights). D-07 `item_added`: emit (needs seed row) vs docfix (needs seed-check first — technical prerequisite, then owner call). D-08 `analysisCached`/blob: wire/rename/remove. D-09 profile replace-vs-merge + stale-face acceptance. D-10 analysis idempotency keys (double-charge tolerance).

# 16 Safe P0 scope (P0-A — no product call; exact files)

1. Num-safe confidence/matchScore (`outfit_analysis_screen:33,251` → `(as num? ?? 0).toDouble()`; mirror `hairstyle_mock_data:92`). 2. Map-safe error getter (`outfit_scan_client:23` → mirror `GarmentAnalysisRun.failureReason:33-37`). 3. String-safe grooming dates (`grooming_client:113,117` → `as String?` + tryParse, mirror hairstyle_models:33). 4. Poll 404-stop + 401-redirect unification toward garment precedent (`outfit_processing_screen` backoff block; garment vagueness → entry-redirect too — mirror outfit). 5. Contract-drift tests per model (missing-field/mixed-type/int-confidence/Map-error/non-dict-body/int-id). 6. Poll-edge widget tests (timeout/failed/401/429/completed-forward). 7. `analysisCached` copy/rename + dead-setter disposition (copy-only). 8. Wardrobe/event double-submit guards ONLY if missing at impl (`_isSubmitting` exists on add screen — verify-then-close). Each: files+fn listed above; deps: none beyond file; live test: owner matrix D1§35 rerun where flows touched; risk: LOW (crash→honest-error, no behavior change).

# 17 Deferred scope (P0-C — do NOT touch)

Engine weights/terms/skeletons/caps; profile merge/locking; preferred_ids activation; mood/fit/palette terms; scan→generate wiring; feedback consumers; garment sidecar reads; `item_added` emit (until D-07); analysis idempotency keys; guest gates/anon; reasoning prompts/models; migration logic; any migration/table/API/provider; reasoning benchmark; trending.

# 18 Test matrix (P0 — write later, not now)

Unit (Flutter): num-safe parse ×N models · Map-error getter · date-safe · reason-map · key helpers. Widget: int-confidence/Map-error render · poll timeout/failed/401/429/forward · guest gates (isGuestUser=true ×3 surfaces) · no-save assertion (scan) · empty/204 + wardrobe CTA (builder) · save-once guard. Integration: submit→poll→render per analysis (MockClient scripted) · save→201→disabled. Backend unit: resolver/seed-guard · empty-reason mapping · component validation · idempotent replay/409. API/DB (PG): 202→terminal · foreign→404 · TRX-6 replace · signal pairs · vocab-422 · UQ clashes. Provider-down/timeout: kill-switch + dead-host → terminal-failed + honest copy (needs Ollama-off env, no install). Negative: 401/404/500 per surface · malformed JSON (non-dict, int-id, mixed-list) · duplicate POST (document, don't fix) · guest vs authed matrices.

# 19 Live-test matrix (owner-run; reuse D1§35 + D4 screens)

Valid image per analysis (face/garment) · empty-profile · wardrobe± · prefs± · provider-down (`DISABLE_VISION=1`) · token-expiry mid-poll · logout/login isolation · repeat-scan (latest-wins check) · guest capture→prompt per surface · builder empty→204 reasons · save→saved-looks visible · regenerate seed walk · event→prefill + event-derive · daily save→list. EXPECTED = current honest behavior (§§4,10); record ACTUAL.

# 20 Phase 1 implementation order (proposed; awaiting approval)

0. D-07 seed-check (read-only; unblocks item_added call). 1. P0-A parser hardening (§16.1–3 + tests §18 rows 1–2). 2. P0-A poll unification (§16.4 + tests). 3. P0-A copy/dead-code (§16.7–8). 4. Owner decisions D-01…D-10 (§15) — BLOCKS all B-work. 5. Then (post-approval only): decided connections in D-order, each with tests §18 + live §19.

---

## Appendix — inspection index (Phase 1A direct evidence)

Casts: outfit_scan (client:23,102-103,129; screen:32-38,140-143,249-252,423-426; processing:103,253) · hairstyle models/client/mock-data:30-36,57-62,88-95,115-119,92-94,130-144,95-96,151,176,242 · grooming client:62-63,107-121 + service:93-107 · outfit models:51-56,112-127,163-166,202-209 + client:89,152 (malformed-catch) · garment strict (D2) · profile_screen:280-329.
Polling: processing:63-184 · garment_client:142-157 · hairstyle_client:123-161 + service:179-226 + face_processing multi-angle · grooming_client:79-130 · builder/today/event single-derive (no poll).
Idempotency: saves/feedback/wears keys (clients+routers+M7) · analysis/wardrobe/events keyless (router signatures) · register-key race (Phase-4A F3) · migration ledger (conversion entry).
preferred_ids: lib ZERO refs · no API field · resolver `analysis_rules:1160` + tests · `frozenset()` ×3 · `engine.py` accepts + `main.py:310` omits (production-unwired both paths).
item_added: backend sole-hit `wardrobe.py:127` · DECISIONS:893-905,1040 (aspirational/DEFERRED) · local record:288 + test:62 · docs ~20 refs (WARDROBE_API, FEEDBACK_LEARNING_API, domain models).
analysisResult: setter `local_storage:86-93` (zero callers) · flag `your_analysis:82` (no-analysis path) · readers profile/home/session.
Profile writers: `analysis.py:308,497` only · repo `repositories:204-233` (replace).
Guest: D1–D4 gates + grooming-input gate (conversion entry) + AnalyzeMyStyle local-chain (style-fix entry).
Feedback: `saved_looks_screen:104-130,304-305,446-495` · `feedback_client:14-82` · assistant:128-178 · wear: ZERO lib refs.
Mood/fit/palette: BuilderOption 16 ids (mock-data:17-117) · backend free-string validate + prose-only (D4).
Scan→Gen: M7 extractor `saved_looks:182` · #42 component validation `outfits:460-504` · seed passthrough (clients+routers).
Garment: D2 journey + imageRef verbatim (`wardrobe.py` router:179; `_buildImageRef` add-screen:149-167).
