"""Garment extraction image processing, private crop storage, explicit save, and cleanup (P5.1).

Reuses the existing Fansivibe infrastructure:
- Pillow safety bounds (`MAX_INPUT_PIXELS = 12_000_000`, `MAX_INPUT_EDGE = 4096`, EXIF transpose, metadata strip)
- `ObjectStoragePort` for private user-scoped temporary extraction crops and canonical wardrobe media
- `MediaUploadAuthorization` + `AddWardrobeItem` (`validate_media_association`) for PostgreSQL persistence
- Explicit user confirmation before any wardrobe item is saved
- Cleanup of temporary extraction assets on save, cancel/discard, and retention expiration
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import logging
import re
from typing import Any, Optional
from uuid import UUID, uuid4
import warnings

from PIL import Image, ImageFile, ImageOps
from sqlalchemy import select
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

# In-process idempotency cache used only when SQL session `db` is absent (pure unit tests).
_IN_MEMORY_SAVE_BATCHES: dict[tuple[UUID, UUID, str], dict[str, Any]] = {}


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


async def delete_run_extraction_assets(
    storage: ObjectStoragePort,
    *,
    user_id: UUID,
    run_id: UUID,
    candidate_ids: set[str] | None = None,
    result_snapshot: dict[str, Any] | None = None,
) -> int:
    """Delete temporary extraction objects under `users/{user_id}/extractions/{run_id}/`."""
    prefix = extraction_prefix(user_id, run_id)
    keys_to_delete: set[str] = set()

    if candidate_ids is None and hasattr(storage, "list_keys"):
        try:
            listed = await storage.list_keys(prefix)  # type: ignore[attr-defined]
            for k in listed:
                validate_scoped_object_key(k, user_id=str(user_id))
                keys_to_delete.add(k)
        except Exception:
            pass

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
    for key in sorted(keys_to_delete):
        try:
            if await storage.object_exists(key):
                await storage.delete_object(key)
                deleted += 1
            else:
                await storage.delete_object(key)
        except Exception as exc:
            logger.warning("Failed to delete temporary extraction asset %s: %s", key, exc)
    return deleted


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
    def _batch_fingerprint(items: list[dict[str, Any]]) -> str:
        canonical = [
            {
                "candidateId": str(it["candidateId"]).strip(),
                "name": str(it["name"]).strip(),
                "category": str(it["category"]).strip().lower(),
                "color": str(it["color"]).strip().lower(),
                "material": (str(it["material"]).strip().lower() if it.get("material") else None),
                "fit": (str(it["fit"]).strip() if it.get("fit") else None),
                "isFavorite": bool(it.get("isFavorite", False)),
            }
            for it in items
        ]
        canonical.sort(key=lambda x: x["candidateId"])
        import json
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()

    def _find_existing_wardrobe_item_for_candidate(
        self, *, user_id: UUID, run_id: UUID, candidate_id: str
    ) -> WardrobeItemRecord | None:
        if self._db is None:
            return None
        idemp_key = f"extract:{run_id}:{candidate_id}"
        auth = self._db.execute(
            select(MediaUploadAuthorization).where(
                MediaUploadAuthorization.user_id == user_id,
                MediaUploadAuthorization.idempotency_key == idemp_key,
            )
        ).scalar_one_or_none()
        if auth is None:
            return None
        upload_id_str = str(auth.upload_id)
        rows = self._db.execute(
            select(WardrobeItems).where(WardrobeItems.user_id == user_id)
        ).scalars().all()
        for row in rows:
            ref = row.image_ref
            if isinstance(ref, dict) and str(ref.get("uploadId")) == upload_id_str:
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
        return None

    async def _promote_crop_to_wardrobe_media(
        self,
        *,
        user_id: UUID,
        run_id: UUID,
        candidate: dict[str, Any],
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
            existing_auth = self._db.execute(
                select(MediaUploadAuthorization).where(
                    MediaUploadAuthorization.user_id == user_id,
                    MediaUploadAuthorization.idempotency_key == idemp_key,
                )
            ).scalar_one_or_none()

        upload_id = existing_auth.upload_id if existing_auth is not None else uuid4()
        canonical_key = (
            existing_auth.canonical_key
            if existing_auth is not None and existing_auth.canonical_key
            else _get_canonical_wardrobe_crop_key(user_id, upload_id)
        )
        now = datetime.now(timezone.utc)

        await self._storage.put_object(
            key=canonical_key,
            data=crop_bytes,
            content_type="image/webp",
            custom_metadata={
                "user_id": str(user_id),
                "upload_id": str(upload_id),
                "source_run_id": str(run_id),
                "candidate_id": cand_id,
                "sha256": cand_sha,
                "width": str(width),
                "height": str(height),
            },
        )

        if self._db is not None and existing_auth is None:
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
            self._db.commit()

        return {
            "uploadId": str(upload_id),
            "objectKey": canonical_key,
            "mediaType": "image/webp",
            "width": width,
            "height": height,
            "sizeBytes": len(crop_bytes),
            "contentHash": cand_sha,
            "uploadedAt": now.isoformat(),
            "status": "ready",
        }

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

        record: AnalysisRunRecord | None = self._runs.get_for_user(
            user_id=user_id, run_id=run_id
        )
        if record is None:
            raise not_found()
        if record.run_type != "garment":
            raise validation([{"field": "run_id", "error": "run is not a garment extraction run"}])
        if record.status != "completed" or not isinstance(record.result, dict):
            raise validation([{"field": "run_id", "error": "garment extraction run is not completed"}])

        clean_key = idempotency_key.strip() if idempotency_key else None
        fingerprint = self._batch_fingerprint(items)
        if clean_key:
            cache_key = (user_id, run_id, clean_key)
            cached = _IN_MEMORY_SAVE_BATCHES.get(cache_key)
            if cached is not None:
                if cached["fingerprint"] != fingerprint:
                    raise conflict("duplicate")
                return cached["response"]

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

            existing = self._find_existing_wardrobe_item_for_candidate(
                user_id=user_id, run_id=run_id, candidate_id=cand_id
            )
            if existing is not None:
                saved_records.append(existing)
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
                )
            except ApiError as exc:
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": exc.message,
                })
                continue

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
                    fit_confidence=sel.get("fitConfidence"),
                )
                saved_records.append(created)
                saved_candidate_ids.add(cand_id)
            except ApiError as exc:
                # Roll back promoted canonical object if DB save failed
                if image_ref and isinstance(image_ref.get("objectKey"), str):
                    try:
                        await self._storage.delete_object(image_ref["objectKey"])
                    except Exception:
                        pass
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": exc.message,
                })
            except Exception:
                if image_ref and isinstance(image_ref.get("objectKey"), str):
                    try:
                        await self._storage.delete_object(image_ref["objectKey"])
                    except Exception:
                        pass
                failed_items.append({
                    "candidateId": cand_id,
                    "name": name,
                    "error": "Failed to save garment to wardrobe.",
                })

        # Clean up temporary extraction assets:
        # - If all selected items succeeded, purge all temporary assets for this run (including unselected).
        # - If partial failure occurred, purge only the succeeded candidates' temporary crops so failed ones can be retried.
        cleaned_up_all = False
        if not failed_items and saved_records:
            await delete_run_extraction_assets(
                self._storage,
                user_id=user_id,
                run_id=run_id,
                candidate_ids=None,
                result_snapshot=record.result,
            )
            cleaned_up_all = True
        elif saved_candidate_ids:
            await delete_run_extraction_assets(
                self._storage,
                user_id=user_id,
                run_id=run_id,
                candidate_ids=saved_candidate_ids,
                result_snapshot=record.result,
            )

        result_payload = {
            "saved_records": saved_records,
            "failed_items": failed_items,
            "cleaned_up_assets": cleaned_up_all,
        }
        if clean_key and not failed_items:
            _IN_MEMORY_SAVE_BATCHES[(user_id, run_id, clean_key)] = {
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
    ) -> None:
        self._runs = runs
        self._storage = storage

    async def execute(self, *, user_id: UUID, run_id: UUID) -> dict[str, Any]:
        record = self._runs.get_for_user(user_id=user_id, run_id=run_id)
        if record is None:
            raise not_found()
        if record.run_type != "garment":
            raise validation([{"field": "run_id", "error": "run is not a garment extraction run"}])

        deleted = await delete_run_extraction_assets(
            self._storage,
            user_id=user_id,
            run_id=run_id,
            candidate_ids=None,
            result_snapshot=record.result if isinstance(record.result, dict) else None,
        )
        return {
            "runId": run_id,
            "deletedCount": deleted,
            "alreadyCleaned": deleted == 0,
        }


async def cleanup_expired_extraction_assets(
    storage: ObjectStoragePort,
    db: Session,
    *,
    older_than_hours: int = 24,
    batch_limit: int = 200,
) -> int:
    """Delete temporary extraction assets for abandoned/expired garment runs."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
    rows = db.execute(
        select(AnalysisRuns)
        .where(
            AnalysisRuns.run_type == "garment",
            AnalysisRuns.created_at < cutoff,
        )
        .order_by(AnalysisRuns.created_at.asc())
        .limit(batch_limit)
    ).scalars().all()

    total_deleted = 0
    for row in rows:
        total_deleted += await delete_run_extraction_assets(
            storage,
            user_id=row.user_id,
            run_id=row.id,
            candidate_ids=None,
            result_snapshot=row.result if isinstance(row.result, dict) else None,
        )
    return total_deleted
