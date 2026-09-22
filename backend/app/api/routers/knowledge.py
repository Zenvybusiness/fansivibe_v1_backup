"""Knowledge API router — endpoints #18–#22 (`GET /v1/knowledge/*`, M5).

Public catalog reads (API-7): no authentication, no user data, read-only
system content (KN-2/KN-9). Every success response carries
`X-Knowledge-Version` (KN-1) from the single authoritative source
(`catalog.KNOWLEDGE_VERSION` — never hardcoded per endpoint).

- #18 looks: honest v1 — unfiltered paginated catalog; any supplied
  `occasion`/`style` is a truthful 422 (DEC-014 P-3).
- #19/#20 categories/colors: DB-backed system vocabulary.
- #21 occasions: frozen 9-row K9.1 config (DEC-014 P-1).
- #22 items: system-owned reference catalog, content-gated (DEC-014 P-2).
- FFO reads: `GET /v1/knowledge/ffo` (26-schema index) + `GET
  /v1/knowledge/ffo/{name}` (verbatim schema, 404 unknown) — file-backed,
  public, read-only; carry `X-Ffo-Version` alongside `X-Knowledge-Version`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.schemas.knowledge import (
    FfoSchemaList,
    ItemReferenceList,
    KnowledgeLookList,
    VocabularyList,
)
from app.application.knowledge import (
    GetFfoSchema,
    ListFfoSchemas,
    ListKnowledgeItems,
    ListKnowledgeLooks,
    ListKnowledgeOccasions,
    ListKnowledgeVocabulary,
)
from app.data import catalog
from app.data.ffo import FFO_VERSION
from app.infrastructure.db.models import Colors, WardrobeCategories
from app.infrastructure.db.repositories import VocabularyRepositorySQL
from app.infrastructure.db.session import get_db
from app.infrastructure.external.knowledge import CatalogKnowledgeSource

router = APIRouter(prefix="/v1/knowledge", tags=["knowledge"])

_VERSION_HEADER = "X-Knowledge-Version"
_FFO_VERSION_HEADER = "X-Ffo-Version"


def _versioned(response: Response) -> str:
    """Set `X-Knowledge-Version` from the authoritative source; return it."""
    response.headers[_VERSION_HEADER] = catalog.KNOWLEDGE_VERSION
    return catalog.KNOWLEDGE_VERSION


def _ffo_versioned(response: Response) -> str:
    """Set `X-Ffo-Version` from the FFO package; return it."""
    response.headers[_FFO_VERSION_HEADER] = FFO_VERSION
    return FFO_VERSION


@router.get(
    "/looks",
    response_model=KnowledgeLookList,
    responses={422: {"model": dict}},
)
def list_knowledge_looks(
    response: Response,
    occasion: str | None = Query(
        default=None,
        description="Not supported by the current catalog; any value → 422.",
    ),
    style: str | None = Query(
        default=None,
        description="Not supported by the current catalog; any value → 422.",
    ),
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
) -> KnowledgeLookList:
    """List the curated look catalog (paginated, deterministic order)."""
    _versioned(response)
    use_case = ListKnowledgeLooks(knowledge=CatalogKnowledgeSource())
    items, total = use_case(page=page, page_size=page_size, occasion=occasion, style=style)
    return KnowledgeLookList(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/categories",
    response_model=VocabularyList,
    responses={422: {"model": dict}},
)
def list_knowledge_categories(
    response: Response,
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
    db: Session = Depends(get_db),
) -> VocabularyList:
    """List the canonical wardrobe-category vocabulary (DB-backed)."""
    _versioned(response)
    use_case = ListKnowledgeVocabulary(
        vocabulary=VocabularyRepositorySQL(db, WardrobeCategories)
    )
    items, total = use_case(page=page, page_size=page_size)
    return VocabularyList(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/colors",
    response_model=VocabularyList,
    responses={422: {"model": dict}},
)
def list_knowledge_colors(
    response: Response,
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
    db: Session = Depends(get_db),
) -> VocabularyList:
    """List the canonical color vocabulary (DB-backed)."""
    _versioned(response)
    use_case = ListKnowledgeVocabulary(
        vocabulary=VocabularyRepositorySQL(db, Colors)
    )
    items, total = use_case(page=page, page_size=page_size)
    return VocabularyList(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/occasions",
    response_model=VocabularyList,
    responses={422: {"model": dict}},
)
def list_knowledge_occasions(
    response: Response,
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
) -> VocabularyList:
    """List the frozen 9-row occasion vocabulary (DEC-014 P-1)."""
    _versioned(response)
    use_case = ListKnowledgeOccasions(knowledge=CatalogKnowledgeSource())
    items, total = use_case(page=page, page_size=page_size)
    return VocabularyList(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/items",
    response_model=ItemReferenceList,
    responses={422: {"model": dict}},
)
def list_knowledge_items(
    response: Response,
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
) -> ItemReferenceList:
    """List the system-owned item-type references (content-gated, DEC-014 P-2)."""
    _versioned(response)
    use_case = ListKnowledgeItems(knowledge=CatalogKnowledgeSource())
    items, total = use_case(page=page, page_size=page_size)
    return ItemReferenceList(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/ffo",
    response_model=FfoSchemaList,
    responses={422: {"model": dict}},
)
def list_ffo_schemas(
    response: Response,
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page, max 100"),
) -> FfoSchemaList:
    """List the 26 FFO foundation schemas (file-backed, public, read-only)."""
    _versioned(response)
    _ffo_versioned(response)
    use_case = ListFfoSchemas()
    items, total = use_case(page=page, page_size=page_size)
    return FfoSchemaList(items=items, page=page, page_size=page_size, total=total)


@router.get(
    "/ffo/{name}",
    response_model=dict,
    responses={404: {"model": dict}},
)
def get_ffo_schema(name: str, response: Response) -> dict:
    """Return one FFO foundation schema verbatim; unknown names → 404."""
    _versioned(response)
    _ffo_versioned(response)
    return GetFfoSchema()(name=name)
