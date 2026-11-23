"""Production garment analysis adapter — Ollama-hosted vision model (M11).

Server-side analyzer behind ``GarmentAnalysisPort``. Sends the ACTUAL
received garment image bytes to the same self-hosted vision model as
``vision_appearance_adapter`` and maps the model's observation to the
canonical garment contract. Transport (``_default_chat``), confidence
parsing, and the failure taxonomy are reused from the appearance adapter —
only the prompt and normalization are garment-specific.

Honesty rules enforced here:
- No usable garment → ``GarmentAnalysisError`` (``no_garment_detected`` /
  ``ambiguous_subject``); never a default category. ``null`` is a
  measurement ("not clearly visible"), never a fallback for a guess.
- Confidence below ``LOW_CONFIDENCE_FLOOR`` → ``low_confidence`` failure.
- ``category`` outside the canonical wardrobe codes is coerced to None
  (the model describing instead of classifying is not a run failure);
  wrong JSON types are ``invalid_analyzer_response``.
- Image bytes are processed ephemerally: base64-encoded for the provider
  call, never logged, never persisted, never echoed in errors.

Configuration reuses the vision settings (never hard-coded):
- ``FANSIVIBE_VISION_HOST`` (default ``http://localhost:11434``)
- ``FANSIVIBE_VISION_MODEL`` (default ``llama3.2-vision`` — deployment MUST
  set a vision-capable model; qwen2.5vl:3b in this deployment)
- ``FANSIVIBE_VISION_TIMEOUT_S`` (default ``20.0``)
- ``FANSIVIBE_DISABLE_VISION=1`` forces ``analyzer_unavailable``.

Adapter identity: ``ADAPTER_ID = "ollama-garment-v1"`` — recorded in the
run's MediaRef ``analyzer`` field by the use case.
"""

from __future__ import annotations

from contextlib import nullcontext
import os
from typing import Callable, Optional
from uuid import UUID

import httpx

from app.ai.vision_appearance_adapter import (
    LOW_CONFIDENCE_FLOOR,
    _parse_confidence,
)
from app.domain.ports.garment_analysis import GarmentAnalysisPort
from app.domain.value_objects import GarmentProfile

ADAPTER_ID = "ollama-garment-v1"

# Canonical wardrobe category codes (wardrobe_categories seed). The prompt
# constrains the model to these; anything else observed is coerced to None.
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
    "navy blue": "navy",
    "light blue": "light_blue",
    "sky blue": "light_blue",
    "baby blue": "light_blue",
    "gray": "grey",
    "grey": "grey",
    "dark grey": "charcoal",
    "dark gray": "charcoal",
    "charcoal grey": "charcoal",
    "charcoal gray": "charcoal",
    "brown": "tan",
    "dark brown": "tan",
    "red": "burgundy",
    "maroon": "burgundy",
    "wine": "burgundy",
    "green": "olive",
    "dark green": "olive",
    "olive green": "olive",
    "emerald": "olive",
    "pink": "blush",
    "yellow": "cream",
    "purple": "indigo",
    "sand": "beige",
    "camel": "beige",
    "off-white": "cream",
    "off white": "cream",
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
    "vegan leather": "leather",
}

# Special model verdicts (not categories).
_NO_GARMENT_TOKEN = "no_garment"
_AMBIGUOUS_TOKEN = "ambiguous"


