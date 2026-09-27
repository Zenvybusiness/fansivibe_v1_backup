# AI Stylist → Personalization + Data Architecture — Deep Audit (DOMAIN 5, INVESTIGATION ONLY)

> Status: INVESTIGATION COMPLETE. No source modified. No fixes, migrations, APIs, installs, commits, or pushes.
> Date (UTC): 2026-09-27. Repo: `fansivibe_v1_backup` (Flutter `newproject/flutter_application_1`, backend `backend`).
> Method: current source as source of truth, spot-verified file:line. Builds on D1 (Scan) + D2 (Garment) + D3 (Outfit Analysis) + D4 (Generate) audits — facts reused by reference, not repeated; NEW ground here: feedback/reactions, wear, local-LearningService vocabulary, LocalStorage inventory, save-surface matrix, `GetForYouFeed` consumer, DB relationship map, docs-claim scan, loop/matrix verdicts.

Legend: GREEN connected · YELLOW partial · RED disconnected/fake · GRAY not implemented · BLUE external-blocked.
Classes: A connected · B partial · C disconnected-existing · D runtime-dep · E UI-without-backend · F data-not-consumed · G backend-not-consumed · H intentional-local · I unsupported.

---

# 1 Executive Summary

**Verdict: disconnected data islands with exactly three live personalization mechanisms — not a personalization engine.** COLLECT→STORE works across ~10 writers; CONSUME exists in only: (1) occasion+wardrobe+favorites deterministic scoring (Generate/Today/Event derives); (2) `GetForYouFeed` saved-look +0.03 reorder boost (the ONE behavioral backend consumer, honest `personalized` flag); (3) Flutter-local established-user display (reasons/badges from on-device signals — presentation, not ranking). Everything else is write-only history (signals, runs, feedback, wear-ledger, saves beyond ForYou), display-only projection (`styleDna`), or dead mechanisms (`preferred_item_ids` → `frozenset()` ×3; `item_added` docstring-only; wear UI nonexistent; mood/fit/palette scoring-inert).

# 2 Previous Audit Baseline

- D1 Scan: `POST /outfit` = face_shape → hairstyle snapshot; TRX-6 + 2 signals; snackbar-only Save; untyped parse; 0/14 reads; guest pre-analysis gate. Doc `AI_STYLIST_SCAN_OUTFIT_DEEP_AUDIT.md` (§§1–42).
- D2 Garment: M11 observation-only (`POST /garment` → strict result → prefill → save+imageRef); no engine/profile/signals; guest pre-analysis gate. Doc §§1–25.
- D3 Outfit Analysis: consolidated OSI; B-appearance verdict; 12 stale doc claims; learning write-only. Doc §§1–23.
- D4 Generate: rules/ranking, zero AI; reads wardrobe subset + occasions; mood/fit/palette inert; profile never scores; dead preference path; 3 derive surfaces, real idempotent saves. Doc §§1–28.
- Guest→Auth conversion (CURRENT_STATE): pending-intent + Merge/Keep/Discard + migration service (wardrobe imageless, prefs additive; face/signals/titles/styleType/vibe/blob stay local), tested 20/20 + 107 neighbors.

# 3 Personalization Data Inventory

| Source | Storage | Kind |
|---|---|---|
| users (+auth pair UQ) | `users` | identity root |
| style_profile (5 keys, JSONB) | `user_state.style_profile` | AI-inferred facts |
| preferences (`preferred_occasions` ONLY) | `user_state.preferences` | user-stated |
| flags/version | `user_state.flags/version` | bookkeeping |
| wardrobe_items (7 cols + image_ref) | `wardrobe_items` | user-confirmed facts |
| analysis_runs (outfit/hairstyle/garment/grooming) | `analysis_runs` | observations (history) |
| learning_signals (5 live types) | `learning_signals` | event history |
| feedback_events (tier-1 append) | `feedback_events` | reactions |
| saved_looks (4 live contexts) | `saved_looks` | user-confirmed |
| user_events + R36 prefs side-effect | `user_events` + prefs | user-stated |
| wear ledger (groups+events) | `wardrobe_wear_*` | behavior history (backend-only; NO Flutter UI) |
| activity_days | `activity_days` | streak |
| sessions/tokens | `user_sessions` + SecureStorage | auth |
| Local: LearningService model (wardrobe/face/saves/prefs/signals/score) | SharedPreferences via LocalStore | device mirror + guest truth |
| Local: displayName/vibe/analysisResult blob/savedLookIds/userProfile/capabilityState/intent/ledger/flags | LocalStorage (SharedPreferences) | device-only |
| Vocab/system (run/signal/look/cat/color/material/event types, knowledge) | system tables + catalog | canonical (ownerless) |

