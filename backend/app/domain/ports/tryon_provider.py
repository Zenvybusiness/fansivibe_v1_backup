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
    ) -> bytes:
        import io
        import logging
        import os
        import subprocess
        import sys
        import tempfile
        from PIL import Image

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
                        "--category", category,
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
                    category=category,
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

            # 3. Mark completed before lease release
            lease.mark_workload_completed()
            logger.info("CatVTON diffusion workload marked completed successfully.")
            return result_bytes

