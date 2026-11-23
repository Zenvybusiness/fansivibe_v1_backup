"""Download official CatVTON model checkpoints and base inpainting components.

Checkpoints:
- zhengchong/CatVTON:
    - mix-48k-1024/attention/model.safetensors
    - vitonhd-16k-512/attention/model.safetensors
    - SCHP/exp-schp-201908261155-lip.pth
    - SCHP/exp-schp-201908301523-atr.pth
    - DensePose/model_final_162be9.pkl
    - DensePose/Base-DensePose-RCNN-FPN.yaml
    - DensePose/densepose_rcnn_R_50_FPN_s1x.yaml
- Base Inpainting model: booksforcharlie/stable-diffusion-inpainting (or runwayml/stable-diffusion-inpainting)
- VAE: stabilityai/sd-vae-ft-mse
"""

import hashlib
import json
import os
import sys
from huggingface_hub import hf_hub_download, snapshot_download

CACHE_DIR = os.environ.get(
    "FANSIVIBE_CATVTON_CACHE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkpoints")
)


def compute_sha256(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def download_catvton_weights():
    os.makedirs(CACHE_DIR, exist_ok=True)
    repo_id = "zhengchong/CatVTON"
    print(f"Downloading official CatVTON weights from {repo_id} to {CACHE_DIR}...")
    
    files = [
        "mix-48k-1024/attention/model.safetensors",
        "vitonhd-16k-512/attention/model.safetensors",
        "SCHP/exp-schp-201908261155-lip.pth",
        "SCHP/exp-schp-201908301523-atr.pth",
        "DensePose/model_final_162be9.pkl",
        "DensePose/Base-DensePose-RCNN-FPN.yaml",
        "DensePose/densepose_rcnn_R_50_FPN_s1x.yaml",
    ]
    
    manifest = {}
    for filename in files:
        target_local = os.path.join(CACHE_DIR, "CatVTON", filename)
        if os.path.exists(target_local) and os.path.getsize(target_local) > 0:
            print(f"Skipping already downloaded {filename}...")
            manifest[filename] = {
                "path": target_local,
                "size_bytes": os.path.getsize(target_local),
                "sha256": compute_sha256(target_local),
            }
            continue
        print(f"Downloading {filename}...")
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            local_dir=os.path.join(CACHE_DIR, "CatVTON"),
        )
        size_bytes = os.path.getsize(local_path)
        sha = compute_sha256(local_path)
        manifest[filename] = {
            "path": local_path,
            "size_bytes": size_bytes,
            "sha256": sha,
        }
        print(f"  -> {filename}: {size_bytes / (1024*1024):.2f} MB, sha256={sha[:12]}...")

    # Also snapshot base inpainting model components (unet + scheduler)
    base_repo = "booksforcharlie/stable-diffusion-inpainting"
    print(f"Downloading base inpainting UNet & scheduler from {base_repo}...")
    base_dir = os.path.join(CACHE_DIR, "base_inpainting")
    for sub in ["unet/config.json", "unet/diffusion_pytorch_model.bin", "scheduler/scheduler_config.json"]:
        target_local = os.path.join(base_dir, sub)
        if os.path.exists(target_local) and os.path.getsize(target_local) > 0:
            print(f"Skipping already downloaded {sub}...")
            manifest[f"base:{sub}"] = {
                "path": target_local,
                "size_bytes": os.path.getsize(target_local),
                "sha256": compute_sha256(target_local),
            }
            continue
        p = hf_hub_download(
            repo_id=base_repo,
            filename=sub,
            local_dir=base_dir,
        )
        manifest[f"base:{sub}"] = {
            "path": p,
            "size_bytes": os.path.getsize(p),
            "sha256": compute_sha256(p),
        }

    # VAE
    vae_repo = "stabilityai/sd-vae-ft-mse"
    print(f"Downloading VAE from {vae_repo}...")
    vae_dir = os.path.join(CACHE_DIR, "vae")
    for sub in ["config.json", "diffusion_pytorch_model.safetensors"]:
        target_local = os.path.join(vae_dir, sub)
        if os.path.exists(target_local) and os.path.getsize(target_local) > 0:
            print(f"Skipping already downloaded {sub}...")
            manifest[f"vae:{sub}"] = {
                "path": target_local,
                "size_bytes": os.path.getsize(target_local),
                "sha256": compute_sha256(target_local),
            }
            continue
        p = hf_hub_download(
            repo_id=vae_repo,
            filename=sub,
            local_dir=vae_dir,
        )
        manifest[f"vae:{sub}"] = {
            "path": p,
            "size_bytes": os.path.getsize(p),
            "sha256": compute_sha256(p),
        }

    manifest_path = os.path.join(CACHE_DIR, "checkpoint_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Checkpoints manifest written to {manifest_path}")
    return manifest


if __name__ == "__main__":
    download_catvton_weights()

