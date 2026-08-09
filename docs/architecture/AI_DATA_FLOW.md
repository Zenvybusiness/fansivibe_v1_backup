# Fansivibe — AI Data Flow

> Companion to `FEATURE_INVENTORY.md`, `SCREEN_DATA_INVENTORY.md`,
> `DATA_MODEL_INVENTORY.md`, `FEATURE_DATA_MATRIX.md`, and
> `DATA_OWNERSHIP.md`.
>
> Maps the AI data flow for every AI-related feature in the REAL Fansivibe
> product:
>
> **INPUT → PROCESSING → KNOWLEDGE → DECISION → OUTPUT → EXPLANATION →
> USER ACTION → FEEDBACK**
>
> and distinguishes, **strictly from the repository**, between:
>
> - **IMPLEMENTED** — behavior that actually runs today (code verified)
> - **BACKEND PROTOTYPE** — behavior running in the FastAPI backend
> - **MOCKED** — static `*mock*` data stands in for an AI result that does not
>   actually compute anything
> - **PLANNED** — the UI/UX implies an AI capability that has no implementation
>   (no computation exists)
>
> Each AI feature is documented with: required user data, required profile data,
> required media, required knowledge, AI output, confidence, explanation/reason,
> model/version requirement, feedback requirement, and historical data
> requirement.
>
> **Scope:** app = `newproject/flutter_application_1`, backend =
> `backend/` (FastAPI, no DB). This is documentation only — no AI implemented,
> no UI changed, no database tables created.

---

## Status legend

| Status | Meaning | Verified evidence |
| --- | --- | --- |
| **IMPLEMENTED** | Code runs today and produces the result | traced in this doc with file:line |
| **BACKEND PROTOTYPE** | Runs in the FastAPI backend (prototype quality) | `backend/app/ai/*` |
| **MOCKED** | A `static const … mock` is displayed; no computation | model flagged `Historical` in the inventory |
| **PLANNED** | Referenced by UI/UX; no computation or mock output exists | missing model / dead code / stub |

> **Verified headline:** the ONLY AI-like behavior that runs today is the
> **Assistant pipeline** (a deterministic rules engine in the backend + an
> on-device mirror, with *optional* local-LLM text enrichment). Every other
> "AI" result in the app — outfit scan, outfit builder, hairstyle, grooming,
> discover matching, today's look, wardrobe insight, style DNA, style score —
> is **MOCKED** (static data). No model, no confidence, no computation exists
> for them.

---

## Part A — Assistant (the only implemented AI pipeline)

Status: **IMPLEMENTED** (rules) + **BACKEND PROTOTYPE** (Ollama enrichment).

### Data flow

```
INPUT
  user message (text)
  + message history (role/content pairs)
  + AssistantUserContext snapshot:
      wardrobe (List<WardrobeEntry>), face (FaceProfile?),
      savedLooks (List<String>), preferredOccasions (List<String>)
        ─ built in AssistantService._buildContext (assistant_service.dart:41)
        ─ serialized to JSON in AssistantClient.chat (assistant_client.dart:34)
  + device signals recorded as the conversation progresses
  → POST {base}/v1/assistant/chat   (assistant_client.dart:38, 12s timeout)

       │
       ▼  (backend/app/ai/engine.py)
PROCESSING
  1. intent.classify(text)            → 10 intents (intent.py:65, rules-based)
  2. intent.detect_occasion(text)     → occasion token, mapped to canonical
                                         (intent.py:102)
  3. bare occasion reply → outfit intent   (engine.py:106)
  4. dialogue policy: greeting/thanks/navigate/clarify vs tool call
                                         (engine.py:110-164)
  5. tools.recommend_outfit / recommend_hairstyle / recommend_grooming /
     wardrobe_summary / daily_tip        (tools.py:23-66)

KNOWLEDGE
  backend/app/data/catalog.py:
    WARDROBE (24 items) · REFINED_OFFICE · CASUAL_LOOK · TEXTURED_QUIFF ·
    CLASSIC_POMPADOUR · STRUCTURED_GOATEE · CLASSIC_STUBBLE · STYLE_TIP ·
    WARDROBE_INSIGHT · OCCASIONS · OCCASION_TO_LOOK · NAVIGATION_MAP
  (tools.py recommends catalog cards; wardrobe_summary counts items/favorites)

DECISION
  intent + occasion (+ user context) determine which card(s) are returned;
  the LLM is NEVER allowed to route — structure is ours (engine.py:166-168)

OUTPUT  → AssistantReply (structured): intent, text, cards[], clarifications[],
          navigation?  (schemas.py:70 / models.dart:75)
          optional text enrichment: Ollama rewrites ONLY reply.text
          (llm_backend.py:42, model llama3.1:8b, 8s timeout, falls back to
          base text on any failure)

EXPLANATION
  Inline in reply text: "For {occasion}, I'd go with the {title} — {subtitle}."
  (engine.py:144-149); hairstyle/grooming state "{name} ({score}% match)"
  (engine.py:150-159); wardrobe cards explain counts. No separate
  explanation/reason field in the DTO. Static scores (91/89/…) come from
  catalog constants, not from computation.

USER ACTION
  reply rendered in assistant_screen; user may tap a card (opens a feature),
  tap a clarification chip, or navigate via navigation request.

FEEDBACK  → LearningService.recordSignal (persisted in UserModel.signals):
  'assistant_message'      on send        (assistant_service.dart:55)
  'suggestion_opened'      on card open   (assistant_service.dart:91)
  'assistant_navigation'   on navigate    (assistant_service.dart:95)
  There is NO thumbs-up/down rating UI — verified.
```

