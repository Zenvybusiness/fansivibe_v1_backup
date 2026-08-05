"""Typed request/response contracts shared between the Fansivibe app and the
backend AI service.

The Flutter client mirrors these shapes exactly (see
`lib/features/assistant/data/models.dart`). Keep the two in sync when the
contract changes.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class WardrobeItem(BaseModel):
    id: str
    name: str
    category: str
    color: str
    material: Optional[str] = None
    isFavorite: bool = False


class FaceData(BaseModel):
    faceShape: Optional[str] = None
    skinTone: Optional[str] = None
    bodyType: Optional[str] = None
    styleType: Optional[str] = None


class UserContext(BaseModel):
    """Snapshot of the on-device user model sent with every request."""

    wardrobe: List[WardrobeItem] = Field(default_factory=list)
    face: Optional[FaceData] = None
    savedLooks: List[str] = Field(default_factory=list)
    preferredOccasions: List[str] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: str
    content: str


class AssistantRequest(BaseModel):
    messages: List[ChatMessage] = Field(default_factory=list)
    user: Optional[UserContext] = None


class SuggestionCard(BaseModel):
    kind: str
    title: str
    subtitle: str
    score: Optional[int] = None
    items: List[str] = Field(default_factory=list)
    action: Optional[str] = None


class ClarificationOption(BaseModel):
    label: str
    value: str


class NavigationRequest(BaseModel):
    route: str
    label: str


class AssistantReply(BaseModel):
    intent: str
    text: str
    cards: List[SuggestionCard] = Field(default_factory=list)
    clarifications: List[ClarificationOption] = Field(default_factory=list)
    navigation: Optional[NavigationRequest] = None
