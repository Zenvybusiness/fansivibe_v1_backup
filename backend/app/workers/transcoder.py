"""Isolated image transcoding worker and process manager (Stage 2 P0-4 Phase 3).

Executes safe, aspect-preserving image canonicalization inside an isolated child
CLI subprocess with strict resource bounds:
- RLIMIT_AS = 256MB on Linux.
- Max input: 12 megapixels (12_000_000 pixels) and max edge 4096px.
- Pillow decompression-bomb protections enabled.
- EXIF orientation normalization (auto-rotation).
- Stripping of all EXIF, GPS, XMP, and comments metadata.
- Resampling: Lanczos aspect-preserving downscaling to max edge 1920px (no upscaling).
- Canonical output: WebP (Quality 85 primary).
- 5.0-second processing timeout with SIGKILL and mandatory reaping.
- Worker-level concurrency limiter: 1 active child per Uvicorn worker.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

# --- Pipeline Constants ---

MAX_INPUT_PIXELS = 12_000_000  # 12 Megapixels
MAX_INPUT_EDGE = 4096          # Max single dimension in pixels
CANONICAL_MAX_EDGE = 1920      # Garment master longest edge
CANONICAL_QUALITY = 85         # Primary WebP quality
MAX_CANONICAL_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB ceiling
RLIMIT_AS_BYTES = 256 * 1024 * 1024          # 256 MB address space limit
DEFAULT_TIMEOUT_SECONDS = 5.0                # 5.0s child timeout


# --- Exception Taxonomy ---


class TranscodingError(Exception):
    """Base exception for transcoding and image validation failures."""

    def __init__(self, message: str, *, code: str = "TRANSCODING_FAILED") -> None:
        super().__init__(message)
        self.message = message
        self.code = code

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


class ImageValidationError(TranscodingError):
    """Raised when an uploaded image fails validation (signature, bounds, bombs)."""


class TranscodingTimeoutError(TranscodingError):
    """Raised when the child transcoding process exceeds the 5.0s processing deadline."""


class MemoryLimitExceededError(TranscodingError):
    """Raised when the child process address space exceeds the 256MB limit."""


# --- Data Transfer Objects ---


@dataclass(frozen=True)
class TranscodingResult:
    """Structured processing metadata and canonical WebP bytes."""

    canonical_bytes: bytes
    canonical_sha256: str
    canonical_size_bytes: int
    width: int
    height: int
    format: str = "image/webp"
    original_format: str = "image/jpeg"
    original_width: int = 0
    original_height: int = 0


# --- Process Manager (Parent Process) ---


class TranscoderProcessManager:
    """Parent process orchestrator for isolated child process transcoding."""

    _semaphore: Optional[asyncio.Semaphore] = None
    _semaphore_loop: Optional[asyncio.AbstractEventLoop] = None

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_edge: int = CANONICAL_MAX_EDGE,
        quality: int = CANONICAL_QUALITY,
        semaphore_timeout_seconds: float = 5.0,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_edge = max_edge
        self.quality = quality
        self.semaphore_timeout_seconds = semaphore_timeout_seconds

    @classmethod
    def get_semaphore(cls) -> asyncio.Semaphore:
        """Worker-level singleton semaphore ensuring 1 child process per worker."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if cls._semaphore is None or (loop is not None and cls._semaphore_loop is not loop):
            cls._semaphore = asyncio.Semaphore(1)
            cls._semaphore_loop = loop
        return cls._semaphore

    async def transcode(self, raw_bytes: bytes) -> TranscodingResult:
        """Transcode raw image bytes into canonical WebP within an isolated child process.

        Guarantees:
        - Strict concurrency: awaits the worker semaphore with bounded wait timeout.
        - Hard timeout: sends SIGKILL on 5.0s timeout and awaits `wait()` to reap PID.
        - Guaranteed temp file cleanup on all execution paths (success, failure, cancellation).
        """
        if not raw_bytes:
            raise ImageValidationError("Empty image payload received", code="EMPTY_OBJECT")

        # Basic pre-flight magic-byte check before spawning child
        if len(raw_bytes) < 12:
            raise ImageValidationError(
                "Image payload too small to be valid", code="INVALID_FILE_SIGNATURE"
            )
        is_jpeg = raw_bytes[:3] == b"\xff\xd8\xff"
        is_webp = raw_bytes[:4] == b"RIFF" and raw_bytes[8:12] == b"WEBP"
        if not (is_jpeg or is_webp):
            raise ImageValidationError(
                "File signature is neither JPEG nor WebP", code="INVALID_FILE_SIGNATURE"
            )

        sem = self.get_semaphore()
        try:
            await asyncio.wait_for(sem.acquire(), timeout=self.semaphore_timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "Transcoder semaphore wait timed out after %.1fs",
                self.semaphore_timeout_seconds,
            )
            raise TranscodingTimeoutError(
                f"Transcoder semaphore wait timed out after {self.semaphore_timeout_seconds} seconds",
                code="TRANSCODING_TIMEOUT",
            )

        try:
            return await self._execute_transcoding_subprocess(raw_bytes)
        finally:
            sem.release()

    async def _execute_transcoding_subprocess(self, raw_bytes: bytes) -> TranscodingResult:
        # Create temporary input and output files
        input_fd, input_path = tempfile.mkstemp(prefix="fv_in_", suffix=".tmp")
        output_fd, output_path = tempfile.mkstemp(prefix="fv_out_", suffix=".webp")
        meta_fd, meta_path = tempfile.mkstemp(prefix="fv_meta_", suffix=".json")

        # Write raw bytes and close descriptors
        try:
            with os.fdopen(input_fd, "wb") as f:
                f.write(raw_bytes)
            os.close(output_fd)
            os.close(meta_fd)

            cmd = [
                sys.executable,
                "-m",
                "app.workers.transcoder",
                "--input",
                input_path,
                "--output",
                output_path,
                "--meta-out",
                meta_path,
                "--max-edge",
                str(self.max_edge),
                "--quality",
                str(self.quality),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=self.timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Transcoder subprocess PID %s timed out after %ss; terminating with SIGKILL",
                    proc.pid,
                    self.timeout_seconds,
                )
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()  # Mandatory reaping
                raise TranscodingTimeoutError(
                    f"Image processing timed out after {self.timeout_seconds} seconds",
                    code="TRANSCODING_TIMEOUT",
                )
            except asyncio.CancelledError:
                logger.warning(
                    "Transcoding task was cancelled; killing child PID %s", proc.pid
                )
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                await proc.wait()
                raise

            # Check process return code
            if proc.returncode != 0:
                err_data = self._read_error_json(meta_path, stderr_b, proc.returncode)
                err_code = err_data.get("error_code", "TRANSCODING_FAILED")
                err_msg = err_data.get("error_message", "Transcoder process failed")

                if err_code in (
                    "INVALID_FILE_SIGNATURE",
                    "UNSUPPORTED_FORMAT",
                    "DIMENSIONS_EXCEEDED",
                    "DECOMPRESSION_BOMB",
                    "CORRUPT_IMAGE",
                    "PRIVACY_VIOLATION",
                ):
                    raise ImageValidationError(err_msg, code=err_code)
                elif err_code == "MEMORY_LIMIT_EXCEEDED":
                    raise MemoryLimitExceededError(err_msg, code=err_code)
                elif err_code == "TRANSCODING_TIMEOUT":
                    raise TranscodingTimeoutError(err_msg, code=err_code)
                else:
                    raise TranscodingError(err_msg, code=err_code)

            # Read canonical output bytes
            canonical_bytes = Path(output_path).read_bytes()
            if not canonical_bytes:
                raise TranscodingError(
                    "Child process produced empty canonical output",
                    code="TRANSCODING_FAILED",
                )

            # Read metadata JSON
            meta_json = json.loads(Path(meta_path).read_text(encoding="utf-8"))

            return TranscodingResult(
                canonical_bytes=canonical_bytes,
                canonical_sha256=meta_json["sha256"],
                canonical_size_bytes=meta_json["size_bytes"],
                width=meta_json["width"],
                height=meta_json["height"],
                format="image/webp",
                original_format=meta_json.get("original_format", "image/jpeg"),
                original_width=meta_json.get("original_width", meta_json["width"]),
                original_height=meta_json.get("original_height", meta_json["height"]),
            )

        finally:
            # Clean up all temporary files on all execution paths
            for p in (input_path, output_path, meta_path):
                try:
                    if os.path.exists(p):
                        os.unlink(p)
                except Exception:
                    pass

    @staticmethod
    def _read_error_json(meta_path: str, stderr_b: bytes, returncode: int) -> dict:
        """Extract structured error JSON from metadata file or stderr."""
        try:
            if os.path.exists(meta_path):
                content = Path(meta_path).read_text(encoding="utf-8").strip()
                if content:
                    data = json.loads(content)
                    if isinstance(data, dict) and not data.get("success", True):
                        return data
        except Exception:
            pass

        # Try parsing stderr
        if stderr_b:
            try:
                line = stderr_b.decode("utf-8", errors="replace").strip().splitlines()[-1]
                data = json.loads(line)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass

        if returncode == -9 or returncode == 137:
            return {
                "error_code": "TRANSCODING_TIMEOUT",
                "error_message": "Process was terminated by SIGKILL",
            }
        return {
            "error_code": "TRANSCODING_FAILED",
            "error_message": f"Worker exited with status {returncode}",
        }


