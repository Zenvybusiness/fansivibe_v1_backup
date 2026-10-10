"""Conservative canonical product identity policy (D4).

Deciding whether two source listings are the *same* canonical product is
deliberately conservative — a wrong merge is worse than a duplicate:

- **exact_source_identity** — ``(source, source_product_id)`` already maps to
  a product (the unique ``product_source_map`` identity). Always wins.
- **verified_cross_source** — the listing carries a valid GTIN that a
  different source's product already carries. The only auto-merge signal.
- **possible_match** — no GTIN match, but an existing product shares the
  normalized brand *and* category. Reported for review; records stay
  separate (never merged on similar titles/categories).
- **no_match** — nothing to compare against; create a new product.

Manufacturer ids (MPN) are not globally unique and are never used alone to
merge. Entity resolution stays deterministic and local: no external service,
no LLM.

This module is pure; the persistence adapter supplies the candidate rows and
applies the resulting decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from app.domain.services.normalization import NormalizedProduct

MATCH_EXACT = "exact_source_identity"
MATCH_VERIFIED = "verified_cross_source"
MATCH_POSSIBLE = "possible_match"
MATCH_NONE = "no_match"


@dataclass(frozen=True)
class IdentityCandidates:
    """Existing rows the adapter found for a candidate listing."""

    source_identity_product_id: Optional[UUID] = None
    stable_id_product_id: Optional[UUID] = None
    possible_match_product_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class IdentityDecision:
    """The identity outcome for one candidate listing.

    ``product_id`` is the product to update/attach to; ``None`` means a new
    canonical product must be created. ``possible_match_product_ids`` is
    populated only for a reported (unmerged) possible match.
    """

    match_status: str
    product_id: Optional[UUID] = None
    possible_match_product_ids: tuple[UUID, ...] = ()

    @property
    def creates_new_product(self) -> bool:
        return self.product_id is None


def resolve_identity(
    candidate: NormalizedProduct, candidates: IdentityCandidates
) -> IdentityDecision:
    """Apply the documented policy in order of decreasing confidence."""
    if candidates.source_identity_product_id is not None:
        return IdentityDecision(MATCH_EXACT, candidates.source_identity_product_id)

    if candidate.gtin and candidates.stable_id_product_id is not None:
        return IdentityDecision(MATCH_VERIFIED, candidates.stable_id_product_id)

    if candidates.possible_match_product_ids:
        return IdentityDecision(
            MATCH_POSSIBLE,
            None,
            possible_match_product_ids=candidates.possible_match_product_ids,
        )

    return IdentityDecision(MATCH_NONE)
