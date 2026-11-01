# FANSIVIBE — STAGE 1D: BATCH 4A
# AI Assistant Canonical Delegation — Pre-Implementation Audit

## 1. Executive Summary

This pre-implementation review provides an architectural audit of the Fansivibe conversational AI assistant. The audit investigates how the assistant currently handles hairstyle recommendations, outfit recommendations, grooming advice, wardrobe intelligence, and styling explanations across the backend FastAPI service, domain logic, and the Flutter client.

### Core Audit Findings

1. **Dual Recommendation Engines (Architectural Divergence)**:
   The Fansivibe platform currently maintains two separate, conflicting recommendation pathways:
   - **Canonical Domain Engine**: Located in `backend/app/domain/services/analysis_rules.py` (and `grooming_rules.py`, `application/outfits.py`), implementing deterministic candidate generation, multi-term scoring (face-shape boost, palette points, fit points, preference boost, feedback points, occasion points), ranking, grounded explanation synthesis, and calibrated confidence calculation.
   - **Assistant Tools Facade**: Located in `backend/app/ai/tools.py` (and parts of `backend/app/ai/engine.py`), implementing hardcoded catalog dictionary lookups (`catalog.OCCASION_TO_LOOK`, `catalog.REFINED_OFFICE`, `catalog.CASUAL_LOOK`, `catalog.TEXTURED_QUIFF`, `catalog.CLASSIC_POMPADOUR`, `catalog.STRUCTURED_GOATEE`, `catalog.CLASSIC_STUBBLE`), returning fixed scores (94%, 91%, 88%, 87%) and static strings.

2. **The "Split Brain" in Assistant Outfit Recommendations**:
   In `backend/app/ai/engine.py`, when a user requests an outfit (`INTENT_OUTFIT`):
   - The conversational card (`reply.cards[0]`) is populated by `tools.recommend_outfit(occasion, user)`, which returns a static catalog look (e.g. `Refined Office Ensemble` or `Effortless Casual`) consisting of hardcoded garments the user does not own.
   - Simultaneously, lines 463–510 execute a separate domain candidate pipeline (`generate_outfit_candidates → score_outfit_candidate → rank_outfit_candidates → select_best_outfit_candidate`) over the client's `user.wardrobe` snapshot to populate `reply.outfitIntelligence.selectedItemIds`.
   - Consequently, the Flutter assistant UI renders two conflicting elements: a `SuggestionCardView` showing static non-owned items, and an `OutfitRecommendationCard` showing owned wardrobe items.

3. **Residual Misleading Copy in Hairstyle Fallbacks**:
   While Batch 1A successfully eliminated the silent programmatic fallback to `"oval"` in `analysis_rules.py` and `tools.py`, the static suggestion card `catalog.TEXTURED_QUIFF` returned by `tools.recommend_hairstyle` hardcodes the subtitle:
   `"Modern volume on top that suits oval faces. Medium maintenance, trim every 4-5 weeks."`
   When an unmeasured user asks for a haircut, the assistant still presents an ungrounded claim that the hairstyle suits their oval face. In contrast, the canonical `analysis_rules.recommend_hairstyle` suppresses all face-match reasons when face shape is unmeasured.

4. **Authenticity & Data Authority Gaps**:
   - The assistant entrypoint (`POST /v1/assistant/chat` in `backend/app/main.py:291-324`) resolves server-authoritative occasions for authenticated users (STEP 11.10), but completely ignores the authenticated user's server-persisted wardrobe (`WardrobeItemRepositorySQL`) and appearance profile (`UserStateRepositorySQL.get_style_profile`).
   - The assistant relies solely on the volatile client snapshot (`request.user`), meaning authenticated users whose local storage is out-of-sync or empty receive degraded assistant results.

5. **GAP-P1-4 Status**:
   Reassessed as **PARTIALLY RESOLVED (Defect Fix in Batch 1A; Structural Delegation Pending)**. The programmatic `oval` fallback was eliminated, but the tools facade still bypasses the canonical decision engine.

---

## 2. Verified Assistant Architecture

### 2.1 Complete Execution Flow: User Message to Assistant Reply

```mermaid
sequenceDiagram
    autonumber
    actor User as User (Flutter Client)
    participant Screen as AssistantScreen
    participant Service as AssistantService
    participant Client as AssistantClient
    participant Router as main.py / assistant.py
    participant Engine as ai/engine.py
    participant Tools as ai/tools.py
    participant Domain as analysis_rules.py / outfits.py
    participant DB as PostgreSQL Repositories

    User->>Screen: Enters "What should I wear to a date?"
    Screen->>Service: send("What should I wear to a date?")
    Service->>Client: chat(history, userContext)
    Note over Service,Client: userContext = transient client snapshot<br/>(wardrobe, face, savedLooks, preferredOccasions)
    Client->>Router: POST /v1/assistant/chat (Bearer Token optional)
    
    opt Authenticated User
        Router->>DB: UserStateRepositorySQL.get_profile(user_id)
        DB-->>Router: profile.preferences["preferred_occasions"]
        Note over Router: STEP 11.10: Server occasions win if non-empty
    end

    Router->>Engine: engine.handle(request, preferred_occasions=occasions)
    Note over Engine: Intent Classification: intent.classify() -> "outfit"<br/>Occasion Detection: intent.detect_occasion() -> "date"
    
    alt Ambiguous Outfit (No Occasion)
        Engine-->>Router: AssistantReply(clarifications=[Casual, Office, Date...])
    else Occasion Specified ("date")
        Engine->>Tools: recommend_outfit("date", user)
        Tools-->>Engine: [catalog.OCCASION_TO_LOOK["date"]] (Static Card)
        
        opt Wardrobe Present in user.wardrobe
            Engine->>Domain: generate_outfit_candidates(user.wardrobe)
            Engine->>Domain: score_outfit_candidate(...)
            Engine->>Domain: rank_outfit_candidates(...)
            Engine->>Domain: select_best_outfit_candidate(...)
            Domain-->>Engine: outfit_winner
            Note over Engine: Populates reply.outfitIntelligence<br/>(selectedItemIds, composition)
        end
        
        opt LLM Available (Ollama)
            Engine->>Engine: llm_backend.enrich_reply(text)
        end
        
        Engine-->>Router: AssistantReply(cards=[StaticCard], outfitIntelligence=...)
    end
    
    Router-->>Client: 200 OK (AssistantReply JSON)
    Client-->>Service: AssistantReply
    Service-->>Screen: notifyListeners()
    Screen->>User: Displays text + SuggestionCardView + OutfitRecommendationCard
```