NOT FOUND IN CURRENT CODE: favorite/disliked colors, styles, seasons, weather, body/fit prefs, hair fields, size, budget, brands, retailers (as data), outfit-level verdicts, multi-item decomposition, anonymous runs, `today_look_records` (by design, DEC-017-A).

# 4 style_profile Trace

Storage: `user_state.style_profile` JSONB NOT NULL `'{}'` (PK user_id → users CASCADE). Keys: `face_shape,skin_tone,body_type,style_type,source_run_id` (free JSON, nullable-by-absence).

| Field | Source | Writer | Reader | Used For | Replace/Merge | Status |
|---|---|---|---|---|---|---|
| face_shape | vision (outfit/hairstyle-image) | CreateOutfitRun:308-314, CreateHairstyleImageRun:497-503 | Hairstyle(profile):117-129, Grooming:591-604, GetProfile→/me, TodayLook styleDna display | gating+ranking (H/G), display | WHOLESALE REPLACE (5 keys; siblings dropped) | A (write+read) |
| skin_tone | `""` (prod) / hash (dev-only) | same TRX-6 | /me, styleDna display | display, completeness→confidence | replace | B (stored, display-only) |
| body_type | same | same | same | same | replace | B |
| style_type | same | same | same | same | replace | B |
| source_run_id | run UUID | same | /me, StyleProfile wire | provenance | replace | B |

Never read by: Scan, Garment, Generate (scoring), Events derive, Saved Looks, Learning, Discover backend. No history (latest-wins; analyses overwrite each other — VERIFIED: no version table, no merge). Hairstyle-image and Outfit both write identical shape (last-writer-wins across features).

# 5 Preferences Trace

- A SERVER (`user_state.preferences.preferred_occasions` — the ONLY persisted pref): entered via event-create (R36 append), `PATCH /me` merge (`||`), Flutter `syncPreferredOccasion` (append-if-absent); read by 3 derive paths as scoring occasions (+5 term). Survives logout (DB); migrates guest→account ADDITIVELY (idempotent). (A)
- B LOCAL GUEST: LearningService prefs + LocalStorage (device-only until migration; prefs migrate, rest stays). (H)
- C UI-ONLY: builder mood/fit/palette selections (request-scoped, echoed, scoring-inert); Discover filter chips (occasion/style/fit — backend catalog rows carry NO such attributes per DEC-014 P-3, so server filtering is vacuous; Flutter-local rail only). (E-effect)
- D REQUEST-ONLY: occasion/mood/fit/palette/seed/variant per derive call; event picker window; search query. (H)
- NOT FOUND: favorite/disliked colors, styles, seasons, weather, formality pref, body/fit prefs, any hidden pref fields. Mood/fit/palette have NO storage field anywhere (request echo only).

# 6 Wardrobe Trace

Columns (`wardrobe_items`): id PK, user_id CASCADE, name, category_id→RESTRICT, color_id→RESTRICT, material_id→NULL, is_favorite, image_ref JSONB NULL, created/updated. Full journey:

```
Garment AI (7 attrs) → strict result → prefill (type/color/texture exact-match; NEVER overwrites picks)
 → user confirms chips → POST /wardrobe/items (vocab-422; imageRef = backend media verbatim + sourceRunId string, NO FK)
 → row → Generate reads id/cat/color/mat/fav/name → ranked combo → #42 save (owned-UUID validated)
```

| Attribute | AI | Stored | Generate | Learning | Status |
|---|---|---|---|---|---|
| category | 5-code | category_id (prior-screen choice, NOT AI-driven) | slots/legality/coverage/occasion | — | PARTIAL (choice fixed upstream) |
| subcategory | string | →type→name (display) | NO | — | LOST (scoring) |
| color | string | color_id (matched) | harmony term | — | CONNECTED |
| pattern | string | NOWHERE (no column) | NO | — | LOST |
| material | string | material_id (matched) | material+season terms | — | CONNECTED |
| style | string | NOWHERE | NO | — | LOST |
| fit | string | NOWHERE | NO | — | LOST |
| confidence | float | NOWHERE (review flag only) | NO | — | LOST |
| imageRef | media meta | verbatim JSONB | NEVER READ | — | UNUSED (F) |
| sourceRunId | run UUID | inside imageRef (string) | NEVER READ | — | UNUSED (F) |

