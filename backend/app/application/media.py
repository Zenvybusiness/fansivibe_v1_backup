"""Media helpers for image-based analysis runs.

Provider-independent (stdlib only — no AI/CV SDKs): SHA-256 content hashing
and MediaRef construction shared by the outfit and hairstyle image passes.

The persisted MediaRef carries metadata only — image bytes are hashed and
discarded, never stored, logged, or echoed in errors.
"""

from __future__ import annotations

import hashlib
import uuid as _uuid
from datetime import datetime, timezone
from uuid import UUID

from app.api.errors import validation

_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def sha256_hex(data: bytes) -> str:
    """Hex SHA-256 digest of the exact bytes received.

    Deterministic: same bytes → same digest; different bytes → different
    digest. Filenames, paths, UUIDs, and timestamps are never hashed.
    """
    return hashlib.sha256(data).hexdigest()


def read_image_bytes(image: object) -> bytes:
    """Read the actual received bytes from an uploaded image.

    Works with Starlette ``UploadFile`` (``.file`` binary stream). The stream
    is rewound first so the received payload — not a regenerated one — is
    hashed. Bytes are returned for hashing only; callers must not persist,
    log, or echo them.
    """
    file_obj = getattr(image, "file", None)
    read = getattr(file_obj, "read", None)
    if read is None:
        raise validation(
            [{"field": "image", "error": "could not read image data"}]
        )
    try:
        file_obj.seek(0)
    except Exception:
        pass
    try:
        content = read()
    except Exception:
        raise validation(
            [{"field": "image", "error": "could not read image data"}]
        )
    if not isinstance(content, (bytes, bytearray)) or len(content) == 0:
        raise validation(
            [{"field": "image", "error": "could not read image data"}]
        )
    return bytes(content)


def build_media_ref(
    *,
    user_id: UUID,
    content_type: str,
    content: bytes,
    analyzer: str | None = None,
) -> dict:
    """Build the persisted MediaRef metadata dict from received bytes.

    Shape preserved: owner-scoped logical ``key``, ``mediaType``, ``sizeBytes``
    (actual received length), hex SHA-256 ``contentHash``, ``isGenerated``
    false, ``uploadedAt``. No image bytes are included. The optional
    ``analyzer`` records the producing adapter identity (provenance) without
    touching the database schema; omitted keys keep the pre-analyzer shape
    byte-identical.
    """
    ext = _EXTENSION_BY_CONTENT_TYPE.get(content_type, "jpg")
    key = f"users/{user_id}/scans/{_uuid.uuid4()}/input.{ext}"
    media_ref = {
        "key": key,
        "mediaType": content_type,
        "sizeBytes": len(content),
        "contentHash": sha256_hex(content),
        "isGenerated": False,
        "uploadedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if analyzer is not None:
        media_ref["analyzer"] = analyzer
    return media_ref