**Offline mirror** (same flow, on-device): when the client returns null
(timeout/unreachable), `AssistantService.send` falls back to
`OfflineAssistant.replyFor` (`assistant_service.dart:71`) — a deterministic
rules engine mirroring `engine.py` (`offline_assistant.dart:35`), reading the
same context plus `WardrobeMockData.items` and the hairstyle/grooming mocks.
The reply shape (`AssistantReply`) is identical; the LLM enrichment is skipped.

### Requirements table

| Requirement | Assistant (verified) |
| --- | --- |
| Required user data | message text; (optional) savedLooks + preferredOccasions feed `wardrobe_summary`/context |
| Required profile data | `wardrobe` (used by `wardrobe_summary`, outfit owned-count), `face` (used only by `recommend_hairstyle` faceShape), `savedLooks` (context summary). `face` is never populated by the app today |
| Required media | none |
| Required knowledge | backend catalog constants (looks, hairstyles, grooming, tips, navigation) + 24-item `WARDROBE` for the owned-count fallback |
| AI output | `AssistantReply`: intent, text, cards, clarifications, navigation |
| Confidence | **none computed.** Card scores are static catalog constants; no model probability is exposed |
| Explanation / reason | reply text only; no structured reason field in the DTO |
| Model / version | none required (rules engine). Optional Ollama `llama3.1:8b` for text enrichment only (`FANSIVIBE_OLLAMA_MODEL`, `FANSIVIBE_OLLAMA_HOST`); disabled via `FANSIVIBE_DISABLE_LLM=1` |
| Feedback requirement | signals only (`assistant_message`, `suggestion_opened`, `assistant_navigation`); no explicit ratings |
| Historical data requirement | conversation is ephemeral (widget state). Only signals persist in `UserModel.signals`; no conversation history, no card-history rows |

---

## Part B — Mocked / planned AI features

Each is `*mock*` today (static data; verified — no computation behind the
fields). Status: **MOCKED**, with the "planned" behavior it will eventually
need.

### B1. Outfit Scan (image → outfit analysis)

```
INPUT      captured outfit image path (device camera; no bytes persisted)
PROCESSING timer-driven *ProcessingScreen* (fixed stage list + durations)
KNOWLEDGE  none (no model, no catalog used)
DECISION   none — result is pre-baked `OutfitAnalysisData.mock`
OUTPUT     OutfitAnalysisData: title, AnalysisSection[] (score double?),
           DetectedClothingItem[]
EXPLANATION AnalysisSection.id/label/description ("Fit", "Color Harmony", …)
USER ACTION "Generate Look" → LearningService.addSavedLook (outfit_analysis_screen.dart:260)
FEEDBACK   'look_saved' signal only
```
- Required user data: none. Required profile data: none. Required media:
  **captured outfit image** (the intended AI input — bytes never stored).
  Required knowledge: none today. AI output: analysis sections + detected
  items. Confidence: **none computed** (mock scores are doubles embedded in
  `AnalysisSection`). Explanation: section descriptions (static). Model:
  **none today; PLANNED** image-analysis model. Feedback: `look_saved`.
  Historical: result is ephemeral (widget state); only the signal persists.

