# Fansivibe Stage 1 Requirements-to-Code Traceability Matrix

**Document type:** Static requirements-to-code traceability audit  
**Date:** 2026-10-24  
**Repository:** `C:\Users\user\Desktop\fansiv2\fansivibe_v1_backup`  
**Baseline commit:** `741493d`  
**Working tree at audit time:** `M CURRENT_STATE.md`; `?? FANSIVIBE_PRODUCT_DEEP_AUDIT.md`; this report is the only file created by this audit.  
**Runtime verification:** None. This is a source-and-copy audit, not a live device, database, model-quality, or end-to-end test run.

> This document separates verified current behavior from intended behavior. A code path is not treated as a product requirement. Where the repository does not establish intent, the item is marked **PRODUCT DECISION REQUIRED** rather than silently filled in.

---

## 1. Executive Summary

Stage 1 is **partially implemented**, but it is not yet a reliable, shared person-understanding system.

The strongest implemented capability is **Hairstyle Scan**: it has a real image-to-face-shape adapter, a real recommendation engine, a working save path, and a guard that prevents mock results from being presented as real analysis. **Outfit Builder** is also substantially real: it generates and saves outfits against the authenticated wardrobe and preferences. The backend also has several genuine trust controls: partial style-profile updates merge instead of erase, guest ephemeral analysis is separate from durable analysis, unsupported image types fail honestly, and account deletion exists at the API layer.

The central Stage 1 failure is **Outfit Scan**. It is presented as outfit analysis, but `CreateOutfitRun` never calls the garment adapter. It calls the hairstyle recommendation engine and returns a hairstyle snapshot. The result screen then reports that no clothing items were detected because the outfit snapshot does not contain a garment key. That is not an honest negative observation; it is a structural absence in the analysis contract.

The second major failure is **Initial Scan**. It is a real guest ephemeral preview, but it is not a durable onboarding analysis. “Save My Progress” stores a pending authentication intent, not the analysis. The snapshot is stashed, but the post-auth flow does not automatically replay it. The post-auth copy can say local progress was kept even after the user discarded it. “Save” language therefore overstates what the system does.

The third major failure is the **shared person model**. The backend has `users.style_profile` and a `ProfileView.styleProfile` schema, but the Flutter profile does not read that backend profile. The Flutter profile reads local storage instead. Guest migration explicitly excludes face/appearance data. The hairstyle adapter only measures face shape, leaving skin tone, body type, and style type empty, yet the hairstyle UI displays those empty fields and the catalog can claim personalized skin-tone and Style-DNA reasoning. The shared model is therefore fragmented by capability, by client/server boundary, and by guest/authenticated state.

The fourth major failure is **goals and desired change**. No persistent goal model, desired-change capture, or outcome target was found. Occasion and mood in Outfit Builder are per-request decision inputs, not a person-level goal. Stage 1 cannot claim to understand what the user wants to change.

The fifth major failure is **context**. Events are real and do feed preferred occasions on creation, and Today’s Look uses the nearest event. But Outfit Builder receives only a preselected occasion; event identity, location, date, and the rest of the event context are display-only. Hairstyle Scan and Outfit Scan do not use event context. No weather provider exists by design, and no weather claim should be made.

The sixth major failure is **uncertainty and unsupported claims**. Hairstyle confidence is derived from evidence completeness and top-pick decisiveness, not from model certainty. The hairstyle UI ignores both `confidence` and `needs_more_data`. Outfit Scan displays confidence, but it is appearance/engine confidence, not clothing confidence. Garment confidence exists in the domain object but is not surfaced in the Initial Scan result. Catalog reasons and mock copy contain claims about skin tone and “your Style DNA” that the measured data cannot support. Outfit Builder labels an ensemble match percentage as “Style Score Impact.”

### Top P0 findings

| ID | Finding | Why it is P0 | Evidence |
|---|---|---|---|
| P0-1 | Outfit Scan does not analyze garments | The capability’s core claim is false; the result is a hairstyle recommendation with an empty outfit section | `backend/app/application/analysis.py:193`, `:229`, `:332`; `outfit_analysis_screen.dart:814-877` |
| P0-2 | Initial Scan does not persist the analysis it offers to save | User-visible save language creates a false expectation of durability | `your_analysis_screen.dart:86-100`; `post_auth_flow.dart:169-180` |
| P0-3 | Guest migration excludes face/appearance data | The authenticated person model silently loses a key onboarding observation | `guest_data_migration.dart:47-55` |
| P0-4 | Hairstyle result presents empty skin-tone/Style-DNA fields and false stage/catalog claims | The UI and content claim analysis that did not occur | `hairstyle_result_screen.dart:234-241`; `hairstyle_mock_data.dart:39-61`, `:162-180`; `catalog.py:130-131` |
| P0-5 | “Style Score Impact” is a mislabeled match percentage | The user is given a false causal/score interpretation | `outfits.py:352-355`; `outfit_recommendation_screen.dart:225-251` |
| P0-6 | Initial Scan save/discard/post-auth truth is inconsistent | The auth transition can claim progress was kept when it was discarded | `post_auth_flow.dart:60-83`, `:169-180`; `create_account_screen.dart:223-231` |
| P0-7 | Outfit/Initial paths can score a hairstyle recommendation with no measured face shape | The scoring helper falls back to `oval`; only the hairstyle image path rejects a missing face | `analysis_rules.py:168`, `:221-223`, `:299`; `analysis.py:229-332`, `:1048-1050` |

### What is genuinely working

- Authenticated durable analysis APIs require authentication; guest ephemeral analysis is separately routed. Evidence: `backend/app/api/routers/analysis.py:86-137`, `:205-241`, `:244-284`, `:285-404`.
- Hairstyle save works and uses a real durable endpoint. Evidence: `hairstyle_service.dart:57`, `:424-448`.
- Outfit Builder generate and save are real. Evidence: `outfit_client.dart:85`, `:143`; `analysis.py:193-390`.
- The garment adapter performs real garment observation when invoked. Evidence: `vision_garment_adapter.py:75-94`, `:196-208`.
- Partial style-profile updates merge non-empty values and do not erase prior fields. Evidence: `repositories.py:265-306`.
- Mock hairstyle results are blocked from the result UI. Evidence: `face_processing_screen.dart:136-159`.
- Outfit Scan uses honest empty-state copy for absent observations, even though the underlying absence is a contract defect. Evidence: `outfit_analysis_screen.dart:865-877`.
- The try-on surface is explicitly mock/test data. Evidence: `try_on_screen.dart:18-29`.
- Account deletion exists at the backend API layer. Evidence: `backend/app/api/routers/users.py:130-151`; cascade in `backend/app/application/auth.py:228-246`.
- Discover “For You” uses real backend personalization scores in the primary path. Evidence: `discover.py:147-167`; `discover_screen.dart:1051-1052`.

### Bottom line

Stage 1 should not be described as “understands the person” yet. It should be described as **a set of partially connected capability prototypes with a real hairstyle path, a real outfit-builder path, a guest-only initial preview, a nonfunctional outfit-analysis path, and a fragmented person model**. The fastest credible path is not a broad redesign; it is a truth-first repair of the four capabilities and the shared model contracts.

---

## 2. Scope, Evidence Standards, and Limitations

### 2.1 Scope

**In scope**

- The six Stage 1 subjects and the four named capabilities.
- Current Flutter screens, navigation, copy, local state, and client calls relevant to those capabilities.
- Backend routers, use cases, domain rules, adapters, repositories, and schemas relevant to those capabilities.
- Shared person/model persistence and guest-to-authenticated transitions.
- User-visible claims about what was analyzed, stored, remembered, personalized, or learned.
- Acceptance criteria, prioritized backlog, dependencies, and founder decisions.

**Out of scope**

- Live AI model quality, prompt quality, or recommendation quality.
- Full visual design QA.
- Runtime latency, crash behavior, database migration execution, and live database state.
- Every backend endpoint and every Flutter screen.
- A general security audit beyond Stage 1 data-flow and privacy claims.
- Implementing fixes.

### 2.2 Evidence standard

| Status | Meaning in this report |
|---|---|
| **VERIFIED** | The relevant code path and/or user-visible copy was read directly in the repository. This is static verification, not runtime verification. |
| **PARTIALLY IMPLEMENTED** | Some real path exists, but the end-to-end subject or capability is incomplete, conditional, or contradicted by another layer. |
| **MISSING** | No implementation path was found in the reviewed code. |
| **UNVERIFIED** | The repository does not provide enough evidence to conclude current behavior; live/runtime verification is required. |
| **PRODUCT DECISION REQUIRED** | The repository does not establish intended behavior, scope, or user promise. The audit must not invent it. |
| **DESIGN PROPOSAL** | A recommended design direction; explicitly not current behavior and not an accepted decision. |

### 2.3 Priority standard

| Priority | Meaning |
|---|---|
| **P0** | False capability claim, data loss/misrepresentation, privacy/consent issue, security issue, or a Stage 1 capability that does not perform its named function. |
| **P1** | The subject is present but not reliably usable, not coherent across capabilities, or not grounded in the shared model. |
| **P2** | User-facing coherence, completeness, feedback-loop, or account-management gap. |
| **P3** | Polish, observability, cleanup, or non-blocking quality improvement. |

### 2.4 Method

1. Read the repository state and the existing preliminary audit.
2. Trace each capability from Flutter entry point to backend endpoint to domain decision to persistence.
3. Trace each subject across all four capabilities.
4. Compare user-visible copy and progress labels with the actual code path.
5. Record evidence at file-and-line level.
6. Separate verified facts, interpretations, proposals, and unresolved questions.
7. Do not run migrations, tests, installs, or destructive Git commands.
8. Do not modify application code, tests, configuration, documentation, or `CURRENT_STATE.md`.

### 2.5 Limitations

- This audit cannot confirm live model output, actual confidence calibration, or recommendation quality.
- This audit cannot confirm live database contents, production feature flags, deployed adapter selection, or environment-specific behavior.
- Flutter line references identify the reviewed source; generated code and platform-specific branches may differ at runtime.
- The report treats comments and docstrings as intent signals only when they are consistent with code. Comments that contradict code are called out.
- The preliminary `FANSIVIBE_PRODUCT_DEEP_AUDIT.md` was used as a starting point only; findings below are based on source re-verification.
- No tests were run. “Verified” in this report never means “tested at runtime.”

---

## 3. Stage 1 Target Requirements

### 3.1 The six subjects

| ID | Subject | Minimum Stage 1 intent |
|---|---|---|
| S1 | Understanding the Person's Current Appearance | Measure a defined set of appearance attributes from a real observation and make clear what was measured. |
| S2 | Understanding Goals and Desired Change | Capture what the person wants to achieve, or explicitly declare goals out of scope. |
| S3 | Understanding Preferences and Style Identity | Use explicit preferences, saved choices, and declared style identity where the product claims personalization. |
| S4 | Understanding Lifestyle, Context, and Constraints | Use occasion, event, environment, budget, comfort, and similar constraints where claimed; never imply unavailable context. |
| S5 | Observation, Evidence, and Uncertainty | Preserve provenance, distinguish observation from inference, and surface uncertainty honestly. |
| S6 | Building a Reliable Person Model | Provide an authoritative, readable, writable, and durable person model with clear boundaries and no silent loss. |

