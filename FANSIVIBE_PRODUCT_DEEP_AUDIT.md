# Fansivibe Product & Engineering Deep Audit

- Date: 2026-10-24
- Repository: `fansivibe_v1_backup`
- Scope: Flutter client, FastAPI backend, PostgreSQL schema, Ollama vision integration, the four capabilities, Stage 1 person understanding, shared person model, decision quality, feedback loop, engineering quality.
- Method: static code and documentation inspection only. No runtime, database, model, or device verification was performed. Every finding below is code-grounded; items not provable from code are marked UNVERIFIED.
- Code changes: none. This document is the only artifact.

## Classification Legend

| Label | Meaning |
|---|---|
| VERIFIED | Implemented and wired end to end in code. |
| PARTIALLY IMPLEMENTED | Core exists, but a required input, output, persistence step, or consumer is missing. |
| MISSING | No implementation, or the implemented path does not perform the claimed function. |
| UNVERIFIED | Could not be proven by static inspection. |
| DESIGN RECOMMENDATION | Proposed change, not current behavior. |
| PRODUCT HYPOTHESIS | Belief to validate, not an engineering fact. |

Priority: P0 blocks product truth or user trust; P1 blocks meaningful personalization; P2 degrades quality or maintainability; P3 polish.

---

## 1. Executive Summary

Fansivibe has a credible engineering skeleton and a much weaker product truth than its UI copy claims.

What is genuinely built:

- Authenticated, owner-scoped analysis runs with idempotency, image validation, and honest failure codes.
- A deterministic hairstyle engine driven by face shape and explicit preferences, with an LLM used only for wording.
- A deterministic outfit scorer over wardrobe and catalog candidates with grounded palette/fit/preference/occasion reasons.
- Wardrobe CRUD, wear logging, saved looks, and a typed try-on mock with explicit synthetic disclosure.
- A guest-safe read experience and an offline assistant that refuses to invent scores.

What is not built:

- Outfit Scan does not analyze outfits. It runs the hairstyle engine.
- Initial Scan is a demo preview. Its result is never persisted, and guest "Save My Progress" saves an intent, not the analysis.
- The person model contains face shape plus three empty-by-design attributes. There are no measurements, proportions, hair properties, color profile, goals, budget, or climate.
- Personalization surfaces mix real backend data with static editorial content, static match badges, and local-only saves.
- The learning loop is mostly write-only. Three of four capabilities have no recommendation-level feedback, and stored signals do not drive ranking.

Top P0 findings:

| ID | Finding | Evidence |
|---|---|---|
| P0-1 | Outfit Scan is a mislabeled hairstyle scan and never evaluates clothing. | `backend/app/application/analysis.py:332`; `outfit_analysis_screen.dart`; `docs/api/SCAN_API.md` S-1 |
| P0-2 | Initial Scan result is never persisted; guest save only records a return route. | `your_analysis_screen.dart:86-145`; `ai_analysis_screen.dart:18-21`; `post_auth_flow.dart` |
| P0-3 | "Analyzing skin tone" and "Applying Style DNA" are false stage claims; the vision adapter extracts face shape only. | `hairstyle_mock_data.dart:48,53`; `outfit_builder_mock_data.dart:141`; `vision_appearance_adapter.py` |
| P0-4 | Discover/Home present static editorial content and static match scores as personalized or trending. | `home_screen.dart:522-532`; `existing_user_home_widgets.dart:1420,1638`; `discover_screen.dart:746-877` |
| P0-5 | Feedback and learning are largely inert: no feedback on hairstyle, outfit builder, Today, or Discover recommendations; backend signals are not consumed for ranking. | `saved_looks_screen.dart`; `backend/app/application/learning.py:150-152` |
| P0-6 | Style Score measures usage volume, not style quality, but is presented as personal style quality. | `backend/app/application/learning.py:150-152`; `backend_summary_cards.dart` |

Verdict by capability:

