"""Progressive Resolution Benchmark for CatVTON on NVIDIA RTX 3050 (6 GB VRAM).

Evaluates:
- 512 x 384
- 640 x 480
- 768 x 576
- 1024 x 768 (conditional if 768x576 passes without OOM)

Measures:
- Latency (load, prep, mask, denoise, total)
- Peak VRAM (allocated + reserved)
- System RAM
- GPU Temperature and Power
- Output image verification
"""

import json
import logging
import os
import sys
import time
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("catvton_benchmark")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from inference_engine import CatVTONExperimentPipeline, cleanup_cuda

CACHE_DIR = os.environ.get(
    "FANSIVIBE_CATVTON_CACHE",
    os.path.join(BASE_DIR, "checkpoints")
)
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Sample test inputs from official demo assets
PERSON_IMG_PATH = os.path.join(BASE_DIR, "catvton_code/resource/demo/example/person/women/049713_0.jpg")
GARMENT_IMG_PATH = os.path.join(BASE_DIR, "catvton_code/resource/demo/example/condition/upper/21514384_52353349_1000.jpg")


def run_benchmark():
    if not os.path.exists(PERSON_IMG_PATH):
        raise FileNotFoundError(f"Person test asset missing: {PERSON_IMG_PATH}")
    if not os.path.exists(GARMENT_IMG_PATH):
        raise FileNotFoundError(f"Garment test asset missing: {GARMENT_IMG_PATH}")

    person_img = Image.open(PERSON_IMG_PATH)
    garment_img = Image.open(GARMENT_IMG_PATH)
    logger.info(f"Loaded person image: {person_img.size}, garment image: {garment_img.size}")

    base_model_path = os.path.join(CACHE_DIR, "base_inpainting")
    attn_ckpt_path = os.path.join(CACHE_DIR, "CatVTON")
    densepose_ckpt = os.path.join(CACHE_DIR, "CatVTON/DensePose")
    schp_ckpt = os.path.join(CACHE_DIR, "CatVTON/SCHP")

    # If local checkpoint cache isn't populated, use direct HF repos
    if not os.path.exists(base_model_path):
        base_model_path = "booksforcharlie/stable-diffusion-inpainting"
    if not os.path.exists(attn_ckpt_path):
        attn_ckpt_path = "zhengchong/CatVTON"

    vae_ckpt = os.path.join(CACHE_DIR, "vae")

    pipeline = CatVTONExperimentPipeline(
        base_model_path=base_model_path,
        attn_ckpt_path=attn_ckpt_path,
        attn_ckpt_version="mix",
        vae_ckpt=vae_ckpt if os.path.exists(vae_ckpt) else None,
        densepose_ckpt=densepose_ckpt if os.path.exists(densepose_ckpt) else None,
        schp_ckpt=schp_ckpt if os.path.exists(schp_ckpt) else None,
        device="cuda",
        dtype="fp16",
        enable_vae_tiling=True,
        enable_attention_slicing=True,
    )

    # Initial target resolutions: (height, width)
    # 1. 512 x 384
    # 2. 640 x 480
    # 3. 768 x 576
    # 4. 1024 x 768 (conditional)
    candidate_resolutions = [
        (512, 384),
        (640, 480),
        (768, 576),
        (1024, 768),
    ]

    benchmark_records = []
    logger.info("================================================================")
    logger.info("STARTING PROGRESSIVE CATVTON BENCHMARK (RTX 3050 6GB)")
    logger.info("================================================================")

    for h, w in candidate_resolutions:
        logger.info(f"--- Evaluating resolution {h} x {w} ---")
        out_path = os.path.join(OUTPUT_DIR, f"catvton_result_{h}x{w}.jpg")

        # Create a realistic cloth-agnostic mask if automasker is not active
        # (upper body mask covering chest/torso region for upper garment try-on)
        mask = None
        if pipeline.automasker is None:
            mask = Image.new("L", (w, h), 0)
            # Create a white polygon or bounding box over the torso region
            import cv2
            import numpy as np
            mask_arr = np.zeros((h, w), dtype=np.uint8)
            # Torso region: approximately top 25% to 65% of height, middle 60% of width
            y1, y2 = int(h * 0.22), int(h * 0.65)
            x1, x2 = int(w * 0.20), int(w * 0.80)
            mask_arr[y1:y2, x1:x2] = 255
            # Dilate/blur slightly
            mask_arr = cv2.GaussianBlur(mask_arr, (21, 21), 0)
            mask = Image.fromarray(mask_arr)

        res = pipeline.run_inference(
            person_image=person_img,
            garment_image=garment_img,
            category="upper",
            mask_image=mask,
            target_resolution=(h, w),
            num_inference_steps=25,
            guidance_scale=2.5,
            seed=42,
            output_path=out_path,
        )

        record = {
            "resolution": f"{h}x{w}",
            "height": h,
            "width": w,
            "success": res.success,
            "cuda_oom": res.cuda_oom,
            "error": res.error_message,
            "output_path": out_path if res.success else None,
            "load_time_s": round(res.model_load_latency_s, 2),
            "preprocessing_time_s": round(res.preprocessing_latency_s, 2),
            "mask_generation_time_s": round(res.mask_generation_latency_s, 2),
            "denoising_time_s": round(res.denoising_latency_s, 2),
            "vae_decoding_time_s": round(res.vae_decoding_latency_s, 2),
            "total_time_s": round(res.total_latency_s, 2),
            "iterations_per_second": round(25.0 / res.denoising_latency_s, 2) if res.denoising_latency_s > 0 else 0.0,
            "seconds_per_iteration": round(res.denoising_latency_s / 25.0, 2) if res.denoising_latency_s > 0 else 0.0,
            "peak_vram_allocated_mb": round(res.telemetry.peak_vram_allocated_mb, 1),
            "peak_vram_reserved_mb": round(res.telemetry.peak_vram_reserved_mb, 1),
            "peak_sys_ram_mb": round(res.telemetry.peak_sys_ram_used_mb, 1),
            "gpu_temp_c": res.telemetry.gpu_temp_c,
            "gpu_power_w": res.telemetry.gpu_power_w,
        }
        benchmark_records.append(record)
        logger.info(
            f"Result for {h}x{w}: Success={res.success}, Denoising={record['denoising_time_s']}s "
            f"({record['iterations_per_second']} it/s, {record['seconds_per_iteration']} s/it), "
            f"VAE_Decode={record['vae_decoding_time_s']}s, "
            f"Total={record['total_time_s']}s, PeakAllocVRAM={record['peak_vram_allocated_mb']}MB, "
            f"PeakResVRAM={record['peak_vram_reserved_mb']}MB, Temp={record['gpu_temp_c']}C, Power={record['gpu_power_w']}W"
        )

        cleanup_cuda()
        time.sleep(1.0)

        # Stop condition: if CUDA OOM occurred, do not attempt larger resolutions
        if res.cuda_oom:
            logger.warning(f"CUDA OOM encountered at {h}x{w}. Ceasing further higher resolution tests.")
            break

    summary_path = os.path.join(OUTPUT_DIR, "benchmark_summary.json")
    with open(summary_path, "w") as f:
        json.dump(benchmark_records, f, indent=2)
    logger.info(f"Benchmark summary written to {summary_path}")
    return benchmark_records


if __name__ == "__main__":
    run_benchmark()

