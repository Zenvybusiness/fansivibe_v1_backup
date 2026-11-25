"""Centralized Pillow safety configuration (startup-only).

Configures process-wide Pillow decompression-bomb and truncated-image guards
once at application startup so concurrent request/worker threads never mutate
global ``PIL.Image.MAX_IMAGE_PIXELS`` or ``PIL.ImageFile.LOAD_TRUNCATED_IMAGES``.
"""

from __future__ import annotations

import warnings

from PIL import Image, ImageFile

MAX_PERSON_IMAGE_PIXELS: int = 12_000_000
MAX_OUTPUT_IMAGE_PIXELS: int = 16_777_216
MAX_PILLOW_IMAGE_PIXELS: int = MAX_OUTPUT_IMAGE_PIXELS


def configure_pillow_limits(*, max_image_pixels: int = MAX_PILLOW_IMAGE_PIXELS) -> int:
    """Configure Pillow global safety limits once at application startup."""
    Image.MAX_IMAGE_PIXELS = max_image_pixels
    ImageFile.LOAD_TRUNCATED_IMAGES = False
    warnings.filterwarnings("error", category=Image.DecompressionBombWarning)
    return max_image_pixels

