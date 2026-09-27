# AI Architecture — Phase 0 Baseline Audit (AUDIT ONLY, FROZEN)

> Status: PHASE 0 COMPLETE. No source modified. No fixes, migrations, installs, commits, or pushes.
> Date (UTC): 2026-09-27. Repo: `fansivibe_v1_backup`. Source of truth: current code. Prior audits D1–D5 referenced, key claims re-verified (spot-checks §15).
> Convention: VERIFIED FACT (cited file:line) · INFERRED (labeled) · DOCUMENTED INTENTION (labeled) · MISSING/UNKNOWN (labeled).

---

# 1 Executive summary

Fansivibe is a Flutter (no external state lib: setState + 5 ChangeNotifiers) + FastAPI (router → deps/auth → use-case → SQLAlchemy repo → Postgres 21 migrations) + Ollama-vision (5 image surfaces, fail-closed) system. Deterministic rules engines do ALL ranking (outfit generate, TodayLook, event outfit, ForYou +0.03); no behavioral learner exists. Verified baseline: `flutter analyze` 0 issues; flutter 1063 pass / 19 pre-existing fails (same files as stashed-HEAD proof); backend 915 pass / 537 skip / 3 fail — all 3 one CRLF-checkout hash artifact (environmental, tree-clean). D1–D5 claims re-verified WITHOUT exception (one line-number drift: none — frozenset still outfits:392/events:389/today:188). Freeze: the architecture below is the baseline; Phase 1 must connect, not replace.

# 2 Repository map

```
fansivibe_v1_backup/
├── newproject/flutter_application_1/  # FLUTTER APP ROOT (lib/, test/, pubspec.yaml)
│   └── lib/{app(router,shell),core(config),shared(auth,utils,components,theme),
│       features/[auth|home|discover|stylist|wardrobe|outfit_scan|outfit_builder|
│       hairstyle|grooming|events|style_profile|profile|learning|assistant|
│       feedback|knowledge|trending]}  # feature-first; presentation/data(/domain); cross-feature imports forbidden
├── backend/                           # FASTAPI ROOT (app/main.py; 341 tracked files)
│   └── app/{api/routers(14: analysis,assistant,auth,events,feedback,knowledge,learning,
│       looks,outfits,reasoning,trending,users,wardrobe), application(use-cases),
│       domain(services/rules,ports,value_objects), infrastructure(db/models+repos+session),
│       ai(adapters,reasoner,ffo*), config, data(ffo corpus), models(pydantic chat), telemetry, trending}
│   └── alembic/versions (21 linear: base→0001…0006→0008…→0022; 0007 numbering-only) + tests/ + deploy/ + Dockerfile
├── docs/ (product, api, architecture, backend, validation)  # many STALE — see §14
├── .agents/skills (20+ flutter/dart skills) · AGENTS.md (workflow) · CURRENT_STATE.md · DECISIONS.md
└── dumps (*.dump 0-byte placeholders) · .pytest_cache · no debt-service/queue infra (sync in-request; no Celery/Redis)
```

Generated/cache excluded: `build/`, `.dart_tool/`, `__pycache__/`, `.venv/` (untracked), `edge shots/*.png`.

# 3 Frontend architecture (VERIFIED FACT)

Screens/routes: 5-tab shell (Home/Discover/Stylist/Wardrobe/Profile) + flows (photo-capture→analysis, scan-outfit→processing→analysis, wardrobe→add-category→add-item, build-outfit→generation→recommendation, events, look-details, daily-outfit, hairstyle×4, grooming×4). go_router `^17.2.3`, typed extras, missing-data screens, guest-safe shell + button-level `promptGuestSignIn` gates.
State: StatefulWidget/setState dominant; 5 ChangeNotifiers (`LearningService`, `AssistantService`, `HairstyleService`, `GroomingService`, `FashionReasoningViewModel`); static singletons (`AuthSession`, `LocalStorage`, `UserSession`, `SecureTokenStorage`); NO Provider/Riverpod/Bloc/GetIt (pubspec proves: go_router/camera/http/http_parser/image_picker/shared_preferences/flutter_secure_storage only). Repos: per-feature contract + server/local impls (wardrobe), injectable clients (tests-only ctor seams). Local: SharedPreferences device mirror + guest truth; SecureStorage token only. DO NOT REPLACE — freeze.