| Capability | Verdict |
|---|---|
| Initial Scan | PARTIALLY IMPLEMENTED (preview only, not persisted) |
| Hairstyle Scan | PARTIALLY IMPLEMENTED (real engine, thin catalog, overstated copy) |
| Outfit Builder | PARTIALLY IMPLEMENTED (real scorer, no mood/style-profile use) |
| Outfit Scan | MISSING as an outfit capability; PARTIAL as a duplicate hairstyle scan |
| Stage 1 person understanding | PARTIALLY IMPLEMENTED (single-signal, no fusion) |
| Shared person model | PARTIALLY IMPLEMENTED (4 fields, 1 populated) |
| Decision quality | PARTIALLY IMPLEMENTED (grounded reasons, static/fallback claims) |
| Feedback loop | MISSING in the closed-loop sense |
| Engineering quality | VERIFIED foundation, PARTIAL maintainability |

---

## 2. Repository & Architecture Map

### 2.1 Backend

Layered FastAPI application:

- `backend/app/api/routers/*`: HTTP contracts for analysis, outfits, wardrobe, events, feedback, learning, auth, users, discovery, knowledge, assistant, reasoning, try-on, trending, trend analysis.
- `backend/app/application/*`: use cases. Largest: `analysis.py` (49 KB), `outfits.py`, `today.py`, `for_you.py`, `learning.py`, `tryon.py`.
- `backend/app/domain/*`: rules, value objects, ports. `analysis_rules.py` is 93 KB / 2299 lines and owns hairstyle, grooming, outfit scoring, feedback context, and ranking helpers.
- `backend/app/infrastructure/*`: SQL repositories, Ollama adapters, knowledge source, external collectors.
- `backend/app/ai/*`: vision adapters, reasoning engine, prompt and admission guards.
- `backend/app/data/catalog.py`: static knowledge catalog (4 hairstyle looks, 4 grooming looks, 9 occasions, empty item references).
- `backend/alembic/versions/*`: schema through 0028 applied plus staged 0030-0032.

Strengths:

- Clear auth dependency (`deps.py`), owner checks in repositories, idempotency on writes.
- Typed domain results and explicit failure codes.
- Analysis runs persisted with hashed media references rather than raw images.
- Try-on mock is honest about being a mock.

Risks:

- `repositories.py` is about 116 KB and mixes many aggregates.
- `analysis_rules.py` combines unrelated domains and is the single point of failure for multiple capabilities.
- Static catalog is too small to support the personalization claims.
- Documentation contracts drifted from implementation (see 7.4 and 12.3).

### 2.2 Flutter

- Feature-first modules under `newproject/flutter_application_1/lib/features/*`.
- `go_router` with `auth_guard.dart` and `route_names.dart`.
- Repository/client pattern per feature; most screens never call HTTP directly.
- `LearningService` is a device-local signal store; `AuthSession` is the session boundary.
- Design system tokens are reused; 65/35 card rule is respected in the audited recommendation cards.

Strengths:

- Guests can browse all five tabs and nested read screens; writes are gated at buttons.
- Offline assistant is deterministic and avoids fabricated scores.
- Analysis clients surface failures instead of fabricating success.

Risks:

- Several "personalized" widgets fall back to static editorial data or local device state.
- Mock processing stages are rendered as if real analysis steps occurred.
- Discover favorites are local-only, while telemetry records a save event.

---

## 3. End-to-End User Journey Audit