### 2.2 Endpoint Inventory

| Endpoint | Method | Location | Auth | Responsibilities |
|---|---|---|---|---|
| `/v1/assistant/chat` | POST | `backend/app/main.py:291-324` | Optional Bearer | Main text dialogue turn. Resolves server occasions (STEP 11.10). Dispatches to `engine.handle()`. |
| `/v1/assistant/chat-with-image` | POST | `backend/app/api/routers/assistant.py:117-144` | Unauthenticated (Rate-limited) | Multipart outfit photo question. Measures garments via `OllamaVisionGarmentAdapter`, matches against `user.wardrobe` snapshot. |
| `/v1/assistant/feedback` | POST | `backend/app/api/routers/assistant.py:35-56` | Required Bearer | Logs card interaction (`suggestion_opened`, `assistant_navigation`) as append-only `learning_signals` row. |
| `/v1/reasoning/query` | POST | `backend/app/api/routers/reasoning.py:92-140` | Optional Bearer | Dedicated Fashion Reasoning pipeline (FFO corpus, Ollama reasoning model). Routed from assistant via navigation actions. |

### 2.3 Assistant Tool Inventory (`backend/app/ai/tools.py`)

| Function | Lines | Responsibilities | Domain Delegation Status |
|---|---|---|---|
| `recommend_outfit` | 23–33 | Returns look card based on occasion or owned count against static `catalog.WARDROBE`. | **None**. Hardcoded lookup in `catalog.OCCASION_TO_LOOK`. |
| `recommend_hairstyle` | 35–48 | Returns Pompadour or Quiff based on face shape. | **None**. Bypasses `analysis_rules.recommend_hairstyle`. |
| `recommend_grooming` | 50–52 | Returns Goatee and Stubble. | **None**. Hardcoded static list; bypasses `grooming_rules.py`. |
| `wardrobe_summary` | 54–70 | Summarizes category count, favorites, and items. | **None**. Pure metric string formatting. |
| `daily_tip` | 73–75 | Returns static `catalog.STYLE_TIP`. | **None**. Static constant. |
| `greeting_reply` | 77–83 | Returns standard greeting string. | **N/A** (Conversational UX responsibility). |
| `thanks_reply` | 85–87 | Returns standard polite reply. | **N/A** (Conversational UX responsibility). |
| `clarify_outfit_text` | 89–91 | Prompt asking user for occasion. | **N/A** (Dialogue policy responsibility). |
| `unknown_reply` | 93–98 | Fallback prompt suggesting supported commands. | **N/A** (Dialogue policy responsibility). |

---

## 3. Hairstyle Recommendation Duplication Analysis

### 3.1 Comparison Matrix: Assistant Tool vs. Canonical Decision Engine

| Dimension | Assistant Tool (`ai/tools.py:35-48`) | Canonical Engine (`domain/services/analysis_rules.py:421-484`) |
|---|---|---|
| **Entry Point** | `tools.recommend_hairstyle(user)` | `analysis_rules.recommend_hairstyle(knowledge, appearance, preferences, personalization_context)` |
| **Catalog Scope** | Exactly 2 styles (`catalog.CLASSIC_POMPADOUR`, `catalog.TEXTURED_QUIFF`). | Full catalog (10+ styles: Quiff, Pompadour, Crew Cut, Side Part, Buzz Cut, Fade Crop, Undercut, etc.). |
| **Knowledge Port** | Direct reference to in-code `catalog` constants. | `KnowledgeSource` port abstraction (`CatalogKnowledgeSource.retrieve_hairstyle_looks()`). |
| **Scoring Model** | Binary switch: `face in ("round", "square", "rectangular")` swaps 1st and 2nd. Hardcoded scores (94%, 87%). | Multi-term continuous scoring: `min(1.0, seed + face_boost + preference_boost + saved_look_boost)`. |
| **Confidence Calculation** | None (0.0 or omitted; card has static `score=94`). | Calibrated run-level confidence: `round(0.5 * completeness + 0.5 * decisiveness, 2)`. |
| **Uncertainty & Missing Data** | Treats missing face shape identically to non-angular face shapes (returns Quiff). | Explicit `needs_more_data = completeness < 1.0`. Suppresses face-shape boost and match reasons. |
| **Reasoning & Explanations** | Static subtitle: *"Modern volume on top that suits oval faces."* | Grounded reasons: `_face_match_reason` (`Strongest match for your {face} face shape (+{boost})`) + catalog reasons. |
| **Exclusions & Preferences** | None. Ignores `excludedLookIds` and `preferredLookIds`. | Stage 3 binary filtering (`filter_candidates`) + Stage 4 preference bonus (+0.03). |
| **Saved Look Influence** | None. Ignores user's saved hairstyle history. | Stage 4 saved look boost (+0.03 for looks previously saved by owner). |

### 3.2 Evaluation of Specific Audit Questions

1. **What logic is duplicated?**
   The face shape mapping heuristic. `tools.py` checks `face in ("round", "square", "rectangular")` to prioritize Pompadour over Quiff. In `analysis_rules.py`, `_HAIRSTYLE_BOOSTS` was specifically tuned to yield Pompadour as the top pick for round (+0.06), square (+0.08), and rectangular (+0.07) faces.

2. **What logic is genuinely assistant-specific?**
   - Natural-language framing: `"Your top pick is the {title} ({score}% match). {subtitle}"`.
   - Card construction: Wrapping the domain result into a `SuggestionCard` with `kind="hairstyle"` and `action="open_hairstyle"`.
   - Navigation routing: Mapping `open_hairstyle` to `RouteNames.hairstyle` (`AssistantRoutes.dart`).

