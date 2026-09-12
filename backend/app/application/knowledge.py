"""Application use cases for the M5 knowledge reads (STEP 19.5, DEC-014).

Endpoints #18–#22 (`GET /v1/knowledge/*`): public, read-only, system-owned
content only (KN-2/KN-9). Each use case composes a knowledge source and
returns `(items, total)`; routers build the envelope and set
`X-Knowledge-Version`. Business rules live here, not in the routers (BA-7).

Sources (one per datum, never duplicated):
- #18 looks: `CatalogKnowledgeSource` hairstyle + grooming retrieval
  (deterministic catalog order; deprecated filtered, KN-3).
- #19/#20 categories/colors: `VocabularyRepository` (DB-backed,
  deterministic `(sort_order, code)` order).
- #21 occasions: `CatalogKnowledgeSource.retrieve_occasions` (frozen
  K9.1 config, DEC-014 P-1).
- #22 items: `CatalogKnowledgeSource.retrieve_item_references` (K9.1
  config; content-gated/empty, DEC-014 P-2 — nothing invented).
"""

from __future__ import annotations

from app.api.errors import validation
from app.domain.ports.repositories import VocabularyRepository


def _check_pagination(*, page: int, page_size: int) -> None:
    """Shared offset-pagination guard (contract: default 20, max 100)."""
    if page < 1:
        raise validation(
            [{"field": "page", "error": "page must be >= 1"}]
        )
    if page_size < 1 or page_size > 100:
        raise validation(
            [{"field": "page_size", "error": "page_size must be between 1 and 100"}]
        )


def _paginate(rows: list, *, page: int, page_size: int) -> tuple[list, int]:
    total = len(rows)
    start = (page - 1) * page_size
    return list(rows[start : start + page_size]), total


class ListKnowledgeLooks:
    """Endpoint #18 — `GET /v1/knowledge/looks` (STEP 19.5, DEC-014 P-3).

    Honest v1: the catalog rows carry no occasion/style attributes, so any
    supplied `occasion`/`style` filter is a truthful 422 (never an invented
    filter, never an `allowed` list of values the catalog cannot honor).
    Unfiltered requests return the paginated deterministic catalog.
    """

    def __init__(self, *, knowledge) -> None:
        self._knowledge = knowledge

    def __call__(
        self,
        *,
        page: int,
        page_size: int,
        occasion: str | None = None,
        style: str | None = None,
    ) -> tuple[list[dict], int]:
        _check_pagination(page=page, page_size=page_size)
        field_errors = []
        if occasion is not None:
            field_errors.append(
                {
                    "field": "occasion",
                    "error": "occasion filtering is not supported by the current look catalog",
                }
            )
        if style is not None:
            field_errors.append(
                {
                    "field": "style",
                    "error": "style filtering is not supported by the current look catalog",
                }
            )
        if field_errors:
            raise validation(field_errors)
        rows = [
            *self._knowledge.retrieve_hairstyle_looks(),
            *self._knowledge.retrieve_grooming_looks(),
        ]
        items = [
            {
                "code": look.id,
                "title": look.name,
                "description": look.description,
                "reasons": list(look.reasons),
                "stylingTips": look.stylingTips,
                "maintenance": look.maintenance,
                "bestFor": look.bestFor,
            }
            for look in rows
        ]
        return _paginate(items, page=page, page_size=page_size)


class ListKnowledgeVocabulary:
    """Endpoints #19/#20 — categories / colors (STEP 19.5).

    Serves the DB-backed system vocabulary (`VocabularyRepository`);
    deterministic source order is preserved verbatim.
    """

    def __init__(self, *, vocabulary: VocabularyRepository) -> None:
        self._vocabulary = vocabulary

    def __call__(self, *, page: int, page_size: int) -> tuple[list[dict], int]:
        _check_pagination(page=page, page_size=page_size)
        rows = self._vocabulary.list_active()
        items = [
            {"code": row.code, "label": row.label, "sortOrder": row.sort_order}
            for row in rows
        ]
        return _paginate(items, page=page, page_size=page_size)


class ListKnowledgeOccasions:
    """Endpoint #21 — `GET /v1/knowledge/occasions` (STEP 19.5, DEC-014 P-1).

    Serves the frozen 9-row K9.1 config verbatim (exact codes, labels,
    `sortOrder` 1..9); no additional codes, no Discover-only ids.
    """

    def __init__(self, *, knowledge) -> None:
        self._knowledge = knowledge

    def __call__(self, *, page: int, page_size: int) -> tuple[list[dict], int]:
        _check_pagination(page=page, page_size=page_size)
        rows = self._knowledge.retrieve_occasions()
        return _paginate(list(rows), page=page, page_size=page_size)


class ListKnowledgeItems:
    """Endpoint #22 — `GET /v1/knowledge/items` (STEP 19.5, DEC-014 P-2).

    Serves the system-owned item-reference config in the frozen
    `{code, label, category, sortOrder}` shape. Content-gated: while no
    authoritative seed exists the catalog is empty and this returns an
    empty page (never invented rows, never user wardrobe rows).
    """

    def __init__(self, *, knowledge) -> None:
        self._knowledge = knowledge

    def __call__(self, *, page: int, page_size: int) -> tuple[list[dict], int]:
        _check_pagination(page=page, page_size=page_size)
        rows = self._knowledge.retrieve_item_references()
        return _paginate(list(rows), page=page, page_size=page_size)
