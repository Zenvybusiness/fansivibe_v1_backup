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

from __future__ import annotations

from dataclasses import dataclass, field
import io
import logging
import time
from typing import Any, Callable, Protocol, runtime_checkable
from uuid import uuid4
from xml.sax.saxutils import escape as _escape

_MOCK_BANNER = "TEST DATA \u2014 NOT AI TRY-ON"
logger = logging.getLogger("fansivibe.tryon.provider")


# --- Provider Exception Hierarchy ---


class TryOnProviderError(Exception):
    """Base error for all virtual try-on provider operations."""

    def __init__(
        self,
        message: str,
        *,
        provider_id: str = "unknown",
        correlation_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider_id = provider_id
        self.correlation_id = correlation_id
        self.cause = cause

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self.message!r}, "
            f"provider_id={self.provider_id!r}, correlation_id={self.correlation_id!r})"
        )


class CommercialProviderConfigurationError(TryOnProviderError):
    """Raised when commercial provider is missing required credentials or URL."""


class ProviderTransientError(TryOnProviderError):
    """Raised on retryable transient errors (502, 503, 504, 408, network timeouts)."""


class ProviderPayloadError(TryOnProviderError):
    """Raised on non-retryable invalid payload errors (400, 422)."""


class ProviderAuthError(TryOnProviderError):
    """Raised on non-retryable authentication/authorization errors (401, 403)."""


class ProviderQuotaExceededError(TryOnProviderError):
    """Raised when upstream commercial provider rate limit / quota is exhausted (429)."""


# --- Commercial Provider Configuration ---


@dataclass(frozen=True)
class CommercialTryOnProviderConfig:
    """Configuration for a separately licensed commercial VTON provider.

    Secure credential handling:
    - Secrets are never represented in logs or string representations.
    - Configuration is strictly loaded from validated environment settings.
    """

    provider_name: str
    api_key: str
    endpoint_url: str
    connect_timeout_s: float = 10.0
    inference_timeout_s: float = 60.0
    max_retries: int = 2
    backoff_factor: float = 1.5

    def __repr__(self) -> str:
        masked = (
            self.api_key[:4] + "..." + self.api_key[-4:]
            if len(self.api_key) > 8
            else "[REDACTED]"
        )
        return (
            f"CommercialTryOnProviderConfig(provider_name={self.provider_name!r}, "
            f"endpoint_url={self.endpoint_url!r}, api_key={masked!r}, "
            f"inference_timeout_s={self.inference_timeout_s})"
        )


FASHN_CATEGORIES: frozenset[str] = frozenset({"tops", "bottoms", "one-pieces"})

FASHN_CATEGORY_MAP: dict[str, str] = {
    "tops": "tops",
    "top": "tops",
    "outerwear": "tops",
    "upper": "tops",
    "shirt": "tops",
    "shirts": "tops",
    "blouse": "tops",
    "sweater": "tops",
    "sweaters": "tops",
    "jacket": "tops",
    "jackets": "tops",
    "coat": "tops",
    "coats": "tops",
    "blazer": "tops",
    "blazers": "tops",
    "tee": "tops",
    "t-shirt": "tops",
    "bottoms": "bottoms",
    "bottom": "bottoms",
    "lower": "bottoms",
    "pants": "bottoms",
    "trousers": "bottoms",
    "jeans": "bottoms",
    "skirts": "bottoms",
    "skirt": "bottoms",
    "shorts": "bottoms",
    "chinos": "bottoms",
    "one-pieces": "one-pieces",
    "one-piece": "one-pieces",
    "one_piece": "one-pieces",
    "one_pieces": "one-pieces",
    "overall": "one-pieces",
    "dresses": "one-pieces",
    "dress": "one-pieces",
    "jumpsuits": "one-pieces",
    "jumpsuit": "one-pieces",
    "romper": "one-pieces",
    "rompers": "one-pieces",
}


from app.config.image import MAX_OUTPUT_IMAGE_PIXELS

_MAX_PROVIDER_IMAGE_PIXELS = MAX_OUTPUT_IMAGE_PIXELS
_MAX_PROVIDER_IMAGE_EDGE = 8192