3. **Are different confidence and missing-data rules used?**
   Yes, completely. The assistant tool has no concept of confidence or missing data. It displays `94% match` even when the user has never scanned their face. The canonical engine derives confidence based on profile completeness and decisiveness, and sets `needs_more_data = True`.

4. **Are face-shape fallbacks consistent with Batch 1A?**
   In Batch 1A, the explicit fallback `else "oval"` was removed from line 36 of `tools.py`. However, the card returned (`catalog.TEXTURED_QUIFF`) contains hardcoded copy: `"Modern volume on top that suits oval faces."` This produces a subtle truth defect: the assistant claims oval suitability to users with unmeasured faces.

5. **Are explanations and recommendation reasons consistent?**
   No. The canonical engine emits truthful reasons explaining why a look was chosen (face fit, maintenance, styling difficulty). The assistant tool emits static steps ("Volumizing mousse...", "Blow-dry...").

6. **Does the assistant fabricate unsupported appearance attributes?**
   Yes, through the hardcoded subtitle of `catalog.TEXTURED_QUIFF`.

7. **What behavior would be lost if the duplicated implementation were removed?**
   None. Delegating to `analysis_rules.recommend_hairstyle` produces the exact same top pick (Pompadour for round/square/rectangular, Quiff for unmeasured/oval), while adding support for the remaining 8 catalog styles, dynamic scores, grounded reasons, and honest uncertainty advisories.

---

## 4. Outfit Recommendation Duplication Analysis

### 4.1 Comparison Matrix: Assistant Tool / Engine vs. Canonical `GenerateOutfit`

| Dimension | Assistant (`ai/tools.py` + `ai/engine.py`) | Canonical Engine (`application/outfits.py`) |
|---|---|---|
| **Entry Point** | `tools.recommend_outfit(occasion, user)` + inline logic in `engine.py:463-510` | `GenerateOutfit.__call__(user_id, occasion, mood, fit, color_palette, ...)` |
| **Garment Selection** | **Cards**: Static lookup in `catalog.OCCASION_TO_LOOK`.<br/>**Wire OI**: In-memory combinations from `user.wardrobe`. | Combinations generated strictly from owner's database wardrobe (`WardrobeItemRepositorySQL`). |
| **Data Authority** | Transient client JSON snapshot (`request.user.wardrobe`). Server DB ignored. | Authoritative PostgreSQL database. Owner-scoping strictly enforced (`OW-1`). |
| **Occasion Handling** | Exact string lookup in `catalog.OCCASION_TO_LOOK`. Falls back to `REFINED_OFFICE`. | `_occasion_points(members, [occasion] + preferred_occasions)` awards +5.0 points in candidate scoring. |
| **Mood Handling** | Ignored completely. | Validated, passed through, and echoed in recommendation contract (`C-02-M`). |
| **Fit & Palette Scoring** | Ignored completely in `engine.py` scoring call (`preferred_palette` & `preferred_fit` default to `""`). | `_palette_points` awards +5.0 pts; `_fit_points` awards +5.0 pts when `fit_confidence >= 0.6`. |
| **Feedback & Learning** | Ignored completely (`feedback_context` is `None` in `engine.py:475`). | `build_feedback_context` loads likes (+4/+2), dislikes (-4/-2), and wears (+2/+1). |
| **Empty/Sparse Handling** | Returns static catalog outfit card (`REFINED_OFFICE`, score 91) even if user wardrobe is empty. | Fails closed with typed empty reason (`empty_wardrobe`, `missing_required_category`) → 204. |
| **Output Representation** | `SuggestionCard(kind="outfit")` + `OutfitIntelligence` wire contract. | `OutfitRecommendation` domain value object with components, metrics, and grounded reasons. |

### 4.2 Evaluation of Specific Audit Questions

1. **How the assistant currently selects garments:**
   The assistant operates a disjoint split-brain:
   - For the visual card: It does not select garments at all; it returns static text strings from `catalog.py`.
   - For `outfitIntelligence`: It calls `generate_outfit_candidates` and `score_outfit_candidate` over `user.wardrobe`, but passes zero palette, zero fit, and zero feedback context.

2. **Whether it uses the canonical recommendation engine:**
   Partially. It reuses the candidate generation and scoring functions from `analysis_rules.py` for the background wire object, but completely bypasses `GenerateOutfit` and ignores domain scoring for the visual card.

3. **Whether it duplicates filtering or scoring:**
   Yes. It re-implements the candidate ranking and selection loop inside `engine.py:473-481` rather than calling `GenerateOutfit`.

4. **Whether it respects wardrobe ownership:**
   It respects client-side snapshot isolation, but does NOT respect database ownership. It never loads the authenticated user's actual database wardrobe items.

5. **Whether it uses the same occasion scoring:**
   In `engine.py`, it passes `request_occasions` to `score_outfit_candidate`, which correctly awards +5.0 points. But in `tools.recommend_outfit`, it uses a dictionary lookup that bypasses scoring entirely.

6. **Whether it handles missing profile information correctly:**
   - Missing occasion triggers dialogue clarification (`_OUTFIT_CLARIFICATION`).
   - Missing wardrobe produces an empty `outfitIntelligence.selectedItemIds`, but the visual card still falsely displays a full 5-piece outfit.

7. **Whether it produces different results from regular Outfit Builder:**
   Yes, completely. The Outfit Builder returns an ensemble composed of the user's real wardrobe items with ensemble match percentages and grounded reasons. The Assistant returns a static catalog look with hardcoded items like "Navy Textured Blazer" that the user may not own.

8. **What assistant-specific behavior must be preserved:**
   - Missing occasion clarification dialogue (`ClarificationOption` chips: Casual, Office, Date, Party, Travel).
   - Conversational reply text ("For {occasion}, I'd go with...").
   - Wire contracts: `AssistantReply`, `SuggestionCard`, `OutfitIntelligence`.
   - Support for guest users who have no database account.

