# MEMORY + PERSONALIZATION TARGET MODEL

## Conceptual Architecture

```
USER
  │
  ├──► PROFILE
  │  │
  │  ├──► identity: display_name, auth_provider, auth_subject, created_at, updated_at
  │  │
  │  ├──► settings: flags (JSONB), version (optimistic lock int)
  │  │
  │  └──► owner scoping: user_id (UUID FK → users, OW-1 on all user-owned endpoints)
  │
  │
  ↓
  ├──► APPEARANCE MEMORY
  │  │
  │  ├──► verified appearance: faceShape (categorical: oval/round/square/heart/diamond/rectangle),
  │  │         skinTone (categorical: dark/medium/light), bodyType (categorical:
  │  │         slim/average/athletic/plus), styleType (categorical: modern_minimalist/
  │  │         classic_elegance/street_style/bohemian/athleisure)
  │  │  - Origin: AI-inferred from analysis runs (hairstyle/outfit/grooming)
  │  │  - Source: `user_state.style_profile` JSONB, linked via `source_run_id` →
  │  │    `analysis_runs.id`
  │  │  - Confidence: per-run confidence score (0-1) from decision engine
  │  │  - Immutable per run; new analysis creates new entry, old preserved (append-only)
  │  │
  │  ├──► appearance history: all `analysis_runs` with run_type, status, result confidence,
  │  │         engine_version, created_at, completed_at, error (if failed)
  │  │  - Append-only per PR-5; never mutates in-place
  │  │
  │  └──► provenance: `saved_looks.source_run_id` → `analysis_runs.id` traceability
  │       for any saved look back to its producing analysis run
  │
  │
  ↓
  ├──► PREFERENCE MEMORY
  │  │
  │  ├──► explicit user-stated: `preferred_occasions` (List<String>, e.g. ['work',
  │  │         'date', 'party', 'travel']) from preferences screen
  │  │  - Origin: User said it (explicit input)
  │  │  - Storage: `user_state.preferences` JSONB + `UserModel.preferredOccasions`
  │  │  - Persistence: survives app restart; user-editable via Preferences screen
  │  │  - Wire format: camelCase `preferredOccasions` → stored snake_case `preferred_occasions`
  │  │
  │  ├──► derived preferences: `excludedLookIds` (frozenset of look IDs user has
  │  │         explicitly dismissed), `preferredLookIds` (frozenset of look IDs user
  │          has saved/liked) — derived from saved look interactions
  │  │  - Origin: System derived from behavior (saved looks = preferred; passed looks =
  │  │         excluded), but labeled as derived not explicit
  │  │  - Storage: `user_state.preferences` JSONB; must distinguish derived vs user-stated
  │  │
  │  └──► preference history: `learning_signals` with signal_type, label, context JSONB,
  │       occurred_at — records how preferences were formed (e.g. 'look_saved' → preferred,
  │       'look_passed' → excluded)
  │
  │
  ↓
  ├──► BEHAVIOR MEMORY
  │  │
  │  ├──► saved_looks: user-saved recommendations
  │  │  - Fields: look_id (catalog look.code), title (user-provided or catalog title),
  │  │    snapshot JSONB (full run result at save time), created_at, idempotency_key
  │  │  - Origin: User saved it (explicit action)
  │  │  - Storage: `saved_looks` table (backend) + `UserModel.savedLooks` (frontend)
  │  │  - Idempotency: `idempotency_key` unique per user per look_id; TRX-3 all-or-nothing
  │  │    commit (saved_looks INSERT + learning_signals look_saved INSERT atomically)
  │  │
  │  ├──► interaction history: `learning_signals` complete log
  │  │  - signal_type: 'look_saved', 'look_passed' (future), 'analysis_updated',
  │  │    'item_added', 'style_updated', 'occasion_preferred', 'assistant_message',
  │  │    'suggestion_opened', 'assistant_navigation'
  │  │  - label: human-readable description (e.g. 'textured_quiff saved', 'analysis
  │  │    updated')
  │  │  - context: JSONB with signal-specific keys (e.g. {"source_context": "hairstyle",
  │  │    "look_id": "textured_quiff"} or {"run_id": "...", "run_type": "outfit"})
  │  │  - Append-only per PR-5; never mutated in-place
  │  │
  │  └──► behavior patterns: derived from signal timeline
  │       - frequency of saves vs passes
  │       - recency of interactions
  │       - preference drift over time
  │
  │
  ↓
  ├──► HISTORY
  │  │
  │  ├──► analysis_runs: complete append-only history
  │  │  - Fields: run_type, status, result JSONB, confidence, engine_version,
  │  │    input_media (MediaRef), error (JSONB, nullable, write-once TRX-5),
  │  │    created_at, completed_at
  │  │
  │  ├──► saved_looks complete history: all saves with idempotency keys, conflict
  │  │    detection records, 409 on conflicting replay
  │  │
  │  └──► learning_signals full timeline: every interaction ever recorded, ordered by
  │       occurred_at, for observability and future ML/pattern analysis
  │
  │
  ↓
  ├──► PERSONALIZATION CONTEXT
  │  │
  │  ├──► appearance: current verified profile + completeness score
  │  │  - completeness = fraction of {faceShape, skinTone, bodyType, styleType} that
  │  │    are non-empty; 0.0-1.0 range
  │  │  - labeled as AI-inferred with confidence attribution
  │  │
  │  ├──► preferences: explicit + derived preferences combined
  │  │  - explicit: preferred_occasions (user-stated, labeled as such)
  │  │  - derived: preferredLookIds/excludedLookIds (labeled as system-derived from
  │  │    behavior, NOT as user preferences)
  │  │  - Never silently treat inference as user preference
  │  │
  │  ├──► behavior: saved looks count, interaction patterns, signal frequency
  │  │  - saved_looks count
  │  │ - signal recency and density
  │  │ - behavior pattern classification (saver, explorer, etc.)
  │  │
  │  └──► history: recent analysis runs, signal timeline summary
  │
  │
  ↓
  └──► DECISION ENGINE
     │
     ├──► 7-stage pipeline (unchanged interface):
     │  Stage 1: ContextBuilder — DecisionContext (appearance + preferences + completeness
     │           + knowledge_version); preferences explicitly labeled
     │  Stage 2: CandidateGeneration — catalog via KnowledgeSource port
     │  Stage 3: Filtering — binary keep/drop of excludedLookIds (labeled derived,
     │           not user-stated); also filter by look_passed signal history
     │  Stage 4: Scoring — weighted signals:
     │       seed (catalog baseline) + face_shape_boost (AI-inferred) +
     │       preference_boost (explicit + derived, labeled) + saved_look_boost
     │           (from behavior history, labeled as derived)
     │  Stage 5: Ranking — score-descending stable sort
     │  Stage 6: Explanation — grounded catalog reasons + face-shape match reason if
     │           boost > 0; each signal breakdown included in ScoredCandidate.signals
     │  Stage 7: Recommendation — HairstyleResult/GroomingResult with confidence +
     ///           needs_more_data; confidence derivation includes signal reliability weight
     │
     └──► confidence derivation enhanced:
          - 50% data completeness + 50% top-pick decisiveness +
          + signal reliability weight (frequency of reliable interactions)
          - explicitly flags AI-inferred vs user-stated sources