| Journey | Current behavior | Status | Main gap |
|---|---|---|---|
| First open, unauthenticated | Entry screen; can sign in, create account, or continue as guest. | VERIFIED | None material. |
| Guest onboarding vibe select | Local vibe stored; no account. | VERIFIED | Vibe is not part of the backend person model. |
| Initial Scan | Parallel ephemeral face + garment calls; result shown on device. | PARTIALLY IMPLEMENTED | Nothing persisted; not resumable. |
| Guest Save My Progress | Records pending intent with route `/home`; prompts account creation. | PARTIALLY IMPLEMENTED | Analysis payload is not retained; guest must rescan after auth. |
| Post-auth merge | Uploads local wardrobe and preferred occasions. | PARTIALLY IMPLEMENTED | No analysis/face/style-profile migration. |
| Hairstyle Scan (auth) | Creates analysis run, polls, stores style profile, shows result. | VERIFIED | Catalog depth, copy truth, feedback absence. |
| Hairstyle Scan (guest) | Synchronous ephemeral pass, no persistence. | VERIFIED | Expected guest boundary. |
| Outfit Builder | Reads wardrobe/profile, scores candidates, saves outfit. | VERIFIED | Mood unused; no Style DNA input; no wear/feedback. |
| Outfit Scan | Posts to outfit endpoint that runs hairstyle analysis. | MISSING as claimed | Does not evaluate clothing, proportions, or fit. |
| Today's Look | Server-derived from events, wardrobe, preferences. | PARTIALLY IMPLEMENTED | No fit confidence, feedback, wear, or weather inputs. |
| Discover Trending | Static editorial sections plus backend look feed when available. | PARTIALLY IMPLEMENTED | Static fallbacks and badges; failure states unreachable in production. |
| Discover For You | Backend personalized feed for authenticated users. | VERIFIED | Local-only favorites; fallback style-type default. |
| Save look | Saved-look backend exists. | VERIFIED in saved looks; PARTIAL in Discover | Discover heart is local only. |
| Feedback | Like/dislike only on saved looks. | PARTIALLY IMPLEMENTED | No capability-level feedback. |
| Wear logging | Available on wardrobe item details. | VERIFIED | Outfit/Today recommendations cannot log wear. |
| Try-On | Mock provider, consent, guest gate, synthetic banner. | VERIFIED as mock | Not a real try-on capability. |
| Assistant | Server chat with optional auth; offline fallback. | VERIFIED | Card feedback only; no image try-on. |

---

## 4. Capability 1: Initial Scan

### Intended behavior

Capture a photo, analyze appearance and outfit, present a personalized analysis, and save progress into the account.

### Actual behavior

- `ai_analysis_screen.dart` calls `POST /v1/analysis/outfit/ephemeral` for the face observation and `POST /v1/analysis/garment/ephemeral` for one garment, in parallel.
- No analysis run row is created. Nothing is persisted server-side.
- The result is stashed as a pending ephemeral result on device.
- `your_analysis_screen.dart` "Save My Progress" calls `recordPendingAuthIntent(action: 'save_progress', route: '/home')` and pushes account creation. It does not upload the analysis.
- Post-auth flow uploads local wardrobe and preferred occasions only.
- The initial scan therefore never becomes a stored `style_profile`; the user must redo scans after authentication.

### Findings

| ID | Finding | Priority | Classification |
|---|---|---|---|
| IS-1 | Initial analysis is not persisted. | P0 | MISSING |
| IS-2 | "Save My Progress" saves a navigation intent, not progress. | P0 | PARTIALLY IMPLEMENTED |
| IS-3 | Guest-to-auth conversion loses the scan result. | P0 | MISSING |
| IS-4 | Parallel ephemeral calls are honest but cannot support history or learning. | P1 | PARTIALLY IMPLEMENTED |
| IS-5 | Garment observation is captured but not used in any stored profile. | P1 | PARTIALLY IMPLEMENTED |

Acceptance criteria for closure:

- Authenticated initial scan creates an analysis run and writes the derived style profile in the same transaction boundary.
- Guest scan result is either explicitly discarded with clear copy or retained locally and replayed into the account after auth.
- The user can view the saved analysis later.

---

## 5. Capability 2: Hairstyle Scan

### Actual pipeline

1. Image validation and hashing.
2. Ollama vision appearance adapter extracts face shape only.
3. `recommend_hairstyle` scores 4 static hairstyle looks.
4. Confidence is derived from input completeness and score decisiveness.
5. LLM wording is optional; the ranking is deterministic.
6. Style profile is merged on run completion.
7. Result is displayed; Save Style writes a saved look.

### Findings

