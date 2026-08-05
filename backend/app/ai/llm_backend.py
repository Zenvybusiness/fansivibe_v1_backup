"""Optional self-hosted LLM enrichment (Ollama).

The backend runs on the server, so phone hardware is irrelevant. Ollama serves
a small open model (default `llama3.1:8b`). When Ollama is unreachable the
engine falls back to our deterministic rules text — the structured contract
never changes.

Set `FANSIVIBE_OLLAMA_HOST` (default `http://localhost:11434`) and
`FANSIVIBE_OLLAMA_MODEL` (default `llama3.1:8b`).
"""

from __future__ import annotations

import os
from typing import Optional

import httpx

_HOST = os.environ.get("FANSIVIBE_OLLAMA_HOST", "http://localhost:11434")
_MODEL = os.environ.get("FANSIVIBE_OLLAMA_MODEL", "llama3.1:8b")
_TIMEOUT = 8.0


def _system_prompt() -> str:
    return (
        "You are Fansivibe's style assistant. Be warm, specific and respectful. "
        "Never judge appearance. Reply in 2-3 short sentences, personalized to "
        "the user's wardrobe and face data when provided. Do not use markdown."
    )


def is_available() -> bool:
    if os.environ.get("FANSIVIBE_DISABLE_LLM") == "1":
        return False
    try:
        with httpx.Client(timeout=1.5) as client:
            return client.get(f"{_HOST}/api/tags").status_code == 200
    except Exception:
        return False


def enrich_reply(intent: str, base_text: str, context: str) -> str:
    """Return a personalized reply from the local model, or [base_text] on any failure."""
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.post(
                f"{_HOST}/api/chat",
                json={
                    "model": _MODEL,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "system", "content": f"User context:\n{context}"},
                        {"role": "user", "content": base_text},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
            return (payload.get("message") or {}).get("content", "").strip() or base_text
    except Exception:
        return base_text
