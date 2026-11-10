"""Model Adapters for AI Model Resource Manager.

Provides hardware, daemon, and framework adapters for shared AI model management.
"""

from app.ai.manager.adapters.ollama_adapter import (
    OllamaAdapterError,
    OllamaConnectionError,
    OllamaLoadedModel,
    OllamaModelAdapter,
    OllamaModelNotFoundError,
    OllamaModelResidency,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnloadError,
    OllamaUnloadResult,
    OllamaUnloadTimeoutError,
)

__all__ = [
    "OllamaModelAdapter",
    "OllamaLoadedModel",
    "OllamaModelResidency",
    "OllamaUnloadResult",
    "OllamaAdapterError",
    "OllamaConnectionError",
    "OllamaTimeoutError",
    "OllamaResponseError",
    "OllamaModelNotFoundError",
    "OllamaUnloadError",
    "OllamaUnloadTimeoutError",
]