| ID | Finding | Priority | Classification |
|---|---|---|---|
| HS-1 | Catalog contains only 4 hairstyle looks, so recommendations repeat quickly. | P1 | VERIFIED |
| HS-2 | Reasons are static catalog text, presented as personalized. | P1 | PARTIALLY IMPLEMENTED |
| HS-3 | "Analyzing skin tone" is shown, but skin tone is not extracted or used. | P0 | MISSING |
| HS-4 | "Applying Style DNA" is shown, but no style profile is an input to hairstyle ranking. | P0 | MISSING |
| HS-5 | Face-shape enum mismatch: adapter canonicalizes `rectangular`, boosts use `rectangle`. | P1 | VERIFIED |
| HS-6 | `_DEFAULT_FACE_SHAPE = "oval"` can fabricate a face shape if an empty value reaches rules. | P1 | VERIFIED (latent) |
| HS-7 | Mock result fallback exists; UI guards contain it, but the seam is fragile. | P1 | PARTIALLY IMPLEMENTED |
| HS-8 | No recommendation-level feedback (like/dislike/why) on hairstyle results. | P1 | MISSING |
| HS-9 | Guest scan is ephemeral by design and cannot contribute to learning. | P2 | VERIFIED |

The hairstyle capability is the most honest of the four, but its UI overstates the analysis depth.

---

## 6. Capability 3: Outfit Builder

### Actual pipeline

- `GenerateOutfit` reads wardrobe, saved looks, preferred occasions, and feedback/wear context.
- Candidate generation and scoring are deterministic.
- Reasons include palette, fit, preferred item, and occasion match.
- Component reasons are generic: "Chosen {category} piece for your {label} outfit."
- Mood is carried into the recommendation but not scored.
- Style profile is not a scoring input.
- Save writes a saved look with `sourceContext="outfit"`.
- No wear logging and no recommendation feedback from the result screen.

### Findings

| ID | Finding | Priority | Classification |
|---|---|---|---|
| OB-1 | "Applying Style DNA" is a false processing claim; no style-profile input exists. | P0 | MISSING |
| OB-2 | Mood is requested but ignored by scoring. | P1 | PARTIALLY IMPLEMENTED |
| OB-3 | Occasion options in Flutter (5) do not match backend knowledge vocabulary (9). | P1 | VERIFIED |
| OB-4 | Component reasons are generic and do not explain why the specific item fits. | P1 | PARTIALLY IMPLEMENTED |
| OB-5 | No feedback on the generated outfit. | P1 | MISSING |
| OB-6 | No wear logging from the recommendation. | P1 | MISSING |
| OB-7 | No weather/context input. | P2 | MISSING |
| OB-8 | Save path is real and owner-scoped. | - | VERIFIED |

The outfit scorer is the strongest personalization surface in the product. It is still limited by the person model and by unused inputs.

---

## 7. Capability 4: Outfit Scan

### 7.1 The central defect

`CreateOutfitRun` calls `recommend_hairstyle` at `backend/app/application/analysis.py:332`. The endpoint is named and documented as an outfit/appearance analysis, but the executed engine is the hairstyle engine.

The Flutter screen renders:

- appearance profile,
- hairstyle recommendations,
- a garment section that looks for `garment`, `detectedItems`, `detected_items`, or `items`, none of which the endpoint returns.

Result: the outfit scan never evaluates the outfit. The "No clothing items detected in this photo" copy is misleading because detection is never attempted.

### 7.2 Contract drift

- `docs/api/SCAN_API.md` section 5.1 (S-1) promises `title`, `sections[]`, `detectedItems[]`, and `confidence`.
- `docs/PRODUCT_BLUEPRINT.md` promises silhouette, proportions, balance, fit, volume, color harmony, structure, and detected clothing.
- Actual response is a hairstyle appearance analysis.

### 7.3 Findings

| ID | Finding | Priority | Classification |
|---|---|---|---|
| OS-1 | Outfit Scan does not analyze outfits. | P0 | MISSING |
| OS-2 | The same endpoint duplicates Hairstyle Scan, creating a second product promise with one engine. | P0 | VERIFIED |
| OS-3 | Processing stages claim clothing detection, proportion analysis, and color analysis that never happen. | P0 | MISSING |
| OS-4 | Garment section is dead UI waiting for fields that are never returned. | P0 | MISSING |
| OS-5 | Docs and implementation disagree on the S-1 contract. | P1 | VERIFIED |
| OS-6 | "Save Profile" on the result screen makes no API call; it clears the pending result and shows a success SnackBar. | P1 | PARTIALLY IMPLEMENTED |