---

## 5. Existing Canonical Use-Case Inventory

| Canonical Use Case / Domain Service | File Location | Inputs | Outputs | State Mutation | DB Dependency |
|---|---|---|---|---|---|
| `analysis_rules.recommend_hairstyle` | `backend/app/domain/services/analysis_rules.py:421` | `KnowledgeSource`, `AppearanceProfile`, `HairstylePreferences`, `PersonalizationContext` | `HairstyleResult` | Read-only (Pure) | None (`CatalogKnowledgeSource` is in-memory) |
| `grooming_rules.recommend_grooming` | `backend/app/domain/services/grooming_rules.py:317` | `KnowledgeSource`, `AppearanceProfile`, `HairstylePreferences`, `PersonalizationContext` | `GroomingResult` | Read-only (Pure) | None (`CatalogKnowledgeSource` is in-memory) |
| `CreateHairstyleRun` | `backend/app/application/analysis.py:52` | `user_id: UUID`, `idempotency_key` | `run_id: UUID` | Writes `analysis_runs` | Yes (`AnalysisRunRepository`, `UserStateRepository`, `SavedLookRepository`) |
| `GenerateOutfit` | `backend/app/application/outfits.py:362` | `user_id: UUID`, `occasion`, `mood`, `fit`, `color_palette`, `seed`, `preferred_item_ids` | `OutfitRecommendation` | Read-only (`TRX-4`) | Yes (`WardrobeItemRepository`, `UserStateRepository`, `FeedbackRepository`, `SavedLookRepository`, `WearEventRepository`) |
| `_derive_outfit` | `backend/app/application/outfits.py:453` | Repositories, `user_id`, preferences | `tuple[OutfitRecommendation?, reason?]` | Read-only | Yes |
| `score_outfit_candidate` | `backend/app/domain/services/analysis_rules.py:1145` | `candidate`, `items_by_id`, `preferred_item_ids`, `occasions`, `palette`, `fit`, `feedback` | `ScoredOutfitCandidate` | Read-only (Pure) | None |

### Key Architectural Discovery on `GenerateOutfit`

`GenerateOutfit` in `application/outfits.py` cannot be directly invoked by the assistant without adaptation:
1. `GenerateOutfit` strictly requires `user_id: UUID` and loads from `WardrobeItemRepositorySQL`. Guest assistant users do not have a `user_id` or database rows.
2. `GenerateOutfit` strictly validates that `occasion`, `mood`, `fit`, and `colorPalette` are non-empty strings (`_validate_preference` raises 422 if any are empty). The conversational assistant only extracts `occasion` from natural language; `mood`, `fit`, and `color_palette` are not specified during a chat turn.
3. Therefore, delegating outfit recommendations requires either:
   - Adapting the underlying domain functions (`analysis_rules.score_outfit_candidate`, etc.) with sensible conversational defaults (`fit="regular"`, `color_palette="neutral"`, `mood="confident"`).
   - Or creating a dedicated `DeriveAssistantOutfit` use case that accepts optional `user_id` (loading from DB when authenticated, or falling back to `UserContext.wardrobe` for guests).

---

## 6. Assistant-Specific Behavior That Must Be Preserved

1. **Dialogue Policy & Clarification**:
   - When an outfit question lacks an occasion, the assistant must return `intent="outfit"` with clarification options (`Casual`, `Office`, `Date`, `Party`, `Travel`) and no recommendation cards.
   - Bare occasion replies (e.g. user sends "date" after clarification) must be mapped to `INTENT_OUTFIT`.

2. **Wire Response Contracts**:
   - `AssistantReply`: `intent`, `text`, `cards: list[SuggestionCard]`, `clarifications: list[ClarificationOption]`, `navigation: Optional[NavigationRequest]`, `outfitIntelligence: Optional[OutfitIntelligence]`.
   - `SuggestionCard`: `kind`, `title`, `subtitle`, `score`, `items: list[str]`, `action: Optional[str]`.
   - `OutfitIntelligence`: `selectedItemIds`, `outfitComposition`, `occasion`, `stylingRationale`, `compatibilityRationale`, `confidence`, `explanation`, `dataAvailability`.

3. **Client Navigation Contracts**:
   - Card actions (`open_hairstyle`, `open_grooming`, `open_outfit`, `open_wardrobe`) must map to the corresponding app route in `AssistantRoutes.dart`.
   - Navigation intent (`open my wardrobe`, `take me to stylist`) must produce `NavigationRequest`.

4. **Guest & Offline Resiliency**:
   - Unauthenticated users must continue to receive valid recommendations based on their local snapshot.
   - When the backend is unreachable, Flutter's `OfflineAssistant` must provide fallback replies without crashing.

5. **Verified Batch 3B Context Boundaries**:
   - Recommendations are conditioned on occasion only.
   - Mood is transmitted but does not affect scoring.
   - Date, time, and location are not automatically considered.

---

## 7. Recommended Delegation Architecture

### 7.1 Architecture Diagram: Target State