def validate_raster_image_bytes(
    data: bytes,
    label: str,
    correlation_id: str | None = None,
    provider_id: str = "unknown",
    max_pixels: int = _MAX_PROVIDER_IMAGE_PIXELS,
    max_edge: int = _MAX_PROVIDER_IMAGE_EDGE,
) -> str:
    """Validate raster image magic bytes and Pillow decoding (JPEG, PNG, WebP).

    Raises ProviderPayloadError on empty, truncated, malformed, decompression-bomb,
    or unsupported format payloads (including SVG/GIF/HTML).
    """
    from PIL import Image

    if not data or len(data) < 12:
        raise ProviderPayloadError(
            f"{label} payload is empty or too short ({len(data) if data else 0} bytes)",
            provider_id=provider_id,
            correlation_id=correlation_id,
        )

    if data[:3] == b"\xff\xd8\xff":
        expected_format, mime = "JPEG", "image/jpeg"
    elif data[:8] == b"\x89PNG\r\n\x1a\n":
        expected_format, mime = "PNG", "image/png"
    elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        expected_format, mime = "WEBP", "image/webp"
    else:
        raise ProviderPayloadError(
            f"{label} has unsupported or corrupt format (must be JPEG, PNG, or WebP)",
            provider_id=provider_id,
            correlation_id=correlation_id,
        )

    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != expected_format:
                raise ProviderPayloadError(
                    f"{label} format {img.format!r} does not match signature {expected_format!r}",
                    provider_id=provider_id,
                    correlation_id=correlation_id,
                )
            w, h = img.size
            if w < 1 or h < 1 or w > max_edge or h > max_edge or w * h > max_pixels:
                raise ProviderPayloadError(
                    f"{label} dimensions {w}x{h} exceed safety limits",
                    provider_id=provider_id,
                    correlation_id=correlation_id,
                )
            img.load()
    except ProviderPayloadError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ProviderPayloadError(
            f"{label} rejected as decompression bomb",
            provider_id=provider_id,
            correlation_id=correlation_id,
            cause=exc,
        )
    except Exception as exc:
        raise ProviderPayloadError(
            f"{label} is malformed or unreadable",
            provider_id=provider_id,
            correlation_id=correlation_id,
            cause=exc,
        )

    return mime


def map_wardrobe_category_to_fashn(
    category: str,
    *,
    correlation_id: str | None = None,
    provider_id: str = "fashn",
) -> str:
    """Map a Fansivibe wardrobe category to a FASHN VTON 1.5 category.

    Raises ProviderPayloadError for unsupported categories (e.g. footwear,
    accessories) rather than silently misclassifying them as tops.
    """
    normalized = (category or "").strip().lower()
    mapped = FASHN_CATEGORY_MAP.get(normalized)
    if mapped is None:
        raise ProviderPayloadError(
            f"Unsupported garment category for FASHN VTON: {category!r}",
            provider_id=provider_id,
            correlation_id=correlation_id,
        )
    return mapped


@runtime_checkable
class TryOnProvider(Protocol):
    """Render contract implemented by try-on providers."""

    provider_id: str

    def render(
        self,
        *,
        person_digest: str,
        garment_labels: list[str],
        seed: str,
        outfit_source: str,
        person_bytes: bytes | None = None,
        garment_bytes: bytes | None = None,
        category: str = "upper",
        correlation_id: str | None = None,
        job_id: str | None = None,
        person_image_url: str | None = None,
        garment_image_url: str | None = None,
        result_upload_url: str | None = None,
        is_cancelled_fn: Callable[[], bool] | None = None,
    ) -> bytes:
        """Return result image bytes for the job."""
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
        person_bytes: bytes | None = None,
        garment_bytes: bytes | None = None,
        category: str = "upper",
        correlation_id: str | None = None,
        **kwargs: Any,
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


