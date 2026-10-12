"""Assistant API router — endpoint #17 (`POST /v1/assistant/feedback`, UC-23).

The single client-facing signal input: records one append-only
`learning_signals` row per call (`suggestion_opened` / `assistant_navigation`).
Deliberately NOT idempotency-keyed — retries append another row.

The conversational surface (`POST /v1/assistant/chat`) stays in `main.py`
untouched (frozen wire F-13/F-5).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from uuid import UUID

from app.ai.vision_garment_adapter import OllamaVisionGarmentAdapter
from app.api.deps import get_current_user_id
from app.api.errors import validation
from app.api.rate_limit import ephemeral_rate_limit
from app.api.schemas.assistant import AssistantCardFeedback
from app.application.assistant import ChatWithImage, SubmitAssistantCardFeedback
from app.infrastructure.db.repositories import ActivityDayRepositorySQL, LearningSignalRepositorySQL
from app.infrastructure.db.session import get_db
from app.models.schemas import AssistantReply, ChatMessage, UserContext

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])

_MAX_CHAT_IMAGE_MESSAGE_CHARS = 2000
_MAX_CHAT_IMAGE_HISTORY_TURNS = 50


@router.post(
    "/feedback",
    status_code=204,
    responses={401: {"model": dict}, 422: {"model": dict}, 429: {"model": dict}},
)
def submit_assistant_card_feedback(
    request: AssistantCardFeedback,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    """Record one assistant card interaction (UC-23)."""
    use_case = SubmitAssistantCardFeedback(
        signals=LearningSignalRepositorySQL(db),
        activity_days=ActivityDayRepositorySQL(db),
    )
    use_case(
        user_id=user_id,
        card_id=request.cardId,
        card_title=request.cardTitle,
        interaction_type=request.interactionType,
    )
    return None


def _parse_chat_image_history(raw: str) -> list[ChatMessage]:
    """Parse the `history` form field into typed chat turns.

    Stateless follow-up context: the client sends back the turns it already
    holds (prior observation text rides along), so the image is never
    re-uploaded. Malformed turns fail closed with 422 — never a guess.
    """
    try:
        decoded = json.loads(raw) if raw.strip() else []
    except Exception:
        raise validation([{"field": "history", "error": "must be a JSON list"}])
    if not isinstance(decoded, list):
        raise validation([{"field": "history", "error": "must be a JSON list"}])
    if len(decoded) > _MAX_CHAT_IMAGE_HISTORY_TURNS:
        raise validation(
            [{"field": "history", "error": "too many turns, max 50"}]
        )
    turns: list[ChatMessage] = []
    for entry in decoded:
        if not isinstance(entry, dict):
            raise validation(
                [{"field": "history", "error": "each turn needs role and content"}]
            )
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            raise validation(
                [{"field": "history", "error": "each turn needs role and content"}]
            )
        if len(content) > _MAX_CHAT_IMAGE_MESSAGE_CHARS:
            raise validation(
                [{"field": "history", "error": "turn content too long"}]
            )
        turns.append(ChatMessage(role=role, content=content))
    return turns


def _parse_chat_image_user(raw: str) -> UserContext | None:
    """Parse the `user` form field into the existing `UserContext` contract.

    The wardrobe snapshot travels here (same shape as `POST
    /v1/assistant/chat`), so matching uses the caller's own saved items.
    `{}` means no context — never a fabricated wardrobe.
    """
    try:
        decoded = json.loads(raw) if raw.strip() else {}
    except Exception:
        raise validation([{"field": "user", "error": "must be a JSON object"}])
    if not isinstance(decoded, dict):
        raise validation([{"field": "user", "error": "must be a JSON object"}])
    if not decoded:
        return None
    try:
        return UserContext(**decoded)
    except Exception:
        raise validation([{"field": "user", "error": "invalid user context"}])


@router.post(
    "/chat-with-image",
    response_model=AssistantReply,
    responses={422: {"model": dict}, 429: {"model": dict}, 503: {"model": dict}},
)
def chat_with_image(
    image: UploadFile = File(...),
    message: str = Form(default=""),
    history: str = Form(default="[]"),
    user: str = Form(default="{}"),
    _: None = Depends(ephemeral_rate_limit),
) -> AssistantReply:
    """Answer one outfit-photo question with genuine vision measurement.

    Multipart (image bytes + question + history + user snapshot), stateless
    and unauthenticated like the ephemeral passes: the actual bytes run
    through the shared garment vision adapter, and matching uses only the
    caller-supplied wardrobe snapshot. Bytes are hashed and discarded —
    never persisted, logged, or echoed. Follow-ups reuse the plain chat
    endpoint (the observation text rides in history), so no re-upload.
    """
    if len(message) > _MAX_CHAT_IMAGE_MESSAGE_CHARS:
        raise validation([{"field": "message", "error": "must be at most 2000 characters"}])
    turns = _parse_chat_image_history(history)
    context = _parse_chat_image_user(user)
    use_case = ChatWithImage(garment_port=OllamaVisionGarmentAdapter())
    return use_case(image=image, message=message, history=turns, user=context)
