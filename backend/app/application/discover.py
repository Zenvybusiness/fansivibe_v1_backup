"""Application use cases — M14 Discover feed + detail (UC-31, endpoints #43–44).

`GetLookFeed` (`GET /v1/looks`) serves the personalized look feed as a
read-only presentation of the knowledge catalog (BAR-0): the merged
hairstyle + grooming rows from the canonical `KnowledgeSource`
(`CatalogKnowledgeSource` — the same infrastructure M5/M7/M9 reuse; no
second catalog, no second engine). `GetLookDetail`
(`GET /v1/looks/{look_id}`) serves one catalog row by its stable code
(PR-3).

Honesty boundaries (frozen-first, nothing invented):

- Filters (`occasion`/`style`/`fit`): the catalog rows carry no
  occasion/style/fit attributes (DEC-014 P-3, verified against the seed
  payloads), so any supplied filter is a truthful 422 — never an
  invented filter, never an `allowed` list of values the catalog cannot
  honor (M5 `#18` precedent verbatim). Unfiltered requests return the
  ranked catalog.
- Ranking ("engine-ranked", API-27): deterministic score-descending over
  the catalog `scoreSeed` values (the Scoring-stage value each row
  carries), ties broken by code ascending (the API-21 stable secondary
  key). This reuses the canonical ordering semantics
  (`rank_*_candidates`: score-desc, ties keep a stable order) — no
  second ranking engine, no per-user score invention. No `sort` param
  exists on this surface (API-27); the feed is returned as produced.
- Scores: `matchScore` is the derived-look family 0–100 int
  (`REC_API` §4.4 — discover is a derived-look surface):
  `round(scoreSeed * 100)`, mechanically rescaled, never rescored.
- Personalization: UC-31 names wardrobe/signals as personalization
  inputs, but no grounded wardrobe↔catalog linkage exists for these
  rows (garment UUIDs never address hairstyle/grooming codes) and no
  stored per-user match score exists — so v1 derives nothing per user
  and invents no `isOwned`/`wardrobeMatchCount`/`isTrending`/
  `matchScoreDetails`/ensemble/tags fields (AI-0: uncomputed fields are
  absent, never fabricated — DEC-015 E-6 precedent). Auth is still
  required (frozen: personalization requires the user); the caller's
  `user_id` is accepted as the seam for future grounded personalization
  but changes nothing today. Wardrobe/signal reads are therefore
  deferred, not wired as dead dependencies.
- Detail shape: the catalog's full grounded content (`stylingTips`,
  `maintenance`, `bestFor`) plus the summary core. `imageRef` is NULL
  for every seeded row, so no image field is served.
- Side effects: none. Read-only, non-transactional (UC-31 boundary):
  no save, no signal, no wear, no preference/event/wardrobe mutation —
  and no commit call at all (the use cases take no session).
"""

from __future__ import annotations

import base64
from typing import Optional
from uuid import UUID

from app.api.errors import validation
from app.domain.ports.external import KnowledgeSource

# Cursor pagination bounds (frozen: default 20, max 50 — feeds carry heavy
# DTOs, so the tighter max keeps a page small; `PAGINATION_FILTERING` §5).
_FEED_DEFAULT_LIMIT = 20
_FEED_MAX_LIMIT = 50


def _feed_error(field: str, error: str) -> None:
    raise validation([{"field": field, "error": error}])


def _to_wire_score(score_seed: float) -> int:
    """Mechanical rescale of the catalog `scoreSeed` (0..1) to the
    derived-look family 0–100 int (`REC_API` §4.4). No rescoring."""
    return int(round(float(score_seed) * 100))


def _ranked_catalog(knowledge: KnowledgeSource) -> list[dict]:
    """Merged hairstyle + grooming catalog in engine rank order.

    Score-descending over `scoreSeed`, ties broken by code ascending
    (API-21 stable secondary key). Deprecated rows never surface (KN-3,
    enforced inside the source); malformed rows raise there, never here.
    """
    rows = [
        *knowledge.retrieve_hairstyle_looks(),
        *knowledge.retrieve_grooming_looks(),
    ]
    ranked = sorted(rows, key=lambda look: (-float(look.matchScore), look.id))
    return [
        {
            "id": look.id,
            "title": look.name,
            "description": look.description,
            "matchScore": _to_wire_score(look.matchScore),
            "reasons": list(look.reasons),
            "_sortScore": _to_wire_score(look.matchScore),
        }
        for look in ranked
    ]


