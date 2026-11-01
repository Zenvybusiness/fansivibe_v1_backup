"""Media upload schemas for request validation and wire responses (Stage 2 P0-4 / M16).

Conforms to:
- Strict field validation and normalization.
- Disallowed MIME types and purposes rejected with 422.
- 2MB max declared size ceiling.
- Sanitized filename hints.
- Client SHA-256 format validation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_MIME_TYPES = {"image/webp", "image/jpeg"}
ALLOWED_PURPOSES = {"wardrobe_item"}
MAX_IMAGE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB (2,097,152 bytes)


class UploadAuthorizationRequest(BaseModel):
    """Client request schema for requesting a presigned upload authorization."""

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(
        ...,
        description="Target business entity purpose. Allowed: 'wardrobe_item'",
    )
    contentType: str = Field(
        ...,
        description="Payload MIME type. Allowed: 'image/webp', 'image/jpeg'",
    )
    sizeBytes: int = Field(
        ...,
        description="Client-declared byte length (between 1 and 2,097,152 bytes)",
    )
    filename: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional original filename hint (sanitized by server)",
    )
    clientAssertionSha256: Optional[str] = Field(
        default=None,
        description="Optional client-asserted SHA-256 hash (64-char lowercase hex)",
    )

    @field_validator("purpose")
    @classmethod
    def validate_purpose(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in ALLOWED_PURPOSES:
            raise ValueError(
                f"Invalid purpose '{v}'. Allowed purposes: {', '.join(sorted(ALLOWED_PURPOSES))}"
            )
        return v_clean

    @field_validator("contentType")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        v_clean = v.strip().lower()
        if v_clean not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Invalid contentType '{v}'. Allowed formats: {', '.join(sorted(ALLOWED_MIME_TYPES))}"
            )
        return v_clean

    @field_validator("sizeBytes")
    @classmethod
    def validate_size_bytes(cls, v: int) -> int:
        if v < 1 or v > MAX_IMAGE_SIZE_BYTES:
            raise ValueError(
                f"sizeBytes must be between 1 and {MAX_IMAGE_SIZE_BYTES} bytes (2 MB)"
            )
        return v

    @field_validator("clientAssertionSha256")
    @classmethod
    def validate_client_sha256(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().lower()
            if len(v_clean) != 64 or not all(c in "0123456789abcdef" for c in v_clean):
                raise ValueError("clientAssertionSha256 must be a 64-character lowercase hex string")
            return v_clean
        return None

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().replace("\\", "/").split("/")[-1][:255]
            return v_clean if v_clean else None
        return None


class UploadAuthorizationResponse(BaseModel):
    """Wire response schema for a granted upload authorization."""

    uploadId: UUID = Field(..., description="Unique upload identifier")
    uploadUrl: str = Field(..., description="Short-lived presigned PUT URL for direct storage upload")
    stagingKey: str = Field(..., description="User-scoped staging object key in storage")
    expiresAt: datetime = Field(..., description="Expiration timestamp of the presigned URL")
    expiresInSeconds: int = Field(default=900, description="Expiration TTL in seconds (15 minutes)")
    requiredHeaders: Dict[str, str] = Field(
        default_factory=dict,
        description="Mandatory HTTP headers the client must send on the direct PUT",
    )


class UploadCompleteRequest(BaseModel):
    """Optional client request body for upload completion."""

    model_config = ConfigDict(extra="forbid")

    clientSha256: Optional[str] = Field(
        default=None,
        description="Optional client-asserted SHA-256 for double verification (64-char lowercase hex)",
    )

    @field_validator("clientSha256")
    @classmethod
    def validate_client_sha256(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = v.strip().lower()
            if len(v_clean) != 64 or not all(c in "0123456789abcdef" for c in v_clean):
                raise ValueError("clientSha256 must be a 64-character lowercase hex string")
            return v_clean
        return None


class PublishedMediaRefResponse(BaseModel):
    """Wire response schema for verified and published canonical media."""

    uploadId: UUID = Field(..., description="Unique upload identifier")
    objectKey: str = Field(..., description="Canonical storage key in cloud storage")
    mediaType: str = Field(default="image/webp", description="Canonical media MIME type")
    width: int = Field(..., description="Width of canonical image in pixels")
    height: int = Field(..., description="Height of canonical image in pixels")
    sizeBytes: int = Field(..., description="Size in bytes of canonical image")
    contentHash: str = Field(..., description="Canonical SHA-256 hex digest")
    uploadedAt: datetime = Field(..., description="Publication timestamp")
    status: str = Field(default="ready", description="Publication status")


class MediaDownloadUrlResponse(BaseModel):
    """Wire response schema for temporary presigned GET retrieval (Stage 2 P0-4 Phase 4)."""

    uploadId: UUID = Field(..., description="Unique upload identifier")
    objectKey: str = Field(..., description="Canonical storage key in cloud storage")
    downloadUrl: str = Field(..., description="Temporary presigned GET URL for media download")
    mediaType: str = Field(default="image/webp", description="Canonical media MIME type")
    width: int = Field(..., description="Width of canonical image in pixels")
    height: int = Field(..., description="Height of canonical image in pixels")
    sizeBytes: int = Field(..., description="Size in bytes of canonical image")
    contentHash: str = Field(..., description="Canonical SHA-256 hex digest")
    expiresAt: datetime = Field(..., description="Expiration timestamp of the presigned URL")
    expiresInSeconds: int = Field(default=900, description="Expiration TTL in seconds (15 minutes)")


