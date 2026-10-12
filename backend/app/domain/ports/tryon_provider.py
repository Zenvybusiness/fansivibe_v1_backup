"""Virtual try-on provider port (Stage F0: mock only).

The product flow (Flutter → backend jobs → polling → retrieval) is built
against this port so a real model can be connected later without
rebuilding it. Only ``mock`` and ``off`` exist in F0 — there is no paid
provider code path, so no paid generation can be silently enabled.

The mock renders a deterministic SVG composite (stdlib only, no image
dependency) with a baked-in TEST DATA banner. It must never be
presented as genuine AI output — callers serve it with
``is_mock: true`` and the UI labels every view.
"""

from __future__ import annotations

from typing import Protocol
from xml.sax.saxutils import escape as _escape

_MOCK_BANNER = "TEST DATA \u2014 NOT AI TRY-ON"


class TryOnProvider(Protocol):
    """Sync render contract a real adapter will implement later."""

    provider_id: str

    def render(
        self,
        *,
        person_digest: str,
        garment_labels: list[str],
        seed: str,
        outfit_source: str,
    ) -> bytes:
        """Return deterministic result image bytes for the job."""
        ...  # pragma: no cover


class MockTryOnProvider:
    """Deterministic $0 mock: same inputs → same SVG bytes.

    The SVG carries only content hashes and caller-supplied garment IDs —
    no real pixels are stored or echoed. The banner is part of the bytes
    so even a saved file stays labelled.
    """

    provider_id = "mock"

    def render(
        self,
        *,
        person_digest: str,
        garment_labels: list[str],
        seed: str,
        outfit_source: str,
    ) -> bytes:
        short = (person_digest or "")[:12]
        hue = int(short[:4], 16) % 360 if len(short) >= 4 else 280
        items = "".join(
            f'<text x="40" y="{300 + i * 28}" font-size="18" fill="#3a3340"'
            f" font-family=\"sans-serif\">{_escape(label)[:60]}</text>"
            for i, label in enumerate(garment_labels[:8])
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="800">'
            f'<rect width="640" height="800" fill="hsl({hue}, 18%, 94%)"/>'
            '<rect x="0" y="0" width="640" height="72" fill="#2b2333"/>'
            f'<text x="320" y="46" font-size="26" font-weight="bold"'
            ' text-anchor="middle" fill="#f5c518"'
            f' font-family="sans-serif">{_escape(_MOCK_BANNER)}</text>'
            '<text x="40" y="140" font-size="22" font-weight="bold"'
            ' fill="#2b2333" font-family="sans-serif">Mock try-on preview</text>'
            '<text x="40" y="175" font-size="15" fill="#5c5566"'
            ' font-family="sans-serif">Test data for UI development \u2014'
            " not AI-generated.</text>"
            f'<text x="40" y="220" font-size="16" fill="#2b2333"'
            f' font-family="sans-serif">source: {_escape(outfit_source)}</text>'
            f'<text x="40" y="248" font-size="16" fill="#2b2333"'
            f' font-family="sans-serif">person: {_escape(short)}</text>'
            f'<text x="40" y="276" font-size="16" fill="#2b2333"'
            f' font-family="sans-serif">seed: {_escape(seed)}</text>'
            f"{items}"
            "</svg>"
        )
        return svg.encode("utf-8")