```mermaid
graph TD
    subgraph Client["Flutter Client"]
        UI[AssistantScreen] --> Service[AssistantService]
        Service --> ClientAPI[AssistantClient]
    end

    subgraph API["FastAPI Layer"]
        ClientAPI --> Endpoint["POST /v1/assistant/chat"]
        Endpoint --> AuthCheck{Authenticated?}
        AuthCheck -->|Yes| ResolveOccasions[Resolve Server Occasions]
        AuthCheck -->|No| ClientOccasions[Use Client Occasions]
        ResolveOccasions --> Orchestrator[ai/engine.py: handle]
        ClientOccasions --> Orchestrator
    end

    subgraph AI_Adapter["Thin AI Tool Adapters (ai/tools.py)"]
        Orchestrator --> ToolH[tools.recommend_hairstyle]
        Orchestrator --> ToolG[tools.recommend_grooming]
        Orchestrator --> ToolO[tools.recommend_outfit]
    end

    subgraph Domain["Canonical Domain Services & Knowledge"]
        ToolH -->|Pure Call| HairEngine["analysis_rules.recommend_hairstyle()"]
        ToolG -->|Pure Call| GroomEngine["grooming_rules.recommend_grooming()"]
        ToolO -->|Pure / Use Case| OutfitEngine["DeriveAssistantOutfit / analysis_rules"]
        
        HairEngine --> KnowledgePort[CatalogKnowledgeSource]
        GroomEngine --> KnowledgePort
        OutfitEngine --> WardrobeRules["analysis_rules: score_outfit_candidate"]
    end

    subgraph Formatting["Conversational Formatting"]
        HairEngine --> FormatH[Format SuggestionCard: real score, grounded reasons]
        GroomEngine --> FormatG[Format SuggestionCard: real score, grounded reasons]
        OutfitEngine --> FormatO[Format SuggestionCard & OutfitIntelligence: owned items]
        
        FormatH --> Orchestrator
        FormatG --> Orchestrator
        FormatO --> Orchestrator
    end
```

### 7.2 Hairstyle Delegation Specification

- **Module**: `backend/app/ai/tools.py`
- **Function**: `recommend_hairstyle(user: Optional[UserContext], *, knowledge: Optional[KnowledgeSource] = None) -> List[SuggestionCard]`
- **Implementation Logic**:
  1. Construct `AppearanceProfile`:
     ```python
     appearance = AppearanceProfile(
         faceShape=(user.face.faceShape if user and user.face else "") or "",
         skinTone=(user.face.skinTone if user and user.face else "") or "",
         bodyType=(user.face.bodyType if user and user.face else "") or "",
         styleType=(user.face.styleType if user and user.face else "") or "",
     )
     ```
  2. Construct `HairstylePreferences`:
     Map `user.savedLooks` into `preferredLookIds` if available.
  3. Invoke canonical engine:
     ```python
     ks = knowledge or CatalogKnowledgeSource()
     result = analysis_rules.recommend_hairstyle(ks, appearance, preferences)
     ```
  4. Transform `HairstyleResult` into `SuggestionCard`s:
     - Top pick:
       - `kind = "hairstyle"`
       - `title = result.top.name`
       - `score = int(round(result.top.matchScore * 100))`
       - `subtitle = result.top.reasons[0] if result.top.reasons else result.top.description`
       - `items = list(result.top.stylingTips)`
       - `action = "open_hairstyle"`
     - If `result.needs_more_data` is True (unmeasured face shape):
       Subtitle truthfully states: `"Versatile style that works across various face proportions. Add a face scan to personalize."` (zero oval fabrication!).
     - Runner-up alternatives (optional second card):
       Mapped from `result.alternatives[0]`.

### 7.3 Outfit Delegation Specification

- **Module**: `backend/app/ai/tools.py` & `backend/app/application/assistant.py`
- **Function**: `recommend_outfit(occasion: Optional[str], user: Optional[UserContext], ...) -> tuple[List[SuggestionCard], Optional[OutfitIntelligence]]`
- **Implementation Logic**:
  1. If `occasion` is None: return clarification text (handled by dialogue policy).
  2. Extract wardrobe items from `user.wardrobe`.
  3. If wardrobe is empty:
     - Return honest empty-state card:
       `title = "Wardrobe Empty"`, `subtitle = "Add items to your wardrobe so I can create personalized outfits for you."`, `action = "open_wardrobe"`.
       `outfitIntelligence = None`.
  4. If wardrobe has items:
     - Execute canonical candidate generation and ranking:
       `candidates = generate_outfit_candidates(wardrobe)`
       `scored = [score_outfit_candidate(c, items_by_id, frozenset(), occasions, preferred_fit="regular", preferred_palette="neutral") for c in candidates]`
       `ranked = rank_outfit_candidates(scored)`
       `winner = select_best_outfit_candidate(ranked)`
     - If `winner` is None (missing tops or bottoms):
       - Return honest incomplete category card:
         `title = "Need Tops & Bottoms"`, `subtitle = "Your wardrobe needs at least one top and one bottom to build an outfit."`, `action = "open_wardrobe"`.
     - If `winner` is found:
       - Map winner items to `SuggestionCard`:
         `title = f"{occasion.title()} Ensemble"`
         `subtitle = f"{int(round(winner.score))}% match from your owned wardrobe pieces."`
         `score = int(round(winner.score))`
         `items = [f"{record.name} - {record.category.title()}" for record in winner_components]`
         `action = "open_outfit"`
       - Map winner to `OutfitIntelligence`:
         `selectedItemIds = list(winner_ids)`
         `outfitComposition = OutfitComposition(...)`
         `occasion = occasion`
         `stylingRationale = ...`

---

## 8. Dependency and Integration Risks

| Risk Area | Description | Severity | Mitigation Strategy |
|---|---|---|---|
| **Guest Context Crash** | `GenerateOutfit` requires `user_id: UUID` and queries the database. Calling it for guest users raises validation errors. | **HIGH** | Do not call `GenerateOutfit` directly from `tools.py`. Call pure domain functions (`analysis_rules.py`) using in-memory `user.wardrobe` for guests, or create an adapter use case supporting both. |
| **Strict Preference Validation** | `GenerateOutfit` requires non-empty `mood`, `fit`, and `color_palette`. Chat turns only provide `occasion`. | **HIGH** | Provide domain-safe conversational defaults (`fit="regular"`, `color_palette="neutral"`, `mood="confident"`) when delegating from chat. |
| **Split-Brain Card Mismatch** | `reply.cards[0]` currently displays static catalog clothes while `reply.outfitIntelligence` has owned items. | **HIGH** | Build `reply.cards[0]` directly from the winning ensemble's owned items, eliminating static catalog lookups. |
| **Database Transaction Latency** | Chat requests are synchronous and expected to return within 500ms. Running heavy DB joins on chat turns could spike latency. | **MEDIUM** | `analysis_rules.recommend_hairstyle` and `grooming_rules.recommend_grooming` are pure in-memory functions (< 1ms). Wardrobe combinatorial search over < 50 items takes < 5ms. |
| **Legacy Test Breakage** | Existing tests assert static card titles (e.g. `Classic Pompadour`, `Refined Office Ensemble`, `test_11_4_1_*`). | **MEDIUM** | Ensure canonical scoring yields identical top picks for standard test inputs (`test_assistant_face_shape_switch_uses_canonical_rectangular` already expects Quiff/Pompadour). |
| **LLM Enrichment Hallucination** | When Ollama is running, `llm_backend.enrich_reply` rewrites text. It could contradict the structured card. | **LOW** | System prompt in `llm_backend.py` strictly constrains the model to 2-3 sentences based on provided context without modifying structured data. |