class GarmentAnalysisError(Exception):
    """Typed analyzer failure carrying a contract failure reason.

    ``reason`` is one of: ``no_garment_detected``, ``ambiguous_subject``,
    ``analyzer_unavailable``, ``analyzer_timeout``, ``low_confidence``,
    ``invalid_analyzer_response``. The application layer maps it to a
    ``PROCESSING_FAILURE`` run error with ``details.reason``.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"garment analysis failed: {reason}")
        self.reason = reason


def _prompt() -> str:
    return (
        "Examine all clothing items and accessories in this photo. Reply with STRICT JSON only, no other text:\n"
        '{\n'
        '  "items": [\n'
        '    {\n'
        '      "id": "<candidate identifier, e.g. cand_1>",\n'
        '      "category": "<code: tops, bottoms, outerwear, footwear, or accessories>",\n'
        '      "subcategory": "<string or null>",\n'
        '      "color": "<string or null>",\n'
        '      "secondary_colors": ["<string>"] or null,\n'
        '      "pattern": "<string or null>",\n'
        '      "material": "<visual material appearance string or null>",\n'
        '      "style": "<string or null>",\n'
        '      "fit": "<string or null>",\n'
        '      "sleeve_type": "<string or null>",\n'
        '      "neckline": "<string or null>",\n'
        '      "length": "<string or null>",\n'
        '      "condition": "<string or null>",\n'
        '      "description": "<short visual description or observations>",\n'
        '      "confidence": <number 0-1>\n'
        '    }\n'
        '  ],\n'
        '  "category": "<primary category code: tops, bottoms, outerwear, footwear, or accessories>",\n'
        '  "subcategory": "<string or null>",\n'
        '  "color": "<string or null>",\n'
        '  "pattern": "<string or null>",\n'
        '  "material": "<string or null>",\n'
        '  "style": "<string or null>",\n'
        '  "fit": "<string or null>",\n'
        '  "confidence": <number 0-1>\n'
        '}\n'
        "Rules:\n"
        "- Include EVERY clothing item and accessory visible in the photo as a separate entry in the 'items' list.\n"
        "- If multiple garments are present (e.g. both top and bottom, shoes, jacket), list each item in 'items'.\n"
        "- Category codes are strictly: tops, bottoms, outerwear, footwear, accessories.\n"
        "- Reply null (JSON null, not the string) for any attribute you cannot clearly see. Never invent hidden details.\n"
        "- Distinguish visual material estimates from verified fabric composition.\n"
        "- confidence is how certain you are about the category, 0 to 1.\n"
        '- If no clothing item is clearly visible, reply {"category": "no_garment", "confidence": 0, "items": []}.\n'
        "- A face-first portrait is NOT a garment photo: unless an item of "
        "clothing is clearly shown as the photo's subject, reply "
        '{"category": "no_garment", "confidence": 0, "items": []}.\n'
        "- If the image is completely ambiguous or unidentifiable, reply "
        '{"category": "ambiguous", "confidence": 0, "items": []}.'
    )


def _normalize_category(raw: object) -> str | None:
    """Map a provider category to the canonical codes, None, or raise."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GarmentAnalysisError("invalid_analyzer_response")
    label = raw.strip().lower()
    if not label or label == "null":
        return None
    if label == _NO_GARMENT_TOKEN:
        raise GarmentAnalysisError("no_garment_detected")
    if label == _AMBIGUOUS_TOKEN:
        raise GarmentAnalysisError("ambiguous_subject")
    # ponytail: describing instead of classifying (e.g. "shirt") is not a
    # run failure — it coerces to None and the user confirms the category.
    if label not in _CANONICAL_CATEGORIES:
        return None
    return label


def _normalize_color(raw: object) -> str | None:
    """Map observed color to canonical database color codes or None."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GarmentAnalysisError("invalid_analyzer_response")
    cleaned = raw.strip().lower()
    if not cleaned or cleaned in ("null", "unknown", "none"):
        return None
    if cleaned in _CANONICAL_COLORS:
        return cleaned
    if cleaned in _COLOR_ALIASES:
        return _COLOR_ALIASES[cleaned]
    for alias, canonical in _COLOR_ALIASES.items():
        if alias in cleaned:
            return canonical
    return None


def _normalize_material(raw: object) -> str | None:
    """Map observed material to canonical database material codes or None."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GarmentAnalysisError("invalid_analyzer_response")
    cleaned = raw.strip().lower()
    if not cleaned or cleaned in ("null", "unknown", "none"):
        return None
    if cleaned in _CANONICAL_MATERIALS:
        return cleaned
    if cleaned in _MATERIAL_ALIASES:
        return _MATERIAL_ALIASES[cleaned]
    for alias, canonical in _MATERIAL_ALIASES.items():
        if alias in cleaned:
            return canonical
    return None