### 3.2 The four capabilities

| Capability | Product promise to trace |
|---|---|
| **Initial Scan** | A first-scan onboarding experience that helps the person understand their starting point and preserves progress where the product says it does. |
| **Hairstyle Scan** | An image-based hairstyle analysis that measures appearance, explains recommendations, and saves useful results. |
| **Outfit Builder** | A request-driven outfit recommendation that uses the person’s wardrobe, preferences, and context. |
| **Outfit Scan** | An image-based outfit analysis that observes clothing and gives outfit-specific feedback. |

### 3.3 Target requirement set

These are target requirements, not claims that the current code satisfies them. A requirement marked **PRODUCT DECISION REQUIRED** cannot be treated as implemented until the founder decides its scope.

| ID | Subject | Target requirement | Current status |
|---|---|---|---|
| R-S1-1 | S1 | Any capability that claims appearance analysis must use a real appearance observation and identify the measured attributes. | PARTIALLY IMPLEMENTED |
| R-S1-2 | S1 | Outfit Scan must observe garments if it claims outfit analysis. | MISSING |
| R-S1-3 | S1 | Appearance fields that are not measured must be hidden, labeled “not measured,” or removed from the result. | PARTIALLY IMPLEMENTED |
| R-S2-1 | S2 | The product must capture a goal or desired change, or explicitly state that Stage 1 does not support goals. | PRODUCT DECISION REQUIRED |
| R-S2-2 | S2 | Per-request mood/occasion must not be presented as a durable personal goal. | PARTIALLY IMPLEMENTED |
| R-S3-1 | S3 | Explicit preferences and style identity must be used where personalization is claimed. | PARTIALLY IMPLEMENTED |
| R-S3-2 | S3 | Style identity must be grounded in a stored or declared value, not inferred from absence. | MISSING |
| R-S3-3 | S3 | Saved looks and feedback must be used consistently by capabilities that claim to learn from them. | PARTIALLY IMPLEMENTED |
| R-S4-1 | S4 | Occasion and event context must be passed to the capability or clearly labeled as display-only. | PARTIALLY IMPLEMENTED |
| R-S4-2 | S4 | Weather, location, budget, and comfort must not be implied unless a real source or user input exists. | VERIFIED as absent |
| R-S4-3 | S4 | Event creation, event-derived preferences, and recommendation context must be consistent about what is remembered. | PARTIALLY IMPLEMENTED |
| R-S5-1 | S5 | Every result must preserve provenance and distinguish observation from inference. | PARTIALLY IMPLEMENTED |
| R-S5-2 | S5 | Confidence must mean a defined, meaningful quantity and must not be presented as model certainty when it is evidence completeness. | PARTIALLY IMPLEMENTED |
| R-S5-3 | S5 | `needs_more_data`, `needs_review`, and confidence must be surfaced consistently on all result surfaces. | MISSING |
| R-S6-1 | S6 | The shared person model must have one declared authority for each field and a documented read/write path. | PARTIALLY IMPLEMENTED |
| R-S6-2 | S6 | Partial updates must not erase prior data. | VERIFIED |
| R-S6-3 | S6 | Guest-to-authenticated migration must preserve or explicitly drop each data class. | PARTIALLY IMPLEMENTED |
| R-S6-4 | S6 | The model must expose enough provenance/versioning to explain why a recommendation changed. | PARTIALLY IMPLEMENTED |
| R-S6-5 | S6 | Account deletion and privacy copy must match actual data retention. | PARTIALLY IMPLEMENTED |
| R-X-1 | Cross-cutting | UI copy and progress labels must not claim work that did not execute. | MISSING |
| R-X-2 | Cross-cutting | Capability-specific observations must not silently become shared person facts. | PARTIALLY IMPLEMENTED |

### 3.4 Requirement interpretation rules

- **S1 does not require every appearance attribute.** It requires honesty about the measured subset.
- **S2 does not require a full coaching plan.** It requires either a captured goal or an explicit out-of-scope statement.
- **S3 does not require a perfect style taxonomy.** It requires that claimed personalization uses a real stored or declared signal.
- **S4 does not require weather.** It requires that absent context is not implied.
- **S5 does not require calibrated probabilities.** It requires that confidence and uncertainty mean something defensible and are shown where decisions depend on them.
- **S6 does not require a database redesign.** It requires a coherent authority and read/write path using existing stores where possible.

---

## 4. Six-Subject Requirements Matrix

Legend: **V** = VERIFIED, **P** = PARTIALLY IMPLEMENTED, **M** = MISSING, **U** = UNVERIFIED, **D** = PRODUCT DECISION REQUIRED.

| Subject | Initial Scan | Hairstyle Scan | Outfit Builder | Outfit Scan | Cross-capability verdict |
|---|---|---|---|---|---|
| **S1 — Current Appearance** | P — ephemeral face-shape + garment observations; no durable person update; no garment confidence display | P — real face-shape observation and profile write; skin tone, body type, style type are empty | M — no image/appearance input; wardrobe only | M — named outfit scan does not invoke the garment adapter; face shape may be empty and is scored with an `oval` fallback | **P/M:** appearance is real only for face shape; outfit appearance is not. |
| **S2 — Goals and Desired Change** | M — photo-only; no goal capture | M — no desired change or outcome target | P — per-request occasion/mood/fit/palette; no durable goal | M — no goal capture | **M/D:** no goal model; decide whether Stage 1 includes goals. |
| **S3 — Preferences and Style Identity** | M — no explicit preferences in the guest preview | P — profile-only path can use saved looks; image path does not; explicit preferred-look mapping is not implemented | P — preferred occasions and per-request fit/palette; no shared style profile use | M — no preference or style-identity use | **P/M:** preference claims are inconsistent by path. |
| **S4 — Lifestyle, Context, Constraints** | M — no occasion/event/weather/constraint input | M — no context input | P — event type can preselect occasion; event identity/location/date are display-only; preferred occasions feed scoring | M — no context input | **P/M:** occasion exists; lifestyle and constraints largely absent. |
| **S5 — Observation, Evidence, Uncertainty** | P — raw snapshot exists; confidence is displayed but is appearance/engine confidence; a missing face can still be scored as `oval` | M — confidence and `needs_more_data` are ignored in Dart; empty fields shown without labels; false stage copy | P — deterministic match/candidate data; confidence/provenance not exposed as uncertainty | P — confidence displayed, but not clothing confidence; garment confidence is absent; no-face can still score as `oval` | **P/M:** observation exists in places; uncertainty is not a shared contract. |
| **S6 — Reliable Person Model** | M — no durable model update; pending intent only | P — face shape persisted to `style_profile`; local face copy; guest excluded from migration | M — does not read/write the shared appearance model | P — writes face shape to `style_profile`; no garment facts | **P/M:** one backend JSONB store exists, but authority and coverage are fragmented. |

### 4.1 Subject scorecard

| Subject | Strongest evidence | Biggest gap | P0? |
|---|---|---|---|
| S1 | Real face-shape adapter and garment adapter exist | Outfit Scan never invokes garment analysis; appearance profile is face-only | Yes |
| S2 | Outfit Builder captures concurrent occasion/mood/fit/palette | No durable goal or desired-change model | Yes, if goals are in Stage 1 |
| S3 | Preferred occasions and wardrobe are real | Style identity is empty; image hairstyle path does not use saved looks/preferences | Yes |
| S4 | Events feed preferred occasions; Today’s Look uses nearest event | Outfit Builder event identity is display-only; no weather/lifestyle model | No, but P1 |
| S5 | Raw snapshots, confidence fields, and `needs_review` exist | Uncertainty is ignored or mislabeled; false progress/catalog claims | Yes |
| S6 | `style_profile` JSONB, provenance, merge semantics, deletion API | No `/me` profile read in Flutter; Today’s Look has a separate `styleDna` projection; guest face migration excluded | Yes |

### 4.2 Subject-level conclusion

- **S1 is not a general appearance model.** It is a face-shape model with an unused garment adapter.
- **S2 is absent as a person-level subject.** Occasion/mood are request parameters.
- **S3 is partially implemented but path-dependent.** The same capability can use different preference signals depending on whether it is image-based or profile-based.
- **S4 is mostly an occasion system.** It is not a lifestyle/context system.
- **S5 is the main trust gap.** The backend has uncertainty primitives; the UI does not consistently consume or explain them.
- **S6 is a persistence primitive, not yet a reliable person model.** The same store is written by different capabilities, but not read by the profile, not fully migrated, and not documented as authoritative.

---

## 5. Four-Capability Traceability Matrices

### 5.1 Initial Scan

#### Current flow

1. The onboarding photo screen evaluates guest state.
2. If the user is authenticated, the photo routes to hairstyle processing, not Initial Scan. Evidence: `photo_capture_screen.dart:397-411`.
3. If the user is a guest, the photo routes to `AiAnalysisScreen`. Evidence: `photo_capture_screen.dart:414-421`.
4. `AiAnalysisScreen` calls the outfit ephemeral endpoint and the garment ephemeral endpoint in parallel. Evidence: `ai_analysis_screen.dart:19-20`, `:108-123`.
5. The resulting snapshots are stashed. Evidence: `ai_analysis_screen.dart:124-137`.
6. The result screen renders the snapshot. “Save My Progress” records a pending `save_progress` intent; it does not send the analysis. Evidence: `your_analysis_screen.dart:86-100`.
7. The post-auth flow can claim local progress was kept, but no automatic replay was found. Evidence: `post_auth_flow.dart:169-180`.

#### Subject matrix

| Subject | Status | What happens | Evidence | Gap |
|---|---|---|---|---|
| S1 | PARTIALLY IMPLEMENTED | Ephemeral outfit analysis produces a face-shape snapshot; garment analysis produces garment observations. | `analysis.py:1001-1053`, `:1116-1150`; `ai_analysis_screen.dart:108-123` | No durable appearance update; garment confidence not surfaced; top-level appearance is face-only. |
| S2 | MISSING | No goal/desired-change input. | `ai_analysis_screen.dart:108-137` | A photo alone cannot establish a goal. |
| S3 | MISSING | No explicit preferences or style identity are sent. | `ai_analysis_screen.dart:108-123` | Personalization cannot be claimed from this flow. |
| S4 | MISSING | No occasion, event, weather, budget, or comfort input. | `ai_analysis_screen.dart:108-137` | Preview is context-free. |
| S5 | PARTIALLY IMPLEMENTED | Result carries `confidence` and `needs_more_data`; preview displays confidence. | `your_analysis_screen.dart:308-449` | Confidence is appearance completeness, not a general scan confidence; garment certainty is not shown. |
| S6 | MISSING | No backend person update; only a pending auth intent and a stashed snapshot. | `your_analysis_screen.dart:86-100`; `post_auth_flow.dart:60-83` | “Save” semantics do not match persistence. |

