"""Wire schemas for the M11 feedback surface (#35, `POST /v1/feedback`).

Shapes mirror `FEEDBACK_LEARNING_API.md` §5.1 (`FeedbackCreate`):
`rating*` (tag string — the exact vocabulary is pending the feedback
design per BC-38/39 and PR-12, so validation here is structural only:
non-blank, 1..200), `reason?` (optional free-text "why", ≤2000 — the
M8-notes free-text bound, borrowed structurally since no numeric bound
is frozen), `targetLookId?` (catalog `looks.code`), `targetSavedLookId?`
(owned `saved_looks.id`). At most one target per reaction; neither is
required (a general rating is valid).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    rating: str = Field(min_length=1, max_length=200)
    reason: Optional[str] = Field(default=None, max_length=2000)
    targetLookId: Optional[str] = Field(default=None, max_length=200)
    targetSavedLookId: Optional[str] = Field(default=None, max_length=200)
