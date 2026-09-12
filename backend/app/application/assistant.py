"""Application use case — assistant card-interaction feedback (UC-23).

`SubmitAssistantCardFeedback` is the single client-facing signal input
(endpoint #17, `POST /v1/assistant/feedback`): one append-only
`learning_signals` row per call (tier 1, never idempotent — retries append).

The use case owns the interactionType → signal_type mapping. Only the two
contract interactions exist; the client can never name a `signal_type`
itself (M10 sole writer, PR-7). No card existence or ownership lookup:
assistant cards are ephemeral suggestions, so there is nothing to look up
and no card table exists.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.api.errors import ApiError, database_failure
from app.application.learning import mark_styled_today
from app.domain.ports.repositories import ActivityDayRepository, LearningSignalRepository

_INTERACTION_TO_SIGNAL_TYPE = {
    "opened": "suggestion_opened",
    "navigated": "assistant_navigation",
}


class SubmitAssistantCardFeedback:
    """Record one card interaction as a learning signal (endpoint #17)."""

    def __init__(
        self,
        *,
        signals: LearningSignalRepository,
        activity_days: Optional[ActivityDayRepository] = None,
    ) -> None:
        self._signals = signals
        self._activity_days = activity_days

    def __call__(
        self,
        *,
        user_id: UUID,
        card_id: Optional[str],
        card_title: Optional[str],
        interaction_type: str,
    ) -> str:
        """Persist the signal; returns the stored `signal_type`.

        Raises 422 for any interaction outside the frozen contract pair.
        The card reference is stored as the signal label (title preferred,
        then id); with neither supplied the interaction itself is the label
        so the append-only row always carries an honest, non-empty label.
        """
        signal_type = _INTERACTION_TO_SIGNAL_TYPE.get(interaction_type)
        if signal_type is None:
            raise ApiError(
                status_code=422,
                code="VALIDATION_ERROR",
                message="Some of the provided values are not valid. Please check your input.",
                details={
                    "field_errors": [
                        {
                            "field": "interactionType",
                            "error": "unknown value",
                            "allowed": sorted(_INTERACTION_TO_SIGNAL_TYPE),
                        }
                    ]
                },
            )
        label = card_title or card_id or interaction_type
        try:
            self._signals.insert_look_saved(
                user_id=user_id,
                signal_type=signal_type,
                label=label,
                context={"interaction_type": interaction_type},
            )
            if self._activity_days is not None:
                # M10-A: today's styled-day upsert rides this same commit.
                # Append-only behavior is unchanged — retries still append
                # another signal row while the day row stays one.
                mark_styled_today(activity_days=self._activity_days, user_id=user_id)
            self._signals.commit()
        except Exception:
            self._signals.rollback()
            raise database_failure()
        return signal_type