#### Findings

- **Initial Scan is a guest-only preview**, not an authenticated onboarding analysis. The authenticated onboarding route goes to hairstyle. This must be explicit in product copy and requirements.
- **The two ephemeral analyses are real**, but they are not combined into a durable person model.
- **The preview is honest in places**: it omits absent garment details and can show “No clear outfit details in this photo.” Evidence: `your_analysis_screen.dart:327-346`, `:400-405`.
- **The save story is not honest enough**: “Save My Progress” only stores an intent; the analysis is not posted. Evidence: `your_analysis_screen.dart:86-100`.
- **Post-auth continuity is not implemented as described**: no automatic replay of the stashed Initial Scan snapshot was found. The `analysis_cached` flag is set unconditionally in the `_onMaybeLater` path. Evidence: `create_account_screen.dart:223-231`.
- **Discard does not transfer analysis**: DISCARD removes local wardrobe/preferences but not a durable analysis payload; the “local progress was kept” message is false after this path. Evidence: `post_auth_flow.dart:60-83`, `:169-180`.
- **Guest face data is excluded from later migration**: `guest_data_migration.dart:47-55` migrates wardrobe and preferred occasions but explicitly not face/appearance.

### 5.2 Hairstyle Scan

#### Current flow

1. Authenticated onboarding routes to hairstyle processing. Evidence: `photo_capture_screen.dart:397-411`.
2. The client uploads an image to the hairstyle endpoint. Evidence: `hairstyle_service.dart:57`, `:424-448`.
3. `CreateHairstyleImageRun` validates type/size, creates a run, and calls the appearance adapter. Evidence: `analysis.py:419-532`.
4. A measured face shape is required; no default shape is fabricated. Evidence: `analysis.py:534-546`.
5. The appearance profile is passed to `recommend_hairstyle`. Evidence: `analysis.py:551-554`.
6. The result includes `confidence` and `needs_more_data`. Evidence: `analysis_rules.py:378-393`, `:461-462`.
7. The Flutter model parses appearance fields but not `confidence` or `needs_more_data`. Evidence: `hairstyle_mock_data.dart:129-145`.
8. The result screen shows skin tone and Style DNA rows even when empty. Evidence: `hairstyle_result_screen.dart:234-241`.
9. Save Style works through `/v1/looks/saved`. Evidence: `hairstyle_service.dart:57`, `:424-448`; `outfit_analysis_screen.dart` is not involved.
10. The local face profile is persisted only for real results; mock results are blocked. Evidence: `face_processing_screen.dart:136-159`, `:147-155`.

#### Subject matrix

| Subject | Status | What happens | Evidence | Gap |
|---|---|---|---|---|
| S1 | PARTIALLY IMPLEMENTED | Face shape is measured and stored; skin tone/body type/style type are empty. | `vision_appearance_adapter.py:229-236`; `analysis.py:587` | Only one appearance attribute is real; UI shows empty others. |
| S2 | MISSING | No desired-change input. | `analysis.py:419-554` | Recommendations are not goal-conditioned. |
| S3 | PARTIALLY IMPLEMENTED | Profile-only path can use saved looks; image path does not; preferred-look mapping is not implemented. | `analysis_rules.py:118-130`, `:419-454` | Preferences are not consistently used. |
| S4 | MISSING | No event/occasion/weather context. | `analysis.py:419-554` | Recommendations are context-free. |
| S5 | MISSING | Confidence/needs_more_data are produced but ignored by Dart; stage labels claim skin-tone/Style-DNA analysis. | `hairstyle_mock_data.dart:39-61`, `:129-145` | Uncertainty is invisible and progress is overstated. |
| S6 | PARTIALLY IMPLEMENTED | Face shape is merged into `style_profile` with `source_run_id`; local face copy is also written. | `analysis.py:587`; `repositories.py:265-306`; `face_processing_screen.dart:147-155` | Only face shape; no shared read path; guest excluded. |

#### Findings

- **The real analysis path is narrow but honest at the backend boundary**: the hairstyle image path rejects a missing face shape and does not substitute a default. Evidence: `analysis.py:534-546`.
- **The honesty guard is not shared with Outfit Scan or the guest Initial Scan**: those paths do not reject an empty face shape, and the scoring helper falls back to `oval`. Evidence: `analysis_rules.py:168`, `:221-223`, `:299`; `analysis.py:229-332`, `:1048-1050`.
- **The UI overstates the result**: skin tone and Style DNA are displayed without labels when the adapter explicitly empties them. Evidence: `vision_appearance_adapter.py:229-236`.
- **The result withholds uncertainty**: `confidence` and `needs_more_data` exist in the response but are not parsed. Evidence: `hairstyle_mock_data.dart:113-154`.
- **The saved style path works**, which makes the hairstyle capability the most complete of the four.
- **The catalog can claim personalization that was not measured**: “warm medium skin tones” and “your Modern Classic Style DNA.” Evidence: `catalog.py:130-131`; mirrored in mock data `hairstyle_mock_data.dart:162-180`.
- **Progress labels claim stages that do not exist**: “Analyzing skin tone” and “Applying Style DNA.” Evidence: `hairstyle_mock_data.dart:39-61`.
- **The face-shape vocabulary is inconsistent**: the adapter canonicalizes `rectangle` to `rectangular`, but hairstyle scoring boosts `rectangle` in one rule. Evidence: `vision_appearance_adapter.py:52-59`; `analysis_rules.py:153-154`, `:179`.
- **The image path does not use preferences or saved looks**; only the profile-only path uses saved looks. Evidence: `analysis.py:553`; `analysis_rules.py:419-454`.
- **The result’s match percentage is a catalog match score**, not a personal confidence or a goal-fit score. Evidence: `hairstyle_result_screen.dart:290`; `analysis_rules.py:300-316`.

### 5.3 Outfit Builder

#### Current flow

1. User enters from Home or an event. Event entry passes occasion and display metadata. Evidence: `event_list_screen.dart:109-117`.
2. The screen collects occasion, mood, fit, and color palette. Evidence: `outfit_models.dart:73-105`.
3. The request is sent to `/v1/outfits/generate`. Evidence: `outfit_client.dart:85`.
4. The backend loads the user’s wardrobe and preferred occasions, plus feedback/wear context. Evidence: `outfits.py:453-516`.
5. The backend does not read `style_profile`, appearance, or event identity. Evidence: `outfits.py:479-516`.
6. The result screen displays the ensemble and match percentage. Evidence: `outfit_recommendation_screen.dart:225-255`.
7. Save uses `/v1/outfits/saved` with `sourceContext: "outfit"`. Evidence: `outfit_client.dart:143`.
8. Regenerate cycles deterministic seeds. Evidence: `outfit_generation_screen.dart`, `outfit_client.dart`.
9. The progress UI shows a static “Applying Style DNA” stage. Evidence: `outfit_builder_mock_data.dart:139-142`; `outfit_generation_screen.dart:242`.

#### Subject matrix

| Subject | Status | What happens | Evidence | Gap |
|---|---|---|---|---|
| S1 | MISSING | No appearance input. | `outfit_models.dart:73-105` | Outfit recommendations cannot reflect measured appearance. |
| S2 | PARTIALLY IMPLEMENTED | Occasion and mood are per-request. | `outfit_models.dart:73-105` | No durable goal/desired change. |
| S3 | PARTIALLY IMPLEMENTED | Preferred occasions and per-request fit/palette; no shared style identity. | `outfits.py:479-516`; `outfit_models.dart:73-105` | Style profile is not used; “Style DNA” claim is unsupported. |
| S4 | PARTIALLY IMPLEMENTED | Event type can preselect occasion; event identity/location/date are display-only; no weather. | `event_list_screen.dart:109-117`; `build_outfit_screen.dart:59-80`; `app_router.dart:269-304` | Event context is not passed as context to the backend. |
| S5 | PARTIALLY IMPLEMENTED | Deterministic match scoring; no explicit confidence/provenance surface. | `outfits.py:339-358`; `analysis_rules.py:1442-1475` | Match is presented as impact; uncertainty absent. |
| S6 | MISSING | Does not read/write the shared appearance model. | `outfits.py:479-516` | Outfit outcomes do not enrich the person model. |

#### Findings

- **Outfit Builder is the strongest consumer of the wardrobe and preference data.** It uses real wardrobe items and preferred occasions.
- **It is not appearance-aware.** A user’s measured face shape or style type has no effect on the generated outfit.
- **It is not event-aware beyond occasion.** `eventId` and event title are passed for display, not sent to the backend. Evidence: `build_outfit_screen.dart:59-80`; `app_router.dart:269-304`.
- **“Style Score Impact” is false semantics.** The backend field is the ensemble match percentage; the UI labels it as an impact. Evidence: `outfits.py:352-355`; `outfit_recommendation_screen.dart:225-251`.
- **The “Applying Style DNA” stage is static copy.** The backend does not read `style_profile`. Evidence: `outfit_builder_mock_data.dart:139-142`; `outfit_generation_screen.dart:242`.
- **The save and regenerate paths are real**, so the main gap is personalization depth and truthfulness, not the basic API.
- **Feedback/wear history affects ranking**, which is a genuine partial learning loop. Evidence: `outfits.py:503-516`; `analysis_rules.py:1442-1475`.
- **Feedback is only captured on saved looks**, not on every generated outfit or on look details. Evidence: `saved_looks_screen.dart:332-333`, `:474-483`; `look_details_screen.dart:17`, `:286`.

### 5.4 Outfit Scan

#### Current flow

1. Guest and authenticated users both reach the outfit scan surface. Evidence: `outfit_scan_screen.dart:308-341`.
2. Guest uses the synchronous ephemeral endpoint. Evidence: `outfit_scan_screen.dart:311-317`, `:391-426`.
3. Authenticated uses `POST /v1/analysis/outfit` and polls. Evidence: `outfit_scan_screen.dart:324-341`; `outfit_processing_screen`.
4. The backend `CreateOutfitRun` calls the appearance adapter and then `recommend_hairstyle`. Evidence: `analysis.py:229`, `:332`.
5. The backend does not invoke the garment adapter. Evidence: no garment call in `analysis.py:193-390`.
6. The result snapshot is the hairstyle snapshot. Evidence: `analysis.py:332`, `:352`.
7. The result screen reads `garment` and `detectedItems` keys. Evidence: `outfit_analysis_screen.dart:814-821`.
8. Because those keys are absent, the screen displays “No clothing items detected in this photo.” Evidence: `outfit_analysis_screen.dart:865-877`.
9. “Save Profile” has no API call; the run already persisted appearance. Evidence: `outfit_analysis_screen.dart:1031-1054`.
10. “See Recommendations” routes to the daily outfit, not to scan-specific recommendations. Evidence: `outfit_analysis_screen.dart:1056-1063`.

#### Subject matrix

