"""Garment extraction image processing, private crop storage, explicit save, and cleanup (P5.1).

Reuses the existing Fansivibe infrastructure:
- Pillow safety bounds (`MAX_INPUT_PIXELS = 12_000_000`, `MAX_INPUT_EDGE = 4096`, EXIF transpose, metadata strip)
- `ObjectStoragePort` for private user-scoped temporary extraction crops and canonical wardrobe media
- `MediaUploadAuthorization` + `AddWardrobeItem` (`validate_media_association`) for PostgreSQL persistence
- Explicit user confirmation before any wardrobe item is saved
- Cleanup of temporary extraction assets on save, cancel/discard, and retention expiration
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import logging
import re
import threading
import time
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4
import warnings

from PIL import Image, ImageFile, ImageOps
from sqlalchemy import and_, case, or_, select, text
from sqlalchemy.orm import Session

from app.api.errors import ApiError, conflict, not_found, validation
from app.application.wardrobe import AddWardrobeItem
from app.domain.ports.repositories import (
    AnalysisRunRecord,
    AnalysisRunRepository,
    LearningSignalRepository,
    WardrobeItemRecord,
    WardrobeItemRepository,
)
from app.domain.ports.storage import (
    ObjectStoragePort,
    StorageError,
    StorageNotFoundError,
    validate_scoped_object_key,
)
from app.infrastructure.db.models import AnalysisRuns, MediaUploadAuthorization, WardrobeItems

logger = logging.getLogger("fansivibe.garment_extraction")

ALLOWED_EXTRACTION_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_EXTRACTION_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB
MAX_INPUT_PIXELS = 12_000_000
MAX_INPUT_EDGE = 4096
VLM_MAX_EDGE = 1920
CROP_MAX_EDGE = 1280
MAX_CROP_BYTES = 2 * 1024 * 1024  # 2 MB canonical WebP ceiling

_CANONICAL_CATEGORIES = frozenset(
    {"tops", "bottoms", "outerwear", "footwear", "accessories"}
)

_CANONICAL_COLORS = frozenset({
    "black", "white", "navy", "charcoal", "grey", "beige", "burgundy",
    "olive", "khaki", "cream", "light_blue", "blush", "tan", "silver",
    "gold", "indigo", "stone",
})

_COLOR_ALIASES = {
    "blue": "navy",
    "dark blue": "navy",
    "dark_blue": "navy",
    "navy blue": "navy",
    "navy_blue": "navy",
    "light blue": "light_blue",
    "sky blue": "light_blue",
    "sky_blue": "light_blue",
    "baby blue": "light_blue",
    "baby_blue": "light_blue",
    "gray": "grey",
    "grey": "grey",
    "dark grey": "charcoal",
    "dark_grey": "charcoal",
    "dark gray": "charcoal",
    "dark_gray": "charcoal",
    "charcoal grey": "charcoal",
    "charcoal_grey": "charcoal",
    "charcoal gray": "charcoal",
    "charcoal_gray": "charcoal",
    "brown": "tan",
    "dark brown": "tan",
    "dark_brown": "tan",
    "red": "burgundy",
    "maroon": "burgundy",
    "wine": "burgundy",
    "green": "olive",
    "dark green": "olive",
    "dark_green": "olive",
    "olive green": "olive",
    "olive_green": "olive",
    "emerald": "olive",
    "pink": "blush",
    "yellow": "cream",
    "purple": "indigo",
    "sand": "beige",
    "camel": "beige",
    "off-white": "cream",
    "off white": "cream",
    "off_white": "cream",
    "ivory": "cream",
}

_CANONICAL_MATERIALS = frozenset({
    "cotton", "linen", "wool", "cashmere", "silk", "denim", "leather",
    "suede", "canvas", "polyester", "velvet", "knit", "jersey", "tweed",
    "corduroy", "fleece",
})

_MATERIAL_ALIASES = {
    "nylon": "polyester",
    "spandex": "polyester",
    "elastane": "polyester",
    "synthetic": "polyester",
    "acrylic": "polyester",
    "viscose": "silk",
    "rayon": "silk",
    "chambray": "cotton",
    "flannel": "cotton",
    "satin": "silk",
    "shearling": "leather",
    "faux leather": "leather",
    "faux_leather": "leather",
    "vegan leather": "leather",
    "vegan_leather": "leather",
    "merino wool": "wool",
    "merino_wool": "wool",
    "pique cotton": "cotton",
    "pique_cotton": "cotton",
}

_SEGMENTATION_UNSUPPORTED = {
    "supported": False,
    "type": "none",
    "reason": (
        "Local VLM (qwen3-vl:4b-instruct) provides 2D bounding-box localization only; "
        "pixel-level segmentation masks are not supported."
    ),
}

MAX_SAVE_BATCH_CACHE_ENTRIES = 1024
SAVE_BATCH_CACHE_TTL_SECONDS = 24 * 3600
MAX_DB_SAVE_BATCHES_PER_RUN = 20


class _BoundedSaveBatchCache:
    """Thread-safe, bounded, TTL-expiring LRU cache for in-memory save batch idempotency.

    - Enforces `max_entries` capacity via LRU eviction.
    - Expires entries after `ttl_seconds` (checked on read/write).
    - Never evicts entries currently marked `in_progress`.
    """

    def __init__(
        self,
        *,
        max_entries: int = MAX_SAVE_BATCH_CACHE_ENTRIES,
        ttl_seconds: float = SAVE_BATCH_CACHE_TTL_SECONDS,
    ) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._lock = threading.Lock()
        self._entries: OrderedDict[tuple[UUID, UUID, str], tuple[float, dict[str, Any]]] = OrderedDict()
        self._in_progress: set[tuple[UUID, UUID, str]] = set()

    def _prune_expired_locked(self, now_mono: float) -> None:
        if self.ttl_seconds <= 0:
            expired = [k for k in self._entries if k not in self._in_progress]
            for k in expired:
                self._entries.pop(k, None)
            return
        cutoff = now_mono - self.ttl_seconds
        expired = [
            k
            for k, (ts, _) in self._entries.items()
            if ts <= cutoff and k not in self._in_progress
        ]
        for k in expired:
            self._entries.pop(k, None)

    def _evict_if_needed_locked(self) -> None:
        if len(self._entries) < self.max_entries:
            return
        # Evict oldest non-in-progress entries until below capacity.
        for k in list(self._entries.keys()):
            if len(self._entries) < self.max_entries:
                break
            if k not in self._in_progress:
                self._entries.pop(k, None)

    def mark_in_progress(self, key: tuple[UUID, UUID, str]) -> None:
        with self._lock:
            self._in_progress.add(key)

    def clear_in_progress(self, key: tuple[UUID, UUID, str]) -> None:
        with self._lock:
            self._in_progress.discard(key)

    def is_in_progress(self, key: tuple[UUID, UUID, str]) -> bool:
        with self._lock:
            return key in self._in_progress

    def get(self, key: tuple[UUID, UUID, str], default: Any = None) -> Any:
        now_mono = time.monotonic()
        with self._lock:
            self._prune_expired_locked(now_mono)
            item = self._entries.get(key)
            if item is None:
                return default
            self._entries.move_to_end(key)
            return item[1]

    def __getitem__(self, key: tuple[UUID, UUID, str]) -> dict[str, Any]:
        val = self.get(key, None)
        if val is None:
            raise KeyError(key)
        return val

    def __setitem__(self, key: tuple[UUID, UUID, str], value: dict[str, Any]) -> None:
        now_mono = time.monotonic()
        with self._lock:
            self._prune_expired_locked(now_mono)
            if key in self._entries:
                self._entries.move_to_end(key)
            else:
                self._evict_if_needed_locked()
            self._entries[key] = (now_mono, value)

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, tuple) or len(key) != 3:
            return False
        return self.get(key, None) is not None  # type: ignore[arg-type]

    def __len__(self) -> int:
        now_mono = time.monotonic()
        with self._lock:
            self._prune_expired_locked(now_mono)
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._in_progress.clear()

    def pop(self, key: tuple[UUID, UUID, str], default: Any = None) -> Any:
        with self._lock:
            item = self._entries.pop(key, None)
            self._in_progress.discard(key)
            return item[1] if item is not None else default

    def keys(self) -> list[tuple[UUID, UUID, str]]:
        now_mono = time.monotonic()
        with self._lock:
            self._prune_expired_locked(now_mono)
            return list(self._entries.keys())


# In-process idempotency cache used when SQL session `db` is absent (pure unit tests).
# Bounded (LRU + 24h TTL) and never evicts in-progress operations.
_IN_MEMORY_SAVE_BATCHES = _BoundedSaveBatchCache()

_SAVE_RUN_LOCKS_GUARD = threading.Lock()
_SAVE_RUN_LOCKS: dict[tuple[int, UUID, UUID], tuple[asyncio.Lock, int]] = {}


@asynccontextmanager
async def _acquire_save_run_lock(
    *,
    user_id: UUID,
    run_id: UUID,
    db: Session | None,
) -> AsyncIterator[None]:
    """Serialize concurrent save requests for the same (user_id, run_id).

    Uses an in-process per-loop asyncio.Lock plus a PostgreSQL session advisory
    lock when backed by PostgreSQL so concurrent requests cannot duplicate saves.
    """
    loop_id = id(asyncio.get_running_loop())
    lock_key = (loop_id, user_id, run_id)
    with _SAVE_RUN_LOCKS_GUARD:
        entry = _SAVE_RUN_LOCKS.get(lock_key)
        if entry is None:
            async_lock = asyncio.Lock()
            _SAVE_RUN_LOCKS[lock_key] = (async_lock, 1)
        else:
            async_lock, waiters = entry
            _SAVE_RUN_LOCKS[lock_key] = (async_lock, waiters + 1)

    pg_lock_name: str | None = None
    try:
        async with async_lock:
            if db is not None:
                try:
                    bind = db.get_bind()
                    if bind is not None and bind.dialect.name == "postgresql":
                        pg_lock_name = f"garment_save:{user_id}:{run_id}"
                        db.execute(
                            text("SELECT pg_advisory_lock(hashtext(:k))"),
                            {"k": pg_lock_name},
                        )
                except Exception:
                    pg_lock_name = None
            try:
                yield
            finally:
                if pg_lock_name is not None and db is not None:
                    try:
                        db.execute(
                            text("SELECT pg_advisory_unlock(hashtext(:k))"),
                            {"k": pg_lock_name},
                        )
                    except Exception:
                        pass
    finally:
        with _SAVE_RUN_LOCKS_GUARD:
            cur = _SAVE_RUN_LOCKS.get(lock_key)
            if cur is not None:
                _, waiters = cur
                if waiters <= 1:
                    _SAVE_RUN_LOCKS.pop(lock_key, None)
                else:
                    _SAVE_RUN_LOCKS[lock_key] = (cur[0], waiters - 1)


class GarmentImageValidationError(Exception):
    """Raised when an uploaded garment extraction image fails validation."""

    def __init__(
        self,
        message: str,
        *,
        reason: str = "invalid_image",
        is_signature_error: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
        self.is_signature_error = is_signature_error


class CropExtractionError(Exception):
    """Raised when a single candidate crop cannot be extracted."""


@dataclass(frozen=True)
class ValidatedGarmentImage:
    """Validated, EXIF-normalized, metadata-stripped garment image."""

    pil_image: Image.Image
    vlm_bytes: bytes
    original_format: str
    width: int
    height: int


@dataclass(frozen=True)
class CroppedGarmentAsset:
    """Cropped WebP bytes and metadata for one extracted garment candidate."""

    webp_bytes: bytes
    sha256: str
    size_bytes: int
    width: int
    height: int
    crop_box_px: tuple[int, int, int, int]


def detect_magic_mime(raw_bytes: bytes) -> str | None:
    """Detect real image MIME type from magic bytes."""
    if len(raw_bytes) < 12:
        return None
    if raw_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_and_normalize_garment_image(
    raw_bytes: bytes,
    content_type: str | None,
) -> ValidatedGarmentImage:
    """Validate uploaded bytes, verify signature/bounds, transpose EXIF, and strip metadata."""
    if not raw_bytes:
        raise GarmentImageValidationError(
            "Image payload is empty.",
            reason="invalid_image",
            is_signature_error=True,
        )
    if len(raw_bytes) > MAX_EXTRACTION_IMAGE_BYTES:
        raise GarmentImageValidationError(
            f"Image too large ({len(raw_bytes)} bytes), max 20 MB.",
            reason="oversized_image",
            is_signature_error=True,
        )
    if content_type not in ALLOWED_EXTRACTION_MIME_TYPES:
        raise GarmentImageValidationError(
            "Unsupported media type, must be JPEG, PNG or WebP.",
            reason="unsupported_format",
            is_signature_error=True,
        )

    detected_mime = detect_magic_mime(raw_bytes)
    if detected_mime is None or detected_mime != content_type:
        raise GarmentImageValidationError(
            "Image file signature is invalid or does not match declared media type.",
            reason="invalid_image",
            is_signature_error=True,
        )

    prev_max = Image.MAX_IMAGE_PIXELS
    prev_trunc = ImageFile.LOAD_TRUNCATED_IMAGES
    try:
        Image.MAX_IMAGE_PIXELS = MAX_INPUT_PIXELS
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw_bytes)) as img:
                fmt = (img.format or "").upper()
                expected_fmt = {
                    "image/jpeg": "JPEG",
                    "image/png": "PNG",
                    "image/webp": "WEBP",
                }[content_type]
                if fmt != expected_fmt:
                    raise GarmentImageValidationError(
                        f"Decoded format {fmt or 'unknown'} does not match {content_type}.",
                        reason="invalid_image",
                    )
                w, h = img.size
                if w <= 0 or h <= 0:
                    raise GarmentImageValidationError(
                        "Image has invalid zero dimensions.",
                        reason="invalid_image",
                    )
                if w * h > MAX_INPUT_PIXELS or w > MAX_INPUT_EDGE or h > MAX_INPUT_EDGE:
                    raise GarmentImageValidationError(
                        f"Image dimensions {w}x{h} exceed safety bounds (12MP, 4096px).",
                        reason="oversized_image",
                    )
                img.load()
                try:
                    transposed = ImageOps.exif_transpose(img)
                except Exception:
                    transposed = img.copy()

                if transposed.mode in ("RGBA", "LA") or (
                    transposed.mode == "P" and "transparency" in transposed.info
                ):
                    normalized = transposed.convert("RGBA")
                else:
                    normalized = transposed.convert("RGB")
                normalized.info = {}

                vlm_img = normalized.copy()
                if max(vlm_img.size) > VLM_MAX_EDGE:
                    vlm_img.thumbnail((VLM_MAX_EDGE, VLM_MAX_EDGE), Image.Resampling.LANCZOS)

                vlm_buf = io.BytesIO()
                if vlm_img.mode == "RGBA":
                    # Composite on neutral background for VLM consistency
                    bg = Image.new("RGB", vlm_img.size, (245, 245, 245))
                    bg.paste(vlm_img, mask=vlm_img.split()[3])
                    bg.save(vlm_buf, format="JPEG", quality=88)
                else:
                    vlm_img.save(vlm_buf, format="JPEG", quality=88)

                return ValidatedGarmentImage(
                    pil_image=normalized,
                    vlm_bytes=vlm_buf.getvalue(),
                    original_format=fmt,
                    width=normalized.size[0],
                    height=normalized.size[1],
                )
    except GarmentImageValidationError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise GarmentImageValidationError(
            f"Image rejected by decompression-bomb guard: {exc}",
            reason="oversized_image",
        ) from exc
    except Exception as exc:
        raise GarmentImageValidationError(
            "Image could not be decoded as a valid JPEG, PNG, or WebP.",
            reason="invalid_image",
        ) from exc
    finally:
        Image.MAX_IMAGE_PIXELS = prev_max
        ImageFile.LOAD_TRUNCATED_IMAGES = prev_trunc


def crop_garment_candidate(
    pil_image: Image.Image,
    bounding_box: dict[str, Any],
    *,
    max_edge: int = CROP_MAX_EDGE,
    padding_ratio: float = 0.04,
) -> CroppedGarmentAsset:
    """Crop one candidate garment from the validated upright image and encode to WebP."""
    if not isinstance(bounding_box, dict):
        raise CropExtractionError("Missing bounding box")
    try:
        x1_n = float(bounding_box["x1"])
        y1_n = float(bounding_box["y1"])
        x2_n = float(bounding_box["x2"])
        y2_n = float(bounding_box["y2"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CropExtractionError("Invalid bounding box coordinates") from exc

    if x2_n <= x1_n or y2_n <= y1_n:
        raise CropExtractionError("Degenerate bounding box")

    img_w, img_h = pil_image.size
    if img_w <= 0 or img_h <= 0:
        raise CropExtractionError("Empty image")

    box_w = x2_n - x1_n
    box_h = y2_n - y1_n
    pad_x = box_w * padding_ratio
    pad_y = box_h * padding_ratio

    px1 = max(0, int(round((x1_n - pad_x) * img_w)))
    py1 = max(0, int(round((y1_n - pad_y) * img_h)))
    px2 = min(img_w, int(round((x2_n + pad_x) * img_w)))
    py2 = min(img_h, int(round((y2_n + pad_y) * img_h)))

    if px2 - px1 < 4 or py2 - py1 < 4:
        raise CropExtractionError("Crop dimensions too small")

    cropped = pil_image.crop((px1, py1, px2, py2))
    cropped.info = {}
    if max(cropped.size) > max_edge:
        cropped.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

    encoded: bytes | None = None
    for q in (85, 80, 75, 65):
        buf = io.BytesIO()
        cropped.save(buf, format="WEBP", quality=q, method=4)
        cand = buf.getvalue()
        if len(cand) <= MAX_CROP_BYTES:
            encoded = cand
            break

    if encoded is None:
        raise CropExtractionError("Cropped WebP exceeds 2MB ceiling")

    return CroppedGarmentAsset(
        webp_bytes=encoded,
        sha256=hashlib.sha256(encoded).hexdigest(),
        size_bytes=len(encoded),
        width=cropped.size[0],
        height=cropped.size[1],
        crop_box_px=(px1, py1, px2, py2),
    )


def _safe_candidate_id(raw_id: str, fallback_idx: int) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", (raw_id or "").strip())[:48]
    return cleaned or f"cand_{fallback_idx + 1}"


def extraction_prefix(user_id: UUID, run_id: UUID) -> str:
    return f"users/{user_id}/extractions/{run_id}/"


def candidate_crop_object_key(user_id: UUID, run_id: UUID, candidate_id: str) -> str:
    key = f"{extraction_prefix(user_id, run_id)}candidates/{candidate_id}.webp"
    validate_scoped_object_key(key, user_id=str(user_id))
    return key


def prepare_candidate_crops(
    pil_image: Image.Image,
    snapshot: dict[str, Any],
    *,
    run_id: UUID,
    user_id: UUID,
) -> tuple[dict[str, Any], list[tuple[str, str, bytes, dict[str, str]]]]:
    """Crop every candidate with a valid bounding box into WebP bytes for private storage."""
    out = dict(snapshot)
    raw_cands = out.get("candidates") or []
    partial_failures = list(out.get("partial_failures") or [])
    new_candidates: list[dict[str, Any]] = []
    crop_blobs: list[tuple[str, str, bytes, dict[str, str]]] = []
    used_ids: set[str] = set()

    for idx, raw_c in enumerate(raw_cands):
        cand = dict(raw_c)
        base_id = _safe_candidate_id(str(cand.get("id") or f"cand_{idx + 1}"), idx)
        cand_id = base_id
        suffix = 2
        while cand_id in used_ids:
            cand_id = f"{base_id}_{suffix}"
            suffix += 1
        used_ids.add(cand_id)
        cand["id"] = cand_id
        cand["has_segmentation_mask"] = False
        cand["mask"] = None
        cand.setdefault("segmentation", dict(_SEGMENTATION_UNSUPPORTED))

        bbox = cand.get("bounding_box")
        if isinstance(bbox, dict):
            try:
                asset = crop_garment_candidate(pil_image, bbox)
                key = candidate_crop_object_key(user_id, run_id, cand_id)
                cand["extraction_method"] = "vlm_bounding_box_crop"
                cand["has_crop"] = True
                cand["crop_key"] = key
                cand["crop_url"] = f"/v1/analysis/runs/{run_id}/candidates/{cand_id}/image"
                cand["crop_width"] = asset.width
                cand["crop_height"] = asset.height
                cand["crop_size_bytes"] = asset.size_bytes
                cand["crop_sha256"] = asset.sha256
                cand["crop_error"] = None
                crop_blobs.append((
                    cand_id,
                    key,
                    asset.webp_bytes,
                    {
                        "user_id": str(user_id),
                        "run_id": str(run_id),
                        "candidate_id": cand_id,
                        "sha256": asset.sha256,
                        "width": str(asset.width),
                        "height": str(asset.height),
                    },
                ))
            except CropExtractionError as exc:
                cand["extraction_method"] = "vlm_attribute_only"
                cand["has_crop"] = False
                cand["crop_key"] = None
                cand["crop_url"] = None
                cand["crop_error"] = str(exc)
                partial_failures.append({
                    "candidate_id": cand_id,
                    "reason": "crop_extraction_failed",
                })
        else:
            cand["extraction_method"] = "vlm_attribute_only"
            cand["has_crop"] = False
            cand["crop_key"] = None
            cand["crop_url"] = None
            cand["crop_error"] = None

        new_candidates.append(cand)

    out["candidates"] = new_candidates
    out["partial_failures"] = partial_failures
    out["has_segmentation_mask"] = False
    out["mask"] = None
    out.setdefault("segmentation", dict(_SEGMENTATION_UNSUPPORTED))
    return out, crop_blobs


async def persist_extraction_crops(
    storage: ObjectStoragePort,
    snapshot: dict[str, Any],
    crop_blobs: list[tuple[str, str, bytes, dict[str, str]]],
) -> dict[str, Any]:
    """Upload cropped candidate WebP assets to private storage (tolerant of per-item failures)."""
    if not crop_blobs:
        return snapshot

    failed_ids: set[str] = set()
    for cand_id, key, data, meta in crop_blobs:
        try:
            await storage.put_object(
                key=key,
                data=data,
                content_type="image/webp",
                custom_metadata=meta,
            )
        except StorageError as exc:
            logger.warning(
                "Failed to store extraction crop for candidate %s: %s",
                cand_id,
                exc.message,
            )
            failed_ids.add(cand_id)

    if not failed_ids:
        return snapshot

    out = dict(snapshot)
    partial_failures = list(out.get("partial_failures") or [])
    updated_cands = []
    for cand in out.get("candidates") or []:
        c = dict(cand)
        if c.get("id") in failed_ids:
            c["has_crop"] = False
            c["crop_key"] = None
            c["crop_url"] = None
            c["crop_error"] = "storage_upload_failed"
            partial_failures.append({
                "candidate_id": c["id"],
                "reason": "storage_upload_failed",
            })
        updated_cands.append(c)
    out["candidates"] = updated_cands
    out["partial_failures"] = partial_failures
    return out


def normalize_wardrobe_vocab(
    *,
    category: str,
    color: str,
    material: str | None,
) -> tuple[str, str, str | None]:
    """Map user-confirmed or AI-suggested attributes onto canonical PostgreSQL vocab codes."""
    cat_clean = category.strip().lower().replace(" ", "_")
    if cat_clean == "shoes":
        cat_clean = "footwear"
    elif cat_clean == "layers":
        cat_clean = "outerwear"

    color_raw = color.strip().lower()
    color_clean = color_raw.replace(" ", "_")
    if color_raw in _CANONICAL_COLORS:
        norm_color = color_raw
    elif color_clean in _CANONICAL_COLORS:
        norm_color = color_clean
    elif color_raw in _COLOR_ALIASES:
        norm_color = _COLOR_ALIASES[color_raw]
    elif color_clean in _COLOR_ALIASES:
        norm_color = _COLOR_ALIASES[color_clean]
    else:
        norm_color = color_clean

    norm_material: str | None = None
    if material is not None:
        mat_raw = material.strip().lower()
        if mat_raw:
            mat_clean = mat_raw.replace(" ", "_")
            if mat_raw in _CANONICAL_MATERIALS:
                norm_material = mat_raw
            elif mat_clean in _CANONICAL_MATERIALS:
                norm_material = mat_clean
            elif mat_raw in _MATERIAL_ALIASES:
                norm_material = _MATERIAL_ALIASES[mat_raw]
            elif mat_clean in _MATERIAL_ALIASES:
                norm_material = _MATERIAL_ALIASES[mat_clean]
            else:
                norm_material = mat_clean

    return cat_clean, norm_color, norm_material


def _get_canonical_wardrobe_crop_key(user_id: UUID, upload_id: UUID) -> str:
    return f"users/{user_id}/wardrobe/{upload_id}/canonical.webp"


@dataclass(frozen=True)
class ExtractionAssetDeleteResult:
    """Detailed result of deleting temporary extraction assets for a run."""

    deleted_count: int
    failed_keys: tuple[str, ...] = ()
    list_failed: bool = False

    @property
    def all_succeeded(self) -> bool:
        return not self.list_failed and not self.failed_keys


@dataclass
class ExtractionCleanupSummary:
    """Summary of a bounded expired-extraction cleanup run."""

    runs_claimed: int = 0
    runs_cleaned: int = 0
    runs_failed: int = 0
    assets_deleted: int = 0
    storage_errors: int = 0


def _mark_run_assets_cleaned(
    db: Session | None,
    *,
    user_id: UUID,
    run_id: UUID,
    deleted_count: int,
) -> None:
    if db is None:
        return
    run_row = db.execute(
        select(AnalysisRuns).where(
            AnalysisRuns.id == run_id,
            AnalysisRuns.user_id == user_id,
        )
    ).scalar_one_or_none()
    if run_row is None:
        return
    updated_result = dict(run_row.result) if isinstance(run_row.result, dict) else {}
    updated_result["assets_cleanup"] = {
        "status": "cleaned",
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
        "deleted_count": int(deleted_count),
    }
    run_row.result = updated_result
    db.commit()


async def delete_run_extraction_assets_detailed(
    storage: ObjectStoragePort,
    *,
    user_id: UUID,
    run_id: UUID,
    candidate_ids: set[str] | None = None,
    result_snapshot: dict[str, Any] | None = None,
) -> ExtractionAssetDeleteResult:
    """Delete temporary extraction objects under `users/{user_id}/extractions/{run_id}/`.

    One failing object never aborts deletion of unrelated objects in the same run.
    Returns `ExtractionAssetDeleteResult` so callers know whether any listing or
    deletion failed and can keep failed runs retryable.
    """
    prefix = extraction_prefix(user_id, run_id)
    keys_to_delete: set[str] = set()
    list_failed = False

    if candidate_ids is None and hasattr(storage, "list_keys"):
        try:
            listed = await storage.list_keys(prefix)  # type: ignore[attr-defined]
            for k in listed:
                validate_scoped_object_key(k, user_id=str(user_id))
                if k.startswith(prefix):
                    keys_to_delete.add(k)
        except Exception as exc:
            list_failed = True
            logger.warning(
                "Failed to list temporary extraction assets under %s: %s", prefix, exc
            )

    if isinstance(result_snapshot, dict):
        for cand in result_snapshot.get("candidates") or []:
            if not isinstance(cand, dict):
                continue
            cid = cand.get("id")
            if candidate_ids is not None and cid not in candidate_ids:
                continue
            ckey = cand.get("crop_key")
            if isinstance(ckey, str) and ckey.startswith(prefix):
                validate_scoped_object_key(ckey, user_id=str(user_id))
                keys_to_delete.add(ckey)

    deleted = 0
    failed_keys: list[str] = []
    for key in sorted(keys_to_delete):
        try:
            if await storage.object_exists(key):
                await storage.delete_object(key)
                deleted += 1
            else:
                await storage.delete_object(key)
        except Exception as exc:
            failed_keys.append(key)
            logger.warning("Failed to delete temporary extraction asset %s: %s", key, exc)

    return ExtractionAssetDeleteResult(
        deleted_count=deleted,
        failed_keys=tuple(failed_keys),
        list_failed=list_failed,
    )


async def delete_run_extraction_assets(
    storage: ObjectStoragePort,
    *,
    user_id: UUID,
    run_id: UUID,
    candidate_ids: set[str] | None = None,
    result_snapshot: dict[str, Any] | None = None,
) -> int:
    """Delete temporary extraction objects under `users/{user_id}/extractions/{run_id}/`."""
    res = await delete_run_extraction_assets_detailed(
        storage,
        user_id=user_id,
        run_id=run_id,
        candidate_ids=candidate_ids,
        result_snapshot=result_snapshot,
    )
    return res.deleted_count


class SaveExtractedGarments:
    """Explicitly save user-selected candidates from a garment run to Digital Wardrobe.

    Guarantees:
    - Owner-scoped lookup on the extraction run (`404` for missing/foreign).
    - Promotes each selected candidate's crop to private canonical wardrobe storage
      + published `MediaUploadAuthorization` record so `AddWardrobeItem` validates it.
    - Prevents duplicate item creation on idempotent retry or repeated confirmation.
    - Handles partial save failures truthfully without dropping successful saves.
    - Cleans up temporary extraction crops after promotion.
    """

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        wardrobe: WardrobeItemRepository,
        storage: ObjectStoragePort,
        signals: LearningSignalRepository | None = None,
        db: Session | None = None,
    ) -> None:
        self._runs = runs
        self._wardrobe = wardrobe
        self._storage = storage
        self._signals = signals
        self._db = db

    @staticmethod
    def _normalize_confidence(raw: Any) -> float | None:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        val = float(raw)
        if 0.0 <= val <= 1.0:
            return val
        return None

    @classmethod
    def _resolve_extraction_confidence(
        cls, sel: dict[str, Any], candidate: dict[str, Any]
    ) -> float | None:
        explicit = cls._normalize_confidence(sel.get("extractionConfidence"))
        if explicit is not None:
            return explicit
        return cls._normalize_confidence(candidate.get("confidence"))

    @classmethod
    def _batch_fingerprint(cls, items: list[dict[str, Any]]) -> str:
        canonical = [
            {
                "candidateId": str(it["candidateId"]).strip(),
                "name": str(it["name"]).strip(),
                "category": str(it["category"]).strip().lower(),
                "color": str(it["color"]).strip().lower(),
                "material": (str(it["material"]).strip().lower() if it.get("material") else None),
                "fit": (str(it["fit"]).strip() if it.get("fit") else None),
                "extractionConfidence": cls._normalize_confidence(it.get("extractionConfidence")),
                "fitConfidence": cls._normalize_confidence(it.get("fitConfidence")),
                "isFavorite": bool(it.get("isFavorite", False)),
            }
            for it in items
        ]
        canonical.sort(key=lambda x: x["candidateId"])
        import json
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _record_from_row(row: WardrobeItems) -> WardrobeItemRecord:
        return WardrobeItemRecord(
            id=row.id,
            user_id=row.user_id,
            name=row.name,
            category=row.category_id,
            color=row.color_id,
            material=row.material_id,
            is_favorite=row.is_favorite,
            image_ref=row.image_ref,
            fit=row.fit,
            fit_confidence=row.fit_confidence,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _find_existing_wardrobe_item_for_candidate(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        candidate_id: str,
        run_result: dict[str, Any] | None = None,
    ) -> WardrobeItemRecord | None:
        if self._db is None:
            try:
                items, _ = self._wardrobe.get_for_user(
                    user_id=user_id,
                    page=1,
                    page_size=100,
                    category=None,
                    color=None,
                    sort="created_at",
                    order="desc",
                )
                for item in items:
                    ref = item.image_ref
                    if (
                        isinstance(ref, dict)
                        and str(ref.get("sourceRunId")) == str(run_id)
                        and str(ref.get("candidateId")) == candidate_id
                    ):
                        return item
            except Exception:
                pass
            return None

        idemp_key = f"extract:{run_id}:{candidate_id}"
        auth = self._db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == user_id,
                MediaUploadAuthorization.idempotency_key == idemp_key,
            )
        ).scalar_one_or_none()
        rows = self._db.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        if auth is not None:
            upload_id_str = str(auth.upload_id)
            for row in rows:
                ref = row.image_ref
                if isinstance(ref, dict) and str(ref.get("uploadId")) == upload_id_str:
                    return self._record_from_row(row)

        for row in rows:
            ref = row.image_ref
            if (
                isinstance(ref, dict)
                and str(ref.get("sourceRunId")) == str(run_id)
                and str(ref.get("candidateId")) == candidate_id
            ):
                return self._record_from_row(row)

        if isinstance(run_result, dict):
            saved_map = run_result.get("saved_candidates")
            if isinstance(saved_map, dict):
                saved_id_raw = saved_map.get(candidate_id)
                if isinstance(saved_id_raw, str):
                    try:
                        saved_uuid = UUID(saved_id_raw)
                        for row in rows:
                            if row.id == saved_uuid:
                                return self._record_from_row(row)
                    except ValueError:
                        pass
        return None

    def _record_saved_candidate_on_run(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        candidate_id: str,
        wardrobe_item_id: UUID,
    ) -> None:
        if self._db is None:
            return
        run_row = self._db.execute(
            select(AnalysisRuns).where(
                AnalysisRuns.id == run_id,
                AnalysisRuns.user_id == user_id,
            )
        ).scalar_one_or_none()
        if run_row is None or not isinstance(run_row.result, dict):
            return
        updated_result = dict(run_row.result)
        saved_map = dict(updated_result.get("saved_candidates") or {})
        saved_map[candidate_id] = str(wardrobe_item_id)
        updated_result["saved_candidates"] = saved_map
        run_row.result = updated_result
        self._db.commit()

    def _is_postgres_db(self) -> bool:
        if self._db is None:
            return False
        try:
            bind = self._db.get_bind()
            return bind is not None and getattr(bind.dialect, "name", "") == "postgresql"
        except Exception:
            return False

    def _persist_failed_promotion_cleanup(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        candidate_id: str,
        upload_id: UUID,
        canonical_key: str,
        staging_key: str,
        size_bytes: int,
        sha256: str,
        width: int,
        height: int,
    ) -> None:
        """Durably record `delete_pending` when promoted object cleanup fails after DB rollback."""
        if self._db is None:
            return
        idemp_key = f"extract:{run_id}:{candidate_id}"
        now = datetime.now(timezone.utc)
        try:
            self._db.rollback()
            stmt = select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == user_id,
                MediaUploadAuthorization.idempotency_key == idemp_key,
            )
            if self._is_postgres_db():
                stmt = stmt.with_for_update()
            auth = self._db.execute(stmt).scalar_one_or_none()
            if auth is not None:
                auth.status = "delete_pending"
                auth.failure_reason = "STORAGE_DELETE_FAILED"
                auth.canonical_key = canonical_key
                auth.canonical_sha256 = sha256
                auth.canonical_size_bytes = size_bytes
                auth.canonical_width = width
                auth.canonical_height = height
                auth.processing_attempts = (auth.processing_attempts or 0) + 1
            else:
                self._db.add(
                    MediaUploadAuthorization(
                        user_id=user_id,
                        idempotency_key=idemp_key,
                        upload_id=upload_id,
                        key_version="kver_extract",
                        request_fingerprint=hashlib.sha256(
                            f"{user_id}:{run_id}:{candidate_id}:{sha256}".encode("utf-8")
                        ).hexdigest(),
                        staging_key=staging_key,
                        content_type="image/webp",
                        size_bytes=size_bytes,
                        created_at=now,
                        expires_at=now + timedelta(hours=24),
                        status="delete_pending",
                        failure_reason="STORAGE_DELETE_FAILED",
                        canonical_key=canonical_key,
                        canonical_sha256=sha256,
                        canonical_size_bytes=size_bytes,
                        canonical_width=width,
                        canonical_height=height,
                        processing_attempts=1,
                        completed_at=None,
                    )
                )
            self._db.commit()
        except Exception:
            try:
                self._db.rollback()
            except Exception:
                pass
            logger.exception(
                "Failed to durably record delete_pending cleanup for %s",
                canonical_key,
            )

    async def _cleanup_promoted_object_after_db_failure(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        candidate_id: str,
        image_ref: dict[str, Any] | None,
        staging_key: str | None = None,
    ) -> None:
        """Delete a promoted storage object after a failed DB save, or durably queue delete_pending."""
        if not image_ref or not isinstance(image_ref.get("objectKey"), str):
            return
        canonical_key = image_ref["objectKey"]
        upload_id_raw = image_ref.get("uploadId")
        try:
            upload_id = UUID(str(upload_id_raw))
        except Exception:
            upload_id = uuid4()

        try:
            await self._storage.delete_object(canonical_key)
        except Exception:
            self._persist_failed_promotion_cleanup(
                user_id=user_id,
                run_id=run_id,
                candidate_id=candidate_id,
                upload_id=upload_id,
                canonical_key=canonical_key,
                staging_key=staging_key or canonical_key,
                size_bytes=int(image_ref.get("sizeBytes") or 1),
                sha256=str(image_ref.get("contentHash") or ("0" * 64)),
                width=int(image_ref.get("width") or 1),
                height=int(image_ref.get("height") or 1),
            )
            return

        if self._db is not None:
            idemp_key = f"extract:{run_id}:{candidate_id}"
            try:
                auth = self._db.execute(
                    select(MediaUploadAuthorization).where(
                        MediaUploadAuthorization.user_id == user_id,
                        MediaUploadAuthorization.idempotency_key == idemp_key,
                    )
                ).scalar_one_or_none()
                if auth is not None and auth.status == "delete_pending":
                    self._db.delete(auth)
                    self._db.commit()
            except Exception:
                try:
                    self._db.rollback()
                except Exception:
                    pass

    async def _promote_crop_to_wardrobe_media(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        candidate: dict[str, Any],
        extraction_confidence: float | None = None,
    ) -> dict[str, Any] | None:
        crop_key = candidate.get("crop_key")
        if not isinstance(crop_key, str) or not crop_key:
            return None

        validate_scoped_object_key(crop_key, user_id=str(user_id))
        try:
            crop_bytes = await self._storage.read_object(crop_key, max_bytes=MAX_CROP_BYTES)
        except StorageNotFoundError:
            return None
        except StorageError as exc:
            raise ApiError(
                status_code=503,
                code="STORAGE_ERROR",
                message=f"Could not read extracted crop from storage: {exc.message}",
            ) from exc

        cand_id = str(candidate["id"])
        cand_sha = hashlib.sha256(crop_bytes).hexdigest()

        width = int(candidate.get("crop_width") or 0)
        height = int(candidate.get("crop_height") or 0)
        if width <= 0 or height <= 0:
            with Image.open(io.BytesIO(crop_bytes)) as img:
                width, height = img.size

        idemp_key = f"extract:{run_id}:{cand_id}"
        existing_auth = None
        if self._db is not None:
            stmt = select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == user_id,
                MediaUploadAuthorization.idempotency_key == idemp_key,
            )
            if self._is_postgres_db():
                stmt = stmt.with_for_update()
            existing_auth = self._db.execute(stmt).scalar_one_or_none()

        upload_id = existing_auth.upload_id if existing_auth is not None else uuid4()
        canonical_key = (
            existing_auth.canonical_key
            if existing_auth is not None and existing_auth.canonical_key
            else _get_canonical_wardrobe_crop_key(user_id, upload_id)
        )
        now = datetime.now(timezone.utc)

        custom_meta = {
            "user_id": str(user_id),
            "upload_id": str(upload_id),
            "source_run_id": str(run_id),
            "candidate_id": cand_id,
            "sha256": cand_sha,
            "width": str(width),
            "height": str(height),
        }
        if extraction_confidence is not None:
            custom_meta["extraction_confidence"] = str(extraction_confidence)

        await self._storage.put_object(
            key=canonical_key,
            data=crop_bytes,
            content_type="image/webp",
            custom_metadata=custom_meta,
        )

        ref: dict[str, Any] = {
            "uploadId": str(upload_id),
            "objectKey": canonical_key,
            "mediaType": "image/webp",
            "width": width,
            "height": height,
            "sizeBytes": len(crop_bytes),
            "contentHash": cand_sha,
            "uploadedAt": now.isoformat(),
            "status": "ready",
            "sourceRunId": str(run_id),
            "candidateId": cand_id,
        }
        if extraction_confidence is not None:
            ref["extractionConfidence"] = extraction_confidence

        if self._db is not None:
            try:
                if existing_auth is None:
                    auth_row = MediaUploadAuthorization(
                        user_id=user_id,
                        idempotency_key=idemp_key,
                        upload_id=upload_id,
                        key_version="kver_extract",
                        request_fingerprint=hashlib.sha256(
                            f"{user_id}:{run_id}:{cand_id}:{cand_sha}".encode("utf-8")
                        ).hexdigest(),
                        staging_key=crop_key,
                        content_type="image/webp",
                        size_bytes=len(crop_bytes),
                        created_at=now,
                        expires_at=now + timedelta(hours=24),
                        status="published",
                        canonical_key=canonical_key,
                        canonical_sha256=cand_sha,
                        canonical_size_bytes=len(crop_bytes),
                        canonical_width=width,
                        canonical_height=height,
                        completed_at=now,
                    )
                    self._db.add(auth_row)
                else:
                    existing_auth.status = "published"
                    existing_auth.failure_reason = None
                    existing_auth.canonical_key = canonical_key
                    existing_auth.canonical_sha256 = cand_sha
                    existing_auth.canonical_size_bytes = len(crop_bytes)
                    existing_auth.canonical_width = width
                    existing_auth.canonical_height = height
                    existing_auth.completed_at = now
                # Flush only (no commit): MediaUploadAuthorization commits atomically
                # with WardrobeItems in AddWardrobeItem.
                self._db.flush()
            except Exception as exc:
                self._db.rollback()
                await self._cleanup_promoted_object_after_db_failure(
                    user_id=user_id,
                    run_id=run_id,
                    candidate_id=cand_id,
                    image_ref=ref,
                    staging_key=crop_key,
                )
                raise ApiError(
                    status_code=500,
                    code="DATABASE_ERROR",
                    message="Failed to prepare media authorization for extracted garment.",
                ) from exc

        return ref

    def _lookup_db_save_batch(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        idempotency_key: str,
        fingerprint: str,
    ) -> dict[str, Any] | None:
        if self._db is None:
            return None
        run_row = self._db.execute(
            select(AnalysisRuns).where(
                AnalysisRuns.id == run_id,
                AnalysisRuns.user_id == user_id,
            )
        ).scalar_one_or_none()
        if run_row is None or not isinstance(run_row.result, dict):
            return None
        batches = run_row.result.get("save_batches")
        if not isinstance(batches, dict):
            return None
        entry = batches.get(idempotency_key)
        if not isinstance(entry, dict):
            return None
        if entry.get("fingerprint") != fingerprint:
            raise conflict("duplicate")
        if entry.get("status") != "completed":
            return None

        saved_item_ids = entry.get("saved_item_ids")
        if not isinstance(saved_item_ids, list):
            return None

        saved_records: list[WardrobeItemRecord] = []
        saved_entries: list[dict[str, Any]] = []
        for item_meta in saved_item_ids:
            if not isinstance(item_meta, dict):
                continue
            cand_id = item_meta.get("candidate_id")
            raw_wid = item_meta.get("wardrobe_item_id")
            if not isinstance(cand_id, str) or not isinstance(raw_wid, str):
                continue
            try:
                wid = UUID(raw_wid)
            except ValueError:
                continue
            row = self._db.execute(
                select(WardrobeItems).where(
                    WardrobeItems.id == wid,
                    WardrobeItems.user_id == user_id,
                )
            ).scalar_one_or_none()
            if row is None:
                continue
            rec = self._record_from_row(row)
            ext_conf = (
                self._normalize_confidence(rec.image_ref.get("extractionConfidence"))
                if isinstance(rec.image_ref, dict)
                else None
            )
            saved_records.append(rec)
            saved_entries.append(
                {
                    "candidate_id": cand_id,
                    "record": rec,
                    "extraction_confidence": ext_conf,
                }
            )

        return {
            "saved_records": saved_records,
            "saved_entries": saved_entries,
            "failed_items": [],
            "cleaned_up_assets": bool(entry.get("cleaned_up_assets", False)),
        }

    def _record_db_save_batch(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        saved_entries: list[dict[str, Any]],
        cleaned_up_assets: bool,
    ) -> None:
        if self._db is None:
            return
        run_row = self._db.execute(
            select(AnalysisRuns).where(
                AnalysisRuns.id == run_id,
                AnalysisRuns.user_id == user_id,
            )
        ).scalar_one_or_none()
        if run_row is None or not isinstance(run_row.result, dict):
            return
        updated_result = dict(run_row.result)
        batches = dict(updated_result.get("save_batches") or {})
        batches[idempotency_key] = {
            "fingerprint": fingerprint,
            "status": "completed",
            "saved_item_ids": [
                {
                    "candidate_id": e["candidate_id"],
                    "wardrobe_item_id": str(e["record"].id),
                }
                for e in saved_entries
            ],
            "cleaned_up_assets": bool(cleaned_up_assets),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        # Bound per-run stored batch keys to prevent unbounded JSONB growth.
        while len(batches) > MAX_DB_SAVE_BATCHES_PER_RUN:
            oldest_key = next(iter(batches))
            if oldest_key == idempotency_key:
                break
            batches.pop(oldest_key, None)
        updated_result["save_batches"] = batches
        run_row.result = updated_result
        self._db.commit()

    async def execute(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        items: list[dict[str, Any]],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        if not items:
            raise validation([{"field": "items", "error": "at least one garment must be selected"}])

        clean_key = idempotency_key.strip() if idempotency_key else None
        fingerprint = self._batch_fingerprint(items)
        cache_key = (user_id, run_id, clean_key) if clean_key else None

        if cache_key is not None:
            _IN_MEMORY_SAVE_BATCHES.mark_in_progress(cache_key)
        try:
            async with _acquire_save_run_lock(user_id=user_id, run_id=run_id, db=self._db):
                record: AnalysisRunRecord | None = self._runs.get_for_user(
                    user_id=user_id, run_id=run_id
                )
                if record is None:
                    raise not_found()
                if record.run_type != "garment":
                    raise validation(
                        [{"field": "run_id", "error": "run is not a garment extraction run"}]
                    )
                if record.status != "completed" or not isinstance(record.result, dict):
                    raise validation(
                        [{"field": "run_id", "error": "garment extraction run is not completed"}]
                    )

                if clean_key:
                    if self._db is not None:
                        db_cached = self._lookup_db_save_batch(
                            user_id=user_id,
                            run_id=run_id,
                            idempotency_key=clean_key,
                            fingerprint=fingerprint,
                        )
                        if db_cached is not None:
                            return db_cached
                    else:
                        cached = _IN_MEMORY_SAVE_BATCHES.get(cache_key)
                        if cached is not None:
                            if cached["fingerprint"] != fingerprint:
                                raise conflict("duplicate")
                            return cached["response"]

                return await self._execute_locked(
                    user_id=user_id,
                    run_id=run_id,
                    record=record,
                    items=items,
                    clean_key=clean_key,
                    fingerprint=fingerprint,
                    cache_key=cache_key,
                )
        finally:
            if cache_key is not None:
                _IN_MEMORY_SAVE_BATCHES.clear_in_progress(cache_key)

    async def _execute_locked(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        record: AnalysisRunRecord,
        items: list[dict[str, Any]],
        clean_key: str | None,
        fingerprint: str,
        cache_key: tuple[UUID, UUID, str] | None,
    ) -> dict[str, Any]:

        candidates_by_id: dict[str, dict[str, Any]] = {}
        for c in record.result.get("candidates") or []:
            if isinstance(c, dict) and c.get("id"):
                candidates_by_id[str(c["id"])] = c

        add_item = AddWardrobeItem(
            wardrobe=self._wardrobe,
            signals=self._signals,
            db=self._db,
        )

        saved_records: list[WardrobeItemRecord] = []
        saved_entries: list[dict[str, Any]] = []
        saved_by_candidate_id: dict[str, dict[str, Any]] = {}
        saved_candidate_ids: set[str] = set()
        failed_items: list[dict[str, str]] = []

        for sel in items:
            cand_id = str(sel["candidateId"]).strip()
            name = str(sel["name"]).strip()
            candidate = candidates_by_id.get(cand_id)
            if candidate is None:
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name or cand_id,
                    "error": f"Unknown candidate '{cand_id}' for run {run_id}",
                })
                continue

            if cand_id in saved_by_candidate_id:
                continue

            extraction_confidence = self._resolve_extraction_confidence(sel, candidate)
            # Fit confidence is distinct from extraction confidence; never fabricate it
            # from candidate/extraction confidence.
            fit_confidence = self._normalize_confidence(sel.get("fitConfidence"))

            existing = self._find_existing_wardrobe_item_for_candidate(
                user_id=user_id,
                run_id=run_id,
                candidate_id=cand_id,
                run_result=record.result,
            )
            if existing is not None:
                existing_ext_conf = (
                    self._normalize_confidence(existing.image_ref.get("extractionConfidence"))
                    if isinstance(existing.image_ref, dict)
                    else None
                )
                entry = {
                    "candidate_id": cand_id,
                    "record": existing,
                    "extraction_confidence": (
                        existing_ext_conf
                        if existing_ext_conf is not None
                        else extraction_confidence
                    ),
                }
                saved_records.append(existing)
                saved_entries.append(entry)
                saved_by_candidate_id[cand_id] = entry
                saved_candidate_ids.add(cand_id)
                continue

            norm_cat, norm_color, norm_material = normalize_wardrobe_vocab(
                category=str(sel["category"]),
                color=str(sel["color"]),
                material=sel.get("material"),
            )

            if norm_cat not in _CANONICAL_CATEGORIES:
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": f"Unsupported wardrobe category '{sel['category']}'",
                })
                continue

            image_ref: dict[str, Any] | None = None
            try:
                image_ref = await self._promote_crop_to_wardrobe_media(
                    user_id=user_id,
                    run_id=run_id,
                    candidate=candidate,
                    extraction_confidence=extraction_confidence,
                )
            except ApiError as exc:
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": exc.message,
                })
                continue

            extraction_meta: dict[str, Any] = {
                "sourceRunId": str(run_id),
                "candidateId": cand_id,
            }
            if extraction_confidence is not None:
                extraction_meta["extractionConfidence"] = extraction_confidence

            item_committed = False
            try:
                created = add_item(
                    user_id=user_id,
                    name=name,
                    category=norm_cat,
                    color=norm_color,
                    material=norm_material,
                    isFavorite=bool(sel.get("isFavorite", False)),
                    image_ref=image_ref,
                    fit=sel.get("fit"),
                    fit_confidence=fit_confidence,
                    extraction_provenance=extraction_meta,
                )
                item_committed = True
            except ApiError as exc:
                if self._db is not None:
                    self._wardrobe.rollback()
                await self._cleanup_promoted_object_after_db_failure(
                    user_id=user_id,
                    run_id=run_id,
                    candidate_id=cand_id,
                    image_ref=image_ref,
                    staging_key=candidate.get("crop_key") if isinstance(candidate.get("crop_key"), str) else None,
                )
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": exc.message,
                })
                continue
            except Exception:
                if self._db is not None:
                    self._wardrobe.rollback()
                await self._cleanup_promoted_object_after_db_failure(
                    user_id=user_id,
                    run_id=run_id,
                    candidate_id=cand_id,
                    image_ref=image_ref,
                    staging_key=candidate.get("crop_key") if isinstance(candidate.get("crop_key"), str) else None,
                )
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": "Failed to save garment to wardrobe.",
                })
                continue

            if item_committed:
                try:
                    self._record_saved_candidate_on_run(
                        user_id=user_id,
                        run_id=run_id,
                        candidate_id=cand_id,
                        wardrobe_item_id=created.id,
                    )
                except Exception:
                    try:
                        if self._db is not None:
                            self._db.rollback()
                    except Exception:
                        pass
                entry = {
                    "candidate_id": cand_id,
                    "record": created,
                    "extraction_confidence": extraction_confidence,
                }
                saved_records.append(created)
                saved_entries.append(entry)
                saved_by_candidate_id[cand_id] = entry
                saved_candidate_ids.add(cand_id)

        # Clean up temporary extraction assets:
        # - If all selected items succeeded, purge all temporary assets for this run (including unselected).
        # - If partial failure occurred, purge only the succeeded candidates' temporary crops so failed ones can be retried.
        cleaned_up_all = False
        if not failed_items and saved_records:
            del_res = await delete_run_extraction_assets_detailed(
                self._storage,
                user_id=user_id,
                run_id=run_id,
                candidate_ids=None,
                result_snapshot=record.result,
            )
            cleaned_up_all = del_res.all_succeeded
            if cleaned_up_all:
                _mark_run_assets_cleaned(
                    self._db,
                    user_id=user_id,
                    run_id=run_id,
                    deleted_count=del_res.deleted_count,
                )
        elif saved_candidate_ids:
            await delete_run_extraction_assets_detailed(
                self._storage,
                user_id=user_id,
                run_id=run_id,
                candidate_ids=saved_candidate_ids,
                result_snapshot=record.result,
            )

        result_payload = {
            "saved_records": saved_records,
            "saved_entries": saved_entries,
            "failed_items": failed_items,
            "cleaned_up_assets": cleaned_up_all,
        }
        if clean_key and not failed_items:
            if self._db is not None:
                self._record_db_save_batch(
                    user_id=user_id,
                    run_id=run_id,
                    idempotency_key=clean_key,
                    fingerprint=fingerprint,
                    saved_entries=saved_entries,
                    cleaned_up_assets=cleaned_up_all,
                )
            elif cache_key is not None:
                _IN_MEMORY_SAVE_BATCHES[cache_key] = {
                    "fingerprint": fingerprint,
                    "response": result_payload,
                }
        return result_payload


class CleanupExtractionAssets:
    """Owner-scoped immediate cleanup of temporary extraction assets for a run."""

    def __init__(
        self,
        *,
        runs: AnalysisRunRepository,
        storage: ObjectStoragePort,
        db: Session | None = None,
    ) -> None:
        self._runs = runs
        self._storage = storage
        self._db = db

    async def execute(self, *, user_id: UUID, run_id: UUID) -> dict[str, Any]:
        record = self._runs.get_for_user(user_id=user_id, run_id=run_id)
        if record is None:
            raise not_found()
        if record.run_type != "garment":
            raise validation([{"field": "run_id", "error": "run is not a garment extraction run"}])

        del_res = await delete_run_extraction_assets_detailed(
            self._storage,
            user_id=user_id,
            run_id=run_id,
            candidate_ids=None,
            result_snapshot=record.result if isinstance(record.result, dict) else None,
        )
        if del_res.all_succeeded:
            _mark_run_assets_cleaned(
                self._db,
                user_id=user_id,
                run_id=run_id,
                deleted_count=del_res.deleted_count,
            )
        return {
            "runId": run_id,
            "deletedCount": del_res.deleted_count,
            "alreadyCleaned": del_res.deleted_count == 0 and del_res.all_succeeded,
        }


def _claim_expired_extraction_runs(
    db: Session,
    *,
    cutoff: datetime,
    now: datetime,
    batch_limit: int,
    lease_seconds: int,
) -> list[tuple[UUID, UUID, str, dict[str, Any] | None]]:
    """Claim a bounded batch of expired garment runs using FOR UPDATE SKIP LOCKED.

    Unattempted/cleaning-expired runs are ordered before previously failed runs so
    persistently failing objects cannot starve newer expired runs, while failed
    runs remain retryable.
    """
    bind = db.get_bind()
    is_pg = bind is not None and bind.dialect.name == "postgresql"

    if is_pg:
        cleanup_obj = AnalysisRuns.result["assets_cleanup"]
        cleanup_status = cleanup_obj["status"].as_string()
        lease_expires = cleanup_obj["lease_expires_at"].as_string()

        eligible_filter = and_(
            AnalysisRuns.run_type == "garment",
            AnalysisRuns.created_at < cutoff,
            or_(
                AnalysisRuns.result.is_(None),
                text("NOT (analysis_runs.result ? 'assets_cleanup')"),
                and_(
                    cleanup_status.is_distinct_from("cleaned"),
                    or_(
                        cleanup_status.is_distinct_from("cleaning"),
                        lease_expires < now.isoformat(),
                    ),
                ),
            ),
        )
        failed_rank = case((cleanup_status == "failed", 1), else_=0)
        stmt = (
            select(AnalysisRuns)
            .where(eligible_filter)
            .order_by(failed_rank.asc(), AnalysisRuns.created_at.asc(), AnalysisRuns.id.asc())
            .limit(batch_limit)
            .with_for_update(skip_locked=True)
        )
        rows = db.execute(stmt).scalars().all()
    else:
        all_rows = db.execute(
            select(AnalysisRuns)
            .where(
                AnalysisRuns.run_type == "garment",
                AnalysisRuns.created_at < cutoff,
            )
            .order_by(AnalysisRuns.created_at.asc(), AnalysisRuns.id.asc())
        ).scalars().all()
        unattempted: list[AnalysisRuns] = []
        failed: list[AnalysisRuns] = []
        for r in all_rows:
            meta = r.result.get("assets_cleanup") if isinstance(r.result, dict) else None
            if not isinstance(meta, dict):
                unattempted.append(r)
                continue
            st = meta.get("status")
            if st == "cleaned":
                continue
            if st == "cleaning":
                exp_raw = meta.get("lease_expires_at")
                if isinstance(exp_raw, str):
                    try:
                        if datetime.fromisoformat(exp_raw) >= now:
                            continue
                    except ValueError:
                        pass
                unattempted.append(r)
            elif st == "failed":
                failed.append(r)
            else:
                unattempted.append(r)
        rows = (unattempted + failed)[:batch_limit]

    claimed: list[tuple[UUID, UUID, str, dict[str, Any] | None]] = []
    lease_until = (now + timedelta(seconds=lease_seconds)).isoformat()
    for row in rows:
        claim_token = str(uuid4())
        updated_result = dict(row.result) if isinstance(row.result, dict) else {}
        prev_meta = updated_result.get("assets_cleanup")
        prev_attempts = int(prev_meta.get("attempts", 0)) if isinstance(prev_meta, dict) else 0
        snapshot = dict(row.result) if isinstance(row.result, dict) else None
        updated_result["assets_cleanup"] = {
            "status": "cleaning",
            "claim_token": claim_token,
            "lease_expires_at": lease_until,
            "attempts": prev_attempts + 1,
        }
        row.result = updated_result
        claimed.append((row.id, row.user_id, claim_token, snapshot))

    db.commit()
    return claimed


def _finalize_extraction_run_cleanup(
    db: Session,
    *,
    run_id: UUID,
    claim_token: str,
    del_res: ExtractionAssetDeleteResult,
    now: datetime,
) -> None:
    bind = db.get_bind()
    is_pg = bind is not None and bind.dialect.name == "postgresql"
    stmt = select(AnalysisRuns).where(AnalysisRuns.id == run_id)
    if is_pg:
        stmt = stmt.with_for_update()
    row = db.execute(stmt).scalar_one_or_none()
    if row is None or not isinstance(row.result, dict):
        return
    meta = row.result.get("assets_cleanup")
    if not isinstance(meta, dict) or meta.get("claim_token") != claim_token:
        # Lease was reclaimed by another worker; do not overwrite its state.
        return

    updated_result = dict(row.result)
    attempts = int(meta.get("attempts", 1))
    if del_res.all_succeeded:
        updated_result["assets_cleanup"] = {
            "status": "cleaned",
            "cleaned_at": now.isoformat(),
            "deleted_count": int(del_res.deleted_count),
            "attempts": attempts,
        }
    else:
        updated_result["assets_cleanup"] = {
            "status": "failed",
            "last_error_at": now.isoformat(),
            "failed_keys_count": len(del_res.failed_keys),
            "list_failed": del_res.list_failed,
            "attempts": attempts,
        }
    row.result = updated_result
    db.commit()


async def cleanup_expired_extraction_assets_detailed(
    storage: ObjectStoragePort,
    db: Session,
    *,
    older_than_hours: int = 24,
    batch_limit: int = 200,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> ExtractionCleanupSummary:
    """Claim and delete temporary extraction assets for expired garment runs in bounded batches."""
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time - timedelta(hours=older_than_hours)
    summary = ExtractionCleanupSummary()

    claimed = _claim_expired_extraction_runs(
        db,
        cutoff=cutoff,
        now=current_time,
        batch_limit=max(1, int(batch_limit)),
        lease_seconds=max(1, int(lease_seconds)),
    )
    summary.runs_claimed = len(claimed)

    for run_id, user_id, claim_token, snapshot in claimed:
        del_res = await delete_run_extraction_assets_detailed(
            storage,
            user_id=user_id,
            run_id=run_id,
            candidate_ids=None,
            result_snapshot=snapshot,
        )
        summary.assets_deleted += del_res.deleted_count
        summary.storage_errors += len(del_res.failed_keys) + (1 if del_res.list_failed else 0)
        if del_res.all_succeeded:
            summary.runs_cleaned += 1
        else:
            summary.runs_failed += 1
        _finalize_extraction_run_cleanup(
            db,
            run_id=run_id,
            claim_token=claim_token,
            del_res=del_res,
            now=datetime.now(timezone.utc) if now is None else current_time,
        )

    return summary


async def cleanup_expired_extraction_assets(
    storage: ObjectStoragePort,
    db: Session,
    *,
    older_than_hours: int = 24,
    batch_limit: int = 200,
    lease_seconds: int = 300,
    now: datetime | None = None,
) -> int:
    """Delete temporary extraction assets for abandoned/expired garment runs."""
    summary = await cleanup_expired_extraction_assets_detailed(
        storage,
        db,
        older_than_hours=older_than_hours,
        batch_limit=batch_limit,
        lease_seconds=lease_seconds,
        now=now,
    )
    return summary.assets_deleted