### B2. Outfit Builder (preferences → outfit)

```
INPUT      occasion/mood/fit/colorPalette chips (route extra, ephemeral)
PROCESSING timer-driven generation stages (GenerationStage[], no logic)
KNOWLEDGE  none (BuilderOption lists are local vocabulary)
DECISION   none — result is `OutfitRecommendation.mock`
OUTPUT     OutfitRecommendation: title, matchScore double, OutfitComponent[],
           reasons[], metrics (colorHarmony/bodyFit/occasionMatch/…)
EXPLANATION per-component `reason` + global `reasons[]` (static)
USER ACTION "Save Outfit" → SnackBar ONLY (no persistence) — verified
FEEDBACK   none
```
- Required user data: preference selections (ephemeral). Required profile
  data: none (no wardrobe input today — PLANNED). Required media: none.
  Required knowledge: none today (options are hardcoded local vocab).
  AI output: recommendation. Confidence: `matchScore` 91 (static, double).
  Explanation: component reasons (static). Model: none; PLANNED preference+
  wardrobe-driven generation. Feedback: **none** (save is snackbar-only).
  Historical: none (nothing persists).

### B3. Hairstyle (face → hairstyle recommendation)

```
INPUT      captured face (camera), FaceScanCheck readiness (static)
PROCESSING timer-driven stages (HairstyleProcessingStage[])
KNOWLEDGE  HairstyleAnalysisResult.mock (top = Textured Quiff, matchScore 0.94)
DECISION   none — static top + alternatives
OUTPUT     HairstyleAnalysisResult: faceShape/skinTone/styleDna, top
           recommendation, alternatives[]
EXPLANATION recommendation reasons[], stylingTips, maintenance, bestFor (static)
USER ACTION "Save Style" → SnackBar ONLY; assistant offline replies reuse .mock
FEEDBACK   none
```
- Required user data: none. Required profile data: **PLANNED** `FaceProfile`
  (setFace exists at learning_service.dart:276 but NO screen calls it —
  verified; so face data is never written). Required media: captured face
  image (never persisted). Required knowledge: the two hairstyle catalog
  cards (Textured Quiff 94 / Classic Pompadour 87, mirrored in
  `catalog.py::TEXTURED_QUIFF`). AI output: recommendation set. Confidence:
  0.94/0.87 static. Explanation: reasons/tips (static). Model: none; PLANNED
  face-analysis model. Feedback: none. Historical: none.

### B4. Grooming (face + grooming inputs → grooming recommendation)

```
INPUT      faceShape/beardStyle/density/color chips (GroomingOption[])
PROCESSING timer-driven stages (GroomingProcessingStage[])
KNOWLEDGE  GroomingAnalysisResult.mock (top = Structured Goatee, 0.92)
DECISION   none — static top + alternatives
OUTPUT     GroomingAnalysisResult: faceShape/beardStyle/beardDensity/
           beardColor, top recommendation, alternatives[]
EXPLANATION recommendation reasons[], beardLength/cheekLine/eyewear fields,
           stylingTips (static)
USER ACTION "Save Style" → SnackBar ONLY
FEEDBACK   none
```
- Required user data: grooming input selections (ephemeral). Required profile
  data: PLANNED FaceProfile (unwritten). Required media: none today (PLANNED
  face image). Required knowledge: grooming catalog cards (Structured Goatee
  92 / Classic Stubble 85). AI output: recommendation. Confidence: 0.92/0.85
  static. Explanation: reasons + specifics (static). Model: none; PLANNED.
  Feedback: none. Historical: none.

### B5. Discover (look matching / scoring)

```
INPUT      none (feed is DiscoverLookData forYouMock/trendingMock — static)
PROCESSING none — matchScore, MatchScoreDetails, RecommendationReason[],
           wardrobeMatchCount, EnsembleComponent.isOwned, WardrobeAlternative[]
           are all baked into the mock
KNOWLEDGE  the 12 static look cards + filter vocabularies
DECISION   none
OUTPUT     look cards + detail payload
EXPLANATION MatchScoreDetails (overall/fit/colorHarmony/occasion/creativity),
           RecommendationReason[] (title/description)
USER ACTION save look → LearningService.addSavedLook (look_details_screen.dart:327)
FEEDBACK   'look_saved' signal only
```
- Required user data: none. Required profile data: **PLANNED** wardrobe for
  `isOwned`/`wardrobeMatchCount`/alternatives (currently mock numbers).
  Required media: imageUrl strings only (no media pipeline). Required
  knowledge: look catalog. AI output: match scores + reasons + alternatives.
  Confidence: mock ints (no computation). Explanation: reasons (static).
  Model: none; PLANNED matching/scoring. Feedback: `look_saved`. Historical:
  none (feed static; no per-user match history).