---

## 9. Stage 1 Requirement Traceability

### 9.1 Requirements Register (R-*) Mapping

| Req ID | Requirement Title | Category | Current Status | Finding Classification | Traceability / Evidence |
|---|---|---|---|---|---|
| **R-S1-1** | Real Appearance Observation | Appearance | Partially Implemented | **B** | Vision adapter extracts attributes; assistant tools previously fabricated `oval`; Batch 1A removed programmatic fallback, but static card copy still claims oval fit. |
| **R-S1-2** | Outfit Scan Garment Observation | Garments | Fully Implemented | **A** | Dual branches run in `CreateOutfitRun`; verified in Batch 3A (`outfit_scan_wardrobe_grounding_test.dart`). |
| **R-S1-3** | Honest Unmeasured Handling | Appearance | Partially Implemented | **B** | Canonical engine suppresses unmeasured boosts; assistant hairstyle card subtitle still contains static oval text. |
| **R-S2-1** | Goal / Desired Change Model | Goals | Missing | **C** | Assistant has no representation of style goals or desired change. |
| **R-S2-2** | Mood / Occasion Request Scoping | Context | Partially Implemented | **B** | Occasion is detected and scored; mood is unconsumed by scoring per Batch 3B; assistant outfit tool uses hardcoded occasion map. |
| **R-S3-1** | Preference / Style Identity Grounding | Preferences | Partially Implemented | **B** | Outfit Builder consumes preferences; assistant tools bypass user preferences and use static catalog constants. |
| **R-S3-2** | Style Identity vs Fallbacks | Preferences | Partially Implemented | **B** | Assistant tool falls back to static catalog look rather than grounded style identity. |
| **R-S3-3** | Feedback & Saved Look Learning Loop | Feedback | Partially Implemented | **B** | `saved_looks` boost in `analysis_rules.py`, but assistant tools ignore saved looks. |
| **R-S4-1** | Event Context Pass-Through | Context | Partially Implemented | **B** | Batch 3B added transparency copy to Outfit Builder; assistant detects occasion but does not consume date/location. |
| **R-S4-2** | Weather / Constraint Honesty | Constraints | Fully Implemented | **A** | `DEC-017` frozen as derived-only without fake weather. |
| **R-S4-3** | Event Preference Consistency | Preferences | Partially Implemented | **B** | STEP 11.10 server-authoritative occasions wired in assistant endpoint, but assistant outfit card ignores them. |
| **R-S5-1** | Provenance Preservation | Provenance | Partially Implemented | **B** | Batch 1A added provenance metadata to `style_profile`; assistant tools do not record or track provenance. |
| **R-S5-2** | Confidence Definition & Calibration | Confidence | Partially Implemented | **B** | `derive_confidence` in `analysis_rules.py`; assistant tools return hardcoded scores 94%/87% with zero confidence derivation. |
| **R-S5-3** | Uncertainty Primitives Surfacing | Uncertainty | Partially Implemented | **B** | Batch 2 surfaced uncertainty in Hairstyle result screen, Batch 3A surfaced garment uncertainty; assistant tools completely omit uncertainty primitives. |
| **R-S6-1** | Shared Person Model Authority | Architecture | Partially Implemented | **B** | Batch 2 established backend profile hydration; assistant endpoint reads server `preferred_occasions` via STEP 11.10, but reads wardrobe/face only from client snapshot. |
| **R-S6-2** | Non-Erasure in Partial Updates | Persistence | Fully Implemented | **A** | Batch 1A CAS atomic update in `repositories.py`. |
| **R-S6-3** | Guest-to-Auth Migration Scope | Auth | Fully Implemented | **A** | Batch 1B explicit guest migration without biometric replay. |
| **R-S6-4** | Provenance & Versioning Shifts | Model | Partially Implemented | **B** | CAS versioning in Batch 1A; assistant responses carry no versioning. |
| **R-S6-5** | Account Deletion & Privacy | Privacy | Partially Implemented | **B** | Backend `DELETE /v1/users/me` exists; UI settings button pending GAP-P1-7. |

*Finding Classifications: A — Fully implemented; B — Partially implemented; C — Missing; D — Contradictory or incorrect; E — Requires verification.*

### 9.2 Stylist Contracts (C-*) Mapping

| Contract ID | Contract Title | Status | Classification | Impact on Assistant Delegation |
|---|---|---|---|---|
| **C-01** | Guest / Authenticated Identity Architecture | Implemented | **A** | Assistant must continue to function for both unauthenticated guests and authenticated users. |
| **C-02** | Mood / Fit / Color Palette | Implemented | **B** | Outfit Builder consumes all three; assistant outfit delegation must provide safe conversational defaults. |
| **C-03** | Preferred Item IDs Recommendation Influence | Implemented | **B** | Supported in `GenerateOutfitRequest`; assistant endpoint currently omits `preferred_item_ids`. |
| **C-04** | Scan → Generate ("Build with this item") | Implemented | **A** | Preselected item ID passed via `preferredItemIds`. |
| **C-05** | Feedback Semantics (Save, Like, Dislike, Wear) | Implemented | **B** | Active in `analysis_rules.py`; assistant outfit tool currently ignores feedback. |
| **C-06** | Garment AI Attributes Persistence and Scoring | Partially Implemented | **B** | Pattern/style scoring pending D-06; core 4 attributes scored. |
| **C-07** | `item_added` Learning Signal Emission | Implemented | **A** | Emitted on wardrobe addition. |
| **C-08** | `analysisCached` / `analysisResult` Storage Integrity | Implemented | **A** | LocalStorage integrity verified. |
| **C-09** | Style Profile Merging Semantics | Implemented (CAS) | **A** | Resolved in Batch 1A with optimistic concurrency control. |
| **C-10** | Analysis Idempotency | Implemented | **A** | Verified in `test_c10_analysis_idempotency.py`. |

