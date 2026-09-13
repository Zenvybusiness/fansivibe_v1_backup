"""Regression for empty candidate selection (RangeError analog).

The deterministic "random" pick (`_select_index`: SHA-256 `% count` in
`today.py` / `outfits.py`) is the backend counterpart of Dart
`Random.nextInt(max)`: with an empty candidate list (`count == 0`) the raw
`% 0` crashes with `ZeroDivisionError` (Python) — the same class as Dart
`RangeError: max must be in range 0 < max ≤ 2^32, was 0`.

Derivations guard `if not ranked: return None` before selecting (honest
204/404 empty states), so this helper must fail clearly with `ValueError`
when called with no candidates instead of `ZeroDivisionError`.

Pure unit tests — no database needed.
"""

from __future__ import annotations

import pytest

from app.application import outfits as outfits_uc
from app.application import today as today_uc
from app.domain.services.analysis_rules import (
    generate_outfit_candidates,
    select_best_outfit_candidate,
)


@pytest.mark.parametrize("module", [outfits_uc, today_uc])
def test_select_index_empty_raises_value_error_not_zero_division(module):
    with pytest.raises(ValueError, match="no candidates"):
        module._select_index(0, "any-seed")
    with pytest.raises(ValueError, match="no candidates"):
        module._select_index(0, None)
    with pytest.raises(ValueError, match="no candidates"):
        module._select_index(-1, "any-seed")


@pytest.mark.parametrize("module", [outfits_uc, today_uc])
def test_select_index_normal_cases_still_work(module):
    # Absent key → winner (rank 0).
    assert module._select_index(3, None) == 0
    # Supplied key → stable index in range, deterministic.
    first = module._select_index(3, "seed-abc")
    assert 0 <= first < 3
    assert module._select_index(3, "seed-abc") == first
    # Single candidate always picks 0.
    assert module._select_index(1, "any-seed") == 0


def test_empty_wardrobe_yields_no_candidates_not_crash():
    # Candidate generation with no items is an honest empty, never a crash.
    assert generate_outfit_candidates([]) == []
    assert generate_outfit_candidates(None) == []  # type: ignore[arg-type]
    # Selection over empty is None (caller maps to 204/404), never IndexError.
    assert select_best_outfit_candidate([]) is None
    assert select_best_outfit_candidate(None) is None  # type: ignore[arg-type]
