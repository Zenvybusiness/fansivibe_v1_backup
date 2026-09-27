# AI Stylist → Build/Generate Outfit — Deep Audit (INVESTIGATION ONLY)

> Status: INVESTIGATION COMPLETE. No source modified. No fixes, APIs, tables, installs, commits, or pushes.
> Date (UTC): 2026-09-27. Repo: `fansivibe_v1_backup` (Flutter `newproject/flutter_application_1`, backend `backend`).
> Method: current source as source of truth, spot-verified file:line. Builds on Domain 1 (Scan), 2 (Garment), 3 (Outfit Analysis).
> Headline: Generate Outfit is a **deterministic rules/ranking engine over owned wardrobe + preferred occasions. Zero AI calls.** Fully wired authed flow with honest empty/error states and real idempotent saves. Guests blocked before generation.

Legend: GREEN verified · YELLOW partial · RED broken/fake · GRAY not implemented · BLUE external-blocked.
Classes: A connected · B partial · C disconnected-existing · D runtime-dep · E UI-without-backend · F data-not-consumed · G backend-not-consumed · H intentional-local · I unsupported.

---

# 1 Executive Summary

Three Flutter entries (Stylist `Build Outfit From My Wardrobe` tile → `buildOutfit`; Home `BUILD THIS LOOK`; event `Plan My Look` → same screen with event extras) feed one 3-screen flow: `BuildOutfitScreen` (4 pref pickers) → `OutfitGenerationScreen` (single derive on entry, `replaceNamed` to result) → `OutfitRecommendationScreen` (components + reasons + metrics + Save + Regenerate with `outfit-N` seeds). Backend: `POST /v1/outfits/generate` (JSON prefs, 12s client timeout) → `GenerateOutfit` (TRX-2 READ-ONLY, no commit, no signals) → deterministic pipeline (candidates → score 0–100 → rank → seed-pick) → 200 recommendation / 204 + `X-Outfit-Empty-Reason` / 422 / 503-never-here. Save: `POST /v1/outfits/saved` → `SaveOutfit` → M7 `SaveRecommendation` (validated, idempotent-key, `look_saved` + styled-day TRX-3). Two sibling derive surfaces reuse the SAME pipeline: TodayLook (#31/#32, +nearest-event + `styleDna` display projection) and Event outfit (#30, event-type-first occasions).

Critical data facts: generator reads ONLY wardrobe (id/category/color/material/is_favorite/name) + occasion lists (request/event + `preferred_occasions`). **Mood/fit/palette are validated free strings echoed in prose — zero scoring effect.** `style_profile` NEVER enters scoring (TodayLook projects it to `styleDna` display only). **Preference sub-score is structurally 0 on all live paths** (`frozenset()` passed at `outfits.py:389`, `events.py:389`, `today.py:188` — the Step-11 mechanism exists, no derive caller supplies it). Garment attrs pattern/style/fit are LOST at wardrobe-save (no columns); imageRef stored but never read by generator. Guests: open + pick inputs, blocked at Generate button (no derive, no result, no save). No AI anywhere on this path — "AI Stylist" naming vs rules engine is the one honest-labeling tension (prose itself is AI-0 restrained).

# 2 Exact User Flow

```
Stylist tile [stylist_screen] / Home BUILD THIS LOOK / Event Plan My Look
 → pushNamed(buildOutfit[, extra{eventId,eventTitle,occasion}]) → /stylist/build-outfit
BuildOutfitScreen: occasion(5) + mood(4) + fit(3) + palette(3) pickers [mock-data BuilderOption; event preselect on exact id-match]
 → guest? prompt 'Sign in to build outfits' + return (NO push) : pushNamed(outfitGeneration, extra{4 prefs[,event]})
OutfitGenerationScreen: single generateOutfit on entry (guest double-guard early-return) → replaceNamed(outfitRecommendation, extra{recommendation, request})
 → 200 → result | 204 → empty + wardrobe CTA | failure → error + retry/back
OutfitRecommendationScreen: components + reasons + metrics + [Save Outfit → POST /saved 201 → 'Outfit saved', once] + [Regenerate → seed outfit-N → same screen state swap]
EventDetails (parallel surface): _generateOutfit → generateEventOutfit(id) → inline section (#30, no save UI here)
DailyOutfit (parallel surface): GET/POST /looks/today → look + GuestSignInCard for guests + real save (#33)
```

Routes (`app_router.dart:237-299`): `build-outfit` (extra `Map<String,String>?`, null-tolerant) → `generation` (extra required, else missing-data screen) → `recommendation` (extra `{recommendation, request}` JSON, else missing-data screen). State: setState + repository + FutureBuilder-style single future; no cross-feature state.

# 3 Flutter Architecture

- Screens: `build_outfit_screen.dart` (240 lines, 4 selections, `_allSelected` gate, guest prompt, event chip), `outfit_generation_screen.dart` (entry-derive, 204/empty vs error branches, retry, wardrobe CTA `goNamed(wardrobe)`), `outfit_recommendation_screen.dart` (rec render, `_handleRegenerate` seed counter, `_handleSave` once-guard, per-failure copy).
- Data: `outfit_client.dart` (`OutfitBuilderClient`: generate never-throws → `OutfitResult{available|noneAvailable+emptyReason|failure}`, save hardcodes `sourceContext outfit`, fresh UUIDv4 idempotency key helper, `dispose`), `outfit_models.dart` (`OutfitComponent/Recommendation/GenerateRequest/SavedOutfit/OutfitResult/OutfitFailure`), `outfit_repository.dart` (contract + impl), `outfit_builder_mock_data.dart` (BuilderOption lists + `GenerationStage` — check unused-vs-used: options ARE the live pickers).
- Buttons (ACTION→CODE→SERVICE→HTTP→BACKEND→DB→FAILURE): Generate → `_buildOutfit` → (guest? stop) → push → generation screen → repo → #41 → wardrobe+prefs read → 200/204/4xx/503/timeout → mapped UI (all verified GREEN except rec-screen missing guest check — unreachable-by-construction, YELLOW); Save → `_handleSave` → #42 → M7 → 201/disabled-once vs truthful fail (GREEN); Regenerate → same-prefs + `outfit-N` seed → state swap, old kept on fail (GREEN); favorite/share/edit-on-result: ABSENT (no fav toggle, no share, no component swap — GRAY vs Home hero which HAS fav/save).

# 4 HTTP Contract

- `POST {base}/v1/outfits/generate` JSON `{occasion,mood,fit,colorPalette,seed?}` · Bearer · 12s → 200 `OutfitRecommendation` | 204 empty (`X-Outfit-Empty-Reason`: `empty_wardrobe|missing_required_category|no_legal_candidate`) | 401/422/429/503 → typed `OutfitFailure` (401 also `notifyUnauthorized`) | malformed-200 → failure (never fake) | transport → `networkError`. Never throws, never keyed, persists nothing.
- `POST {base}/v1/outfits/saved` JSON `{lookId?,title,sourceContext:'outfit'(const),snapshot}` + `Idempotency-Key` (empty refused client-side) → 201 `SavedOutfit` else null (409→null→honest fail).
- Mismatches: NONE structural (client mirrors router: 200/204+header/422/503). Minor: client sends `seed` only when non-null (matches optional); `fit`/`mood`/`palette` accepted but scoring-inert (contract-honest, effect-misleading — B).

# 5 FastAPI Trace

`routers/outfits.py:86-130` (`POST /generate`, `response_model OutfitRecommendation`, `exclude_none`, 422/503 declared; docstring: TRX-2, seed semantics, 204+header) → `get_current_user_id` → `OutfitGenerateRequest` (Pydantic: 4 prefs + optional seed) → `GenerateOutfit(wardrobe_items, user_state)` → `_validate_preference×4` (1–200 non-blank; NO vocab table — structural only) + `_validate_selector` → `_derive_outfit` (wardrobe pages-of-100 + `[request-occasion + persisted prefs]` deduped) → winner/`None+reason` → `_to_recommendation` → 200 / 204+header / 422 / 503 (`_DerivationFailed` only). Zero commits, zero signals, zero writes on derive (verified: no `insert_look_saved|mark_styled|commit()` in `outfits.py` derive path). `#42` → `SaveOutfit` → component-ID fail-closed (422 malformed / 404 foreign, OW-1) → M7 verbatim (idempotent replay / 409).

# 6 Generator Algorithm (what the code ACTUALLY does)

- Candidates (`generate_outfit_candidates`): owned IDs grouped by 5 categories → lexical-first-3 per category (scoring-blind) → 5 fixed skeletons in order (`tops+bottoms` mandatory; +footwear; +outerwear+footwear; +footwear+accessories; full) → skeleton legality via `_COMPATIBLE_PAIRINGS` (core pair mutual; optionals attach to accepted set; unknown fails closed) → lexical product combos, dedup, HARD CAP 25 (deterministic prefix). Only `.id/.category` read here.
- Scoring (`score_outfit_candidate`, 0–100 = compat 0–70 + pref 0–15 + fav 0–15, each clamped, round-2): coverage +8/filled-category; color: <2 known→0, any bright–bright pair→−10 else +10 (neutral-gate); material: all-known-natural→+5 else 0; season: category+material season-sets intersect→+5 / disjoint→−5 / <2 informative→0; formality: single register→+5 else 0; occasion: ONE requested occasion suits EVERY member→+5 else 0; preference +5/matched saved-item (ALWAYS 0 live — `frozenset()`); favorite +5/fav-member cap 15.
- Rank (`rank_outfit_candidates`): score↓, item-count↓, lexical-IDs↑. Winner rank-0 (no seed) or `sha256(seed)%count`. Alternatives `ranked[1:3]` computed but NOT surfaced by #41 (single-rec response — dead-ish mechanism on this endpoint, B).
- Assembly (`_to_recommendation`): title `{Occ} Outfit`; `match_score = score/100` (0–1, 4dp — RANKING score, NOT confidence; never threshold it); components (owned id/name/category/color/material + templated reason); reasons (occasion + coverage + favorites); 5 metric proses templated from request+winner (AI-0: no comfort/flattery/invented claims); `missing` → improvement suggest first absent slot else full-coverage line.
- Missing/empty: no wardrobe → `empty_wardrobe`; no tops/bottoms → `missing_required_category`; ranked-empty → `no_legal_candidate` (defensive, marked unreachable); skeleton unsatisfiable → skipped silently (fewer combos, never error).

# 7 AI vs Rules

**RULE-BASED. No AI model is used.** Verified: zero Ollama/vision/LLM/embedding/prompt/inference imports or calls on the generate path (`analysis_rules.py` scoring+ranking are pure functions; `compute_outfit_intelligence` docstring: "deterministic rules only… No AI provider calls"; embeddings exist ONLY in `ffo_semantic.py`, zero live-path imports per Phase 4A). Mood/fit/palette do not even reach scoring — the "personalization" surface is one occasion list + favorites + coverage/color/material/season/formality rules. Enrichment (`enrichment.py`) rewrites wording only, never scores. State clearly: recommendations are ranked wardrobe combinations, not model output.

# 8 Wardrobe Connection

| Field | Read? | Used for |
|---|---|---|
| id | YES | slots, combos, dedup, tie-break, save validation |
| category | YES | slots, skeletons, legality, coverage, occasion, formality, season |
| color | YES | harmony term |
| material | YES | material + season terms |
| is_favorite | YES | +5/member (cap 15), reasons line |
| name | YES | display + reasons only |
| image_ref | NO (stored, never read) | — (F) |
| created/updated | NO | — |
| pattern/style/fit | N/A | NO SUCH COLUMNS (lost at save) |
| wear history | NO | never read (F) |

Reads: owner-scoped pages of 100 (`_load_owner_wardrobe`, all three derive paths). No filtering by query — full-wardrobe load per derive.

# 9 Garment Connection

Journey per field (garment → wardrobe → generate): category ✓ (vocab code → slots); color ✓ (matched name → harmony); material ✓ (texture → material/season); subcategory→type→name (display only ✗ scoring); pattern/style/fit LOST (no columns — I); imageRef STORED, UNUSED by generator (F); sourceRunId string-only (no FK). So garment intelligence partially survives (3 of 7 attrs score-relevant) — the rest is display/provenance. Chain status: Garment→Wardrobe CONNECTED (user-confirmed save); Wardrobe→Generate CONNECTED (field subset).

# 10 Analyze My Style Connection

GenerateOutfit: NOT CONNECTED — never reads `style_profile` (deps prove: wardrobe + prefs-only user_state; scoring inputs = occasions). face/skin/body/style: none enter ranking. TodayLook: PARTIAL — reads profile ONLY for `styleDna` 4-field display projection (`today.py:246-259,345`), never for scoring. Sharing the table ≠ connection; scoring connection does not exist on any derive path.

# 11 Preferences

- `preferred_occasions` (only prefs field that exists): `user_state.preferences` → appended by event create (R36) / `PATCH /me` / Flutter sync → read by all 3 derive paths → composed `[request|event-code + persisted]` deduped → the ONLY request-adjacent scoring term (+5 all-members-suit). SOURCE→STORAGE→GENERATOR→EFFECT fully traced (A).
- occasion (request): same +5 path (A). mood/fit/palette (request): validated, echoed in prose, NO scoring effect (E-effect: controls exist, backend effect absent — P2/P3). favorite colors/disliked/styles/season/weather: NO SUCH FIELDS (I — only occasions persisted). Event-type code: top-priority occasion on #30 + TodayLook (A).

# 12 Outfit Analysis Connection

Both directions NOT CONNECTED: outfit-analysis runs/snapshots never enter generation (no run read, no snapshot field, no navigation extra — `See Recommendations` forwards nothing); generated outfits never enter analysis (no run attach, no analyze button on rec screen, snapshot carries no `sourceRunId` of an analysis). Reusable for a future link (C): rec→`POST /looks/saved`→saved row CAN carry analysis `source_run_id` via snapshot (M7 extracts it — `saved_looks.py:182`); garment→wardrobe→generate already valid item-level grounding.

# 13 Saved Looks

| Save API | Input | DB | Source Context | Idempotent | Signal |
|---|---|---|---|---|---|
| `POST /v1/outfits/saved` (#42, builder USES) | title+snapshot(components UUID-validated+owned) | saved_looks (+FK run if in snapshot) | `outfit` (const) | key: replay→original / clash→409 | look_saved + day (TRX-3) |
| `POST /v1/looks/saved` (M7 direct) | look_id?+title+snapshot+context | same | hairstyle/grooming/outfit/daily (validated) | same | same |
| `POST /v1/looks/today/save` (#33, daily USES) | title+snapshot | same | `daily` | same (fresh key/attempt) | same |
| `GET /v1/analysis/runs` | — | read summaries (no result/error) | — | — | — |

Builder uses #42 (component fail-closed BEFORE M7). Differences: #42 adds outfit-component ownership validation; M7 adds outfit-family `selectedItemIds` normalization; #33 is the daily alias. All owner-scoped, 404-foreign.

# 14 Today Look

Shares: THE pipeline (generate→score→rank→select verbatim), wardrobe + prefs reads, `OutfitRecommendation`-family wire, M7 save semantics, guest-blocked pattern. Differs: +nearest-event auto-occasion (server-UTC today+, type-code only), +`styleDna` display projection, title `{Label} Look`, no-request-needed GET (#31) + POST regenerate (#32), NO user seed (variant instead), no commit/save on derive. No duplicate logic — one engine, three call shapes (#30 event-code-first, #31/32 event-auto, #41 request-first). TodayLook never reads analysis runs either.

# 15 Events

TWO systems, explained: (a) `GenerateEventOutfit` (#30, `events.py:327-399`): derive-for-eventId inline (event must be owned else 404; type-code = top occasion; same pipeline; 204-on-empty; NO save/signal/commit) — surfaced in `EventDetailsScreen._generateOutfit` inline section; (b) handoff button → `BuildOutfitScreen(eventId/eventTitle/initialOccasion)` (exact-id preselect only) → normal #41 flow → save. So event→outfit exists BOTH as instant-derive (no persistence) AND as prefilled-builder (persistence via #42). Past events derive freely (no date gate). Event create ALSO writes `preferred_occasions` (R36) — the durable event→generation influence.

# 16 Learning

- Generate (#41), TodayLook derive (#31/32), Event derive (#30): write NOTHING (verified: zero `insert_look_saved|mark_styled|commit` in `outfits.py` derive, `today.py`, `events.py` derive; docstrings assert; commits in events.py are CRUD-only). TRX-2/read-only is real.
- Saves (#42/#33/M7): `look_saved{source_context,title}` + styled-day (TRX-3) — the ONLY learning write in this domain.
- Consumers: summary labels + counts only; NO ranking/scoring/feed branch reads signal types; `resolve_preferred_item_ids` exists but derive passes `frozenset()` — the preference loop is unwired (P3). WRITE (saves) EXISTS; CONSUMER (personalization-driving) does NOT. Wardrobe saves emit NOTHING (`item_added` docstring-only, D2 finding stands).

# 17 Guest Flow

OPEN ✓ (build screen renders, all 4 pickers selectable; shell guest-safe) · INPUTS ✓ · GENERATE ✗ (button prompt `Sign in to build outfits`, no push, no HTTP) · RESULT ✗ (generation screen double-guards `isGuestUser→return`, no request) · SAVE ✗ · PERSIST ✗ (zero rows) · REGENERATE ✗ (unreachable; rec screen itself has NO guest check — relies on gates; backend 401s honestly if reached). Auth required at: build-button (first), generation screen (second), #41 401 (third), save 401 (fourth). Vs intended (use+see, gate-on-persist): NOT met — same before-generation pattern as analyses; architecture COULD support viewable-derives only with anonymous-derivation (genuinely new: derives read OWNER wardrobe — no-user derivation is I without a session/user row).

# 18 Auth/Security

JWT (`get_current_user_id`) on #41/#42/#30/#31/#32/#33; wardrobe/events/saves owner-scoped paged reads + `get_by_id` checks; foreign/unknown IDs → 404 indistinguishable (OW-1, enforced in SaveOutfit + M7 + derive scoping); no IDOR path found (rec screen re-parses server JSON, IDs verbatim but saves re-validate ownership); seed/prefs are free strings (1–200, no injection surface — no SQL/formatting sinks); idempotency keys UUIDv4 client, server-authoritative compare; no image/PII logging on path (no images at all); `notifyUnauthorized` on 401. Pre-existing notes: no generate idempotency (re-derive is read-only so safe); `NO_LEGAL_CANDIDATE` defensive-unreachable marker.

# 19 Errors

Empty wardrobe → 204 `empty_wardrobe` → `No outfit available… Add wardrobe pieces` + wardrobe CTA (GREEN). Missing tops/bottoms → 204 `missing_required_category` (GREEN). Invalid prefs (blank/>200/wrong types) → 422 → `invalidInput` copy (GREEN). Engine exception → 503 → `serviceUnavailable` (GREEN; unreachable in practice — defensive). 401 → `unauthorized` + session-clear (GREEN). 429 → rate-limited copy (GREEN). 500/unhandled + request_id → `unknown` (GREEN). Network/timeout(12s) → `networkError` (GREEN). Malformed-200 → failure, never fake (GREEN). Save: 409 → null → `Couldn't save…` (GREEN); validation → same; offline → same. Duplicate save: same key+payload → original (no dup); same key+payload-differ → 409 (GREEN). Guest: prompts, never 401-storms (GREEN). Failure mode with NO honest path: none found on builder (vs Scan's fake-save — builder is clean).

# 20 Determinism

FULLY deterministic: same wardrobe + same prefs + same seed → byte-identical pick. Mechanisms: lexical reps (3/cat), skeleton order, lexical combos, 25-cap prefix, pure-function scoring, total ranking order (score, count, lexical IDs — no timestamps/row-order), sha256-seed pick, no `Random` in engine (Flutter `Random.secure` only mints idempotency keys). DB ordering neutralized (sort-by-ID reps + lexical tie-break). Regenerate `outfit-N` walks the ranked list stably; collisions possible in bounded space (documented best-effort). New wardrobe item / changed prefs / changed favorites → possibly different winner (expected, still deterministic per input state).

# 21 Performance

Per derive: wardrobe full-load via pages-of-100 (1–N queries, no N+1 per-item queries — single list + in-memory); ≤25 candidates × ≤5 members pure scoring (microseconds); prefs 1 read; events 1 list (#30/#31). No caching (every generate/regenerate refetches + re-derives — fine at this scale, note for later). 12s client timeout ≫ actual (no vision/LLM). Images: none transferred (IDs only; item images lazy in UI). No optimization needed; report-only: unbounded-wardrobe paging loop is linear-safe; 25-cap bounds compute.

# 22 Tests

| Area | Tests | Verified | Missing |
|---|---|---|---|
| Generate API | `test_m13_outfits_api` (DB-gated) | 200-shape, owned-UUIDs, 204-empty, determinism, no-side-effects, foreign-ignore | run in PG CI here |
| Bridge | `test_m11_p3` (DB) | garment-save → reload → generate uses real IDs/values | — |
| Event outfit | `test_m8c_event_outfit_api` | #30 derive, 204, ownership | — |
| Today | `test_m9_today_look_api` | #31/#32 incl. event + styleDna | — |
| Flutter API | `outfit_builder_api_test` | generate/save mapping, 204+header, failures | — |
| Flutter screens | `outfit_builder_screens_test` | pickers→generate nav, loading/error/empty, save/regen | guest-gate widget test; rec-screen no-guest-check lock |
| Today/events UI | `today_look_*`, `event_screens`, `events_api_test` | cards, save, event CRUD+outfit section | — |
| Ranking units | rules tests (13.x family) | score/rank/seed determinism | preference-path test WITH ids (currently always empty live) |
| Live/provider | NONE | — | n/a (no provider on path — nothing to live-test; correct) |

Fake-vs-real: no mocks on derive path in tests that matter (M11-P3/M13 prove HTTP-boundary with real rows where PG available).

# 23 Documentation Conflicts (CODE WINS)

1. Mood/fit/palette pickers imply scoring influence; backend scores occasion ONLY (UI-vs-code effect gap — P2/P3; options real, effect absent).
2. `matchScore` (score/100) is NOT confidence — code comments forbid thresholding; any doc/UI treating % as AI confidence is wrong.
3. `select_outfit_alternatives` (ranked[1:3]) unused by #41 single-rec response (mechanism without surface — B).
4. Preference sub-system (`resolve_preferred_item_ids`, +0.05 cap) unwired on ALL derive paths (`frozenset()` ×3) — docs describing saved-look-boosted generation overclaim current behavior.
5. `styleDna` on TodayLook is display projection, not scoring input — must not be cited as profile-driven ranking.
6. `GenerationStage` durations (800ms mock-data) vs real single-request derive (no staged progress) — check which UI consumes stages; if shown as timed progress, it's theater (verify before wiring claims).
7. CURRENT_STATE M13/M9 entries consistent (deterministic, read-only, no commit) — no conflict found.

# 24 OSI Status

A UI GREEN (pickers/loading/empty/error/save/regen all real; fav/share/edit absent = GRAY sub-items) · B Navigation GREEN (typed extras, missing-data screens, replace-to-result) · C Flutter arch GREEN (contract repo, never-throw client, once-guards) · D HTTP GREEN (200/204+header/422/503 mapped; 12s) · E FastAPI GREEN (validate→derive→200/204, TRX-2) · F Auth GREEN (JWT+owner scoping+OW-1) · G Generator GREEN (pure deterministic; NO provider → no BLUE needed) · H Wardrobe GREEN (subset reads, owner pages) · I Preferences YELLOW (occasions real; mood/fit/palette inert) · J AnalyzeMyStyle RED scoring / BLUE-display on TodayLook only (PARTIAL overall → YELLOW) · K Garment YELLOW (3/7 attrs survive; rest lost/unused) · L OutfitAnalysis RED (both directions unwired) · M SavedLooks GREEN (validated+idempotent+signal) · N TodayLook GREEN (shared engine+event+styleDna) · O Events GREEN (dual systems, both real) · P Learning YELLOW (save-signals real, zero consumers, preference dead) · Q Guest YELLOW (honest, pre-generation) · R Errors GREEN (only honest paths) · S Security GREEN · T Tests GREEN (contracts+boundary; PG-gated gaps noted) · U Docs YELLOW (7 conflicts above).

# 25 P0–P4 Findings

- P0: preference sub-score dead on all live paths (`frozenset()` ×3 — personalization mechanism present but unwired; either wire or remove to avoid false claims); rec-screen missing guest check (defense-in-depth; currently unreachable-by-construction).
- P1: mood/fit/palette have no backend effect (controls promise what scoring doesn't deliver); Scan↔Generate unwired both ways; `See Recommendations` context loss (D3, still open); guest pre-generation block vs intended use-then-gate.
- P2: no favorite/share/edit/swap on rec screen; alternatives computed-but-unsurfaced; `GenerationStage` timed theater if rendered; empty-reason header missing on old backends → generic copy (handled).
- P3: styleDna display-only (don't oversell); imageRef/wear-history/favorites-beyond-+5 unread; garment pattern/style/fit lost at save (schema I); latest-wins profile overwrite (D1, affects future scoring if profile ever wired in).
- P4: doc conflicts §23; PG-gated tests skipped here; seed-collision best-effort documented (fine).

# 26 Connection-Only Opportunities

Generate↔Wardrobe CONNECTED (subset; extend reads: wear, imageRef — NO new arch) · ↔Garment PARTIAL via wardrobe (direct: pass observation IDs? needs mapping decision — NO new arch) · ↔AnalyzeMyStyle/↔style_profile NOT CONNECTED scoring-side (read `GET /me` + add body/style terms? needs product contract — NO new arch) · ↔Preferences CONNECTED occasions (mood/fit/palette: define terms or drop controls — NO new arch) · ↔OutfitAnalysis NOT CONNECTED (forward snapshot/runId as prefs/seed; save rec WITH analysis source_run_id via M7 — NO new arch) · ↔SavedLooks CONNECTED · ↔TodayLook CONNECTED (shared engine; unify rec-screen? optional) · ↔Events CONNECTED (both systems; dedup decision optional) · ↔Learning write-via-save only (wire preference IDs + define consumer — NO new arch).

# 27 Final Data Flow

```
Analyze My Style ──writes──▶ style_profile ──reads──▶ Hairstyle/Grooming [CONNECTED]
        │                              ║
        │ (image pass TRX-6)           ║ scoring-read by Generate/Today/Event? [NOT CONNECTED]
        ▼                              ║ display-projection by TodayLook (styleDna) [PARTIAL]
Outfit Analysis ──writes──▶ style_profile [CONNECTED]   runs/signals [CONNECTED] ──▶ consumers [NOT CONNECTED]
        ║──▶ Garment [NOT CONNECTED] ║──▶ Wardrobe [NOT CONNECTED] ║──▶ Generate [NOT CONNECTED] ║──▶ Saved Looks [NOT CONNECTED]
Garment Analysis ──confirm-save──▶ Wardrobe (category/color/material/name/imageRef) [CONNECTED, pattern/style/fit LOST]
Wardrobe ──reads(id/cat/color/mat/fav/name)──▶ Generate Outfit [CONNECTED] ──▶ Saved Looks (#42, validated+idempotent) [CONNECTED] ──▶ look_saved+day [CONNECTED] ──▶ scoring-consumers [NOT CONNECTED]
Preferences (preferred_occasions) ──▶ Generate/Today/Event scoring (+5 term) [CONNECTED]; mood/fit/palette ──▶ prose only [PARTIAL]
Events ──▶ Event-outfit derive (#30, no save) [CONNECTED] + builder prefill [CONNECTED] + R36 prefs write [CONNECTED]
TodayLook ──▶ derive (#31/#32, event+styleDna) [CONNECTED] ──▶ save (#33) [CONNECTED]
Guest ──▶ build inputs [CONNECTED] / derive+result+save [NOT CONNECTED — pre-generation gate]
```

# 28 Recommended Next Investigation

1. Live PG run of M13/M9/M8C suites (confirm 204-reasons/ownership/determinism live; nothing in code suggests failure).
2. `GenerationStage` UI audit (timed theater vs real progress) — open question from §23.6.
3. Preference-wiring decision (wire `resolve_preferred_item_ids` into derive calls vs remove mechanism) — kills the P0 dead-mechanism.
4. Mood/fit/palette product decision (score terms vs control removal) — biggest honesty gap in builder UX.
5. Scan→Generate spike (snapshot/seed forwarding shape; `outfit-N` seed already supports external variety keys).
6. Guest-derivation policy (anonymous derive = new; reposition = connection-only) — same decision as D3, now with three gated surfaces inventoried.

---

## Appendix — Source index (spot-verified)

Backend: `application/outfits.py:60-164 (validate/select/load/prefs), 181-267 (_to_recommendation), 268-420 (GenerateOutfit+derive), 433-533 (SaveOutfit)` · `application/today.py:1-120 (contract), 143-260 (derive+styleDna), 272-345 (rec)` · `application/events.py:111-139 (R36), 320-419 (GenerateEventOutfit)` · `domain/services/analysis_rules.py:1195-1299 (contract/skeletons/score-compose), 1311-1462 (rank/select/generate), 1466-1648 (score terms)` · `api/routers/outfits.py:1-130` · `api/schemas/outfits.py` · `application/saved_looks.py:76-205` · `domain/ports/repositories.py` (OutfitRecommendation etc.).
Flutter: `outfit_builder/{outfit_client:1-202, outfit_models (rec/component/request/saved/result/failure), outfit_repository}` · `presentation/{build_outfit_screen:1-240, outfit_generation_screen (derive+204+retry), outfit_recommendation_screen (regen+save)}` · `widgets/outfit_builder_widgets` · `outfit_builder_mock_data (BuilderOption×16, GenerationStage)` · `app/router/app_router:237-299` + `route_names` · `events/event_details_screen:115-130,206,379-443` · `home/presentation/daily_outfit_screen:185-284` + `today_look_{client,models,repository}`.
Tests: backend `test_m13_outfits_api`, `test_m11_p3`, `test_m8c_event_outfit_api`, `test_m9_today_look_api` · Flutter `outfit_builder_{api,screens}_test`, `today_look_{api,screens}_test`, `events_{api,screens}_test`, `assistant_outfit_wardrobe_wiring_test`.
Skills lens: `flutter-apply-architecture-best-practices` (carried; no code emitted).