| Subject | Status | What happens | Evidence | Gap |
|---|---|---|---|---|
| S1 | MISSING | Claims outfit analysis but measures only face shape. | `analysis.py:229-352` | No garment observation. |
| S2 | MISSING | No goal/desired-change input. | `outfit_analysis_screen.dart:74-114` | No goal conditioning. |
| S3 | MISSING | No preference/style-identity input. | `analysis.py:229-332` | No personalization signal. |
| S4 | MISSING | No occasion/event/weather context. | `analysis.py:229-332` | No context. |
| S5 | PARTIALLY IMPLEMENTED | Displays confidence and `needs_more_data`, but they describe appearance/engine completeness. | `outfit_analysis_screen.dart:75-78`, `:404-431` | Not clothing confidence; garment confidence is never surfaced. |
| S6 | PARTIALLY IMPLEMENTED | Persists face shape to `style_profile`; no garment facts. | `analysis.py:365-372`; `repositories.py:265-306` | Outfit scan does not enrich the outfit model. |

#### Findings

- **Outfit Scan is not an outfit analyzer.** It is a face-shape analyzer with a hairstyle recommendation and an empty outfit section.
- **The empty outfit state is a false negative.** The UI says no clothing items were detected in the photo; the actual cause is that no garment adapter was called. Evidence: `outfit_analysis_screen.dart:877`.
- **The confidence display is semantically wrong for the capability.** It shows appearance/engine confidence while the user is looking at an “Outfit Analysis” screen. Evidence: `outfit_analysis_screen.dart:75-78`, `:404-431`.
- **Garment uncertainty exists but is not shown.** The domain object has `confidence` and `needs_review`; the result UI has no garment-confidence surface. Evidence: `value_objects.py:102-117`.
- **“Save Profile” is a no-op API-wise.** The appearance profile was already persisted during the run. The toast is technically true but the button is misleading. Evidence: `outfit_analysis_screen.dart:1031-1054`; `analysis.py:365-372`.
- **“See Recommendations” is generic.** It opens the daily outfit, not recommendations based on the scanned outfit. Evidence: `outfit_analysis_screen.dart:1056-1063`.
- **The general advice is an honest fallback** for partial appearance data, but it does not make the capability an outfit scan. Evidence: `outfit_analysis_screen.dart:665`, `:754`.
- **A no-face result can still receive a hairstyle direction.** `CreateOutfitRun` and `EphemeralOutfitAnalysis` do not require `faceShape`; `score_candidates` falls back to `oval` for an empty profile. The UI can therefore say the face was not measurable while still showing a “Styling direction.” Evidence: `analysis.py:229-332`, `:1048-1050`; `analysis_rules.py:168`, `:221-223`, `:299`, `:347-354`.
- **`needs_more_data` is always true for a face-only profile** because completeness is 0.25. This is technically honest but functionally deterministic; the user sees general advice rather than an outfit result. Evidence: `analysis_rules.py:226-243`, `:461-462`.

### 5.5 Capability comparison

| Dimension | Initial Scan | Hairstyle Scan | Outfit Builder | Outfit Scan |
|---|---|---|---|---|
| Real AI observation | Face + garment ephemeral | Face shape | None (wardrobe/context) | Face shape only |
| Durable person update | None | Face shape | None | Face shape |
| Uses preferences | No | Partial/profile-only | Partial | No |
| Uses event context | No | No | Occasion only | No |
| Surfaces uncertainty | Partial | No | No | Partial but mislabeled |
| Working save path | No analysis save | Yes | Yes | No separate save |
| Capability truth | Preview only | Real narrow analysis | Real outfit generation | Not outfit analysis |

---

## 6. Shared Person Model, Decision State, and Capability-Specific Data Boundaries

### 6.1 Boundary model

| Boundary | Purpose | Current stores/paths | Authority in reviewed code | Problems |
|---|---|---|---|---|
| **A. Shared persistent person model** | Durable facts/preferences reused across sessions and capabilities | `users.style_profile` JSONB; `users.preferences.preferred_occasions`; wardrobe; saved looks; events; analysis runs; learning signals | Backend database is the durable authority for server-side fields; Flutter local storage is a separate authority for profile display | The Flutter profile does not read `/me` `styleProfile`; Today’s Look separately parses a `styleDna` projection; guest migration excludes face; style profile is mostly face-shaped and not complete; no explicit field-level ownership. |
| **B. Temporary decision state** | In-flight analysis, preview, pending auth intent, per-request generation context | Analysis snapshots; stashed ephemeral results; pending post-auth intent; outfit builder form; preference optimistic buffer | In-memory/local only; not durable by design | “Save My Progress” language hides that the state is only an intent; no replay guarantee. |
| **C. Capability-specific records** | Run history, outputs, saved outfits, hairstyle results, garment observations, feedback | `analysis_runs`; saved looks; saved outfits; feedback rows; try-on fixture data | Capability-specific tables/services | Some outputs never become shared facts; some shared facts are written from partial capability views; garment observations are not persisted as reusable person data. |

### 6.2 Shared model field map

| Field/group | Current location | Written by | Read by | Status |
|---|---|---|---|---|
| `faceShape` | `users.style_profile`; local `FaceProfile` | Hairstyle image run; Outfit Scan run; local face processing | Hairstyle recommendations; profile local UI | PARTIALLY IMPLEMENTED |
| `skinTone` | `AppearanceProfile`; `users.style_profile` possible key | No real writer; adapter returns `None` | Hairstyle result UI; profile local UI | MISSING in practice |
| `bodyType` | `AppearanceProfile`; `users.style_profile` possible key | No real writer; adapter returns `None` | Hairstyle result UI; profile local UI | MISSING in practice |
| `styleType` | `AppearanceProfile`; `users.style_profile` possible key | No real writer; adapter returns `None` | Hairstyle result UI; profile local UI | MISSING in practice |
| `sourceRunId` | `AppearanceProfile`; `users.style_profile` | Image analysis runs | Backend projection/provenance | PARTIALLY IMPLEMENTED |
| `preferred_occasions` | `users.preferences`; local preferences | Preferences screen; event R36 feed | Outfit Builder; Today’s Look; Discover/For You | VERIFIED |
| Wardrobe items | `wardrobe_items`; local guest wardrobe | Wardrobe flows; migration | Outfit Builder; Today’s Look; insight | VERIFIED |
| Saved looks | `saved_looks` | Hairstyle save; saved looks flow | Hairstyle profile-only path; profile counts | VERIFIED |
| Saved outfits | Outfit saved tables | Outfit Builder save | Saved outfits/profile | VERIFIED |
| Events | `user_events` | Event add/edit | Today’s Look; R36 preferred occasion feed | VERIFIED |
| Feedback | Feedback table | Saved looks feedback | Outfit Builder ranking | PARTIALLY IMPLEMENTED |
| Learning signals | `learning_signals` | Analysis/outfit actions | Not shown as a ranking read in reviewed paths | PARTIALLY IMPLEMENTED |
| `appearanceConfidence` | `ProfileView` | Derived from `style_profile` completeness | No Flutter parse found | VERIFIED schema; MISSING UI |

### 6.3 Boundary violations

1. **Flutter profile asserts local appearance as the profile.**
   `ProfileScreen` reads `skinTone`, `faceShape`, `bodyType`, and `styleType` from local storage. Evidence: `profile_screen.dart:358-374`. It does not read the backend `ProfileView.styleProfile`.
2. **Backend schema exposes a profile the client does not consume.**
   `ProfileView` includes `styleProfile`. Evidence: `users.py:17-32`. No Flutter parse of that field was found.
3. **Guest migration drops a shared-model field.**
   Face/appearance data is explicitly excluded from guest migration. Evidence: `guest_data_migration.dart:47-55`.
4. **Outfit Scan writes a face shape into the shared model** even though its own capability is about outfits. Evidence: `analysis.py:365-372`.
5. **Hairstyle and Outfit Scan share the same `style_profile` write path** but have different observation scopes; there is no field-level capability provenance beyond `source_run_id`.
6. **Garment observations are capability-specific and not persisted as shared person data.** The garment adapter returns a profile, but no shared model write for garments was found.
7. **Temporary state is described as durable.** “Save My Progress” stores an intent, not the analysis. Evidence: `your_analysis_screen.dart:86-100`.

### 6.4 Reliability assessment

| Property | Assessment | Evidence |
|---|---|---|
| Single authority per field | Weak | Backend JSONB and local Flutter storage both hold appearance/profile values. |
| Read path | Weak | Profile screen reads local values; `/me` `styleProfile` is not consumed. Today’s Look parses a separate `styleDna` projection, but it is not the profile authority. |
| Write path | Partial | Hairstyle/Outfit Scan write face shape; preferences/events/wardrobe have their own writes. |
| Partial-update safety | Good | `update_style_profile` merges non-empty fields. Evidence: `repositories.py:265-306`. |
| Erasure/deletion | Partial | Account deletion cascade exists; no in-app delete UI; no clear style-profile operation. |
| Provenance | Partial | `source_run_id` exists; no field-level provenance, confidence, or version in the profile. |
| Guest continuity | Weak | Wardrobe/preferences migrate; face appearance explicitly does not. |
| Capability separation | Weak | Capability-specific observations can become shared facts without a declared projection contract. |

### 6.5 Recommended boundary contract

**DESIGN PROPOSAL — not current behavior**

- Declare the backend `users.style_profile` as the authoritative shared appearance store.
- Define a projection contract: which fields each capability may write, which fields are read-only for that capability, and what provenance/confidence is attached.
- Keep garment observations capability-specific unless a product decision explicitly promotes them to the shared model.
- Keep temporary previews in Boundary B and never call them “saved” unless a durable write has occurred.
- Add a guest migration matrix that lists every data class and its disposition.
- Use the existing store and merge semantics; no database redesign is required for the smallest safe repair.

---

## 7. End-to-End User Journey Traces

### 7.1 Guest Initial Scan journey

| Step | User experience | Actual system behavior | Evidence | Truth status |
|---|---|---|---|---|
| 1 | User reaches onboarding photo capture without an account | Guest branch routes to `AiAnalysisScreen` | `photo_capture_screen.dart:414-421` | VERIFIED |
| 2 | User takes/selects a photo | Image bytes are read | `ai_analysis_screen.dart:108-123` | VERIFIED |
| 3 | “Analyzing” progress | Outfit ephemeral and garment ephemeral calls run in parallel | `ai_analysis_screen.dart:19-20`, `:108-123` | VERIFIED |
| 4 | Preview appears | Snapshot is stashed and passed to the preview screen | `ai_analysis_screen.dart:124-137`; `your_analysis_screen.dart:308-449` | VERIFIED |
| 5 | User taps “Save My Progress” | A pending `save_progress` intent is recorded; no analysis POST is made | `your_analysis_screen.dart:86-100` | FALSE SAVE |
| 6 | User taps “Continue Without Account” | Local guest flags are set; home is shown | `your_analysis_screen.dart:102-118` | VERIFIED |
| 7 | User creates an account / chooses maybe later | `analysis_cached` is set true in `_onMaybeLater`; the pending intent may route home | `create_account_screen.dart:223-231`; `post_auth_flow.dart` | PARTIAL |
| 8 | Post-auth message | “Account ready — your local progress was kept.” can appear even after discard | `post_auth_flow.dart:169-180` | FALSE IN DISCARD PATH |