### 9.3 GAP-P1-4 Reassessment

- **Previous Status**: Documented as P1 in `STAGE1_GAP_ANALYSIS_FINAL.md:747`.
- **Current Audit Finding**:
  - The programmatic fallback `else "oval"` was resolved in Batch 1A.
  - However, `backend/app/ai/tools.py` remains an unrouted, hardcoded facade that bypasses the decision engine.
  - The split-brain defect between `reply.cards` and `reply.outfitIntelligence` remains active.
  - Static subtitle text in `catalog.py` still fabricates oval face suitability.
- **Exact Current Status**: **PARTIALLY RESOLVED (Honesty Defect Mitigated; Canonical Delegation Pending)**.

---

## 10. Proposed Implementation Batches

To guarantee zero regression, preserve client contracts, and isolate integration risks, assistant canonical delegation must be split into two sequential batches:

```mermaid
graph LR
    Batch4A["Batch 4A:<br/>Hairstyle & Grooming Delegation<br/>(Pure Domain / DB-Free)"] --> Batch4B["Batch 4B:<br/>Outfit Delegation & Wardrobe Unification<br/>(Guest/Auth Contexts)"]
```

### Batch 4A: Hairstyle & Grooming Delegation (Target Scope for Next Batch)
- **Scope**:
  - Refactor `recommend_hairstyle` in `backend/app/ai/tools.py` to delegate directly to `analysis_rules.recommend_hairstyle`.
  - Refactor `recommend_grooming` in `backend/app/ai/tools.py` to delegate directly to `grooming_rules.recommend_grooming`.
  - Remove misleading static subtitles from `catalog.py` (`catalog.TEXTURED_QUIFF`).
  - Wire grounded explanation reasons into `SuggestionCard.subtitle` and conversational text.
  - Surface honest unconditioned advisories when face shape is missing (`needs_more_data == True`).
- **Dependencies**: Completely self-contained. Pure domain calls using `CatalogKnowledgeSource`. Zero database migrations, zero schema changes, zero Flutter changes.
- **Risk Level**: **LOW**.

### Batch 4B: Outfit Delegation & Wardrobe Unification (Subsequent Batch)
- **Scope**:
  - Unify `reply.cards` and `reply.outfitIntelligence` in `engine.py` so the visual card presents the winning ensemble of owned pieces rather than static catalog looks.
  - Create a unified derivation seam in `application/assistant.py` that handles both authenticated database wardrobes and guest snapshot wardrobes.
  - Supply conversational defaults for unspecified preferences (`fit="regular"`, `color_palette="neutral"`, `mood="confident"`).
  - Handle empty and sparse wardrobes honestly with guidance cards (`action="open_wardrobe"`) instead of fake catalog outfits.
- **Dependencies**: Depends on database repository injection in `main.py:assistant_chat` or `application/assistant.py`.
- **Risk Level**: **MEDIUM-HIGH** (requires careful auth/guest regression testing).

---

## 11. Required Regression Tests

When implementing Batch 4A (Hairstyle Delegation), the following test suites must be executed and pass cleanly:

### Backend Test Coverage
1. `backend/tests/test_analysis_rules.py`:
   - `test_ai_tools_recommend_hairstyle_zero_fabrication`: Verifies Quiff is top for unmeasured/None, Pompadour is top for round.
   - `test_zero_fabrication_when_shape_missing`: Verifies 0.0 face boost and no oval claim.
2. `backend/tests/test_decision_engine.py`:
   - `test_assistant_face_shape_switch_uses_canonical_rectangular`: Verifies rectangular face normalization.
   - `test_11_10_hairstyle_and_grooming_unaffected`: Verifies occasions do not perturb hairstyle results.
3. `backend/tests/test_engine.py`:
   - `test_hairstyle_returns_cards`: Verifies `reply.intent == "hairstyle"` and card properties.
   - `test_grooming_returns_cards`: Verifies `reply.intent == "grooming"`.
   - `test_non_wardrobe_intents_unchanged`: Verifies dialogue policy preservation.
4. New Targeted Tests (`test_assistant_canonical_delegation.py`):
   - Proves `recommend_hairstyle` returns dynamic scores rather than static 94%/87%.
   - Proves `recommend_hairstyle` returns grounded reasons from `analysis_rules.py`.
   - Proves `recommend_hairstyle` handles user excluded looks and saved look boosts.
   - Proves unmeasured face shape emits honest advisory without "oval" claims.

### Flutter Test Coverage
1. `test/assistant_offline_labeling_test.dart`: Verifies assistant reply parsing and badge rendering.
2. `test/assistant_card_feedback_test.dart`: Verifies card tap telemetry (`POST /v1/assistant/feedback`).
3. `test/assistant_outfit_wardrobe_wiring_test.dart`: Verifies message bubble rendering and action dispatch.
4. `flutter analyze`: Must remain 100% clean (0 issues).

---

## 12. Known Limitations and Unresolved Decisions

1. **Guest Wardrobe Boundary (D10 Alignment)**:
   Guest appearance scans are ephemeral and strictly unpersisted (Batch 1B). Guest wardrobe items, however, reside in Flutter local storage (`guest_mode.dart`). The assistant must continue to operate over the client snapshot for guests, while authenticated users should ideally hydrate from the database.

