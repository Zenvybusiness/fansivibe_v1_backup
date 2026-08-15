# Fansivibe Analytics Specification

## Section 13 — Analytics Requirements

Minimum event instrumentation required to observe the core value loop (6 events):

| Event Name | Trigger | Required Properties | Why It Matters | Success Interpretation | Failure Interpretation |
|---|---|---|---|---|---|
| `appearance_scan_started` | User taps "Scan My Hairstyle" CTA; flow begins at `FaceScanScreen` | `camera_source` (front/back), `image_quality` (resolution, lighting) | Measures flow entry point; validates the trigger works | Scan initiated successfully | User abandons before scan starts; camera permission denied |
| `appearance_scan_completed` | Analysis run status reaches terminal state (completed/failed) after polling | `run_status` (completed/failed/timeout), `error_code` (if failed), `poll_attempts` (1–30) | Measures if analysis produced a result; core infrastructure check | Run completed with result; `status=completed` | Run failed (`status=failed`), timed out (30 attempts), never completed |
| `recommendations_viewed` | `HairstyleResultScreen` renders with recommendation data | `recommendation_id`, `confidence_score` (0–1), `has_explanation` (boolean), `top_style_name` | Measures if user saw the recommendation; primary exposure event | Recommendation displayed on screen; not a mock fallback | Recommendation fell back to mock data (indicates server unreachable) |
| `explanation_viewed` | User views the explanation section on result screen (may require scroll) | `explanation_text` (the grounded reason string), `time_in_view` (seconds, if trackable) | Measures if user sees the grounded explanation (key differentiator); without this, the mechanism is just a black box | Explanation rendered and visible to user | Explanation not displayed or user skips past it |
| `recommendation_selected` | User taps "Save Style" CTA or dismisses screen | `action` (save/dismiss), `recommendation_id`, `confidence_at_selection` | Measures the user decision point; the "decision" in the value loop | User initiated save action (tapped CTA) | User dismissed/navigated away without saving |
| `recommendation_saved` | `POST /v1/looks/saved` returns 201 with `Idempotency-Key`; TRX-3 committed | `save_success` (boolean), `idempotency_key`, `look_saved_signal` (committed/failed), `snackbar_shown` (success/error) | Confirms the save action completed; closes the feedback loop in the value mechanism | Save succeeded: snackbar "Look saved to profile"; `look_saved` signal recorded | Save failed: 409 conflict, 404 unknown, 422 invalid; snackbar shows error; no signal committed |

### Events NOT Included (not required for this experiment)

- `onboarding_started` — not required; experiment may include existing users
- `profile_completed` — not required; experiment tests with whatever profile data user has
- `plan_viewed` / `plan_shared` — these are downstream outcomes beyond the MVP experiment
- `real_world_action` / `outcome_submitted` / `satisfaction_recorded` — these require user follow-up beyond the app; not in MVP scope
- `return_session` — retention metric; separate experiment

### Rationale

These 6 events directly observe the 6 stages of the core value loop: input → analysis → recommendation → explanation → decision → save/feedback. No vanity metrics (e.g., "app launches," "screen views" without purpose) are included. State transitions (scan → result → save) are preferred over count-based metrics.