**Outcome:** The user gets a real preview, but no durable analysis from the Initial Scan. The guest face/garment observations are not promoted to the authenticated person model. The save/discard/auth transition is the weakest part of the journey.

### 7.2 Authenticated Hairstyle journey

| Step | User experience | Actual system behavior | Evidence | Truth status |
|---|---|---|---|---|
| 1 | Authenticated user takes onboarding photo | Routes to hairstyle processing | `photo_capture_screen.dart:397-411` | VERIFIED |
| 2 | Progress stages | Shows “Analyzing skin tone,” “Applying Style DNA,” etc. | `hairstyle_mock_data.dart:39-61` | FALSE STAGES |
| 3 | Backend analyzes image | Real face-shape adapter; no default shape | `analysis.py:502-546` | VERIFIED |
| 4 | Recommendation is generated | `recommend_hairstyle` uses face shape; image path does not use saved looks/preferences | `analysis.py:551-554`; `analysis_rules.py:419-454` | PARTIAL |
| 5 | Result screen | Skin tone and Style DNA rows can be empty; match percentage shown | `hairstyle_result_screen.dart:234-241`, `:290` | MISLEADING |
| 6 | Result confidence | Backend has confidence/needs_more_data; Dart ignores both | `analysis_rules.py:378-393`, `:461-462`; `hairstyle_mock_data.dart:129-145` | MISSING UI |
| 7 | Save Style | Durable `/v1/looks/saved` call | `hairstyle_service.dart:57`, `:424-448` | VERIFIED |
| 8 | Profile after save | Local face profile is set; backend `style_profile` gets face shape | `face_processing_screen.dart:147-155`; `analysis.py:587` | PARTIAL |

**Outcome:** The hairstyle path is real but narrow. It measures face shape, recommends from a catalog, and saves a look. It does not measure skin tone/body/style, does not use goals, and does not expose uncertainty. The UI’s stage and result copy overstate the analysis.

### 7.3 Outfit Builder journey

| Step | User experience | Actual system behavior | Evidence | Truth status |
|---|---|---|---|---|
| 1 | User opens Outfit Builder from Home or an event | Form is shown; event entry may pass occasion/display metadata | `event_list_screen.dart:109-117`; `build_outfit_screen.dart:59-80` | VERIFIED |
| 2 | User chooses occasion, mood, fit, palette | Form values are captured | `outfit_models.dart:73-105` | VERIFIED |
| 3 | User generates | `POST /v1/outfits/generate` | `outfit_client.dart:85` | VERIFIED |
| 4 | Progress | Static “Applying Style DNA” stage | `outfit_builder_mock_data.dart:139-142`; `outfit_generation_screen.dart:242` | FALSE CLAIM |
| 5 | Backend derives outfit | Wardrobe + preferred occasions + feedback/wear; no appearance/style profile/event identity | `outfits.py:453-516` | PARTIAL |
| 6 | Result | Ensemble and match percentage; mislabeled “Style Score Impact” | `outfit_recommendation_screen.dart:225-251`; `outfits.py:352-355` | FALSE SEMANTICS |
| 7 | Save outfit | Durable save with `sourceContext: "outfit"` | `outfit_client.dart:143` | VERIFIED |
| 8 | Regenerate | Deterministic seed cycle | `outfit_generation_screen.dart`; `outfit_client.dart` | VERIFIED |

**Outcome:** Outfit Builder is real and useful as a wardrobe/occasion generator. It is not an appearance-aware or event-aware stylist, and its “Style DNA” and “Style Score Impact” language is not supported by the backend.

### 7.4 Outfit Scan journey

| Step | User experience | Actual system behavior | Evidence | Truth status |
|---|---|---|---|---|
| 1 | User opens Outfit Scan | Guest/auth paths available | `outfit_scan_screen.dart:308-341` | VERIFIED |
| 2 | Guest submits photo | Ephemeral call, snapshot stashed | `outfit_scan_screen.dart:391-426` | VERIFIED |
| 3 | Auth user submits photo | Durable `POST /v1/analysis/outfit`, then poll | `outfit_scan_screen.dart:324-341`; `outfit_processing_screen` | VERIFIED |
| 4 | Backend processes | Appearance adapter + `recommend_hairstyle`; no garment adapter | `analysis.py:229-352` | FALSE CAPABILITY |
| 5 | Result screen | Reads `garment`/`detectedItems`; none exist | `outfit_analysis_screen.dart:814-821` | CONTRACT MISMATCH |
| 6 | Outfit observations | “No clothing items detected in this photo.” | `outfit_analysis_screen.dart:865-877` | FALSE NEGATIVE |
| 7 | Confidence | Displays appearance/engine confidence | `outfit_analysis_screen.dart:404-431` | MISLABELED |
| 8 | Save Profile | No API; run already persisted face shape | `outfit_analysis_screen.dart:1031-1054`; `analysis.py:365-372` | REDUNDANT |
| 9 | See Recommendations | Routes to daily outfit | `outfit_analysis_screen.dart:1056-1063` | GENERIC |
| 10 | Persistence | Face shape to `style_profile`; no garment facts | `analysis.py:365-372` | PARTIAL |

**Outcome:** The user sees an “Outfit Analysis” screen that did not analyze the outfit. This is the most serious capability-truth failure in Stage 1.

### 7.5 Return loop: profile, preferences, saved looks, home

| Step | User experience | Actual system behavior | Evidence | Truth status |
|---|---|---|---|---|
| 1 | User opens profile | Local appearance/preferences are shown | `profile_screen.dart:358-374` | LOCAL ONLY |
| 2 | User edits preferences | Only occasion focus is available; optimistic local buffer then PATCH | `preferences_screen.dart:18`, `:50-56`, `:91-95`, `:121-190` | PARTIAL |
| 3 | User views saved looks | Feedback controls available | `saved_looks_screen.dart:332-333`, `:474-483` | VERIFIED |
| 4 | User views look details | No feedback controls | `look_details_screen.dart:17`, `:286` | GAP |
| 5 | Home summary | Style Score is base 60 + wardrobe/saved looks; supporting copy is honest | `learning.py:116-152`; `backend_summary_cards.dart:100-117` | VERIFIED |
| 6 | Home Today’s Look | Uses nearest event occasion + preferred occasions; no weather | `today.py:160-171`, `:29-30` | VERIFIED |
| 7 | Discover For You | Uses backend personalization scores in primary path | `discover.py:147-167`; `discover_screen.dart:1051-1052` | VERIFIED |
| 8 | Next analysis | Hairstyle image path does not use saved looks; guest migration excludes face | `analysis.py:553`; `guest_data_migration.dart:47-55` | BROKEN LOOP |

**Outcome:** The loop is partially closed for wardrobe, occasions, saved looks, and outfit feedback. It is not closed for appearance, goals, style identity, garment observations, or guest continuity.

---

## 8. Missing Information, Contradictions, and Unsupported Claims

### 8.1 Contradiction and claim ledger

| ID | Claim or expectation | Actual behavior | Evidence | Severity | Disposition |
|---|---|---|---|---|---|
| C-01 | Initial Scan saves the user’s progress/analysis | “Save My Progress” records only a pending auth intent; no analysis is posted | `your_analysis_screen.dart:86-100` | P0 | Fix copy or implement durable save/replay |
| C-02 | After sign-in, local progress was kept | Post-auth copy can say this after DISCARD; no automatic replay found | `post_auth_flow.dart:60-83`, `:169-180`; `create_account_screen.dart:229` | P0 | Fix copy and state transition |
| C-03 | Guest migration preserves the person model | Face/appearance is explicitly excluded; only wardrobe/preferences migrate | `guest_data_migration.dart:47-55` | P0 | Product decision + migration change |
| C-04 | Outfit Scan analyzes the outfit | It calls the hairstyle engine and never the garment adapter | `analysis.py:193-352` | P0 | Implement garment contract or rename capability |
| C-05 | Outfit Scan detected no clothing | No garment request was made; the UI interprets a missing key as a negative observation | `outfit_analysis_screen.dart:814-877` | P0 | Remove false negative; add real garment path |
| C-06 | Outfit Scan shows outfit confidence | It shows appearance/engine confidence | `outfit_analysis_screen.dart:75-78`, `:404-431` | P0 | Rename/reposition or add garment confidence |
| C-07 | Hairstyle analyzes skin tone and Style DNA | Adapter measures only face shape; skin tone/body/style are forced empty | `vision_appearance_adapter.py:229-236`; `hairstyle_result_screen.dart:234-241` | P0 | Remove empty rows and false stages |
| C-08 | Hairstyle recommendation is personalized | Image path uses face shape only; explicit preferred-look mapping is not implemented | `analysis.py:551-554`; `analysis_rules.py:118-130` | P0/P1 | Use real preference signals or qualify claim |
| C-09 | Catalog reasons are personalized | Reasons reference “warm medium skin tones” and “your Modern Classic Style DNA” without measured values | `catalog.py:130-131` | P0 | Replace with grounded generic reasons |
| C-10 | Progress stages reflect real work | “Analyzing skin tone,” “Applying Style DNA” are static/mock stages | `hairstyle_mock_data.dart:39-61`; `outfit_builder_mock_data.dart:139-142` | P0/P1 | Remove or rename to actual stages |
| C-11 | “Style Score Impact” measures score impact | It is the ensemble match percentage | `outfits.py:352-355`; `outfit_recommendation_screen.dart:225-251` | P0 | Rename to Match or compute real delta |
| C-12 | Camera data is not stored | Image bytes are handled ephemerally in the reviewed path, but profile fields are persisted after analysis; copy is overbroad | `camera_permission_screen.dart:154-169`; `analysis.py:587` | P1 | Rewrite privacy copy to distinguish image bytes/profile |
| C-13 | Account can be deleted | Backend API exists; no Flutter delete-account UI was found | `users.py:130-151` | P1 | Add UI or remove product claim |
| C-14 | Feedback improves recommendations consistently | Outfit ranking uses feedback; hairstyle image path does not use saved looks; look details have no feedback | `outfits.py:503-516`; `analysis.py:553`; `look_details_screen.dart:17` | P2 | Define feedback scope |
| C-15 | Profile shows the current person model | Flutter profile reads local storage, not backend `styleProfile` | `profile_screen.dart:358-374` | P1 | Hydrate backend or label local |
| C-16 | Events shape recommendations | Event R36 feeds preferred occasions; Outfit Builder uses a preselected occasion; event identity/location/date are display-only | `events.py:114-129`; `build_outfit_screen.dart:59-80` | P1 | Pass event context or state scope |
| C-17 | Weather affects recommendations | No weather provider; Today’s Look explicitly has no weather hint | `today.py:29-30` | Verified absence | Do not imply weather |
| C-18 | `needs_more_data` tells the user what is missing | Backend emits it; hairstyle Dart ignores it; Outfit Scan shows a general fallback | `analysis_rules.py:461-462`; `hairstyle_mock_data.dart:129-145` | P1 | Surface specific missing evidence |
| C-19 | Confidence is model confidence | Hairstyle confidence is derived from completeness and top-pick decisiveness | `analysis_rules.py:378-393` | P1 | Label as evidence completeness/decision confidence |
| C-20 | Garment confidence is used | Domain object has it; Initial Scan does not display it | `value_objects.py:102-117` | P1 | Surface or explicitly omit |
| C-21 | “See Recommendations” uses the scanned outfit | Routes to daily outfit | `outfit_analysis_screen.dart:1056-1063` | P2 | Make scan-specific or relabel |
| C-22 | “Save Profile” saves a profile from the outfit scan | No API call; the run already persisted appearance | `outfit_analysis_screen.dart:1031-1054` | P2 | Remove or explain |
| C-23 | Try-on is a production capability | Explicitly mock/test data | `try_on_screen.dart:18-29` | Verified limitation | Keep honest label |
| C-24 | Offline assistant analyzes photos | Explicitly says it cannot analyze photos offline | `offline_assistant.dart:206-230` | Verified limitation | Keep honest label |
| C-25 | A missing face shape prevents a hairstyle recommendation | Outfit Scan and Initial Scan do not guard `faceShape`; scoring falls back to `oval` | `analysis.py:229-332`, `:1048-1050`; `analysis_rules.py:168`, `:221-223`, `:299` | P0 | Fail honestly or label a fallback; do not infer a face shape |
| C-26 | Guest analyses never run | The screen’s own comment says this, while `AiAnalysisScreen` runs live ephemeral calls and the preview shows their observations | `your_analysis_screen.dart:89`; `ai_analysis_screen.dart:97-140` | P2 | Correct the comment to prevent a truth regression |