Discard points: save mapping (4 attrs have no columns), generator projection (image/provenance unread), no consumer downstream of item reads except ranking.

# 7 Analysis Runs

| Type | Producer | Input | Output | Reader | Consumer | Status |
|---|---|---|---|---|---|---|
| outfit | CreateOutfitRun (appearance adapter) | face photo | hairstyle snapshot | poll→SCAN-003; /me? no; history? no UI | profile-writers downstream only | history-only (F) |
| hairstyle | CreateHairstyle{,Image}Run | profile XOR face photo | hairstyle snapshot | result screens; profile-gate | hairstyle/grooming gating | PARTIAL (gating, not ranking) |
| garment | CreateGarmentRun | garment photo | observation snapshot | add-item prefill (latest only) | chip preselect | immediate-UI only (F) |
| grooming | CreateGroomingRun | profile (+beard opts UI-only) | grooming snapshot | result screens | — | immediate-UI only (F) |

All: historical rows accumulate (no TTL); only latest surfaces in UI; result JSON reusable in principle, reused NOWHERE except single-shot screens; `source_run_id` FK exists on SAVES (SET NULL), not between runs; analyses influence future ONLY via TRX-6 profile overwrite (face_shape gating) — never via run-result reads.

# 8 Learning Signals

Live vocabulary (backend seeds + writers): `look_saved` (M7 saves), `analysis_updated` (outfit+hairstyle-image), `outfit_selected` (outfit-run lifecycle, misnomer), `suggestion_opened` + `assistant_navigation` (assistant cards, backend-first). Claimed-but-ABSENT: `item_added` (docstring-only, zero emits repo-wide), `styled_day` (is ActivityDays row, NOT a signal), wear/favorite/reaction/event/analysis-generic signals.

| Signal | Writer | Payload | Reader | Changes recs? |
|---|---|---|---|---|
| look_saved | M7 (all saves) | {source_context, look_id?, title} | GetLearningSummary (labels); ForYou (codes, hairstyle/grooming only) | YES (ForYou +0.03, catalog contexts only) |
| analysis_updated | outfit/hairstyle-image runs | {run_id, run_type} | labels only | NO |
| outfit_selected | outfit runs | {source_context, run_id} | labels only | NO |
| suggestion_opened/assistant_navigation | assistant (confirmed-write; local fallback) | title/route | labels only | NO |
| (local-only) item_added/removed/updated, style_updated, occasion_preferred | LearningService (device) | labels | local score + established reasons | LOCAL display/score only |

Loop audit: ACTION→SIGNAL→STORAGE connected (A); STORAGE→CONSUMER→EFFECT connected ONLY for look_saved→ForYou (A) and local-score display (H); all other rows are write-only. NO general learning loop exists.

# 9 Saved Looks