Acceptance criteria for closure:

- Either rename the capability to what it does, or implement real garment/outfit analysis.
- Remove or implement every processing stage label.
- Remove the dead garment section or populate it from a real analyzer.
- Align `SCAN_API.md` and `PRODUCT_BLUEPRINT.md` with the shipped contract.

---

## 8. Stage 1 Person-Understanding Framework

Stage 1 as implemented is a single-pass vision observation plus deterministic ranking, not a multi-signal person-understanding framework.

| Layer | Implemented | Gap |
|---|---|---|
| Observation | Face shape from one image; garment attributes from one image. | No body shape, proportions, skin tone, hair properties, or measurements. |
| Fusion | Face shape + explicit preferences for hairstyle; wardrobe + preferences + feedback/wear for outfits. | No cross-capability fusion; no confidence-weighted evidence model. |
| Person state | 4-field style profile JSONB. | 3 of 4 fields are deliberately empty from vision; no direct edit API. |
| Decision | Deterministic scoring over static catalogs. | Small candidate space; static reasons; no learned ranking. |
| Explanation | Template reasons grounded in available fields. | Some UI copy claims inputs that do not exist. |
| Feedback | Saved-look feedback; wear events. | No capability-level feedback; no closed-loop consumption. |
| Memory | Analysis runs, saved looks, events, signals. | Signals mostly write-only; no personalization read path. |

Verdict: PARTIALLY IMPLEMENTED. It is a defensible Stage 1 for hairstyle and outfit selection, but it cannot support claims about body proportions, skin tone, color harmony, or style DNA.

---

## 9. Shared Person Model

### Stored

`UserState.style_profile` JSONB holds:

- `face_shape`
- `skin_tone` (empty by design from vision)
- `body_type` (empty by design from vision)
- `style_type` (empty by design from vision)
- `source_run_id`

### Write paths

- Analysis run completion merges non-empty image-derived attributes.
- Preferences update writes `preferred_occasions` only.
- No public API edits face shape, body type, skin tone, or style type directly.

### Read paths

- Hairstyle engine: face shape and preferences.
- Outfit scoring: preferences, feedback/wear context, wardrobe, saved looks.
- Today: preferences and events.
- Discover For You: profile and preferences.

### Findings

| ID | Finding | Priority | Classification |
|---|---|---|---|
| PM-1 | Only face shape is populated from vision. | P1 | VERIFIED |
| PM-2 | No measurements, proportions, hair properties, color profile, goals, budget, or climate. | P1 | MISSING |
| PM-3 | No user-editable profile surface for face/body/skin/style. | P1 | MISSING |
| PM-4 | Face-shape enum mismatch creates a dead boost path. | P1 | VERIFIED |
| PM-5 | Default `oval` fallback can fabricate a shape. | P1 | VERIFIED (latent) |
| PM-6 | Guest local data is not migrated into the person model after auth. | P1 | MISSING |
| PM-7 | Raw images are not stored; media references are hashed. | - | VERIFIED (privacy positive) |

---

## 10. Decision Quality & Personalization

### Grounded

- Hairstyle ranking uses face shape and explicit preferences.
- Outfit ranking uses wardrobe, saved looks, preferred occasions, feedback, and wear context.
- Outfit reasons are deterministic and tied to available signals.
- Assistant offline mode deliberately avoids scores.

### Ungrounded or overstated