def _normalize_text(raw: object) -> str | None:
    """Observed free-form attribute or None; wrong types fail the run."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise GarmentAnalysisError("invalid_analyzer_response")
    text = raw.strip()
    if not text or text.lower() == "null":
        return None
    return text


def _normalize_string_list(raw: object) -> list[str] | None:
    """Normalize a list of strings or single string into clean lowercase strings."""
    if raw is None:
        return None
    if isinstance(raw, list):
        out: list[str] = []
        for x in raw:
            if isinstance(x, str) and x.strip() and x.strip().lower() not in ("null", "none"):
                out.append(x.strip().lower())
        return out if out else None
    if isinstance(raw, str):
        cleaned = raw.strip().lower()
        if cleaned and cleaned not in ("null", "none"):
            return [cleaned]
    return None


def _deduplicate_candidates(candidates: list[dict]) -> list[dict]:
    """Prevent returning identical garment candidates from the model."""
    seen = set()
    deduped = []
    for cand in candidates:
        key = (
            cand.get("category"),
            (cand.get("subcategory") or "").lower(),
            (cand.get("color") or "").lower(),
            (cand.get("material") or "").lower(),
            (cand.get("pattern") or "").lower(),
            (cand.get("fit") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cand)
    return deduped


def _acquire_gpu_lease_context(model_id: str, timeout_s: float):
    """Acquire Priority 1 GPU lease context manager, or nullcontext if scheduler unavailable."""
    try:
        from app.ai.manager.scheduler import get_gpu_scheduler
        from app.ai.manager.types import WorkloadType
        scheduler = get_gpu_scheduler()
        return scheduler.acquire_lease_sync(
            model_id=model_id,
            workload_type=WorkloadType.REASONING_VISION,
            priority=1,
            timeout_s=timeout_s + 5.0,
            acquisition_timeout_s=3.0,
        )
    except Exception:
        return nullcontext(None)


def _garment_chat(
    *, host: str, model: str, timeout_s: float, image_b64: str, prompt: str
) -> dict:
    """POST the image to Ollama chat under two-tier GPU scheduler lease coordination."""
    cm = _acquire_gpu_lease_context(model, timeout_s)
    with cm as lease:
        request_submitted = False
        if lease is not None:
            lease.register_termination_check(lambda: not request_submitted)
        try:
            request_submitted = True
            with httpx.Client(timeout=timeout_s) as client:
                response = client.post(
                    f"{host}/api/chat",
                    json={
                        "model": model,
                        "stream": False,
                        "format": "json",
                        "options": {"temperature": 0},
                        "messages": [
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [image_b64],
                            }
                        ],
                    },
                )
                response.raise_for_status()
                # Invariant: receiving HTTP 200 headers alone must NOT mark inference as completed.
                # The lease must remain active until the complete response body has been received.
                _ = response.content
                if lease is not None:
                    lease.mark_workload_completed()
                payload = response.json()
        except GarmentAnalysisError:
            raise
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            request_submitted = False
            raise GarmentAnalysisError("analyzer_unavailable") from exc
        except httpx.TimeoutException as exc:
            raise GarmentAnalysisError("analyzer_timeout") from exc
        except httpx.HTTPError as exc:
            raise GarmentAnalysisError("analyzer_unavailable") from exc
        except Exception as exc:
            raise GarmentAnalysisError("analyzer_unavailable") from exc

    if not isinstance(payload, dict):
        raise GarmentAnalysisError("invalid_analyzer_response")
    message = payload.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise GarmentAnalysisError("invalid_analyzer_response")
    import json as _json

    try:
        decoded = _json.loads(content)
    except ValueError as exc:
        raise GarmentAnalysisError("invalid_analyzer_response") from exc
    if not isinstance(decoded, dict):
        raise GarmentAnalysisError("invalid_analyzer_response")
    return decoded


class OllamaVisionGarmentAdapter(GarmentAnalysisPort):
    """Production adapter: measures garment attributes from actual pixels."""

    adapter_id = ADAPTER_ID

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        model: Optional[str] = None,
        timeout_s: Optional[float] = None,
        chat_fn: Optional[Callable[..., dict]] = None,
    ) -> None:
        from app.config.settings import get_settings

        settings = get_settings()
        self._host = host or settings.vision_host
        self._model = model or settings.vision_model
        self._timeout_s = timeout_s or settings.vision_timeout_s
        self._disabled = bool(getattr(settings, "disable_vision", False))
        # Injectable transport boundary: tests supply a fake, production
        # uses Ollama over httpx with GPU lease coordination.
        self._chat_fn = chat_fn or _garment_chat

    def analyze(
        self,
        *,
        media_ref: dict,
        user_id: UUID,
        image_bytes: bytes | None = None,
    ) -> GarmentProfile:
        """Measure garment attributes from the supplied image bytes."""
        import base64

        if image_bytes is None:
            raise ValueError("OllamaVisionGarmentAdapter requires image_bytes")
        if self._disabled or os.environ.get("FANSIVIBE_DISABLE_VISION") == "1":
            raise GarmentAnalysisError("analyzer_unavailable")
        image_b64 = base64.b64encode(bytes(image_bytes)).decode("ascii")
        try:
            decoded = self._chat_fn(
                host=self._host,
                model=self._model,
                timeout_s=self._timeout_s,
                image_b64=image_b64,
                prompt=_prompt(),
            )
        except GarmentAnalysisError:
            raise
        except httpx.TimeoutException as exc:
            raise GarmentAnalysisError("analyzer_timeout") from exc
        except httpx.HTTPError as exc:
            raise GarmentAnalysisError("analyzer_unavailable") from exc
        except Exception as exc:
            raise GarmentAnalysisError("analyzer_unavailable") from exc
        if not isinstance(decoded, dict):
            raise GarmentAnalysisError("invalid_analyzer_response")

        raw_candidates = decoded.get("candidates") or decoded.get("items")

        # Category verdict first (face-adapter precedent): no_garment /
        # ambiguous carry confidence 0 by contract and must surface their
        # specific reason, never low_confidence.
        raw_cat = decoded.get("category")
        if raw_cat is None and isinstance(raw_candidates, list) and raw_candidates:
            first = raw_candidates[0]
            if isinstance(first, dict):
                raw_cat = first.get("category")
        category = _normalize_category(raw_cat)

        raw_conf = decoded.get("confidence")
        if raw_conf is None and isinstance(raw_candidates, list) and raw_candidates:
            first = raw_candidates[0]
            if isinstance(first, dict):
                raw_conf = first.get("confidence")

        try:
            confidence = _parse_confidence(raw_conf)
        except Exception as exc:
            # _parse_confidence raises AppearanceAnalysisError; re-map to
            # the garment taxonomy so callers see one reason vocabulary.
            raise GarmentAnalysisError("invalid_analyzer_response") from exc
        if confidence < LOW_CONFIDENCE_FLOOR:
            raise GarmentAnalysisError("low_confidence")

        subcategory = _normalize_text(decoded.get("subcategory") or decoded.get("subtype") or decoded.get("name"))
        color = _normalize_text(decoded.get("color"))
        secondary_colors = _normalize_string_list(decoded.get("secondary_colors"))
        pattern = _normalize_text(decoded.get("pattern"))
        material = _normalize_text(decoded.get("material"))
        style = _normalize_text(decoded.get("style"))
        fit = _normalize_text(decoded.get("fit") or decoded.get("silhouette"))
        sleeve_type = _normalize_text(decoded.get("sleeve_type") or decoded.get("sleeve"))
        neckline = _normalize_text(decoded.get("neckline"))
        length = _normalize_text(decoded.get("length"))
        condition = _normalize_text(decoded.get("condition"))
        description = _normalize_text(decoded.get("description") or decoded.get("visual_observations"))

        candidates_list: list[dict] = []
        if isinstance(raw_candidates, list) and raw_candidates:
            for idx, item in enumerate(raw_candidates):
                if isinstance(item, dict):
                    cand_id = _normalize_text(item.get("id")) or f"cand_{idx + 1}"
                    c_cat = _normalize_category(item.get("category"))
                    c_subcat = _normalize_text(item.get("subcategory") or item.get("subtype") or item.get("name"))
                    c_color = _normalize_text(item.get("color"))
                    c_sec_colors = _normalize_string_list(item.get("secondary_colors"))
                    c_pattern = _normalize_text(item.get("pattern"))
                    c_material = _normalize_text(item.get("material"))
                    c_style = _normalize_text(item.get("style"))
                    c_fit = _normalize_text(item.get("fit") or item.get("silhouette"))
                    c_sleeve = _normalize_text(item.get("sleeve_type") or item.get("sleeve"))
                    c_neckline = _normalize_text(item.get("neckline"))
                    c_length = _normalize_text(item.get("length"))
                    c_condition = _normalize_text(item.get("condition"))
                    c_desc = _normalize_text(item.get("description") or item.get("visual_observations") or item.get("notes"))
                    c_conf = _parse_confidence(item.get("confidence", confidence))
                    c_bbox = item.get("bounding_box") if isinstance(item.get("bounding_box"), dict) else None

                    candidates_list.append({
                        "id": cand_id,
                        "category": c_cat,
                        "subcategory": c_subcat,
                        "color": c_color,
                        "secondary_colors": c_sec_colors,
                        "pattern": c_pattern,
                        "material": c_material,
                        "style": c_style,
                        "fit": c_fit,
                        "sleeve_type": c_sleeve,
                        "neckline": c_neckline,
                        "length": c_length,
                        "condition": c_condition,
                        "description": c_desc,
                        "confidence": c_conf,
                        "bounding_box": c_bbox,
                        "needs_review": c_cat is None or c_color is None or c_conf < 0.6,
                    })

        candidates_list = _deduplicate_candidates(candidates_list)
        for i, c in enumerate(candidates_list):
            if not c.get("id"):
                c["id"] = f"cand_{i + 1}"

        if candidates_list:
            if category is None and candidates_list[0]["category"] is not None:
                category = candidates_list[0]["category"]
            if color is None and candidates_list[0]["color"] is not None:
                color = candidates_list[0]["color"]
            if material is None and candidates_list[0]["material"] is not None:
                material = candidates_list[0]["material"]

        # ponytail: deterministic review flag — missing core facts or a
        # weak measurement always routes through user confirmation.
        needs_review = (
            category is None or color is None or material is None or confidence < 0.6
        )

        if not candidates_list:
            candidates_list.append({
                "id": "cand_1",
                "category": category,
                "subcategory": subcategory,
                "color": color,
                "secondary_colors": secondary_colors,
                "pattern": pattern,
                "material": material,
                "style": style,
                "fit": fit,
                "sleeve_type": sleeve_type,
                "neckline": neckline,
                "length": length,
                "condition": condition,
                "description": description,
                "confidence": confidence,
                "bounding_box": None,
                "needs_review": needs_review,
            })

        first_cand = candidates_list[0]
        return GarmentProfile(
            category=category,
            subcategory=subcategory,
            color=color,
            pattern=pattern,
            material=material,
            style=style,
            fit=fit,
            confidence=confidence,
            needs_review=needs_review,
            sourceRunId="",
            candidates=tuple(candidates_list),
            secondary_colors=tuple(first_cand.get("secondary_colors") or secondary_colors or ()),
            sleeve_type=first_cand.get("sleeve_type") or sleeve_type,
            neckline=first_cand.get("neckline") or neckline,
            length=first_cand.get("length") or length,
            condition=first_cand.get("condition") or condition,
            description=first_cand.get("description") or description,
        )

    def validate_result(self, result: dict) -> bool:
        """Contract validation for garment result dicts."""
        required = {
            "category",
            "subcategory",
            "color",
            "pattern",
            "material",
            "style",
            "fit",
            "confidence",
            "needs_review",
        }
        if not isinstance(result, dict) or not all(k in result for k in required):
            return False
        category = result["category"]
        if category is not None and category not in _CANONICAL_CATEGORIES:
            return False
        for key in ("subcategory", "color", "pattern", "material", "style", "fit"):
            value = result[key]
            if value is not None and not isinstance(value, str):
                return False
        try:
            conf = result["confidence"]
            if isinstance(conf, bool) or not isinstance(conf, (int, float)):
                return False
            if not 0.0 <= float(conf) <= 1.0:
                return False
        except (TypeError, ValueError):
            return False
        if not isinstance(result["needs_review"], bool):
            return False
        return True


__all__ = [
    "ADAPTER_ID",
    "GarmentAnalysisError",
    "OllamaVisionGarmentAdapter",
]