### 8.2 Positive truth controls found

- Mock hairstyle results are blocked from the result UI. Evidence: `face_processing_screen.dart:136-159`.
- Outfit Scan does not fabricate garment attributes when the key is absent. It shows an empty state. The problem is the missing request, not fabricated values. Evidence: `outfit_analysis_screen.dart:865-877`.
- The hairstyle image path does not substitute a default face shape. Evidence: `analysis.py:534-546`. This guard is not shared with Outfit Scan or the guest Initial Scan.
- Style Score supporting copy is grounded in wardrobe/saved looks. Evidence: `backend_summary_cards.dart:100-117`.
- The try-on screen explicitly labels test data. Evidence: `try_on_screen.dart:18-29`.
- The offline assistant states its limitation. Evidence: `offline_assistant.dart:206-230`.
- Partial style-profile updates do not erase previous fields. Evidence: `repositories.py:265-306`.
- The garment adapter reports `needs_review` and confidence rather than pretending certainty. Evidence: `vision_garment_adapter.py:196-208`.

### 8.3 Missing information

| ID | Missing information | Why it matters | Current evidence |
|---|---|---|---|
| M-01 | Explicit goal/desired-change model | S2 cannot be evaluated as implemented | No goal field found in reviewed profile/request paths |
| M-02 | Skin tone/body type/style type measurement | S1 claims appearance breadth it does not have | `vision_appearance_adapter.py:229-236` |
| M-03 | Garment observation in Outfit Scan | S1 and Outfit Scan core promise | `analysis.py:193-352` |
| M-04 | Garment confidence in result UI | S5 uncertainty | `value_objects.py:102-117`; no UI key |
| M-05 | Shared person-model read path in Flutter | S6 reliability | `profile_screen.dart:358-374` |
| M-06 | Guest face/appearance migration | S6 continuity | `guest_data_migration.dart:47-55` |
| M-07 | Event identity/context pass-through | S4 context | `build_outfit_screen.dart:59-80` |
| M-08 | Feedback on non-saved recommendations | S3/S6 learning loop | `look_details_screen.dart:17` |
| M-09 | Account deletion UI | S6 privacy promise | `users.py:130-151`; no Flutter UI found |
| M-10 | Explicit photo/image retention policy in UI | S5/S6 privacy | `camera_permission_screen.dart:154-169` is ambiguous |
| M-11 | Clear style-profile erasure operation | S6 delete/control | Merge-only update path; no clear operation found |
| M-12 | Field-level provenance/version in shared profile | S6 explainability | `source_run_id` only |
| M-13 | `needs_more_data` reason details | S5 actionable uncertainty | Boolean only |
| M-14 | Style identity source of truth | S3 | Empty adapter fields + local profile |
| M-15 | Definition of “Style Score” in product language | Trust | Base-60 usage metric; supporting copy only partially explains |

---

## 9. Acceptance Criteria

These criteria are written to be testable without requiring live AI quality judgments. They test contracts, truthfulness, persistence, and capability boundaries.

### 9.1 Capability truth

- [ ] **AC-01 — Outfit Scan performs outfit observation.** An authenticated Outfit Scan run invokes a garment analyzer and the result contains a non-empty garment observation or an explicit “no garment detected” result produced by that analyzer.
- [ ] **AC-02 — Outfit Scan does not fake a negative.** The string “No clothing items detected” is shown only when the garment analyzer explicitly reports no garment, never merely because the garment key is absent.
- [ ] **AC-03 — Outfit Scan confidence is outfit confidence.** Any confidence shown on an outfit result describes garment observation confidence or is labeled as appearance confidence and visually separated from outfit observations.
- [ ] **AC-04 — Initial Scan persistence is truthful.** Either the analysis is durably saved, or “Save My Progress” is removed/replaced with copy that says only a sign-in intent is stored.
- [ ] **AC-05 — Post-auth copy matches state.** If DISCARD was chosen, no post-auth message says local progress was kept.
- [ ] **AC-06 — Guest migration declares its scope.** The migration UI/copy states that face/appearance data is not migrated, or the migration includes it under explicit consent.

### 9.2 Subject S1 — appearance

- [ ] **AC-07 — Measured-only appearance.** No screen displays a skin-tone, body-type, or style-type value unless a real source produced it.
- [ ] **AC-08 — Empty appearance fields are labeled.** If a field is intentionally not measured, the UI shows “Not measured”/“Not available” or hides the row.
- [ ] **AC-09 — Face-shape vocabulary is consistent.** The adapter, rule engine, persistence, and UI use one canonical face-shape value set.
- [ ] **AC-10 — Appearance profile is not written by a capability that did not measure it.** Outfit Scan must not write appearance facts unless appearance analysis is an explicit part of its contract.

### 9.3 Subject S2 — goals

- [ ] **AC-11 — Goal decision recorded.** The repository contains an accepted decision that goals/desired change are either in Stage 1 or explicitly out of scope.
- [ ] **AC-12 — If in scope, goals are durable.** A goal can be created, read, updated, and used by at least one capability.
- [ ] **AC-13 — Request mood is not a goal.** UI and analytics do not label per-request mood/occasion as a persistent personal goal.

### 9.4 Subject S3 — preferences and style identity

- [ ] **AC-14 — Claimed personalization is grounded.** Any copy that says “your style,” “personalized,” or “Style DNA” is backed by a stored or declared field used by that capability.
- [ ] **AC-15 — Hairstyle preference use is consistent.** Image-based and profile-based hairstyle paths either both use the documented preference signals or the difference is explicitly labeled.
- [ ] **AC-16 — Style identity has an authority.** The source of truth for `skinTone`, `bodyType`, and `styleType` is documented and read by the profile and relevant capabilities.

### 9.5 Subject S4 — context

- [ ] **AC-17 — Event context is passed or labeled.** If Outfit Builder uses event identity/date/location, those fields reach the backend; otherwise the UI says occasion only.
- [ ] **AC-18 — No weather claim without weather data.** No screen implies weather-aware recommendations while no weather source exists.
- [ ] **AC-19 — Constraint fields are honest.** Budget, comfort, dress code, or mobility constraints are either captured and used or explicitly out of scope.

### 9.6 Subject S5 — uncertainty

- [ ] **AC-20 — Confidence has a definition.** Each confidence shown to users has a documented meaning and is not presented as calibrated model certainty unless it is.
- [ ] **AC-21 — `needs_more_data` is actionable.** When true, the UI explains which evidence is missing and what the user can do next.
- [ ] **AC-22 — Garment uncertainty is surfaced.** Garment confidence/`needs_review` is shown or explicitly omitted in every interface that presents garment observations.
- [ ] **AC-23 — Stage labels are real.** No progress label claims a stage that did not execute.

### 9.7 Subject S6 — reliable model

- [ ] **AC-24 — One read authority.** The authenticated profile reads the backend person model, or the UI clearly labels local-only values.
- [ ] **AC-25 — No silent erasure.** A partial update never clears fields it did not intend to update.
- [ ] **AC-26 — Guest transition is explicit.** Every data class has a documented migrate/drop decision, and the user is told which applies.
- [ ] **AC-27 — Provenance is usable.** A recommendation can be traced to a run/profile version without reading raw logs.
- [ ] **AC-28 — Deletion is complete and accessible.** If account deletion is offered, the Flutter UI exists and the privacy copy matches the backend cascade.

### 9.8 Cross-cutting truth and privacy

- [ ] **AC-29 — No unsupported catalog claims.** Catalog reasons are generic unless grounded in measured values.
- [ ] **AC-30 — No fake save.** A button labeled Save performs a durable write or clearly states what is stored.
- [ ] **AC-31 — Privacy copy distinguishes image bytes from profile data.** The camera/scan copy is accurate for both.
- [ ] **AC-32 — “Style Score Impact” is renamed or computed as an actual delta.**
- [ ] **AC-33 — No hidden face-shape default.** A missing face shape produces an explicit no-face state, not a hairstyle recommendation scored as `oval`.

---

## 10. Prioritized Implementation Backlog

### 10.1 P0 — truth, capability, and data continuity

| ID | Item | Subject/capability | Smallest safe change | Depends on | Acceptance |
|---|---|---|---|---|---|
| P0-01 | Add garment observation to Outfit Scan | S1 / Outfit Scan | Reuse existing garment adapter; call it in `CreateOutfitRun`; include garment in snapshot | D3 | AC-01, AC-02 |
| P0-02 | Remove false outfit empty state and separate confidence semantics | S5 / Outfit Scan | Show garment absence only from garment result; label appearance confidence separately | P0-01 | AC-02, AC-03 |
| P0-03 | Make Initial Scan save truthful | S6 / Initial Scan | Either persist/replay the snapshot or change “Save My Progress” to sign-in intent copy | D2 | AC-04, AC-05 |
| P0-04 | Fix guest migration scope | S6 / onboarding | Migrate face/appearance with consent, or explicitly disclose exclusion | D10 | AC-06, AC-26 |
| P0-05 | Fix post-auth state copy | S6 / onboarding | Derive message from actual pending state; do not set `analysis_cached` true unconditionally | P0-03 | AC-05 |
| P0-06 | Remove false hairstyle appearance/stage claims | S1, S5 / Hairstyle | Hide empty skin/style rows; replace false stages; ground catalog reasons | D1, D8 | AC-07, AC-08, AC-23, AC-29 |
| P0-07 | Rename or compute “Style Score Impact” | S5 / Outfit Builder | Rename to “Match” or compute a real before/after score delta | D9 | AC-32 |
| P0-08 | Fix face-shape canonicalization mismatch | S1 / Hairstyle | Use one canonical value in scoring and boost rules | None | AC-09 |
| P0-09 | Remove hidden `oval` fallback from no-face paths | S1, S5 / Initial Scan, Outfit Scan | Reject empty face shape or return an explicit no-face state; do not score a default shape | D1 | AC-33 |

