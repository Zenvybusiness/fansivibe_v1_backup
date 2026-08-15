# Fansivibe Current Truth

## Section 2 — Current Truth (Truth Ledger)

| Claim | Classification | Evidence/Source | Confidence | Remaining Uncertainty | What Could Change Our Mind |
|---|---|---|---|---|---|
| Hairstyle recommendation flow works end-to-end (Flutter→API→DB→Engine→Result) | FACT | 384 Flutter tests pass; 85 backend tests pass; STEP 7 scenarios 1-15 validated; `alembic upgrade --sql head` clean | High (≥0.9) | Whether it works with real PostgreSQL live server | Running DB-backed tests with PostgreSQL |
| Save with Idempotency-Key is TRX-3 all-or-nothing | FACT | 9 unit tests for SaveRecommendation; TRX-3 guard in repositories; `Idempotency-Key` replay returns original/409 | High (≥0.9) | None identified | — |
| Analysis submit is NOT idempotent (202 + {run_id} each time) | FACT | API contract §4.2; `CreateHairstyleRun` returns 202 {run_id}; not marked idempotent in contract | High (≥0.9) | — | — |
| Decision engine has 7 stages (context, candidates, filter, score, rank, explain, confidence) | FACT | `analysis_rules.py` source code; 18 unit tests in `test_decision_engine.py` | High (≥0.9) | — | — |
| 4 hairstyle looks in catalog seed | FACT | `app/data/catalog.py` `HAIRSTYLE_LOOKS` (4 looks); knowledge tests verify | High (≥0.9) | — | — |
| Owner scoping 404-not-403 on user-owned endpoints | FACT | OW-1 in DEC-001; enforced in SQL repos; API contract C-7; test verification | High (≥0.9) | — | — |
| Bearer dev auth seam (D-AUTH-1) | FACT | `app/api/deps.py` maps Bearer `dev` token to seeded user; test infrastructure | Medium (0.7) | If/when real auth replaces dev seam | Auth provider swap |
| 65% visual / 35% content card rule for recommendations | OBSERVATION | Design system spec; `HairstyleResultScreen` implements 65/35 layout; UI audit | Medium (0.6) | Whether rule is enforced or just observed in hairstyle screen | Design system review |
| Flutter must not depend on AI providers directly | FACT | DEC-003; all AI goes through FastAPI backend | High (≥0.9) | — | — |
| PostgreSQL is the intended primary database | FACT | DEC-004; schema has 8 tables with approved types/constraints | High (≥0.9) | — | — |
| Grooming input asks for 4 feature groups (face shape, beard style, density, color) | OBSERVATION | `grooming_input_screen.dart` source; grooming E2E validation | Medium (0.6) | If grooming flow changes | Grooming feature review |
| All unrelated screens unchanged after STEP 7/8 work | OBSERVATION | `git diff HEAD` empty for home/discover/wardrobe/profile/outfit_scan/stylist/shared/router_shell | High (≥0.9) | — | — |
| "Users need this" — founder assumption about hairstyle demand | HYPOTHESIS | Not tested with real users; assumption behind product existence | Low (0.3) | Everything — requires user validation | Real-user experiment |
| Recommendation explanations are grounded (never invented) | SUPPORTED | Engine uses catalog reasons + score signal; never fabricates result; `KnowledgeError` on empty catalog | High (≥0.8) | If LLM enrichment changes wording | LLM enrichment behavior |
| Confidence derived as 50% data completeness × 50% top-pick decisiveness | FACT | `derive_confidence()` in `analysis_rules.py`; 18 engine tests verify | High (≥0.9) | — | — |
| `faceProfileRef` only; face-image upload deferred behind MS10.3 | FACT | D-2 in DEC-001; analysis submits `faceProfileRef` only; no image upload until MS10.3 | High (≥0.9) | — | — |
| `/v1/feedback` remains gated/unmounted (M11) | FACT | Verified in `main.py`; only `look_saved` signal is committed; no fake 200 | High (≥0.9) | — | — |
| Mock data used by default when no backend result | FACT | Client falls back to offline mock; `fromRunResult` with null result → mock | High (≥0.9) | — | — |
| Discovery shows personalized looks with match scores | OBSERVATION | `DiscoverScreen` + `LookDetailsScreen` implement match scoring; but whether users engage | Medium (0.5) | User engagement data | Analytics from real users |
| Style DNA, Style Score, progress in Profile | OBSERVATION | Profile screen exists with these concepts; but not validated with users | Medium (0.5) | — | User feedback |
| App feels "premium, modern, intelligent, warm, personal, trustworthy" | INTERPRETATION | Design system targets these qualities; subjective user perception | Low (0.4) | Entirely subjective | User testing on perceived qualities |
| Analysis run polling works (30 attempts) | FACT | Client `pollAnalysisRun` with injectable interval; tests verify terminal behavior | High (≥0.9) | — | — |
| Learning signal `look_saved` committed in same TRX-3 as save | FACT | `SaveRecommendation` UC-15; TRX-3 all-or-nothing; 9 unit tests verify | High (≥0.9) | — | — |