# 4 Backend architecture (path per domain)

`client → router → get_current_user_id/get_db → UseCase → *RepositorySQL → Postgres; owner-scoped everywhere (OW-1 404)`. Verified paths: auth (register/login/logout/social, resolve_session) · users (/me GET/PATCH, profile view) · wardrobe (CRUD + insight + wears + summary; vocab-422) · analysis ×4 (sync create→adapter→engine→complete/fail; 202 semantic) · outfits (#41 derive TRX-2 / #42 save→M7 TRX-3) · looks (today #31/#32/#33, saved CRUD, feed, for-you +0.03, detail) · events (CRUD + R36 prefs + #30 derive) · learning (read-only summary) · feedback (#35 append-only) · assistant (card-feedback #17 ONLY — no server chat; chat is Flutter-local+offline) · reasoning (`POST /v1/reasoning`, `/query`; FashionReasoner port→Ollama; benchmark harness Ollama-only, never in suite) · knowledge (vocab/catalog, attributeless rows) · trending (stateless, no DB). No two same-named features share code unless cited (derive trio shares ONE pipeline — verified).

# 5 Database architecture

21 migrations, 20 tables + `alembic_version`, 2 SQL fns (`complete/fail_analysis_run`, write-once). A. Tables: users, user_sessions, user_state, looks, run/signal_types, analysis_runs, saved_looks, learning_signals, feedback_events, activity_days, wardrobe_categories/colors/materials, wardrobe_items (+image_ref JSONB), wear_groups/events, event_types, user_events. B/C. Source-of-truth: users identity; user_state single-row profile+prefs (REPLACE semantics); wardrobe owned facts; runs append-only history; saves frozen snapshots; signals/feedback/wear/days append-only history; vocab ownerless. D. All user tables `user_id→users CASCADE`; vocab RESTRICT; saves look/run SET NULL; NO run↔run links. E. JSON(B): style_profile(5 keys), preferences(occasions), input_media/result/error, snapshot, image_ref, flags. F. Unused tables: NONE structurally (wear* empty only because no UI calls). G/H. Written-never-consumed: image_ref, provenance, 4/5 signal types, feedback rows, run results (beyond single-shot screens), skin/body/style `""`. I. Consumed-never-written: NONE (all scoring inputs have writers) except `preferred_item_ids` resolver input (fed empty). Indexes: user+created/occurred/worn/date + UQs (auth-pair, token-digest, save/feedback/wear keys, activity day). No TTL/purge anywhere.

# 6 API map (deltas vs D1–D4; full per-endpoint detail in D1§8/D2§5/D4§4)

14 routers; deltas newly mapped: assistant = card-feedback ONLY (no chat endpoint — INFERRED: chat intentionally local); reasoning ×2 (query auth OPTIONAL session-first — only optional-auth endpoint in system); auth = register/login/logout/social, NO refresh (docstring-verified), logout revokes (204); knowledge = vocab/catalog reads; trending = stateless reads. Mismatches reconfirmed: OpenAPI 413/503 unreachable on analysis (oversize→422; vision-fail→failed-run); `image + typed fields` claim vs image-only; `sections/detectedItems` vs snapshots; Discover filters vs attributeless catalog. Flutter callers 1:1 per surface (verified); idempotency on saves/feedback/wears/auth-register (analysis/generate/event-CRUD: none — generate safe by read-only).

# 7 Auth/guest baseline (VERIFIED FACT)

LOGIN/REGISTER (public, credentials→session), LOGOUT (auth, revoke 204), SOCIAL; NO refresh (tokens: `auth_expires_in_s=3600`, re-login on 401 via `notifyUnauthorized` → entry). Storage: SecureStorage token; `AuthSession.effectiveToken('dev')` session-first; dev-token accepted ONLY if `FANSIVIBE_ALLOW_DEV_TOKEN` (deps.py:76). Guards: shell browsable (incl. stylist/wardrobe/profile), `/assistant,/reasoning` blocked; per-button `promptGuestSignIn` (no auto-POST, pending-intent path-only/24h). Guests CAN: browse, capture/preview, local wardrobe/prefs/saves/score. CANNOT: any POST (analyses, generate, derives, saves — all pre-gated or 401). Migration (verified impl+20/20 tests): wardrobe imageless+dedup, prefs additive, Merge/Keep/Discard + ledger + retry; face/signals/titles/styleType/vibe/blob stay local.

# 8 AI architecture (per-path; CODE vs RUNTIME)

| Path | Adapter → provider/model/env/20s | Output → persist → consumer | Runtime |
|---|---|---|---|
| AnalyzeMyStyle/hairstyle-image | OllamaVisionAppearanceAdapter → `FANSIVIBE_VISION_HOST`/`MODEL` (dflt llama3.2-vision; needs vision-capable) | face_shape → TRX-6 → gates/display | CODE ✓ / PROVIDER UNVERIFIED (D) |
| Scan/Outfit | SAME adapter (face only) → recommend_hairstyle | snapshot → TRX-6+signals → result screen | same D |
| Garment | OllamaVisionGarmentAdapter (7 attrs, face-portrait guard) | snapshot verbatim → prefill→save | same D |
| Grooming-vision | appearance adapter (face gate) | snapshot | same D |
| Assistant chat | Flutter-local + offline + reasoning model (server) | chat text only | server reasoning = D |
| Reasoning | FashionReasoner→Ollama (`OLLAMA_HOST/MODEL`, 60s, retries, concurrency cap) | validated response | D |
| Generate/Today/Event/ForYou/scores | NO AI (pure functions — verified zero model imports on paths) | — | independent ✓ |

All vision: single-attempt, 6-reason taxonomy, kill-switch `DISABLE_VISION`, bytes ephemeral (tests assert no leak). Fail-closed terminal runs + honest UI everywhere. No embeddings on live paths (ffo_* unused).

# 9 Generate architecture (condensed; full D4 §§6–7)

Pipeline: lexical-first-3 IDs × 5 skeletons (tops+bottoms mandatory, cap 25) → legality (pairings) → score 0–100 (coverage 8/cat; color neutral-gate ±10; natural-mat +5; season ±5; formality +5; all-members-occasion +5; preference +5/match; favorite +5/member) → rank (score,count,lexical) → winner/sha256-seed → templated prose (AI-0). USED: wardrobe subset + occasion lists + favs. INERT: mood/fit/palette (echoed), preferred_item_ids (`frozenset()`×3 — dead), style_profile (scoring), imageRef/wear, signals/feedback/saves. 200/204+header/422/503-defensive; TRX-2 zero-write; save→M7 validated+idempotent.

# 10 Personalization matrix (condensed from D5 §20)

Real effects ONLY: preferred_occasions +5 term (A) · wardrobe 5-field ranking (A) · favorites +5 (A) · event-type occasions (A) · face_shape gating (A) · ForYou +0.03 saved-code boost, 2 contexts (B) · styleDna/display/local-reasons (display-only B/H). Stored-but-inert: skin/body/style, mood/fit/palette, imageRef/provenance, runs/results, 4/5 signals, feedback, wear(empty), pattern/style/fit (lost), dislikes/seasons/weather (nonexistent). See D5 §20 for the 16-row table.

# 11 Event/learning matrix

WRITE→READ→EFFECT: look_saved → labels + ForYou(2ctx) → +0.03 (CONSUMED, narrow) · analysis_updated/outfit_selected/cards → labels only (WRITE-ONLY) · local 7-type vocab → local score/reasons (CONSUMED, device) · feedback → nothing (DEAD behaviorally) · wear → summary APIs, no UI (DEAD by disuse) · activity_days → counts/streak (READ-ONLY display) · events → derives + R36 (CONSUMED) · saves → ForYou + resolver(dead) (PARTIAL). No learner, no weights (VERIFIED FACT: no training loop in repo).

# 12 Security baseline (VERIFIED FACT, no change)

JWT Bearer→user_id; dev-token gated by env flag; owner-scoping on every user read/write/list (404-foreign OW-1; saves re-validate owned UUIDs); UQ idempotency keys; upload validation (type-set + 20MB + readable → 422, both layers); images hashed/ephemeral, never logged (test-asserted); errors carry run_id only; guest tokenless + local-only; migration dedups + ledgers; secrets: only `.env.example` + `key.properties.example` tracked (verified `git ls-files`); SecureStorage/SharedPrefs split correct. Pre-existing notes (frozen, not fixed): register-key UQ race, profile wholesale-replace, string-only provenance, analysis double-charge (no idempotency), 404-timing oracle (accepted), CRLF-hash artifact (§14).

# 13 Test baseline (RAN — read-only, unmodified)

- `flutter analyze lib test`: **0 issues** (27.2s).
- `flutter test`: **1063 pass / 19 fail** — files: clothes×6, auth_screens×5, for_you×4, guest_phase2×2, widget×2 = SAME pre-existing set as stashed-HEAD proof (prior entry counted for_you×5/20 total; current file-set identical, count 19 — variance is one for_you case, INFERRED flaky-oracle, NOT a regression: zero files outside the known set, zero AI-stylist/builder/learning/conversion files).
- backend `pytest tests -q`: **915 pass / 537 skip / 3 fail** (49.68s) — all 3 = `TestFrozenArtifactHashes` (canary/soak/staging-observability) on ONE root cause: `reasoning_prompt.py` pinned-sha vs CRLF-checkout bytes (`core.autocrlf=true`; tree CLEAN per `git diff`, backend tracked 341 files). ENVIRONMENTAL, pre-existing-at-checkout, unrelated to product code (file untouched; prior runs with LF checkouts passed 907–918/0).
- DB-gated tests skip without PG (537) — live PG E2E unverified here. No test modified.

# 14 Documentation inconsistencies (CODE WINS; do not fix in Phase 0)

Product ("personalized AI platform", "AI-powered") vs 1 narrow consumer + display-local reasons — OVERCLAIM. 12 stale API claims (D3 §19S: sections/detectedItems, typed-fields, mock-NOW, async-workers, addSavedLook@260-absent, 413s). D4 §23 (mood/fit/palette effect, alternatives unsurfacing, preference-overclaim, styleDna-as-ranking, stage-theater). `item_added`/`outfit_selected` naming. `matchScore`≠confidence. Discover filters vs attributeless catalog. "History/learning" prose vs write-only signals. CURRENT_STATE/DECISIONS preservation entries accurate as of write dates (no new conflicts found).

# 15 Domain 1–5 verification (claim → re-check → status)

- D1 appearance-not-garment: adapters per-route (`analysis.py:34-35,113,223,265`) + face-only prompt — CONFIRMED. Save-Profile noop (no client/repo refs in screen) — CONFIRMED. Untyped parse — CONFIRMED (file unchanged).
- D2 garment-in-wardrobe + strict parse + no side-writes (ctor deps) — CONFIRMED (files unchanged per git status).
- D3 static Details + unwired pairs + write-only learning — CONFIRMED (screens/routers unchanged).
- D4 deterministic + mood/fit/palette inert + `frozenset()` STILL at outfits:392/events:389/today:188 (exact lines — zero drift) — CONFIRMED.
- D5 3-mechanism verdict + `item_added` absent (only docstring hit repo-wide — re-grepped) + ForYou boost + guest-migration scope — CONFIRMED.
- INFERRED (not re-run): stashed-HEAD failure proof (rely on prior entry + identical file-set); live vision/face-photo (never run — needs Ollama).

# 16 Current architecture diagram (text, VERIFIED)

```
Flutter(setState+5×ChangeNotifier+singletons; go_router; per-feature clients/repos; guest-local mirrors)
  ↓ Bearer(session|dev-gated) / multipart|JSON
FastAPI(14 routers; deps auth+db; use-cases; SQL repos; OW-1; idempotent saves; TRX-2/3/5/6)
  ├── Vision (Ollama ×5 surfaces, 20s, fail-closed) → runs → TRX-6 profile + signals → screens
  ├── Rules (generate/today/event/for-you + scoring; zero AI) → recs → M7 saves → labels
  ├── CRUD (wardrobe/events/prefs/saves/feedback/wears) → tables
  └── Reasoning (port→Ollama; optional-auth query; benchmark offline)
Postgres(20 tables; CASCADE-owned; RESTRICT-vocab; SET-NULL-history; JSONB facts; no TTL)
Device (SharedPrefs mirror+guest truth; SecureStorage token; intent slot; ledger)
```

# 17 Target comparison (Flutter→FastAPI→Domain→UserContext→DecisionEngine→Recommendation→Action→Ledger→Derived→Context)

A. EXISTS: Flutter→FastAPI→domain modules→recommendation→action→ledger-rows→derived-reads (occasions, wardrobe rank, ForYou boost, summaries). B. PARTIAL: User Context (profile/prefs/wardrobe real BUT scoring-blind spots: mood/fit/palette, body/style facts, taste IDs); Decision Engine (deterministic ranker real BUT no learning/weights); Event Ledger (rows real BUT mostly unledgered-to-decisions); Derived State (styleDna/summaries real BUT display-scoped). C. REUSABLE DISCONNECTED: preferred_ids resolver, feedback rows, wear ledger+summary, run snapshots, imageRef/provenance, style facts, analysis→generate links, guest taste (post-auth seed). D. MISSING: behavioral learner, dislike model, anonymous derive, multi-item decomposition, outfit verdicts, run-history UI, wear logging UI. E. GENUINELY NEW: learner infra, anonymous-session design, multi-subject vision contract, verdict engine (D5 §23 — conservative list stands).

# 18 Reusable existing components (Phase 1 inventory)

`GarmentClient`+poll · `OutfitBuilderClient` (never-throw, idempotent saves) · `resolve_preferred_item_ids` · `GetForYouFeed` boost pattern · `SaveRecommendation/SaveOutfit` (validated, TRX-3) · `GenerateOutfit` + shared pipeline (event/today variants) · `get_style_profile`/`GET /me` · `submitCardFeedback` contract · wear log/summary APIs · run GET/history · pending-intent + Merge/Keep/Discard + migration service · strict parsers (`GarmentAnalysisResult`) as templates · vocab/knowledge endpoints · idempotency-key helpers (×4 features) · honest empty/error UI patterns (204+header, GuestSignInCard).

# 19 Genuine architecture gaps (everything else is connection-only)

Anonymous derivation (FK/owner model forbids); multi-garment decomposition (single-subject contracts); outfit-level verdicts (no engine); online learning (no features/labels loop); negative preferences (no storage); first-class pattern/style/fit (or JSONB-sidecar to avoid); guest-vision policy (product call first). Plus frozen risks: P0 casts, wholesale profile replace, analysis double-charge, register-key race.

# 20 Phase 1 prerequisites (no implementation until owner approves)

1. Owner product calls (guest-derivation policy; mood/fit/palette semantics; preference-wiring; Scan→Generate shape; feedback semantics) — decide BEFORE code. 2. Vision provider provisioned + live face/garment matrix (unblocks all D). 3. PG-backed CI run (unskip 537; confirm M13/M9/M8C live). 4. CRLF decision (`.gitattributes` text/eol vs re-pin hashes — currently 3 red). 5. Doc-freeze note: D1–D5 + this file are the frozen baseline; any Phase 1 change must cite the §15 verification lines it alters.

---

## Appendix — verification index (Phase 0 direct evidence)

`git status` (tree state) · root/backend/flutter listings · `pubspec.yaml` (no state lib) · 5×ChangeNotifier grep · 14 routers + assistant/reasoning/auth routes · `deps.py:59-76` (dev gate) · `git ls-files` secrets scan · adapters import map · Save-Profile grep (noop) · `frozenset()` ×3 exact · `insert_look_saved` 5 call sites (no item_added) · `flutter analyze` (0) · `flutter test` (1063/19, file-set match) · `pytest` (915/537/3-CRLF; `git diff` clean + `autocrlf=true` + 248/248 CRLF bytes) · auth.py docstring (no refresh) · reasoning optional-auth (:117).
Prior audits: D1 §§1–42 · D2 §§1–25 · D3 §§1–23 · D4 §§1–28 · D5 §§1–33 · CURRENT_STATE conversion/M14/Phase4 entries.
Skills lens: `flutter-apply-architecture-best-practices` (carried; no code emitted).