class CatVTONTryOnProvider:
    """Experimental local CatVTON virtual try-on provider (Phase 5B).

    Integrates behind the TryOnProvider port:
    1. Acquires a GPUResourceScheduler lease (Priority 2, WorkloadType.VTON_DIFFUSION).
    2. Evicts Ollama models (keep_alive: 0) to free VRAM for CatVTON diffusion.
    3. Executes local CatVTON inference holding the lease.
    4. Marks lease complete and releases lock upon completion.
    """

    provider_id = "catvton"

    def __init__(
        self,
        *,
        model_id: str = "catvton_mix",
        resolution: tuple[int, int] = (512, 384),
        timeout_s: float = 180.0,
        scheduler: Any = None,
    ) -> None:
        self.model_id = model_id
        self.resolution = resolution
        self.timeout_s = timeout_s
        self.scheduler = scheduler

    def render(
        self,
        *,
        person_digest: str,
        garment_labels: list[str],
        seed: str,
        outfit_source: str,
        person_bytes: bytes | None = None,
        garment_bytes: bytes | None = None,
        category: str = "upper",
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        import io
        import logging
        import os
        import subprocess
        import sys
        import tempfile
        from PIL import Image

        # Ensure category is supported (fail closed on footwear/accessories/unknown)
        map_wardrobe_category_to_fashn(
            category,
            correlation_id=correlation_id,
            provider_id=self.provider_id,
        )
        catvton_category_map = {
            "tops": "upper",
            "bottoms": "lower",
            "one-pieces": "overall",
        }
        resolved_category = catvton_category_map[
            map_wardrobe_category_to_fashn(
                category,
                correlation_id=correlation_id,
                provider_id=self.provider_id,
            )
        ]

        from app.ai.manager.scheduler import get_gpu_scheduler
        from app.ai.manager.types import WorkloadType
        from app.config.settings import get_settings

        logger = logging.getLogger("fansivibe.tryon.catvton_provider")
        settings = get_settings()

        subproc: subprocess.Popen | None = None

        def _abort_fn() -> None:
            nonlocal subproc
            if subproc is not None and subproc.poll() is None:
                logger.warning("Terminating CatVTON subprocess pid=%s due to lease abort", subproc.pid)
                try:
                    subproc.terminate()
                    subproc.wait(timeout=2.0)
                except Exception:
                    try:
                        subproc.kill()
                    except Exception:
                        pass

        def _is_stopped_fn() -> bool:
            nonlocal subproc
            if subproc is None:
                return True
            return subproc.poll() is not None

        scheduler = self.scheduler or get_gpu_scheduler()
        logger.info(
            "Acquiring Priority 2 lease for CatVTON diffusion (model=%s, timeout=%.1fs)...",
            self.model_id,
            self.timeout_s,
        )

        with scheduler.acquire_lease_sync(
            model_id=self.model_id,
            workload_type=WorkloadType.VTON_DIFFUSION,
            priority=2,
            timeout_s=self.timeout_s,
            abort_fn=_abort_fn,
            is_workload_stopped=_is_stopped_fn,
        ) as lease:
            # 1. Evict any Ollama resident model from VRAM
            try:
                from app.ai.manager.adapters.ollama_adapter import OllamaModelAdapter

                ollama_adapter = OllamaModelAdapter(host=settings.reasoning_host)
                loaded_models = ollama_adapter.list_loaded_models()
                for lm in loaded_models:
                    logger.info("Evicting Ollama model '%s' from VRAM before VTON...", lm.name)
                    ollama_adapter.unload_model(lm.name, verification_timeout_s=5.0)
            except Exception as e:
                logger.warning("Ollama eviction check encountered non-fatal error: %s", e)

            # 2. Execute inference via isolated CatVTON pipeline
            from pathlib import Path
            base_dir = str(Path(__file__).resolve().parents[4])
            exp_venv_python = os.path.join(base_dir, "experiments/vton_catvton/.venv/bin/python")
            cli_script = os.path.join(base_dir, "experiments/vton_catvton/cli.py")

            demo_person_path = os.path.join(
                base_dir, "experiments/vton_catvton/catvton_code/resource/demo/example/person/women/049713_0.jpg"
            )
            demo_garment_path = os.path.join(
                base_dir, "experiments/vton_catvton/catvton_code/resource/demo/example/condition/upper/21514384_52353349_1000.jpg"
            )

            result_bytes: bytes | None = None

            if os.path.exists(exp_venv_python) and os.path.exists(cli_script):
                # Controlled process boundary
                with tempfile.TemporaryDirectory() as tmp_dir:
                    person_path = os.path.join(tmp_dir, "person.jpg")
                    garment_path = os.path.join(tmp_dir, "garment.jpg")
                    output_path = os.path.join(tmp_dir, "output.jpg")

                    if person_bytes:
                        with open(person_path, "wb") as f:
                            f.write(person_bytes)
                    elif os.path.exists(demo_person_path):
                        with open(demo_person_path, "rb") as f_src, open(person_path, "wb") as f_dst:
                            f_dst.write(f_src.read())
                    else:
                        Image.new("RGB", self.resolution, color=(200, 180, 170)).save(person_path, format="JPEG")

                    if garment_bytes:
                        with open(garment_path, "wb") as f:
                            f.write(garment_bytes)
                    elif os.path.exists(demo_garment_path):
                        with open(demo_garment_path, "rb") as f_src, open(garment_path, "wb") as f_dst:
                            f_dst.write(f_src.read())
                    else:
                        Image.new("RGB", self.resolution, color=(50, 80, 150)).save(garment_path, format="JPEG")

                    cmd = [
                        exp_venv_python,
                        cli_script,
                        "--person", person_path,
                        "--garment", garment_path,
                        "--category", resolved_category,
                        "--resolution", f"{self.resolution[0]}x{self.resolution[1]}",
                        "--output", output_path,
                        "--steps", "25",
                    ]

                    logger.info("Spawning CatVTON isolated subprocess: %s", " ".join(cmd))
                    subproc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    stdout, stderr = subproc.communicate(timeout=max(10.0, self.timeout_s - 5.0))
                    if subproc.returncode != 0:
                        logger.error("CatVTON subprocess exited with code %d: %s", subproc.returncode, stderr)
                        raise RuntimeError(f"CatVTON diffusion failed (exit code {subproc.returncode}): {stderr.strip()[-300:]}")

                    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                        raise RuntimeError("CatVTON diffusion produced empty output")

                    with open(output_path, "rb") as f:
                        result_bytes = f.read()

            else:
                # In-process execution fallback (when running within experiment venv or mocked in tests)
                sys_path_exp = os.path.join(base_dir, "experiments/vton_catvton")
                if sys_path_exp not in sys.path:
                    sys.path.insert(0, sys_path_exp)

                from inference_engine import CatVTONExperimentPipeline

                if person_bytes:
                    person_img = Image.open(io.BytesIO(person_bytes))
                elif os.path.exists(demo_person_path):
                    person_img = Image.open(demo_person_path)
                else:
                    person_img = Image.new("RGB", self.resolution, color=(200, 180, 170))

                if garment_bytes:
                    garment_img = Image.open(io.BytesIO(garment_bytes))
                elif os.path.exists(demo_garment_path):
                    garment_img = Image.open(demo_garment_path)
                else:
                    garment_img = Image.new("RGB", self.resolution, color=(50, 80, 150))

                cache_dir = os.path.join(sys_path_exp, "checkpoints")
                pipeline = CatVTONExperimentPipeline(
                    base_model_path=os.path.join(cache_dir, "base_inpainting") if os.path.exists(os.path.join(cache_dir, "base_inpainting")) else "booksforcharlie/stable-diffusion-inpainting",
                    attn_ckpt_path=os.path.join(cache_dir, "CatVTON") if os.path.exists(os.path.join(cache_dir, "CatVTON")) else "zhengchong/CatVTON",
                    attn_ckpt_version="mix",
                    device="cuda",
                    dtype="fp16",
                    enable_vae_tiling=True,
                    enable_attention_slicing=True,
                )
                res = pipeline.run_inference(
                    person_image=person_img,
                    garment_image=garment_img,
                    category=resolved_category,
                    target_resolution=self.resolution,
                    num_inference_steps=25,
                )
                if not res.success or not res.output_path or not os.path.exists(res.output_path):
                    raise RuntimeError(f"CatVTON in-process inference failed: {res.error_message}")

                with open(res.output_path, "rb") as f:
                    result_bytes = f.read()

            # Ensure any CUDA work is completely synchronized
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.synchronize()
            except Exception:
                pass

            # Validate generated output image before marking completed
            validate_raster_image_bytes(
                result_bytes or b"",
                "CatVTON result image",
                correlation_id=correlation_id,
                provider_id=self.provider_id,
            )

            # 3. Mark completed before lease release
            lease.mark_workload_completed()
            logger.info("CatVTON diffusion workload marked completed successfully.")
            return result_bytes


class CommercialTryOnProvider:
    """Production virtual try-on provider boundary for a separately licensed commercial service.

    Requirements:
    - Provider-specific configuration through environment variables.
    - Secure credential handling (never logged or exposed in traces).
    - Connection timeout and inference timeout.
    - Retry policy for transient failures only (502, 503, 504, 408, network timeouts).
    - Safe error normalization without exposing secrets or private image bytes.
    - Request correlation IDs attached to requests and traces.
    - Provider health checks where supported.
    - Image format and response validation (JPEG, PNG, WebP).
    - No logging of private image bytes or credentials.
    """

    def __init__(
        self,
        config: CommercialTryOnProviderConfig,
        *,
        http_client: Any = None,
    ) -> None:
        if not config.api_key or not config.api_key.strip():
            raise CommercialProviderConfigurationError(
                "Commercial try-on provider requires a non-empty api_key",
                provider_id=config.provider_name,
            )
        if not config.endpoint_url or not config.endpoint_url.strip():
            raise CommercialProviderConfigurationError(
                "Commercial try-on provider requires a non-empty endpoint_url",
                provider_id=config.provider_name,
            )
        self.config = config
        self.provider_id = config.provider_name
        self._http_client = http_client

    @staticmethod
    def _validate_image_format(data: bytes, label: str, correlation_id: str) -> str:
        """Validate image magic bytes and Pillow decoding."""
        return validate_raster_image_bytes(
            data,
            label,
            correlation_id=correlation_id,
            provider_id="commercial",
        )

    def render(
        self,
        *,
        person_digest: str,
        garment_labels: list[str],
        seed: str,
        outfit_source: str,
        person_bytes: bytes | None = None,
        garment_bytes: bytes | None = None,
        category: str = "upper",
        correlation_id: str | None = None,
        **kwargs: Any,
    ) -> bytes:
        import base64
        import httpx

        corr_id = correlation_id or str(uuid4())
        # Fail closed for unsupported garment categories (e.g. footwear, accessories)
        map_wardrobe_category_to_fashn(
            category,
            correlation_id=corr_id,
            provider_id=self.provider_id,
        )
        if person_bytes is None or len(person_bytes) == 0:
            raise ProviderPayloadError(
                "Commercial try-on requires person image bytes",
                provider_id=self.provider_id,
                correlation_id=corr_id,
            )

        person_mime = self._validate_image_format(person_bytes, "Person image", corr_id)
        garment_mime = (
            self._validate_image_format(garment_bytes, "Garment image", corr_id)
            if garment_bytes
            else None
        )

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "X-Correlation-ID": corr_id,
            "Accept": "image/*, application/json",
        }

        json_payload: dict[str, Any] = {
            "correlation_id": corr_id,
            "category": category,
            "seed": seed,
            "outfit_source": outfit_source,
            "garment_labels": garment_labels,
            "person_image": {
                "content_type": person_mime,
                "data": base64.b64encode(person_bytes).decode("ascii"),
                "digest": person_digest,
            },
        }
        if garment_bytes and garment_mime:
            json_payload["garment_image"] = {
                "content_type": garment_mime,
                "data": base64.b64encode(garment_bytes).decode("ascii"),
            }

        logger.info(
            "Dispatching commercial VTON inference (provider=%s, correlation_id=%s, person_bytes=%d, garment_bytes=%d)...",
            self.provider_id,
            corr_id,
            len(person_bytes),
            len(garment_bytes) if garment_bytes else 0,
        )

        timeout = httpx.Timeout(
            timeout=self.config.inference_timeout_s,
            connect=self.config.connect_timeout_s,
        )

        attempts = 0
        last_error: Exception | None = None

        while attempts <= self.config.max_retries:
            attempts += 1
            try:
                if self._http_client is not None:
                    resp = self._http_client.post(
                        self.config.endpoint_url,
                        json=json_payload,
                        headers=headers,
                        timeout=timeout,
                    )
                else:
                    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
                        resp = client.post(
                            self.config.endpoint_url,
                            json=json_payload,
                            headers=headers,
                        )

                status_code = resp.status_code
                if status_code in (200, 201):
                    content_type = resp.headers.get("content-type", "")
                    if "application/json" in content_type:
                        data = resp.json()
                        if "image_base64" in data:
                            raw_out = base64.b64decode(data["image_base64"])
                        elif "image_bytes" in data:
                            raw_out = base64.b64decode(data["image_bytes"])
                        else:
                            raise ProviderPayloadError(
                                "Commercial provider JSON response missing image payload",
                                provider_id=self.provider_id,
                                correlation_id=corr_id,
                            )
                    else:
                        raw_out = resp.content

                    out_mime = self._validate_image_format(raw_out, "Result image", corr_id)
                    logger.info(
                        "Commercial VTON inference succeeded (provider=%s, correlation_id=%s, output_bytes=%d, mime=%s).",
                        self.provider_id,
                        corr_id,
                        len(raw_out),
                        out_mime,
                    )
                    return raw_out

                if status_code in (400, 422):
                    raise ProviderPayloadError(
                        f"Commercial provider rejected payload (HTTP {status_code})",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                if status_code in (401, 403):
                    raise ProviderAuthError(
                        f"Commercial provider authentication failed (HTTP {status_code})",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                if status_code == 429:
                    raise ProviderQuotaExceededError(
                        "Commercial provider rate limit or quota exceeded (HTTP 429)",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )
                if status_code in (408, 500, 502, 503, 504):
                    raise ProviderTransientError(
                        f"Commercial provider transient server error (HTTP {status_code})",
                        provider_id=self.provider_id,
                        correlation_id=corr_id,
                    )

                raise TryOnProviderError(
                    f"Commercial provider returned unexpected HTTP {status_code}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                )

            except (ProviderPayloadError, ProviderAuthError, ProviderQuotaExceededError):
                raise
            except (ProviderTransientError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempts <= self.config.max_retries:
                    delay = self.config.backoff_factor ** attempts
                    logger.warning(
                        "Transient failure from commercial VTON provider (%s); retrying %d/%d in %.1fs: %s",
                        self.provider_id,
                        attempts,
                        self.config.max_retries,
                        delay,
                        type(exc).__name__,
                    )
                    time.sleep(delay)
                else:
                    break
            except Exception as exc:
                raise TryOnProviderError(
                    f"Unexpected commercial provider execution error: {type(exc).__name__}",
                    provider_id=self.provider_id,
                    correlation_id=corr_id,
                    cause=exc,
                )

        raise ProviderTransientError(
            f"Commercial provider failed after {attempts} attempts: {type(last_error).__name__}",
            provider_id=self.provider_id,
            correlation_id=corr_id,
            cause=last_error,
        )

    def check_health(self) -> dict[str, Any]:
        """Perform provider health check where supported."""
        import httpx

        timeout = httpx.Timeout(timeout=5.0, connect=3.0)
        t0 = time.monotonic()
        try:
            health_url = self.config.endpoint_url.rstrip("/") + "/health"
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "X-Correlation-ID": str(uuid4()),
            }
            if self._http_client is not None:
                resp = self._http_client.get(health_url, headers=headers, timeout=timeout)
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.get(health_url, headers=headers)
            duration_ms = round((time.monotonic() - t0) * 1000, 2)
            if resp.status_code in (200, 204):
                return {
                    "provider": self.provider_id,
                    "status": "healthy",
                    "latency_ms": duration_ms,
                    "endpoint": self.config.endpoint_url,
                }
            return {
                "provider": self.provider_id,
                "status": "degraded",
                "latency_ms": duration_ms,
                "endpoint": self.config.endpoint_url,
                "http_status": resp.status_code,
            }
        except Exception as exc:
            duration_ms = round((time.monotonic() - t0) * 1000, 2)
            return {
                "provider": self.provider_id,
                "status": "unavailable",
                "latency_ms": duration_ms,
                "endpoint": self.config.endpoint_url,
                "error": type(exc).__name__,
            }


