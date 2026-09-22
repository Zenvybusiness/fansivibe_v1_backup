"""Wire schemas for the M5 knowledge reads (STEP 19.5, DEC-014).

Endpoints #18–#22 (`GET /v1/knowledge/*`): public catalog reads.
List endpoints return offset envelopes (`API_CONTRACT_RULES.md` §8.2);
JSON keys are camelCase (API-19).
"""

from __future__ import annotations

from pydantic import BaseModel


class VocabularyItem(BaseModel):
    """One controlled-vocabulary row (#19/#20/#21)."""

    code: str
    label: str
    sortOrder: int


class ItemReference(BaseModel):
    """One system-owned item-type reference row (#22, DEC-014 P-2)."""

    code: str
    label: str
    category: str
    sortOrder: int


class KnowledgeLook(BaseModel):
    """One curated catalog look (#18).

    Verbatim catalog content fields only — the rows carry no
    occasion/style attributes (DEC-014 P-3), so none appear here.
    """

    code: str
    title: str
    description: str
    reasons: list[str]
    stylingTips: str
    maintenance: str
    bestFor: str


class KnowledgeLookList(BaseModel):
    """Offset envelope for `GET /v1/knowledge/looks` (#18)."""

    items: list[KnowledgeLook]
    page: int
    page_size: int
    total: int


class VocabularyList(BaseModel):
    """Offset envelope for `#19`/`#20`/`#21` vocabulary reads."""

    items: list[VocabularyItem]
    page: int
    page_size: int
    total: int


class ItemReferenceList(BaseModel):
    """Offset envelope for `GET /v1/knowledge/items` (#22)."""

    items: list[ItemReference]
    page: int
    page_size: int
    total: int


class FfoSchemaSummary(BaseModel):
    """One FFO foundation schema (`GET /v1/knowledge/ffo`)."""

    name: str
    title: str


class FfoSchemaList(BaseModel):
    """Offset envelope for `GET /v1/knowledge/ffo`."""

    items: list[FfoSchemaSummary]
    page: int
    page_size: int
    total: int