### 10.2 P1 — subject coherence

| ID | Item | Subject/capability | Smallest safe change | Depends on | Acceptance |
|---|---|---|---|---|---|
| P1-01 | Hydrate profile from backend `styleProfile` | S6 / profile | Read `/v1/users/me`; merge with local fallback; label local-only | D4 | AC-24 |
| P1-02 | Surface hairstyle confidence/needs_more_data | S5 / Hairstyle | Parse fields; show evidence completeness and missing-data guidance | P0-06 | AC-20, AC-21 |
| P1-03 | Surface garment confidence/needs_review | S5 / Initial Scan | Add confidence/review indicators to garment observations | P0-01 | AC-22 |
| P1-04 | Define goal/desired-change contract | S2 / all | Decide in/out of scope; if in, add minimal durable field and one consumer | D5 | AC-11, AC-12 |
| P1-05 | Pass event context or label it | S4 / Outfit Builder | Send event ID/date/location where permitted, or change UI to “occasion only” | D6 | AC-17 |
| P1-06 | Use preferences in image hairstyle path | S3 / Hairstyle | Pass preferred/saved signals consistently or document the difference | D4 | AC-15 |
| P1-07 | Fix Save Profile / See Recommendations semantics | S6 / Outfit Scan | Remove redundant save; link to scan-specific or relabel | P0-01 | AC-30 |
| P1-08 | Fix privacy copy | S6 / camera | Distinguish image processing from profile persistence | None | AC-31 |
| P1-09 | Add account deletion UI if supported | S6 / account | Wire existing backend delete into settings with confirmation | D11 | AC-28 |

### 10.3 P2 — feedback, consistency, and account surfaces

| ID | Item | Subject/capability | Smallest safe change | Depends on | Acceptance |
|---|---|---|---|---|---|
| P2-01 | Add feedback to all recommendation surfaces or scope it | S3/S6 | Add feedback to look details or state saved-look-only scope | D12 | AC-14 |
| P2-02 | Unify appearance/local profile display | S6 / profile | Prefer backend values; local fallback only | P1-01 | AC-24 |
| P2-03 | Make stage labels truthful globally | S5 / all | Replace mock stages with actual pipeline stages | P0-06 | AC-23 |
| P2-04 | Add explicit style-profile clear/erase if promised | S6 / profile | Add clear operation or document no-erasure behavior | D14 | AC-25 |
| P2-05 | Clarify Style Score explanation | S6 / Home | Expose formula/meaning or keep supporting text only | D9 | AC-32 |
| P2-06 | Ensure garment observations are not lost | S5/S6 | Persist or clearly scope garment data | P0-01 | AC-22 |

### 10.4 P3 — polish and observability

| ID | Item | Subject/capability | Smallest safe change | Depends on | Acceptance |
|---|---|---|---|---|---|
| P3-01 | Add truth regression tests for result copy | Cross-cutting | Widget tests for forbidden claims | P0 items | AC suite |
| P3-02 | Add contract tests for snapshot keys | Cross-cutting | Backend/Flutter contract tests for `garment`, `confidence`, `needs_more_data` | P0-01 | AC-01 |
| P3-03 | Add provenance to result surfaces | S6 | Show run/source metadata in debug/detail view | P1-01 | AC-27 |
| P3-04 | Audit catalog metadata for unsupported personalization | S3/S5 | Classify catalog reasons; remove ungrounded claims | P0-06 | AC-29 |
| P3-05 | Document data-class migration matrix | S6 | Add docs, not code | None | AC-26 |

### 10.5 Backlog ordering rationale

- P0-01 and P0-02 must precede any claim that Outfit Scan works.
- P0-03 and P0-05 must precede any onboarding “save” promise.
- P0-04 and P0-06 are trust-and-consent work; they should not wait for a shared-model redesign.
- P0-07, P0-08, and P0-09 are small, high-trust fixes that can ship independently.
- P1 work should not begin until the P0 truth pass is accepted; otherwise new UI will encode the same false model.

---

## 11. Dependencies and Implementation Sequence

### 11.1 Dependency graph

```text
D1 appearance scope ─┬─> P0-06 hairstyle truth
                    └─> P0-09 no-face honesty
D2 Initial Scan scope ──> P0-03 save/replay ──> P0-05 post-auth truth
D3 Outfit Scan scope ──> P0-01 garment contract ──> P0-02 confidence/empty state
D4 shared model authority ──> P1-01 backend profile hydration ──> P2-02 profile unification
D5 goal scope ──> P1-04 goal contract
D6 event context scope ──> P1-05 event pass-through
D7 confidence definition ──> P1-02/P1-03 uncertainty UI
D8 catalog grounding ──> P0-06 catalog copy
D9 Style Score semantics ──> P0-07 label/calculation
D10 guest migration scope ──> P0-04 migration
D11 deletion promise ──> P1-09 deletion UI
D12 feedback scope ──> P2-01 feedback surfaces
D13 image retention ──> P1-08 privacy copy
D14 style-identity authority ──> P1-06/P2-04
```

### 11.2 Recommended sequence

**Phase 0 — Decision lock (no code)**

- Resolve D1, D2, D3, D5, D7, D9, D10, D13, D14.
- Record decisions in `DECISIONS.md` only after founder approval.
- Do not start broad UI changes before these decisions.

**Phase 1 — P0 truth pass (smallest safe changes)**

- P0-06 hairstyle empty-field/stage/catalog truth.
- P0-07 Style Score Impact label.
- P0-08 face-shape canonicalization.
- P0-09 remove the hidden `oval` fallback from no-face paths.
- P0-05 post-auth copy/flag.
- P0-03 Initial Scan save language or replay.

This phase removes false claims and prevents new copy from encoding them.

**Phase 2 — Outfit Scan contract**

- Implement P0-01 using the existing garment adapter and snapshot contract.
- Implement P0-02 so outfit observation and appearance confidence are separate.
- Add contract tests for garment/detectedItems/confidence/needs_review.
- Do not call the capability “fixed” until the result contains a real garment observation or a real garment-negative.

**Phase 3 — Guest and shared model continuity**

- P0-04 guest migration decision and implementation.
- P1-01 backend style-profile hydration.
- P2-02 local/backend profile unification.
- Preserve merge semantics and avoid DB redesign unless a decision requires it.

**Phase 4 — Subject expansion**

- P1-04 goal/desired-change contract if in scope.
- P1-05 event context pass-through if approved.
- P1-06 hairstyle preference consistency.
- P1-02/P1-03 uncertainty surfaces.

**Phase 5 — Loop and account**

- P2-01 feedback scope.
- P1-09 account deletion UI if supported.
- P1-08 privacy copy.
- P2-04 style-profile clear/erase behavior.

**Phase 6 — Verification**

- Run the existing Flutter and backend test suites.
- Add contract and copy regression tests.
- Perform a live device walkthrough.
- Re-run this audit’s acceptance checklist.

### 11.3 Sequencing constraints

- **Do not add a goal UI before D5.** Otherwise the UI will invent a goal model.
- **Do not pass event identity to the backend before D6.** Privacy and retention scope must be decided.
- **Do not show garment confidence before P0-01.** That would make an absent observation look measured.
- **Do not hydrate the backend profile before D4.** The authority and conflict rules must be explicit.
- **Do not migrate face data before D10.** Consent and retention are product decisions.
- **Do not rename “Style Score Impact” without deciding whether a real delta is wanted.** A label-only fix is acceptable only if the product accepts match semantics.

### 11.4 Migration and schema note

The smallest safe repair uses existing structures:

- `users.style_profile` already exists and merges non-empty fields.
- `GarmentProfile` already has confidence/`needs_review`.
- `analysis_runs` already provides run history.
- The outfit snapshot contract already has a place for garment/detectedItems.
- `/v1/users/me` already exposes `styleProfile`.

A schema redesign is **not** the default. Only add fields/tables if a founder decision requires durable goals, field-level provenance, or garment-history storage.

---

## 12. Product Decisions Requiring Founder Approval

These are not audit conclusions. They are decisions the repository does not answer.

| ID | Decision | Why it must be decided | Audit recommendation | Impact if undecided |
|---|---|---|---|---|
| D1 | What appearance attributes are in Stage 1? | Adapter measures only face shape; UI claims more | Stage 1 = face shape + explicitly measured attributes only; label the rest “not measured” | False appearance claims continue |
| D2 | Is Initial Scan a preview or a persistent onboarding analysis? | Save/continue/auth copy assumes persistence; code stores an intent | If preview: remove save language. If onboarding: implement durable snapshot/replay | User loses progress and trust |
| D3 | Is Outfit Scan supposed to analyze outfits? | Current implementation is a hairstyle run | Yes: add garment analyzer. No: rename/remove outfit claims | P0 capability falsehood remains |
| D4 | What is authoritative for the shared person model? | Backend JSONB and local storage both hold profile data | Backend authoritative; Flutter reads it; local only offline fallback | Profile continues to diverge |
| D5 | Are goals/desired change in Stage 1? | No goal model exists | Either add a minimal durable goal or declare out of scope | S2 cannot be honestly claimed |
| D6 | Should event context affect recommendations? | Event type feeds occasion; identity/date/location are display-only | Pass occasion + relevant event fields with explicit retention; otherwise label occasion-only | Event-aware claims remain ambiguous |
| D7 | What does confidence mean? | Derived completeness vs model certainty vs match percentage are conflated | Define separate evidence-completeness, observation-confidence, and match score | Users cannot interpret certainty |
| D8 | Can catalog copy be personalized? | Catalog claims skin tone/Style DNA without measured data | Generic reasons unless grounded in measured values | Unsupported personalization |
| D9 | Is “Style Score Impact” a delta or a match? | Backend field is match percentage | Rename to Match; add delta only if a real before/after exists | Misleading metric |
| D10 | Does guest migration include face/appearance? | Currently excluded | Include only with explicit consent and retention copy; otherwise disclose exclusion | Silent data loss |
| D11 | Is account deletion available in-app? | Backend API exists; no Flutter UI found | Add UI if deletion is promised; otherwise remove claim | Privacy promise gap |
| D12 | What is feedback scope? | Only saved looks have feedback; look details do not | Define saved-look-only or add feedback everywhere recommendations are shown | Inconsistent learning loop |
| D13 | What is image retention? | Camera copy is ambiguous | State whether image bytes are ephemeral; distinguish profile persistence | Privacy confusion |
| D14 | What is style-identity authority? | Style identity is empty in adapter and local in UI | Define stored/declared fields; remove ungrounded UI | S3 cannot be reliable |
| D15 | Is Stage 1 allowed to add durable storage? | Some fixes need goal/provenance/garment history | Prefer existing stores; approve new fields only with necessity | Either overbuild or underdeliver |

