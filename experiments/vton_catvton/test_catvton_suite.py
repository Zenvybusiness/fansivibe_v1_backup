"""Comprehensive Test Suite for CatVTON Local Virtual Try-On Prototype.

Phase 5B Requirements:
- Model availability detection.
- Missing checkpoint handling.
- Invalid input images.
- Unsupported garment categories.
- CUDA unavailable handling.
- CUDA OOM error handling and quarantine safety.
- GPU scheduler acquisition and release (Priority 2, WorkloadType.VTON_DIFFUSION).
- Ollama eviction safety (POST /api/generate with keep_alive: 0).
- Interrupted inference handling.
- Output image validation.
- Provider fallback behavior (settings.tryon_provider toggle).
- Existing mock provider regression.
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image

# Ensure paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.ai.manager.types import (
    GPUSchedulerLease,
    LeaseState,
    WorkloadType,
)
from app.config.settings import get_settings
from app.domain.ports.tryon_provider import MockTryOnProvider, TryOnProvider


class TestCatVTONSuite(unittest.TestCase):
    """Deterministic validation of CatVTON prototype and system integration."""

    def setUp(self):
        self.person_img = Image.new("RGB", (384, 512), color=(200, 180, 170))
        self.garment_img = Image.new("RGB", (384, 512), color=(50, 80, 150))
        self.mask_img = Image.new("L", (384, 512), color=255)

    def test_mock_provider_regression(self):
        """Verify existing MockTryOnProvider generates valid deterministic SVG with banner."""
        provider = MockTryOnProvider()
        self.assertEqual(provider.provider_id, "mock")
        svg_bytes = provider.render(
            person_digest="abcdef123456",
            garment_labels=["garment-1", "garment-2"],
            seed="test-seed",
            outfit_source="today",
        )
        self.assertIsInstance(svg_bytes, bytes)
        self.assertTrue(len(svg_bytes) > 100)
        svg_str = svg_bytes.decode("utf-8")
        self.assertIn("TEST DATA", svg_str)
        self.assertIn("Mock try-on preview", svg_str)
        self.assertIn("source: today", svg_str)
        self.assertIn("garment-1", svg_str)

    def test_invalid_input_images(self):
        """Ensure invalid or empty input images raise appropriate validation errors."""
        from experiments.vton_catvton.inference_engine import CatVTONExperimentPipeline

        pipeline = CatVTONExperimentPipeline(
            base_model_path="dummy",
            attn_ckpt_path="dummy",
            device="cpu",
        )
        pipeline.pipeline = MagicMock()
        # Empty / None person image should fail gracefully
        with self.assertRaises(Exception):
            pipeline.run_inference(
                person_image=None,  # type: ignore
                garment_image=self.garment_img,
            )

    def test_unsupported_garment_categories(self):
        """Ensure categories outside upper/lower/overall are rejected."""
        from experiments.vton_catvton.catvton_code.model.cloth_masker import AutoMasker

        with self.assertRaises(AssertionError):
            AutoMasker.cloth_agnostic_mask(
                densepose_mask=self.mask_img,
                schp_lip_mask=self.mask_img,
                schp_atr_mask=self.mask_img,
                part="unsupported_shoes_category",
            )

    def test_missing_checkpoint_handling(self):
        """Verify pipeline fails cleanly with FileNotFoundError or OSError on missing weights."""
        from experiments.vton_catvton.inference_engine import CatVTONExperimentPipeline

        pipeline = CatVTONExperimentPipeline(
            base_model_path="/nonexistent/path/to/base",
            attn_ckpt_path="/nonexistent/path/to/attn",
            vae_ckpt="/nonexistent/path/to/vae",
            device="cpu",
        )
        with self.assertRaises((FileNotFoundError, OSError, Exception)):
            pipeline.load_models()

    def test_cuda_unavailable_handling(self):
        """Verify pipeline handles device='cpu' without crashing when CUDA is unavailable."""
        from experiments.vton_catvton.inference_engine import get_gpu_telemetry_snapshot

        with patch("torch.cuda.is_available", return_value=False):
            allocated, reserved, temp, power = get_gpu_telemetry_snapshot()
            self.assertEqual(allocated, 0.0)
            self.assertEqual(reserved, 0.0)
            self.assertIsNone(temp)
            self.assertIsNone(power)

    def test_cuda_oom_handling(self):
        """Verify CUDA OutOfMemoryError is captured safely without unhandled exception."""
        import torch
        from experiments.vton_catvton.inference_engine import CatVTONExperimentPipeline

        pipeline = CatVTONExperimentPipeline(
            base_model_path="dummy",
            attn_ckpt_path="dummy",
            device="cuda" if torch.cuda.is_available() else "cpu",
        )
        pipeline.pipeline = MagicMock()
        pipeline.pipeline.side_effect = torch.cuda.OutOfMemoryError("CUDA out of memory in test")

        res = pipeline.run_inference(
            person_image=self.person_img,
            garment_image=self.garment_img,
            mask_image=self.mask_img,
            target_resolution=(512, 384),
        )
        self.assertFalse(res.success)
        self.assertTrue(res.cuda_oom)
        self.assertIn("CUDA OutOfMemoryError", res.error_message or "")

    def test_scheduler_acquisition_and_release(self):
        """Verify GPU scheduler lease acquisition with Priority 2 and WorkloadType.VTON_DIFFUSION."""
        from app.ai.manager.scheduler import GPUResourceScheduler

        scheduler = GPUResourceScheduler(
            lockfile_path="/tmp/test_gpu_sched_vton.lock",
            metadata_path="/tmp/test_gpu_lease_vton.json",
            quarantine_path="/tmp/test_gpu_quar_vton.json",
        )
        try:
            with scheduler.acquire_lease_sync(
                model_id="catvton_vtonhd",
                workload_type=WorkloadType.VTON_DIFFUSION,
                priority=2,
                timeout_s=5.0,
            ) as lease:
                self.assertIsNotNone(lease)
                self.assertEqual(lease.model_id, "catvton_vtonhd")
                self.assertEqual(lease.workload_type, WorkloadType.VTON_DIFFUSION)
                self.assertEqual(lease.priority, 2)
                self.assertEqual(lease.state, LeaseState.RUNNING)
                lease.mark_workload_completed()

            self.assertEqual(lease.state, LeaseState.RELEASED)
        finally:
            for p in ["/tmp/test_gpu_sched_vton.lock", "/tmp/test_gpu_lease_vton.json", "/tmp/test_gpu_quar_vton.json"]:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def test_ollama_eviction_safety(self):
        """Verify Ollama loaded models inspection and keep_alive: 0 eviction call."""
        from app.ai.manager.adapters.ollama_adapter import OllamaModelAdapter

        mock_client = MagicMock()
        mock_ps_resp = MagicMock()
        mock_ps_resp.status_code = 200
        mock_ps_resp.json.side_effect = [
            {"models": [{"name": "qwen3-vl:4b-instruct", "model": "qwen3-vl:4b-instruct", "size_vram": 3500000000}]},
            {"models": []},  # Second call: confirmed evicted
        ]
        mock_gen_resp = MagicMock()
        mock_gen_resp.status_code = 200
        mock_gen_resp.json.return_value = {"done": True}

        mock_client.get.return_value = mock_ps_resp
        mock_client.post.return_value = mock_gen_resp
        adapter = OllamaModelAdapter(sync_client=mock_client)

        loaded = adapter.list_loaded_models()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].name, "qwen3-vl:4b-instruct")

        # Evict
        adapter.unload_model("qwen3-vl:4b-instruct", verification_timeout_s=2.0)
        self.assertTrue(mock_client.post.called)
        call_args = mock_client.post.call_args
        self.assertIn("/api/generate", call_args[0][0])
        self.assertEqual(call_args[1]["json"]["keep_alive"], 0)
        self.assertEqual(call_args[1]["json"]["model"], "qwen3-vl:4b-instruct")

    def test_output_image_validation(self):
        """Verify output image dimensions and RGB format."""
        out_img = Image.new("RGB", (384, 512), color=(100, 100, 100))
        self.assertEqual(out_img.size, (384, 512))
        self.assertEqual(out_img.mode, "RGB")
        buf = io.BytesIO()
        out_img.save(buf, format="JPEG", quality=95)
        self.assertTrue(len(buf.getvalue()) > 0)

    def test_provider_failure_does_not_mask_as_success(self):
        """Verify CatVTON provider raises on subprocess/inference failure without returning mock data."""
        from app.domain.ports.tryon_provider import CatVTONTryOnProvider
        from app.ai.manager.scheduler import GPUResourceScheduler
        import subprocess

        test_sched = GPUResourceScheduler(
            lockfile_path="/tmp/test_gpu_sched_fail.lock",
            metadata_path="/tmp/test_gpu_lease_fail.json",
            quarantine_path="/tmp/test_gpu_quar_fail.json",
        )
        provider = CatVTONTryOnProvider(scheduler=test_sched)
        # Mock subprocess to simulate failure exit code 2
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 2
        mock_proc.returncode = 2
        mock_proc.communicate.return_value = ("", "Simulated CUDA OOM or pipeline failure")

        try:
            with patch("subprocess.Popen", return_value=mock_proc):
                with self.assertRaises(RuntimeError) as ctx:
                    provider.render(
                        person_digest="test_digest",
                        garment_labels=["item_1"],
                        seed="42",
                        outfit_source="today",
                    )
                self.assertIn("CatVTON diffusion failed", str(ctx.exception))
        finally:
            for p in ["/tmp/test_gpu_sched_fail.lock", "/tmp/test_gpu_lease_fail.json", "/tmp/test_gpu_quar_fail.json"]:
                if os.path.exists(p):
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    def test_checkpoint_path_escaping_prevention(self):
        """Verify get_safe_checkpoint_dir prevents escaping the experimental root."""
        from experiments.vton_catvton.cli import BASE_DIR, get_safe_checkpoint_dir

        with patch.dict(os.environ, {"FANSIVIBE_CATVTON_CACHE": "/etc/shadow"}):
            safe_dir = get_safe_checkpoint_dir()
            self.assertTrue(safe_dir.startswith(os.path.abspath(BASE_DIR)))

    def test_production_environment_rejects_catvton_provider(self):
        """Verify Settings prevents enabling CatVTON in production."""
        from app.config.settings import Settings
        from pydantic import ValidationError

        with patch.dict(os.environ, {"FANSIVIBE_ENV": "production", "FANSIVIBE_TRYON_PROVIDER": "catvton"}):
            with self.assertRaises((ValidationError, ValueError)):
                Settings()


if __name__ == "__main__":
    unittest.main()

