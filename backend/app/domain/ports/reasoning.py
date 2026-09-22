"""Fashion reasoner port — Phase 3A reasoning boundary.

The application depends only on this interface; the domain never sees a
model, a prompt, or a provider SDK. A future model adapter implements
this contract behind the unmoved port — it is NOT created here.
"""

from __future__ import annotations

from typing import Protocol


class FashionReasoner(Protocol):
    """Model-agnostic fashion reasoning seam.

    ``contract_version`` must equal the contracts module's
    ``REASONING_CONTRACT_VERSION`` — adapters on another contract are
    rejected by the caller, never silently mixed. ``reason`` is total
    over validated inputs: it returns a validated output or raises, and
    it must be able to return insufficient-evidence / unsupported
    verdicts instead of inventing answers.
    """

    contract_version: str

    def reason(self, reasoning_input) -> object: ...