| Claim | Reality | Priority |
|---|---|---|
| "Analyzing skin tone" | Skin tone is never extracted. | P0 |
| "Applying Style DNA" | Style profile is not an input to hairstyle or outfit ranking. | P0 |
| "Detecting clothing items" in Outfit Scan | No garment detection occurs. | P0 |
| "Match" badges on Discover trending | Static catalog seed rescaled to 0-100; user-invariant. | P0 |
| "Curated For You" / "Trending For You" on Home | Static asset cards, not backend personalization. | P0 |
| "Style Score" | Base 60 plus wardrobe count plus saved count; usage volume. | P0 |
| For You fallback style type | Defaults to "Minimal Tailoring" when no style type exists. | P1 |
| Affinity score | `(styleScore + 12).clamp(84, 96)` manufactures a high affinity band. | P1 |
| Today's Look fit confidence | Omitted, although the outfit scorer can produce it. | P1 |
| Discover favorites | Local-only; not account saved looks, but telemetry records `product_save`. | P1 |

The system generally explains what it actually used. The problem is that the UI adds claims and inputs that the engine never sees.

---

## 11. Feedback Loop & Learning

### What exists

- Saved-look like/dislike feedback (append-only `feedback_events`).
- Wear logging from wardrobe item details.
- Learning signals written by analysis runs, saved looks, item adds, and assistant card feedback.
- Discovery interaction events (write-only).
- Device-local `LearningService` signals.

### What is missing

- No feedback on hairstyle results.
- No feedback on outfit builder results.
- No feedback on Today's Look.
- No feedback on Discover recommendations beyond local saves.
- Backend signals are read only for recent labels, not for ranking.
- Local signals never sync to the backend.
- Guest feedback and wear are lost.
- No experiment assignment, no counterfactual logging, no outcome measurement.

| ID | Finding | Priority | Classification |
|---|---|---|---|
| FB-1 | Feedback coverage is one surface out of many. | P0 | MISSING |
| FB-2 | Signals are not consumed by ranking. | P0 | MISSING |
| FB-3 | Local and server learning stores are disconnected. | P1 | PARTIALLY IMPLEMENTED |
| FB-4 | Discovery saves are local-only but emit save telemetry. | P1 | PARTIALLY IMPLEMENTED |
| FB-5 | No closed-loop evaluation of recommendation quality. | P1 | MISSING |
| FB-6 | Feedback is append-only and privacy-scoped. | - | VERIFIED (positive) |

The product currently records intent but does not learn from it in any ranking path.

---

## 12. Engineering Quality, Risks & Prioritized Roadmap

### 12.1 Strengths

- Owner scoping and auth boundaries are consistently enforced.
- Idempotency and conflict handling exist on writes.
- Analysis failures are typed and honest.
- Try-on mock discloses synthetic output.
- Offline assistant avoids fabricated scores.
- Test inventory is substantial: 116 backend test files and 110 Flutter test files.

### 12.2 Risks

| Risk | Impact | Priority |
|---|---|---|
| Outfit Scan mislabel | Product trust; users believe clothing was analyzed. | P0 |
| Initial scan not persisted | Onboarding promise broken; conversion loss. | P0 |
| Static content presented as personalized | Trust; perceived intelligence inflation. | P0 |
| Style Score semantics | Misleading progress metric. | P0 |
| Single-signal person model | Personalization ceiling. | P1 |
| 4-item catalogs | Repetitive recommendations. | P1 |
| Mock try-on in memory | Not multi-instance; not production-ready. | P1 |
| Docs drift | Future work builds against wrong contracts. | P1 |
| `analysis_rules.py` and `repositories.py` size | Change risk; slow review. | P2 |
| Migration head mismatch (dev 0029 vs staged 0032) | Deployment risk if not reconciled. | P2 |

### 12.3 Documentation drift

- `docs/api/SCAN_API.md` S-1 contract does not match the shipped outfit endpoint.
- `docs/PRODUCT_BLUEPRINT.md` promises outfit attributes and component alternatives that are not implemented.
- `CURRENT_STATE.md` records completed discovery work, but the Flutter Trending surface still renders static fallback content when the feed is empty or fails.

### 12.4 Prioritized roadmap

P0: make the product truthful.

