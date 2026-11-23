"""CatVTON Local Virtual Try-On CLI Entry Point.

Usage:
    python cli.py --person <path> --garment <path> [--category upper] [--output <path>] [--resolution 512x384] [--steps 25] [--device cuda]
"""

import argparse
import logging
import os
import sys
from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("catvton_cli")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from inference_engine import CatVTONExperimentPipeline, cleanup_cuda

def get_safe_checkpoint_dir() -> str:
    """Return validated checkpoint directory strictly contained within experimental folder."""
    default_dir = os.path.abspath(os.path.join(BASE_DIR, "checkpoints"))
    cache_env = os.environ.get("FANSIVIBE_CATVTON_CACHE")
    if cache_env:
        resolved = os.path.abspath(cache_env)
        if not resolved.startswith(os.path.abspath(BASE_DIR)):
            logger.warning("FANSIVIBE_CATVTON_CACHE attempts to escape %s; using %s", BASE_DIR, default_dir)
            return default_dir
        return resolved
    return default_dir

CACHE_DIR = get_safe_checkpoint_dir()


def parse_resolution(res_str: str) -> tuple[int, int]:
    """Parse 'HxW' or 'WxH' into (height, width). Standard default is 512x384 (H x W)."""
    parts = res_str.lower().split("x")
    if len(parts) != 2:
        raise ValueError(f"Invalid resolution format '{res_str}'. Expected format like '512x384'.")
    val1, val2 = int(parts[0]), int(parts[1])
    # By convention in try-on models, images are portrait (height > width)
    if val1 > val2:
        return (val1, val2)  # (height, width)
    else:
        return (val2, val1)


def main():
    parser = argparse.ArgumentParser(description="CatVTON Local Virtual Try-On Prototype CLI")
    parser.add_argument("--person", type=str, required=True, help="Path to person photograph")
    parser.add_argument("--garment", type=str, required=True, help="Path to garment photograph")
    parser.add_argument("--category", type=str, default="upper", choices=["upper", "lower", "overall"], help="Garment category")
    parser.add_argument("--output", type=str, default="output/tryon_output.jpg", help="Path to save generated try-on image")
    parser.add_argument("--resolution", type=str, default="512x384", help="Inference resolution, e.g. 512x384, 640x480, 768x576, 1024x768")
    parser.add_argument("--steps", type=int, default=25, help="Number of denoising steps (default: 25)")
    parser.add_argument("--guidance", type=float, default=2.5, help="Classifier-free guidance scale (default: 2.5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--device", type=str, default="cuda", choices=["cuda", "cpu"], help="Inference device")
    parser.add_argument("--dtype", type=str, default="fp16", choices=["fp16", "bf16", "fp32"], help="Floating point precision")

    args = parser.parse_args()

    if not os.path.exists(args.person):
        logger.error(f"Person image not found: {args.person}")
        sys.exit(1)
    if not os.path.exists(args.garment):
        logger.error(f"Garment image not found: {args.garment}")
        sys.exit(1)

    target_res = parse_resolution(args.resolution)
    logger.info(f"Loading person: {args.person}, garment: {args.garment}, category: {args.category}, resolution: {target_res[0]}x{target_res[1]}")

    person_img = Image.open(args.person)
    garment_img = Image.open(args.garment)

    base_model_path = os.path.join(CACHE_DIR, "base_inpainting")
    attn_ckpt_path = os.path.join(CACHE_DIR, "CatVTON")
    densepose_ckpt = os.path.join(CACHE_DIR, "CatVTON/DensePose")
    schp_ckpt = os.path.join(CACHE_DIR, "CatVTON/SCHP")

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
        device=args.device,
        dtype=args.dtype,
        enable_vae_tiling=True,
        enable_attention_slicing=True,
    )

    result = pipeline.run_inference(
        person_image=person_img,
        garment_image=garment_img,
        category=args.category,
        target_resolution=target_res,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        seed=args.seed,
        output_path=args.output,
    )

    if result.success:
        import torch
        if torch.cuda.is_available():
            torch.cuda.synchronize()
        logger.info("========================================================")
        logger.info(f"SUCCESS! Output saved to: {result.output_path}")
        logger.info(f"Total Latency: {result.total_latency_s:.2f}s (Denoising: {result.denoising_latency_s:.2f}s)")
        logger.info(f"Peak VRAM: Allocated={result.telemetry.peak_vram_allocated_mb:.1f}MB, Reserved={result.telemetry.peak_vram_reserved_mb:.1f}MB")
        logger.info(f"Peak System RAM: {result.telemetry.peak_sys_ram_used_mb:.1f}MB")
        logger.info(f"GPU Temp: {result.telemetry.gpu_temp_c}C, GPU Power: {result.telemetry.gpu_power_w}W")
        logger.info("========================================================")
        sys.exit(0)
    else:
        logger.error(f"Inference failed: {result.error_message}")
        if result.cuda_oom:
            logger.error("CUDA OOM detected! Consider downscaling resolution (e.g. 512x384).")
        sys.exit(2)


if __name__ == "__main__":
    main()

