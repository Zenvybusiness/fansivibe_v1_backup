"""Application settings (leaf module — no imports from ``app.*``)."""

from app.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
