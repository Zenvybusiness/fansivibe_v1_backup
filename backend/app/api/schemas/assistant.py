"""Wire schemas for the assistant card-feedback surface (#17).

Shapes mirror `FEEDBACK_LEARNING_API.md` §4.4 (`AssistantCardFeedback`):
the client sends only the public interaction contract — never a
`signal_type` (M10 sole writer, PR-7).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class AssistantCardFeedback(BaseModel):
    cardId: Optional[str] = Field(default=None, max_length=200)
    cardTitle: Optional[str] = Field(default=None, max_length=200)
    interactionType: str = Field(min_length=1, max_length=32)