### B6. Home — Today's Look / style score / streak / wardrobe insight

Status: **MOCKED** (three cards are static consts; no computation).

```
INPUT      none (mock consts)
PROCESSING none
KNOWLEDGE  DailyOutfitData.mock, StyleScoreData.mock, StyleStreakData.mock,
           AIWardrobeInsightData.mock, TodaysLookData.mock
DECISION   none
OUTPUT     the four cards
EXPLANATION StyleScoreBreakdownItem[] (category/label/score); streak timeline;
           insight text
USER ACTION save today's look → addSavedLook (daily_outfit_screen.dart:1172)
FEEDBACK   'look_saved' only
```
- Required user data: name (from onboarding extras, default 'Alex'); nothing
  else. Required profile data: **PLANNED** UserModel (wardrobe/face/signals)
  for a real styleScore/streak/insight. Required media: none. Required
  knowledge: the mock card content. AI output: today's look, score, streak,
  insight. Confidence: **none computed** (note `LearningService.styleScore`
  IS computed in-memory: 60 + wardrobe +20 + savedLooks×2 — a deterministic
  formula, not AI; mock cards don't use it). Explanation: breakdown items
  (static). Model: none; PLANNED personalization. Feedback: `look_saved`.
  Historical: streak/score history would need per-user rows — **missing
  concept** (DATA_MODEL_INVENTORY §19.6).

### B7. Wardrobe insight

Status: **MOCKED**.

```
INPUT      none
PROCESSING none
KNOWLEDGE  WardrobeInsightData.mock / AIWardrobeInsightData.mock /
           catalog.WARDROBE_INSIGHT (3 shapes, same concept)
DECISION   none
OUTPUT     "Wardrobe Gap Detected" banner (title/insight/actionLabel/route)
EXPLANATION static insight text; no link to actual wardrobe contents
USER ACTION tap action → route (static)
FEEDBACK   none
```
- Required user data: none. Required profile data: **PLANNED** wardrobe for a
  real gap analysis (a real rule exists only in the assistant's
  `wardrobe_summary` tool: "consider a lightweight jacket"). Required media:
  none. Required knowledge: the insight content. AI output: insight card.
  Confidence: none. Explanation: static text. Model: none; PLANNED rule/AI
  insight. Feedback: none. Historical: none.

### B8. Profile style DNA

Status: **MOCKED** (and disconnected from FaceProfile).

```
INPUT      none
PROCESSING none
KNOWLEDGE  StyleDnaData mock (skinTone/faceShape/bodyType/styleType)
DECISION   none
OUTPUT     style DNA block on the profile dashboard
EXPLANATION none (labels only)
USER ACTION none
FEEDBACK   none
```
- Required user data: none. Required profile data: **PLANNED** `FaceProfile`
  (the true source — currently never written; the mock is disconnected).
  Required media: none (PLANNED face image). Required knowledge: none.
  AI output: style DNA fields. Confidence: none. Explanation: none.
  Model: none; PLANNED face analysis. Feedback: none. Historical: none.

### B9. Onboarding face analysis

Status: **PLANNED** (no implementation; the model is dead code).

```
INPUT      chosen vibe + captured image (PLANNED)
PROCESSING none today
KNOWLEDGE  allCapabilities lists "Face Analysis" + "Color Analysis" as active
DECISION   none
OUTPUT     AnalysisResult (score, silhouetteLabel, observations, palette,
           formalityLabel) — declared in onboarding_data.dart:33 but NEVER
           referenced anywhere (dead code, verified); YourAnalysisScreen builds
           inline palettes from PaletteSwatch
EXPLANATION observations[] (planned)
USER ACTION continue → home
FEEDBACK   none
```
- Required user data: chosen vibe. Required profile data: **PLANNED**
  FaceProfile write via `setFace`. Required media: **PLANNED** captured image.
  Required knowledge: vibe/palette config. AI output: analysis result.
  Confidence: none. Explanation: planned observations. Model: none; PLANNED
  face analysis model. Feedback: none. Historical: none.

---

## Part C — Consolidated requirements matrix

| AI feature | Status | User data | Profile data | Media | Knowledge | Output | Confidence | Explanation | Model/version | Feedback | Historical need |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Assistant chat/intent | IMPLEMENTED + PROTOTYPE | message text | wardrobe, face¹, savedLooks, preferredOccasions | none | backend catalog + WARDROBE | AssistantReply | none (static scores) | reply text | none (rules) / Ollama llama3.1:8b (text only) | signals only | signals; conversation not kept |
| Assistant offline | IMPLEMENTED (mirror) | message text | wardrobe (fallback seed) | none | Flutter mocks + catalog mirrors | AssistantReply | none | reply text | none | signals only | signals |
| Outfit scan analysis | MOCKED → PLANNED | none | none (wardrobe planned) | **captured image** | none | sections + detected items | none | section descriptions | PLANNED image model | `look_saved` | result not kept |
| Outfit builder | MOCKED → PLANNED | preference chips | wardrobe planned | none | option vocab | recommendation | static 91 | reasons | PLANNED generator | none (save stub) | none |
| Hairstyle | MOCKED → PLANNED | none | FaceProfile planned (never written) | captured face | hairstyle catalog | rec + alternatives | static 0.94/0.87 | reasons/tips | PLANNED face model | none | none |
| Grooming | MOCKED → PLANNED | input chips | FaceProfile planned | face planned | grooming catalog | rec + alternatives | static 0.92/0.85 | reasons/specifics | PLANNED | none | none |
| Discover matching | MOCKED → PLANNED | none | wardrobe planned | imageUrl only | look catalog | scores + reasons + alternatives | none | reasons | PLANNED scorer | `look_saved` | no match history |
| Home today's look / score / streak / insight | MOCKED → PLANNED | name only | UserModel planned | none | mock card content | 4 cards | none (styleScore is a formula, not AI) | breakdown items | PLANNED personalization | `look_saved` | **score/streak history missing** |
| Wardrobe insight | MOCKED → PLANNED | none | wardrobe planned | none | insight content | insight banner | none | static text | PLANNED rule/AI | none | none |
| Profile style DNA | MOCKED → PLANNED | none | FaceProfile planned | none | none | DNA block | none | none | PLANNED face model | none | none |
| Onboarding analysis | PLANNED (dead code) | chosen vibe | FaceProfile planned | captured image planned | vibe/palette | AnalysisResult (unused) | none | planned observations | PLANNED face model | none | none |

¹ `face` is consumed by `tools.recommend_hairstyle` but the app never writes it —
  so in practice the assistant always uses the oval default branch.

---

## Part D — Verified facts and caveats

1. **No real model runs in the product today.** The word "AI" in the UI is
   backed by (a) the assistant rules engine (backend + offline mirror) and
   (b) static mock data everywhere else. `allCapabilities` lists "Face
   Analysis" and "Color Analysis" as active — this is marketing copy in a
   static config; **no such computation exists** (verified: no call, no
   service, no model).
2. **The only backend is a prototype.** `backend/app/ai/*` is a deterministic
   prototype (rules + catalog); the optional Ollama enrichment rewrites only
   reply text and is off by default (unreachable localhost → falls back).
3. **No confidence is ever computed or transmitted.** Card scores are catalog
   constants; mock scores are baked doubles. The DTO has no confidence field.
4. **No explanation field exists** in the assistant contract; explanation is
   prose baked into reply text or static mock reason lists.
5. **Feedback is signals-only.** The single persistent trace is
   `LearningSignal` rows in `UserModel.signals` (`item_added`,
   `analysis_updated`, `style_updated`, `look_saved`, `occasion_preferred`,
   `assistant_message`, `suggestion_opened`, `assistant_navigation`). There is
   no rating, no like/dislike, no model-training loop.
6. **Face data is dead in practice:** `FaceProfile` + `setFace` exist but no
   screen writes them — so every face-dependent path (hairstyle, grooming,
   assistant recommendation branch, style DNA) runs on defaults or mocks.
7. **Media never persists:** captured images exist only as transient file
   paths; no image bytes are stored anywhere.
8. **Historical gaps** (from DATA_MODEL_INVENTORY §19.6): no score/streak
   history, no recommendation history, no event rows, no saved-look payload —
   all would be needed to train/improve any future real model.