2. **Fashion Reasoning Separation**:
   Fashion knowledge queries (e.g. "Can I wear navy and black together?") are handled by the separate `POST /v1/reasoning/query` service (FFO corpus). The assistant currently maps reasoning queries to navigation (`AssistantRoutes.routeFor` -> `RouteNames.fashionReasoning`). Full inline conversational synthesis of FFO reasoning remains a future enhancement.

3. **Founder Decisions Pending**:
   - `D7`: Hairstyle/grooming uncertainty semantic labels (Batch 2 documented as pending approval).
   - `D-06`: Garment pattern and style formal scoring weights (Batch 3A preserved without modification).

---

## 13. Exact Source File References

### Backend Core & Application
- `backend/app/ai/tools.py`: Lines 23–98 (Hardcoded tool functions, occasion lookups, face switches).
- `backend/app/ai/engine.py`: Lines 66–79 (`_cards_from`), lines 103–517 (`handle`, split-brain outfit logic in 463–510).
- `backend/app/ai/intent.py`: Lines 15–26 (Intent constants), lines 66–100 (`classify`), lines 103–113 (`detect_occasion`).
- `backend/app/ai/llm_backend.py`: Lines 32–63 (Ollama reachability and reply enrichment).
- `backend/app/main.py`: Lines 291–324 (`assistant_chat` endpoint, STEP 11.10 occasion resolution).
- `backend/app/api/routers/assistant.py`: Lines 35–56 (`/feedback`), lines 117–144 (`/chat-with-image`).
- `backend/app/application/assistant.py`: Lines 38–99 (`SubmitAssistantCardFeedback`), lines 188–301 (`ChatWithImage`).
- `backend/app/application/outfits.py`: Lines 362–450 (`GenerateOutfit`), lines 453–546 (`_derive_outfit`).
- `backend/app/domain/services/analysis_rules.py`: Lines 421–484 (`recommend_hairstyle`), lines 653–680 (`recommend_grooming`), lines 1145–1480 (`score_outfit_candidate`).
- `backend/app/domain/services/grooming_rules.py`: Lines 317–380 (`recommend_grooming`).
- `backend/app/infrastructure/external/knowledge.py`: Lines 167–230 (`CatalogKnowledgeSource`).
- `backend/app/data/catalog.py`: Lines 18–43 (`WARDROBE`), lines 49–76 (`REFINED_OFFICE`, `CASUAL_LOOK`), lines 82–100 (`TEXTURED_QUIFF`, `CLASSIC_POMPADOUR`).

### Flutter Client
- `newproject/flutter_application_1/lib/features/assistant/presentation/assistant_screen.dart`: Lines 50–140 (Service wiring), lines 250–320 (Card action and save handling).
- `newproject/flutter_application_1/lib/features/assistant/presentation/widgets/assistant_widgets.dart`: Lines 183–263 (Message bubble card & outfit intelligence rendering), lines 271–380 (`SuggestionCardView`).
- `newproject/flutter_application_1/lib/features/assistant/presentation/widgets/outfit_recommendation_card.dart`: Lines 50–100 (`OutfitRecommendationCard`).
- `newproject/flutter_application_1/lib/features/assistant/presentation/assistant_routes.dart`: Lines 13–42 (Route mapping).
- `newproject/flutter_application_1/lib/features/assistant/domain/assistant_service.dart`: Lines 63–108 (Context building and chat turn orchestration).
- `newproject/flutter_application_1/lib/features/assistant/data/assistant_client.dart`: Lines 47–78 (`chat`), lines 89–132 (`chatWithImage`).

---

## 14. Git Preservation Verification

- **Repository**: `/home/tony/projects/fansivibe_v1_backup`
- **Branch**: `main`
- **Current HEAD**: `97f6ded99d3f3e67b477616380320058cd396f48`
- **Status Before Audit**:
  - Modified tracked files: `CURRENT_STATE.md`, `backend/app/ai/tools.py`, `backend/app/application/analysis.py`, `backend/app/domain/ports/repositories.py`, `backend/app/domain/services/analysis_rules.py`, `backend/app/domain/services/grooming_rules.py`, `backend/app/infrastructure/db/repositories.py`, Flutter UI files, and test files from Batches 1A, 1B, 2, 3A, 3A.1, and 3B.
  - Untracked audit and implementation reports: Preserved intact.
- **Modifications during Audit**:
  - Strictly read-only audit. Zero backend code modified. Zero Flutter code modified. Zero tests modified. Zero database schemas touched. Zero git resets, stashes, commits, or branch switches performed.
  - Exactly one new deliverable created: `STAGE1_BATCH4A_PREIMPLEMENTATION_REVIEW.md`.

---

## 15. Final Recommendation

### Recommendation: Implement Hairstyle Delegation First (Batch 4A)

Based on actual repository evidence, **Hairstyle (and Grooming) Delegation should be implemented first as Batch 4A**, followed by **Outfit Delegation in a subsequent batch (Batch 4B)**.

### Concrete Justification:
1. **Zero Database Blockers**: `analysis_rules.recommend_hairstyle` and `grooming_rules.recommend_grooming` are pure domain functions requiring only `CatalogKnowledgeSource`. They have no database session requirements, require no transactions, and operate synchronously (< 1ms).
2. **Immediate Honesty & Trust Win**: Batch 4A eliminates the residual defect where `catalog.TEXTURED_QUIFF` claims to suit oval faces for users with unmeasured face geometry. It immediately brings the assistant into 100% compliance with Batch 1A zero-fabrication rules.
3. **Full Catalog Activation**: Replaces the 2 hardcoded styles with the full 10-style catalog, providing immediate user value without touching client code.
4. **Decoupled Risk**: Outfit delegation involves reconciling guest vs. authenticated database wardrobes, providing preference fallbacks, and fixing the split-brain rendering between `reply.cards` and `reply.outfitIntelligence`. Coupling outfit delegation into the same batch would unnecessarily bloat scope and increase regression risk.
5. **Clear Seam**: Batch 4A can be implemented, fully verified with focused unit and widget tests, and documented cleanly before tackling the multi-layered outfit pipeline in Batch 4B.