def _encode_cursor(*, score: int, code: str) -> str:
    """Opaque server-generated cursor for the last item of a page (API-21).

    Clients never construct it. Encodes the rank position
    (`<matchScore>:<code>`); the code is the stable secondary key, so the
    window never shifts between pages.
    """
    raw = f"{score}:{code}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[int, str]:
    """Resolve an opaque cursor to its rank position.

    Malformed, foreign, or expired (not issued by the server) cursors are
    never silently reset to page 1 — they are 422 (`PAGINATION` §5.3).
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except Exception:
        _feed_error("cursor", "cursor is malformed or expired")
        raise AssertionError("unreachable")
    score_text, sep, code = raw.partition(":")
    if not sep or not code:
        _feed_error("cursor", "cursor is malformed or expired")
        raise AssertionError("unreachable")
    try:
        score = int(score_text)
    except ValueError:
        _feed_error("cursor", "cursor is malformed or expired")
        raise AssertionError("unreachable")
    return score, code


def _strip_internal(item: dict) -> dict:
    return {key: value for key, value in item.items() if not key.startswith("_")}


class GetLookFeed:
    """Serve the ranked look feed page (endpoint #43 `GET /v1/looks`,
    UC-31).

    Read-only: repeated calls over an unchanged catalog are
    byte-identical. Empty catalog → empty page (200, never 404).
    """

    def __init__(self, *, knowledge: KnowledgeSource) -> None:
        self._knowledge = knowledge

    def __call__(
        self,
        *,
        user_id: UUID,
        occasion: Optional[object] = None,
        style: Optional[object] = None,
        fit: Optional[object] = None,
        cursor: Optional[object] = None,
        limit: Optional[object] = None,
    ) -> tuple[list[dict], Optional[str], bool]:
        """Returns `(items, next_cursor, has_more)`.

        `user_id` is the authenticated caller (frozen auth rule); the
        catalog is system-owned so derivation is user-invariant today.
        """
        _ = user_id
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
        if fit is not None:
            field_errors.append(
                {
                    "field": "fit",
                    "error": "fit filtering is not supported by the current look catalog",
                }
            )
        if field_errors:
            raise validation(field_errors)

        clean_limit = _FEED_DEFAULT_LIMIT if limit is None else limit
        if (
            isinstance(clean_limit, bool)
            or not isinstance(clean_limit, int)
            or not (1 <= clean_limit <= _FEED_MAX_LIMIT)
        ):
            _feed_error(
                "limit",
                f"limit must be between 1 and {_FEED_MAX_LIMIT}",
            )
            raise AssertionError("unreachable")

        if cursor is not None and (not isinstance(cursor, str) or not cursor):
            _feed_error("cursor", "cursor is malformed or expired")

        ranked = _ranked_catalog(self._knowledge)
        start = 0
        if cursor is not None:
            assert isinstance(cursor, str)
            score, code = _decode_cursor(cursor)
            position = next(
                (
                    index
                    for index, item in enumerate(ranked)
                    if item["_sortScore"] == score and item["id"] == code
                ),
                None,
            )
            if position is None:
                _feed_error("cursor", "cursor is malformed or expired")
                raise AssertionError("unreachable")
            start = position + 1

        window = ranked[start : start + clean_limit]
        items = [_strip_internal(item) for item in window]
        remaining = len(ranked) - (start + len(window))
        has_more = remaining > 0
        next_cursor = (
            _encode_cursor(score=window[-1]["_sortScore"], code=window[-1]["id"])
            if has_more
            else None
        )
        return items, next_cursor, has_more


class GetLookDetail:
    """Serve one catalog look by stable code (endpoint #44
    `GET /v1/looks/{look_id}`).

    Returns the grounded detail dict, or `None` when no catalog row
    carries the code (the router maps `None` to 404). Read-only.
    """

    def __init__(self, *, knowledge: KnowledgeSource) -> None:
        self._knowledge = knowledge

    def __call__(self, *, user_id: UUID, look_id: str) -> Optional[dict]:
        _ = user_id
        look = self._knowledge.lookup_hairstyle_look(look_id)
        if look is None:
            look = self._knowledge.lookup_grooming_look(look_id)
        if look is None:
            return None
        return {
            "id": look.id,
            "title": look.name,
            "description": look.description,
            "matchScore": _to_wire_score(look.matchScore),
            "reasons": list(look.reasons),
            "stylingTips": look.stylingTips,
            "maintenance": look.maintenance,
            "bestFor": look.bestFor,
        }
