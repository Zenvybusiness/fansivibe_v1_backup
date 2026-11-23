"""Download official CatVTON code and test assets from Hugging Face Space.

Repository: https://huggingface.co/spaces/zhengchong/CatVTON
License: CC BY-NC-SA 4.0 (Non-commercial research only)
"""

import json
import os
import urllib.request

HF_SPACE = "zhengchong/CatVTON"
BASE_URL = f"https://huggingface.co/spaces/{HF_SPACE}/raw/main"
API_TREE_URL = f"https://huggingface.co/api/spaces/{HF_SPACE}/tree/main?recursive=true"
DEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catvton_code")


def fetch_file(path: str, dest_path: str) -> None:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        return
    url = f"{BASE_URL}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Fansivibe-Research/1.0"})
    try:
        with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as f:
            f.write(resp.read())
        print(f"Downloaded: {path} -> {dest_path}")
    except Exception as e:
        print(f"Failed to download {path}: {e}")


def main() -> None:
    req = urllib.request.Request(API_TREE_URL, headers={"User-Agent": "Fansivibe-Research/1.0"})
    with urllib.request.urlopen(req) as resp:
        items = json.loads(resp.read().decode("utf-8"))

    # Relevant paths: model/, utils.py, densepose/, and demo examples
    target_prefixes = ("model/", "densepose/", "resource/demo/example/")
    target_files = ("utils.py", "requirements.txt", "README.md")

    files_to_download = []
    for item in items:
        if item.get("type") == "file":
            path = item.get("path", "")
            if path.endswith(".pyc") or path.endswith(".DS_Store"):
                continue
            if path in target_files or any(path.startswith(p) for p in target_prefixes):
                files_to_download.append(path)

    print(f"Found {len(files_to_download)} files to download from {HF_SPACE}...")
    for p in files_to_download:
        dest = os.path.join(DEST_DIR, p)
        fetch_file(p, dest)
    print("Done downloading official CatVTON code and assets.")


if __name__ == "__main__":
    main()