# --- Subprocess CLI Implementation (Child Process) ---


def _apply_resource_limits() -> None:
    """Set Linux address-space memory limit (RLIMIT_AS = 256MB)."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (RLIMIT_AS_BYTES, RLIMIT_AS_BYTES))
    except (ImportError, ValueError, OSError):
        # On non-Linux or unsupported platforms, proceed without setrlimit
        pass


def _write_error(meta_path: Optional[str], code: str, message: str) -> None:
    """Write structured failure JSON to meta file and stderr."""
    payload = {
        "success": False,
        "error_code": code,
        "error_message": message,
    }
    encoded = json.dumps(payload)
    if meta_path:
        try:
            Path(meta_path).write_text(encoded, encoding="utf-8")
        except Exception:
            pass
    sys.stderr.write(f"{encoded}\n")
    sys.stderr.flush()


def run_transcoder(
    input_path: str,
    output_path: str,
    meta_path: Optional[str] = None,
    max_edge: int = CANONICAL_MAX_EDGE,
    quality: int = CANONICAL_QUALITY,
) -> None:
    """Execute isolated image transcoding pipeline adhering strictly to security bounds."""
    # 1. Read input bytes
    input_bytes = Path(input_path).read_bytes()
    if not input_bytes:
        _write_error(meta_path, "EMPTY_OBJECT", "Input image is empty")
        sys.exit(2)

    # 2. Signature verification
    if len(input_bytes) < 12:
        _write_error(meta_path, "INVALID_FILE_SIGNATURE", "Input bytes too short for valid image")
        sys.exit(2)

    is_jpeg = input_bytes[:3] == b"\xff\xd8\xff"
    is_webp = input_bytes[:4] == b"RIFF" and input_bytes[8:12] == b"WEBP"
    if not (is_jpeg or is_webp):
        _write_error(
            meta_path,
            "INVALID_FILE_SIGNATURE",
            "File signature matches neither JPEG nor WebP magic bytes",
        )
        sys.exit(2)

    # 3. Configure Pillow
    import warnings
    from PIL import Image, ImageFile, ImageOps
    from PIL.Image import DecompressionBombError

    Image.MAX_IMAGE_PIXELS = MAX_INPUT_PIXELS
    warnings.simplefilter("error", Image.DecompressionBombWarning)
    ImageFile.LOAD_TRUNCATED_IMAGES = False

    try:
        bio = io.BytesIO(input_bytes)
        with Image.open(bio) as img:
            orig_format = img.format
            if orig_format not in ("JPEG", "WEBP"):
                _write_error(
                    meta_path,
                    "UNSUPPORTED_FORMAT",
                    f"Detected format {orig_format} is not permitted (only JPEG/WebP)",
                )
                sys.exit(2)

            orig_w, orig_h = img.size
            if orig_w * orig_h > MAX_INPUT_PIXELS or orig_w > MAX_INPUT_EDGE or orig_h > MAX_INPUT_EDGE:
                _write_error(
                    meta_path,
                    "DIMENSIONS_EXCEEDED",
                    f"Dimensions {orig_w}x{orig_h} exceed safety ceilings (12MP, 4096px)",
                )
                sys.exit(2)

            # 4. Safe raster decode
            img.load()

            # 5. EXIF orientation normalization
            try:
                img = ImageOps.exif_transpose(img)
            except Exception:
                pass

            # 6. Color mode normalization
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                target_mode = "RGBA"
            else:
                target_mode = "RGB"

            if img.mode != target_mode:
                img = img.convert(target_mode)

            # 7. Privacy scrubbing: discard info dictionary
            img.info = {}

            # 8. Aspect-preserving Lanczos downscaling (no upscaling)
            if max(img.size) > max_edge:
                img.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)

            out_w, out_h = img.size

            # 9. Canonical WebP re-encoding with deterministic step-down if > 2MB
            encoded_bytes = None
            for q in [quality, 80, 75]:
                buf = io.BytesIO()
                img.save(buf, format="WEBP", quality=q, method=4)
                candidate = buf.getvalue()
                if len(candidate) <= MAX_CANONICAL_SIZE_BYTES:
                    encoded_bytes = candidate
                    break

            if encoded_bytes is None:
                # Step-down dimensions 10% down to floor 1280px / Q70
                stepped_img = img.copy()
                while max(stepped_img.size) > 1280:
                    new_w = max(1, int(stepped_img.size[0] * 0.9))
                    new_h = max(1, int(stepped_img.size[1] * 0.9))
                    stepped_img = stepped_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    stepped_img.save(buf, format="WEBP", quality=70, method=4)
                    candidate = buf.getvalue()
                    if len(candidate) <= MAX_CANONICAL_SIZE_BYTES:
                        encoded_bytes = candidate
                        out_w, out_h = stepped_img.size
                        break

            if encoded_bytes is None or len(encoded_bytes) > MAX_CANONICAL_SIZE_BYTES:
                _write_error(
                    meta_path,
                    "OUTPUT_SIZE_EXCEEDED",
                    "Encoded canonical WebP exceeds 2MB size ceiling",
                )
                sys.exit(2)

            # 10. Privacy check: verify output contains zero EXIF / GPS tags
            with Image.open(io.BytesIO(encoded_bytes)) as check_img:
                check_exif = check_img.getexif()
                if check_exif and (0x8825 in check_exif or len(check_exif) > 0):
                    _write_error(
                        meta_path,
                        "PRIVACY_VIOLATION",
                        "Failed to strip sensitive EXIF/GPS metadata from canonical image",
                    )
                    sys.exit(2)

            # 11. Write canonical WebP to destination
            Path(output_path).write_bytes(encoded_bytes)

            # 12. Calculate SHA-256 and produce metadata
            canonical_sha256 = hashlib.sha256(encoded_bytes).hexdigest()
            meta_payload = {
                "success": True,
                "width": out_w,
                "height": out_h,
                "size_bytes": len(encoded_bytes),
                "sha256": canonical_sha256,
                "format": "WEBP",
                "original_format": orig_format,
                "original_width": orig_w,
                "original_height": orig_h,
            }

            meta_json = json.dumps(meta_payload)
            if meta_path:
                Path(meta_path).write_text(meta_json, encoding="utf-8")
            sys.stdout.write(f"{meta_json}\n")
            sys.stdout.flush()

    except (DecompressionBombError, Image.DecompressionBombWarning) as exc:
        _write_error(meta_path, "DECOMPRESSION_BOMB", f"Decompression bomb detected: {exc}")
        sys.exit(2)
    except MemoryError:
        _write_error(meta_path, "MEMORY_LIMIT_EXCEEDED", "Process address space limit (256MB) exceeded")
        sys.exit(3)
    except Exception as exc:
        if "DecompressionBomb" in type(exc).__name__:
            _write_error(meta_path, "DECOMPRESSION_BOMB", f"Decompression bomb detected: {exc}")
            sys.exit(2)
        _write_error(meta_path, "CORRUPT_IMAGE", f"Image decoding failed: {exc}")
        sys.exit(2)


def main() -> None:
    """CLI entrypoint for standalone image transcoding process."""
    _apply_resource_limits()

    parser = argparse.ArgumentParser(description="Fansivibe image transcoder worker")
    parser.add_argument("--input", required=True, help="Path to input image file")
    parser.add_argument("--output", required=True, help="Path to write canonical WebP output")
    parser.add_argument("--meta-out", default=None, help="Path to write JSON processing metadata")
    parser.add_argument("--max-edge", type=int, default=CANONICAL_MAX_EDGE, help="Max edge in pixels")
    parser.add_argument("--quality", type=int, default=CANONICAL_QUALITY, help="WebP quality (0-100)")

    args = parser.parse_args()

    run_transcoder(
        input_path=args.input,
        output_path=args.output,
        meta_path=args.meta_out,
        max_edge=args.max_edge,
        quality=args.quality,
    )


if __name__ == "__main__":
    main()