1. Rename Outfit Scan to what it does, or implement real outfit analysis. Remove false stage labels and dead garment UI.
2. Persist Initial Scan for authenticated users and define an explicit guest discard or replay policy.
3. Remove or implement every claim that requires missing inputs: skin tone, Style DNA, clothing detection, proportions, color analysis.
4. Replace static match badges and static "personalized" sections with real data or clearly labeled editorial content.
5. Redefine Style Score as a usage/activity metric, or replace it with a quality metric that has a defensible formula.
6. Add recommendation-level feedback to hairstyle, outfit builder, Today, and Discover.

P1: make personalization real.

1. Expand the person model and add a user-editable profile surface.
2. Expand hairstyle and grooming catalogs; add specific reason generation.
3. Use mood, fit confidence, and style profile in outfit ranking.
4. Connect feedback and wear signals to ranking with explicit, testable rules.
5. Unify occasion vocabularies across Flutter, knowledge API, and scoring.
6. Fix the face-shape enum mismatch and remove default fabrication.
7. Make Discover favorites account-persisted or explicitly local.

P2: harden engineering.

1. Split `analysis_rules.py` and `repositories.py` by capability.
2. Reconcile documentation contracts with shipped behavior.
3. Reconcile migration heads across dev and test.
4. Add contract tests that assert UI claims match returned fields.
5. Decide whether try-on remains mock-only or gets a real provider.

P3: polish.

1. Remove unused mock imports and dead code.
2. Normalize naming across analysis/outfit/garment domains.
3. Improve empty/error copy consistency.
4. Add accessibility and text-scaling checks for new surfaces.

### 12.5 Open questions for the founder

1. Should Outfit Scan be renamed to Hairstyle Scan, or is real outfit analysis required next?
2. Should Initial Scan persist for guests on-device until signup, or be explicitly discarded?
3. Which single capability should be the first true closed-loop personalization surface?
4. Is Style Score intended as activity, style quality, or both?
5. Is try-on a near-term product requirement or a later-stage mock?

---

## Appendix A: Evidence Index

| Area | Files |
|---|---|
| Outfit Scan mislabel | `backend/app/application/analysis.py:332`; `backend/app/api/routers/analysis.py`; `outfit_scan_client.dart`; `outfit_analysis_screen.dart`; `outfit_processing_screen.dart` |
| Initial Scan | `ai_analysis_screen.dart:18-21,109-126`; `your_analysis_screen.dart:86-145`; `post_auth_flow.dart` |
| False stage claims | `hairstyle_mock_data.dart:48,53`; `outfit_builder_mock_data.dart:141`; `outfit_scan_mock_data.dart:46-59` |
| Vision limits | `vision_appearance_adapter.py`; `vision_garment_adapter.py` |
| Static content | `home_screen.dart:522-532`; `existing_user_home_widgets.dart:1420,1638`; `discover_screen.dart:746-877` |
| Local-only saves | `discover_screen.dart:408-418`; `existing_user_for_you_widgets.dart:710-731` |
| Style score | `backend/app/application/learning.py:150-152`; `backend_summary_cards.dart:106-115` |
| Feedback coverage | `saved_looks_screen.dart`; `backend/app/application/feedback.py` |
| Learning signals | `backend/app/application/learning.py`; `learning_service.dart` |
| Person model | `backend/app/infrastructure/db/models.py:127`; `analysis_rules.py:152,168,223` |
| Catalog | `backend/app/data/catalog.py:115-221` |
| Docs drift | `docs/api/SCAN_API.md` section 5.1; `docs/PRODUCT_BLUEPRINT.md` |
| Try-on mock | `backend/app/api/routers/tryon.py`; `backend/app/domain/ports/tryon_provider.py`; `try_on_screen.dart` |

## Appendix B: Unverified

- Actual runtime behavior of Ollama vision on real images.
- Actual database migration state of the development database.
- Whether all 116 backend and 110 Flutter test files currently pass.
- Real-device rendering, overflow, and text-scaling behavior.
- Real network failure behavior of every client.
- Whether any external provider or production deployment currently uses try-on.

## Appendix C: Completion Statement

No code was modified. This audit is based on static inspection. The next step requires founder decisions on the P0 scope before implementation begins.
