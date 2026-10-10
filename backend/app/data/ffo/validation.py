"""FFO JSON-Schema validation (D7).

``corpus.py`` checks documents structurally and explicitly defers full
JSON-Schema evaluation, noting: "add `jsonschema` only when a consumer needs
deeper checks." D7's trend-publication guard is that first consumer.

These helpers evaluate an arbitrary instance against the *authoritative* FFO
schema loaded from ``schemas/`` (via :func:`app.data.ffo.load_schema`). They
never rewrite a schema and never invent a replacement; they only report the
violations that the schema itself defines. Draft 2020-12 is the dialect the
schemas declare.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from app.data.ffo import load_schema


def _errors(validator: Draft202012Validator, instance: Any) -> list[str]:
    """Deterministic (path-sorted) violation messages; empty means valid."""
    return [
        f"{'/'.join(str(p) for p in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(
            validator.iter_errors(instance),
            key=lambda e: [str(p) for p in e.absolute_path],
        )
    ]


_TREND_VALIDATOR = Draft202012Validator(load_schema("trend"))
_TREND_SIGNAL_VALIDATOR = Draft202012Validator(load_schema("trend_signal"))


def trend_errors(instance: Any) -> list[str]:
    """Violations of the authoritative ``trend.schema.json`` ([] == valid)."""
    return _errors(_TREND_VALIDATOR, instance)


def trend_signal_errors(instance: Any) -> list[str]:
    """Violations of the authoritative ``trend_signal.schema.json``."""
    return _errors(_TREND_SIGNAL_VALIDATOR, instance)