### 12.1 Decision handling rule

A decision becomes an accepted requirement only when it is recorded in `DECISIONS.md` with the founder’s approval. Until then, the audit must keep the item marked **PRODUCT DECISION REQUIRED** and must not describe a proposed behavior as current.

---

## 13. Truth Ledger: Verified Facts, Interpretations, Proposals, and Unresolved Questions

### 13.1 Verified facts

| ID | Fact | Evidence |
|---|---|---|
| V-01 | Outfit Scan calls `CreateOutfitRun`, which calls only `recommend_hairstyle`; no garment adapter call was found. | `backend/app/application/analysis.py:193-352` |
| V-02 | Outfit Scan persists face-shape appearance to `style_profile`. | `analysis.py:365-372`; `repositories.py:265-306` |
| V-03 | Outfit Scan UI expects `garment`/`detectedItems`; the hairstyle snapshot does not provide them. | `outfit_analysis_screen.dart:814-821`; `analysis.py:332-352` |
| V-04 | Outfit Scan shows “No clothing items detected” when those keys are absent. | `outfit_analysis_screen.dart:865-877` |
| V-05 | Outfit Scan “Save Profile” has no API call. | `outfit_analysis_screen.dart:1031-1054` |
| V-06 | Outfit Scan “See Recommendations” routes to the daily outfit. | `outfit_analysis_screen.dart:1056-1063` |
| V-07 | Initial Scan is guest-only; authenticated onboarding routes to hairstyle. | `photo_capture_screen.dart:397-421` |
| V-08 | Initial Scan calls outfit and garment ephemeral endpoints in parallel. | `ai_analysis_screen.dart:108-123` |
| V-09 | Initial Scan “Save My Progress” records a pending intent, not the analysis. | `your_analysis_screen.dart:86-100` |
| V-10 | No automatic replay of the Initial Scan snapshot after authentication was found. | `post_auth_flow.dart`; `create_account_screen.dart:229` |
| V-11 | Post-auth copy can say local progress was kept after DISCARD. | `post_auth_flow.dart:60-83`, `:169-180` |
| V-12 | Guest migration excludes face/appearance. | `guest_data_migration.dart:47-55` |
| V-13 | The appearance adapter measures face shape only; skin tone/body type/style type are empty. | `vision_appearance_adapter.py:229-236` |
| V-14 | `AppearanceProfile` has no confidence field; confidence is returned separately as an analysis result. | `value_objects.py:66-78`; `value_objects.py:121-152` |
| V-15 | Hairstyle confidence is derived from completeness and top-pick decisiveness. | `analysis_rules.py:378-393` |
| V-16 | Hairstyle `needs_more_data` is `completeness < 1.0`. | `analysis_rules.py:461-462` |
| V-17 | Hairstyle Dart model ignores confidence and needs_more_data. | `hairstyle_mock_data.dart:129-145` |
| V-18 | Hairstyle result displays empty skin-tone/Style-DNA rows. | `hairstyle_result_screen.dart:234-241` |
| V-19 | Hairstyle save uses `/v1/looks/saved`. | `hairstyle_service.dart:57`, `:424-448` |
| V-20 | Mock hairstyle results are blocked from the result UI. | `face_processing_screen.dart:136-159` |
| V-21 | Outfit Builder uses wardrobe + preferred occasions + feedback/wear. | `outfits.py:479-516` |
| V-22 | Outfit Builder does not read `style_profile`, appearance, or event identity. | `outfits.py:479-516` |
| V-23 | Outfit Builder “Style Score Impact” maps to ensemble match percentage. | `outfits.py:352-355`; `outfit_recommendation_screen.dart:225-251` |
| V-24 | Event creation feeds preferred occasions via R36. | `events.py:114-129` |
| V-25 | Today’s Look uses the nearest event and has no weather provider. | `today.py:160-171`, `:29-30` |
| V-26 | Flutter profile reads local appearance values, not backend `styleProfile`. | `profile_screen.dart:358-374` |
| V-27 | Preferences expose only occasion focus. | `preferences_screen.dart:18`, `:50-56`, `:91-95` |
| V-28 | Style Score is base 60 + wardrobe points + saved-look points, not a usage/activity metric. | `learning.py:116-152` |
| V-29 | Account deletion exists at backend API level; no Flutter delete-account UI was found. | `users.py:130-151` |
| V-30 | Camera permission copy and face-scan consent are inconsistent about what is stored. | `camera_permission_screen.dart:154-169`; `face_scan_screen.dart:867-899` |
| V-31 | Feedback is available on saved looks, not on look details. | `saved_looks_screen.dart:332-333`; `look_details_screen.dart:17` |
| V-32 | Garment domain data includes confidence and needs_review. | `value_objects.py:102-117` |
| V-33 | The garment adapter is real and reports needs_review. | `vision_garment_adapter.py:75-94`, `:196-208` |
| V-34 | The try-on surface is explicitly mock/test data. | `try_on_screen.dart:18-29` |
| V-35 | Style-profile updates merge non-empty fields and do not erase prior values. | `repositories.py:265-306` |
| V-36 | Outfit Scan and the guest Initial Scan do not require a face shape; the scoring helper falls back to `oval` for an empty profile. | `analysis.py:229-332`, `:1048-1050`; `analysis_rules.py:168`, `:221-223`, `:299` |

### 13.2 Interpretations

These are audit judgments, not direct code facts.

| ID | Interpretation | Confidence | Basis |
|---|---|---|---|
| I-01 | Outfit Scan is a hairstyle feature wearing an outfit label. | High | No garment call; hairstyle snapshot; empty outfit UI |
| I-02 | Initial Scan was intended as a preview, but the save/discard copy implies persistence. | Medium-high | Ephemeral endpoints + pending intent + save language |
| I-03 | The shared person model is backend-first in intent, but Flutter-local in practice. | High | `/me` has styleProfile; profile reads local storage |
| I-04 | Face shape is the only production appearance attribute. | High | Adapter empties all others |
| I-05 | Hairstyle confidence is an evidence-completeness measure, not model certainty. | High | Formula uses completeness/decisiveness |
| I-06 | Outfit Builder’s “Style DNA” stage is marketing/progress copy, not a pipeline step. | High | Backend does not read style_profile |
| I-07 | The catalog’s skin-tone/Style-DNA claims are ungrounded personalization. | High | Text references values the adapter never measures |
| I-08 | Event support is real but unevenly connected to capabilities. | High | R36 + Today’s Look vs display-only Outfit Builder event identity |
| I-09 | The product has outgrown the single `style_profile` blob without defining capability boundaries. | Medium | Multiple writers, partial fields, no field-level provenance |
| I-10 | The quickest trust win is copy/contract repair, not a new person-model architecture. | Medium-high | Existing stores already cover most data; defects are mostly boundary/truth issues |
| I-11 | A no-face image can receive a hairstyle recommendation because the fallback face is scored as `oval`. | High | No face guard in outfit/ephemeral outfit; `_face_shape` default |

### 13.3 Proposals

These are **DESIGN PROPOSAL** items, not current behavior.

| ID | Proposal | Scope | Priority |
|---|---|---|---|
| P-01 | Add garment observation to Outfit Scan using the existing garment adapter. | Capability repair | P0 |
| P-02 | Rename Outfit Scan confidence or separate appearance and garment confidence. | Truth/UX | P0 |
| P-03 | Make Initial Scan either preview-only with truthful copy or durable with replay. | Onboarding contract | P0 |
| P-04 | Add a guest migration matrix and include face/appearance only with consent. | Person model | P0 |
| P-05 | Define backend `style_profile` as the shared appearance authority and hydrate Flutter from `/me`. | Person model | P1 |
| P-06 | Add a minimal goal/desired-change field if S2 is in Stage 1. | Subject model | P1 |
| P-07 | Pass event occasion/context to Outfit Builder or label it occasion-only. | Context | P1 |
| P-08 | Replace empty skin-tone/Style-DNA rows with “Not measured” or hide them. | Hairstyle truth | P0 |
| P-09 | Replace false progress stages with actual pipeline stages. | Truth/UX | P0 |
| P-10 | Ground or genericize catalog personalization copy. | Content truth | P0 |
| P-11 | Rename “Style Score Impact” to “Match” unless a real delta is implemented. | Metrics truth | P0 |
| P-12 | Surface `needs_more_data` with specific missing evidence. | Uncertainty | P1 |
| P-13 | Add feedback to look details or scope feedback to saved looks explicitly. | Learning loop | P2 |
| P-14 | Add account deletion UI if the product promises deletion. | Privacy | P1 |
| P-15 | Add truth regression tests for forbidden claims and snapshot contracts. | Verification | P3 |
| P-16 | Fail no-face scans honestly or return an explicit no-face state; never score a default shape. | Uncertainty | P0 |

### 13.4 Unresolved questions

| ID | Question | Why unresolved | Needed from |
|---|---|---|---|
| U-01 | Is Initial Scan meant to be a preview or a persistent onboarding step? | Code has preview mechanics plus save language | Founder/product |
| U-02 | Is Outfit Scan meant to analyze garments, or is it a style/face scan? | Name and UI say outfit; backend says hairstyle | Founder/product |
| U-03 | Are goals/desired change in Stage 1? | No model found | Founder/product |
| U-04 | Which appearance attributes are actually in scope? | Adapter only measures face shape | Founder/product + AI feasibility |
| U-05 | Is `style_profile` the single shared authority? | Flutter reads local; backend schema unused | Founder/architecture |
| U-06 | Should guest face data migrate? Under what consent? | Explicitly excluded today | Founder/privacy |
| U-07 | Should event identity/location/date affect recommendations? | Current path is display-only | Founder/product |
| U-08 | What should confidence mean to users? | Multiple incompatible meanings | Founder/product |
| U-09 | Should catalog copy be personalized at all? | Current copy is ungrounded | Founder/content |
| U-10 | Is “Style Score Impact” intended to be a delta? | Backend provides match percentage | Founder/product |
| U-11 | Is in-app account deletion required? | Backend supports it; UI absent | Founder/legal |
| U-12 | What is the image retention policy? | Copy is ambiguous | Founder/privacy |
| U-13 | Should feedback be captured on every recommendation? | Only saved looks have it | Founder/product |
| U-14 | Should style identity be explicit user input or model-inferred? | Both are absent/incomplete | Founder/product |
| U-15 | Is a schema change approved for goals/provenance/garment history? | Do not redesign by default | Founder/architecture |
| U-16 | Should a no-face scan fail, return an outfit-only result, or show a labeled fallback? | Current code silently scores `oval`; product intent is not documented | Founder/product |

### 13.5 Truth-ledger status

- Verified facts are static source facts; they are not runtime test results.
- Interpretations are explicitly labeled and may be revised if product intent differs.
- Proposals are not commitments and must not be represented as implemented.
- Unresolved questions must remain visible in planning until a founder decision is recorded.
- No claim in this report should be used to assert that Stage 1 is complete.

---

**End of report.**