Saved: title (1–200) + snapshot verbatim (components/selectedItemIds owned-UUID-validated, 404-foreign) + source_context (4 live: hairstyle/grooming/outfit/daily) + look_id? + idempotency_key (UQ per user; replay→original, clash→409) + source_run_id (extracted from snapshot, FK SET NULL) → row + `look_saved` + styled-day (TRX-3). Flutter savers: hairstyle, grooming, builder(#42), assistant(outfit), daily(#33) — all real; Scan saves NOTHING.
Personalization reads: ForYou boost (hairstyle/grooming codes only — outfit/daily saves IGNORED since look_id null → PARTIAL); `resolve_preferred_item_ids` EXISTS but derive passes `frozenset()` (dead — P0 carried); Flutter established-reasons read local save list (display). NOT influencing: Generate, TodayLook, Events, profile, Explore ordering.

# 10 Feedback

(a) Saved-look reactions: Like/Dislike buttons (`saved_looks_screen:446-455` → `_reactToLook` → `POST /v1/feedback` #35, 12s, tier-1 append to `feedback_events`, UQ idempotency, NO signal, NO commit beyond row) — stored, CONSUMED NOWHERE (verified: no reader of feedback_events in any ranking/scoring path → F). (b) Assistant cards: opened/navigated → `submitCardFeedback` (2-type contract, client can't name signals) → suggestion signals; offline fallback to local (no double-count). UI exists, effects don't (beyond label history). Favorites (wardrobe star): persisted flag, +5 ranking term (the one favorite-effect that IS real), migration follow-up-update. Wear: backend ledger + summary exist; Flutter has ZERO wear references (no log UI → ledger can only stay empty → G). Shares/skips: no-ops/stubs.

# 11 Analyze My Style → Personalization

Outputs → storage: face_shape (+3 `""`/hash fields, confidence→derived, source_run_id) via TRX-6 (outfit path identical writer). Reads: hairstyle/grooming 422-gates (face_shape REQUIRED — the one hard personalization gate in the system), /me display, TodayLook styleDna display. Affects ranking: NO (no scoring input anywhere). So Analyze My Style personalizes FUTURE GATING + DISPLAY, not recommendations. Confidence/needs_more_data are run-scoped (never persisted beyond result JSON).

# 12 Garment → Personalization

| Attribute | AI | Wardrobe | Generate | Learning | Final |
|---|---|---|---|---|---|
| category/color/material | ✓ | ✓ | ✓ (+terms) | ✗ | CONNECTED (via wardrobe) |
| subcategory | ✓ | →name | display only | ✗ | PARTIAL |
| pattern/style/fit/confidence | ✓ | ✗ | ✗ | ✗ | LOST |
| imageRef/sourceRunId | meta | ✓ verbatim | ✗ | ✗ | UNUSED |

Full chain Garment→Wardrobe→Generate→Saved→Learning: scoring influence REAL for 3 attrs (the only AI-to-ranking path in the system, mediated by user confirmation); everything else drops at save or generator projection; saved outfit rows carry NO garment provenance usable downstream (sourceRunId string, no consumer).

# 13 Outfit Analysis → Personalization

Writes: runs + TRX-6 + 2 signals + day (A). Influences: Generate ✗ / Today ✗ / Events ✗ / Saves ✗ / ForYou ✗ (outfit context ignored) / Explore ✗ / Hairstyle ✓ (face_shape gate) / Grooming ✓ (same) / Wardrobe ✗ / Learning ✗ (labels only). Net: outfit analysis personalizes FUTURE FACE-GATED analyses + profile display — nothing else. Code-evidence only; no inferred links.

# 14 Generate Inputs (scoring-truth table)

- ACTUALLY USED: wardrobe subset (id/cat/color/mat/fav), request occasion, event-type code (#30/Today), persisted preferred_occasions, favorites flag. 
- LOADED BUT NOT USED: imageRef, names (beyond display), full profile object (TodayLook loads for styleDna only), preferred_item_ids resolver (exists, fed empty).
- VALIDATED BUT SCORING-INERT: mood, fit, colorPalette (1–200 free strings → prose echo).
- STORED ELSEWHERE, IGNORED: signals, feedback, wear, saves (except ForYou), runs, style facts.
- AVAILABLE BUT DISCONNECTED: body/style/face facts, garment pattern/style/fit (unsavable), dislike/negative prefs (nonexistent).

# 15 Today Look

Reads: wardrobe + prefs + nearest-event (UTC-today+, type-code only) + style_profile (styleDna DISPLAY ONLY — `_style_dna` never enters scoring, verified). Differs from Generate: no request needed, event-auto, title `{Label} Look`, variant/seed instead of seed, no commit. Personalized? PARTIALLY — same wardrobes+occasions scoring as Generate (real), event-aware (real), styleDna cosmetic (display), saves/feedback/signals non-influential (same gaps).

# 16 Guest → Authenticated Migration

(Verified implementation, CURRENT_STATE; spot-confirmed file presence.) MIGRATED: wardrobe (server UUIDs, imageless, content-dedup, favorites via updateItem) CONNECTED; preferred occasions (additive/idempotent) CONNECTED. NOT MIGRATED (LOCAL ONLY, documented): face data, learning signals (M10 sole-writer — backend signals can't be forged from device), saved-look titles (no IDs), styleType, vibe, analysis blob. Merge/Keep/Discard (+double-confirm Discard, dismiss=Keep) + `migratedGuestIds` ledger + server-tuple dedup + failure-preserves-locals + ledger-safe Retry — all verified tested (20/20 + 107). Pending-intent: single-slot, path-only, 24h, no auto-POST (class-D). Post-auth: resume-destination walk-up table. Net: PREFS+WARDROBE bridge real; taste/profile/history do NOT cross (fresh-account cold start on signals/saves/runs by design).

# 17 Database Relationships (verified: models + migrations + FK policy)

```
users (PK id, UQ auth pair)
 ├── user_state (PK/FK user_id CASCADE; JSONB profile/prefs/flags; NO per-field cols/versions)
 ├── user_sessions (FK CASCADE, UQ token_digest, ix user+expiry)
 ├── analysis_runs (FK user CASCADE, run_type→RESTRICT, CHECK 3 statuses, ix user+created & user+type+created; input_media/result/error JSONB; NO FK to saves)
 ├── saved_looks (FK user CASCADE; look_id→looks SET NULL; source_run_id→runs SET NULL [loose-string origin]; UQ(user,key); ix user+created)
 ├── learning_signals (FK user CASCADE, type→RESTRICT, ix user+occurred)
 ├── feedback_events (FK user CASCADE, UQ(user,key), ix user+occurred; NO signal link)
 ├── activity_days (FK CASCADE, UQ(user,day))
 ├── wardrobe_items (FK user CASCADE; cat/color→RESTRICT (+material NULL); image_ref JSONB; ix user)
 ├── wardrobe_wear_groups/events (FK user CASCADE; item FK; UQ keys; ix user+worn)
 └── user_events (FK user CASCADE; type→RESTRICT; ix user+date)
system (ownerless, RESTRICT targets): run/signal/look/cat/color/material/event types, looks catalog
```

Source-of-truth notes: users=identity; user_state=profile+prefs (single-row, replace semantics); wardrobe_items=owned facts; runs=append-only history; saves=snapshots (NOT live views — wardrobe edits don't propagate); signals/feedback/wear/days=append-only history; no cross-user FKs anywhere (all owner-scoped).

# 18 Source-of-Truth Map

style_profile → user_state (authoritative; LocalStorage analysisResult blob = stale-device-copy DANGER: never synced back, survives logout, feeds guest UI). wardrobe → server table (authoritative authed) vs LearningService LocalStore (authoritative guest) — migration DEDUPS by content (intentional duality, documented). preferred_occasions → user_state (authoritative; R36/event/patch/sync all append). favorites → wardrobe_items.is_favorite (authoritative; local mirror pre-migration). saved outfit → saved_looks.snapshot (frozen; wardrobe drift NOT reflected — intentional snapshot semantics). analysis result → runs.result (authoritative) vs style_profile projection (lossy: 5 keys only) vs LocalStorage blob (stale). event occasion → user_events (authoritative) vs prefs copy (R36 append — intentional denormalization). learning signal → learning_signals (authoritative; local LearningService.signals are a SEPARATE device-only list with OVERLAPPING type names — dangerous duplication: same names, different stores, never reconciled).

# 19 Personalization Loop

COLLECT GREEN (10+ writers) → STORE GREEN (20 tables + device) → NORMALIZE YELLOW (vocab-422 + strict parses exist; but wholesale profile replace, snapshot freezing, string-only links) → DERIVE GREEN (3 deterministic derives) → CONSUME YELLOW (occasion/wardrobe/fav scoring + ForYou boost + display; everything else ignored) → USER ACTION GREEN (rich UI) → LEARN RED (no behavioral learner; signals→labels; feedback→/dev/null behaviorally) → UPDATE YELLOW (profile overwrite, prefs append, saves accumulate) → PERSONALIZE-AGAIN RED (next cycle reads the same 3 mechanisms only). System stops at COLLECT→STORE→(narrow)CONSUME. No model, no weights, no online learning anywhere (verified: no training/inference loop in repo).

# 20 Personalization Matrix

| Data | Stored | Writer | Reader | Rec Effect | Learn Effect | Status |
|---|---|---|---|---|---|---|
| face_shape | Y | TRX-6 ×2 | H/G gates, /me, styleDna | gating only | — | B |
| skin/body/style | Y(`""`) | TRX-6 | display only | none | — | B (dead fields) |
| preferred_occasions | Y | R36/patch/sync | 3 derives | +5 term | — | A |
| mood/fit/palette | N (request) | user/request | prose echo | none | — | E |
| wardrobe 5 fields | Y | user+AI-prefill | generator | ranking | — | A |
| imageRef/provenance | Y | runs→save | none | none | — | F |
| pattern/style/fit-AI | N | — (no cols) | — | — | — | LOST (I) |
| runs/results | Y | 4 analyses | single-shot screens | none | — | F |
| signals (5 live) | Y | runs/saves/cards | labels; ForYou(codes) | +0.03 (saved contexts) | — | B |
| feedback likes | Y | UI | none | none | — | F |
| favorites | Y | user | generator +5 | yes | — | A |
| wear ledger | Y(iff API used; UI never calls) | API only | summary APIs | none | — | G (backend w/o UI) |
| saves | Y | 4 surfaces | ForYou (2 contexts) | +0.03 partial | — | B |
| events/R36 | Y | user | #30/Today + prefs | occasions | — | A |
| guest-local taste | Y(device) | device | local UI | display/score | — | H |
| styleDna | derived | TodayLook | wire display | none (display) | — | B |

# 21 Full Connection Map

AnalyzeMyStyle→profile A · profile→Hairstyle/Grooming A (gating) · profile→Generate scoring X NOT CONNECTED · profile→TodayLook PARTIAL (display) · Garment→Wardrobe A (confirmed subset) · Wardrobe→Generate A (subset) · Generate→Saved A · Saved→ForYou PARTIAL (2/4 contexts) · Saved→Generate X (dead resolver) · OutfitAnalysis→profile A / →else X · Events→Generate A (dual) · Events→prefs A (R36) · Feedback→anything X NOT CONNECTED · Wear→anything X (no UI) · Signals→ranking X (labels only) · Guest→account PARTIAL (wardrobe+prefs only) · Assistant context (wardrobe/face/saves/prefs→chat) A as CHAT GROUNDING (not ranking).

# 22 Connection-Only Opportunities

1. `resolve_preferred_item_ids` → 3 derive calls (pass real sets; mechanism+tests exist) = saved-taste ranking, zero schema. 2. Mood/fit/palette → real terms ( Everton: color-term vs palette map; fit vs item-fit — needs vocab decision, code-only) OR remove controls. 3. Scan snapshot → #41 prefs/seed + save-with-source_run_id (M7 extracts;atis). 4. Garment pattern/style/fit → wardrobe `snapshot`-sidecar? (schema says no cols — sidecar inside imageRef JSONB is connection-only, no migration). 5. styleDna/body/style → scoring terms (code-only; needs product weights). 6. Feedback likes → ForYou-style boost or negative-rerank (code-only; needs semantics call). 7. Wear ledger → recency/diversity term (needs UI logging first — Flutter gap, then code-only). 8. `outfit_selected`/analysis signals → occasion-affinity counters (code-only). 9. ForYou boost → include outfit/daily contexts (one-line scope widening + test). 10. Guest taste → post-auth seeding (face/vibe/blob → profile/prefs writers exist; policy call).

# 23 Genuinely New Architecture

(a) Anonymous/guest derivation+analysis (no-user rows violate every FK/owner scope — needs session-scoped or deferred-persist design). (b) Multi-item outfit decomposition (single-subject adapters by contract). (c) Outfit-level styling verdicts beyond wardrobe ranking (no engine exists). (d) Online/behavioral learner (weights/training; current signals lack features/labels for it). (e) Negative-preference model (no dislike storage anywhere; feedback is append-only reactions). (f) Fresh signals columns if product wants pattern/style/fit as FIRST-CLASS queryable fields (sidecar-in-JSONB avoids this — conservative path stays connection-only). Everything else in §22 needs no new tables/APIs/services.

# 24 Ollama/AI Separation

REQUIRES Ollama (vision `POST /api/chat`, 20s, kill-switch): Analyze My Style, Scan/Outfit Analysis, Hairstyle-image, Garment, Grooming-vision (5 surfaces; all fail CLOSED to terminal failed runs + honest UI without it). NO Ollama: Generate (#41), TodayLook (#31/32), Event outfit (#30), ALL saves, wardrobe CRUD, events CRUD, prefs, Discover catalog/ForYou (deterministic reorder), assistant CHAT Welling? — assistant chat path: reasoning model IS Ollama-backed (`reasoning_host`, excluded from guest per auth_guard) — chat needs it; card-feedback writes don't. Learning/summary/scores: pure SQL/counts. Offline Flutter: guest browsing, local score/reasons, cached blob display. Net: ~70% of product value (derive+save+history) runs with ZERO AI runtime; vision gates only the 5 image-analysis surfaces.

# 25 Security

JWT everywhere server-side (`get_current_user_id`; dev-token only where allowed); owner-scoped reads/writes/lists on ALL user tables (verified per-use-case; foreign→404 OW-1; saves validate owned UUIDs, never drop); idempotency UQs (saves, feedback, wears, auth-pair); image bytes hashed/ephemeral, never logged (tests assert); error payloads carry run_id only; guest = no token + local-only (no cross-boundary leak; migration dedups + ledgers); SecureStorage token vs SharedPreferences device data (correct split). Pre-existing notes (no change): register-key UQ race, wholesale profile replace, string-only provenance, no analysis idempotency (double-tap double-run), 404-timing oracle (accepted).

# 26 Tests

style_profile TRX-6 (backend use-case GREEN) · prefs merge/R36 (GREEN) · wardrobe CRUD+vocab+imageRef (GREEN) · garment 18T (GREEN) · outfit contract (GREEN) · generate determinism/ownership/204/no-side-effects (GREEN, PG-gated) · saves idempotent/409 (GREEN) · learning summary read-only (GREEN) · events CRUD+outfit (GREEN) · feedback append (GREEN) · guest migration 20/20 + neighbors 107 (GREEN) · Flutter clients/parsers/screens (GREEN unit, YELLOW widget depth) · ForYou boost (GREEN). RED/missing: parse-robustness (P0 casts), guest-gate widgets, no-read locks, preference-with-ids liveness, wear-UI (none to test), live vision (needs Ollama), live PG here (skipped), negative-preference (nothing exists).

# 27 Documentation Conflicts (CODE WINS)

Product ("personalized AI style intelligence", "AI-powered", "learns"-adjacent copy) vs ONE behavioral consumer (+0.03) + occasion scoring + display-local reasons — "personalized" overclaims; "AI-powered" true ONLY for 5 vision surfaces (generate/rank/discover/saves run model-free). Prior 12 stale API claims (D3 §19S) stand. `item_added` docstring (zero emits). `outfit_selected` name (lifecycle≠tap). `matchScore`≠confidence (code forbids thresholding). `GenerationStage` 800ms theater (verify vs single-request derive). Discover filters vs attributeless catalog rows (server filtering vacuous). "History/learning" prose vs write-only signals.

# 28 OSI Status

A Profile YELLOW (gates+display real; 3/5 fields dead; replace semantics) · B style_profile YELLOW (same) · C Preferences YELLOW (occasions A; rest inert/nonexistent) · D Wardrobe GREEN (CRUD+vocab+imageRef+reads) · E Garment GREEN code/BLUE runtime · F Runs GREEN store/YELLOW consume · G Outfit Analysis YELLOW (real pipeline, mislabeled, fake save) · H Generate GREEN (deterministic, honest, no-AI) · I Saved GREEN (validated+idempotent) · J Signals YELLOW (writes real, ~all unconsumed) · K Feedback RED (stored, never consumed) · L Events GREEN (dual systems + R36) · M TodayLook GREEN (shared engine + display) · N Guest Migration GREEN (tested) · O Loop RED (stops at store/narrow-consume; no learner) · P Relations GREEN (FK policy verified) · Q AI/Ollama BLUE (5 surfaces; rest independent) · R Security GREEN · S Tests YELLOW (contracts strong; widget/live/PG gaps) · T Docs RED (overclaim + 12 stale).

# 29 P0–P4 Findings

- P0: Flutter cast crashes (int-confidence, Map-error) — real shapes crash UI; `preferred_item_ids` dead on live paths (personalization theater); register-key race; double-run double-charge (no analysis idempotency); LocalStorage blob staleness (feeds guest UI, never reconciled).
- P1: feedback/wear/signals unconsumed; mood-fit-palette inert; Scan↔rest unwired; guest pre-gates vs intended; 404-retry; no history UI for runs.
- P2: no fav/share/swap on rec screens; alternatives unsurfacing; dead chips (skin/body/style `""`); stage theater; generic copies; snapshot-vs-live wardrobe drift (by design — disclose).
- P3: negative prefs nonexistent; pattern/style/fit unsavable; latest-wins profile; outfit/daily excluded from ForYou; local/backend signal-name duplication; cold-start honesty (already good — keep).
- P4: §27 conflicts; PG-gated skips; missing widget/robustness tests; seed-collision note (documented, fine).

# 30 Final Data Flow (ACTUAL — [X] = not connected)

```
USER ──▶ PROFILE(displayName/vibe/blob, device) ──▶ guest UI [CONNECTED, device-only]
USER ──▶ AnalyzeMyStyle ──▶ style_profile [CONNECTED] ──▶ Hairstyle/Grooming gates [CONNECTED]
                                                          ║──▶ Generate scoring [X NOT CONNECTED]
                                                          ║──▶ TodayLook scoring [X] (display PROJECTION only)
USER ──▶ Garment ──▶ Wardrobe (cat/color/mat + name) [CONNECTED] ──▶ Generate scoring [CONNECTED]
              pattern/style/fit/confidence [X LOST]   imageRef/provenance [X UNUSED]
USER ──▶ OutfitAnalysis ──▶ runs+profile+signals [CONNECTED] ──▶ future recs [X NOT CONNECTED]
USER ──▶ prefs/occasions/mood-fit-palette ──▶ Generate [occasions CONNECTED; m/f/p X INERT]
USER ──▶ Events ──▶ derive (#30) + prefs (R36) [CONNECTED]
GENERATION (wardrobe+occasions+favs deterministic) ──▶ Saved Looks [CONNECTED] ──▶ ForYou +0.03 (2 contexts) [PARTIAL]
Saves/feedback/wear/runs/signals ──▶ ranking consumers [X NOT CONNECTED] (labels/display only)
Guest taste ──▶ account [wardrobe+prefs CONNECTED; face/signals/saves/history X LOCAL-ONLY]
```

# 31 Final Verdict

1. True personalization engine? NO — 3 narrow mechanisms, no learner, no weights. 2. Genuinely personalized today? occasion-aware wardrobe ranking (+favorites), saved-look ForYou boost (hairstyle/grooming), face-gated analyses, event-aware derives, local established-user display. 3. Collected but unused? feedback, wear (no UI), imageRef/provenance, runs/results, 4/5 signal types, skin/body/style fields, pattern/style/fit (lost), mood/fit/palette (inert). 4. Lost? pattern/style/fit/confidence at save; subcategory→display; snapshot-vs-live drift; guest taste at conversion (by design); profile siblings on replace. 5. Duplicated? local-vs-server wardrobe/prefs/signals/score; blob-vs-runs; prefs-vs-R36 (intentional); signal-name overlap (dangerous). 6. Learning that happens? NONE behaviorally — labels + counts + displays. 7. What changes recs from behavior? wardrobe edits, favorites, saves (ForYou, 2 contexts), pref/event occasions. 8. Connectable without rebuild? ~90% (§22: 10 items, all code-only). 9. Genuinely new? anonymous derive, multi-item decomposition, outfit verdicts, online learner, dislike model, first-class pattern/style/fit (or JSONB sidecar to avoid). 10. Ollama-required? 5 vision surfaces only. 11. Ollama-free? derives, saves, CRUD, prefs, discover, summaries, scores, guest browsing. 12. Next? §33 + D4 §28 (live PG → preference call → mood/fit/palette call → Scan→Generate spike → guest policy → doc/test pass).

# 32 (Deliverable note)

This file is the deliverable (`AI_STYLIST_PERSONALIZATION_DATA_ARCHITECTURE_AUDIT.md`); CURRENT_STATE.md updated separately. No code, migration, install, commit, or push performed.

# 33 Source Index (practical)

Prior audits: `AI_STYLIST_SCAN_OUTFIT_DEEP_AUDIT.md` · `AI_STYLIST_GARMENT_ANALYSIS_DEEP_AUDIT.md` · `AI_STYLIST_OUTFIT_ANALYSIS_DEEP_AUDIT.md` · `AI_STYLIST_GENERATE_OUTFIT_DEEP_AUDIT.md` · `CURRENT_STATE.md:1-60` (+ guest-conversion/M14/Phase4 entries).
New: `backend/app/application/discover.py:286-359` (ForYou boost) · `assistant.py:3-89` (card signals) · `feedback.py` + `feedback_client:14-82` + `saved_looks_screen:104-130,304-305,446-495` (reactions) · `learning/domain/learning_service.dart:196-456` (local vocab) · `learning/data/models.dart:50` (FaceProfile) · `assistant_service:39-178` (context+feedback) · `discover_screen:1-80` + established widgets (D1) · `local_storage.dart:11-225` + `user_session.dart` (device keys) · `guest_data_migration.dart` + `pending_auth_intent` + `post_auth_flow` (conversion) · `models.py` (20 tables: 51,81,111,127-209,212-260,247,FeedbackEvents,ActivityDays,Wear*,552) · `PRODUCT_BLUEPRINT:5,15,37` + `PROJECT_CONTEXT:5-45` (claims) · DEC-014 P-3 (attributeless catalog) · `test_guest_auth_conversion` (20/20).
Skills lens: `flutter-apply-architecture-best-practices` (carried; no code emitted).
