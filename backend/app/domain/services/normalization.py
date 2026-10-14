"""Deterministic normalization boundary for discovery source records (D2/D4).

The pipeline's stages stay explicit and distinct:

1. **raw source payload** — the untrusted value inside a
   :class:`~app.domain.ports.source_adapter.RawSourceRecord`.
2. **source adapter output** — ``RawSourceRecord`` (provider-shaped).
3. **normalized product** — :class:`NormalizedProduct` (canonical fields).
4. **validation outcome** — :class:`NormalizationResult` (accepted /
   accepted-with-missing-optional / rejected, plus errors).

Everything here is pure Python: no database, no network, and never Qwen,
MediaPipe or an LLM. Values are only ever mapped or validated — never
fabricated: a missing price, discount, rating, size, availability, source
timestamp or fashion attribute stays absent.

Source-specific parsing stays in the adapter; field mapping into the shared
canonical contract is centralized here so every source is normalized the
same way.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlsplit

from app.domain.ports.source_adapter import RawSourceRecord

# Field bounds — matched by the `products` / `product_source_map` CHECK
# constraints in migration 0026.
_TITLE_MAX = 300
_BRAND_MAX = 150
_CATEGORY_MAX = 100
_CURRENCY_MAX = 10
_SOURCE_PRODUCT_ID_MAX = 200
_URL_MAX = 2000
_MPN_MAX = 100

_CURRENCY_RE = re.compile(r"[A-Za-z]{3}\Z")
_GTIN_LENGTHS = (8, 12, 13, 14)
_GTIN_KEYS = ("gtin", "gtin14", "gtin13", "gtin12", "gtin8", "ean", "ean13", "upc", "barcode")
_MANUFACTURER_KEYS = ("mpn", "manufacturer_id", "model")
_AVAILABILITY_TRUE = {"true", "in_stock", "instock", "available", "yes"}
_AVAILABILITY_FALSE = {"false", "out_of_stock", "outofstock", "sold_out", "unavailable", "no"}


@dataclass(frozen=True)
class NormalizedProduct:
    """A canonical product, deterministically mapped from one raw record.

    Unprovided optional fields stay ``None`` (or empty) — never fabricated.
    ``image_urls`` holds provider CDN URLs only, never image binaries.
    ``gtin`` is a validated, zero-padded-to-14 stable identifier when the
    feed supplies a correct one; ``manufacturer_id`` is a non-global
    manufacturer reference (never used alone to merge products).
    """

    title: str
    source: str
    source_product_id: str
    brand: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    attributes: dict = field(default_factory=dict)
    price: Optional[float] = None
    currency: Optional[str] = None
    availability: Optional[bool] = None
    product_url: Optional[str] = None
    image_urls: tuple[str, ...] = ()
    observed_at: Optional[datetime] = None
    gtin: Optional[str] = None
    manufacturer_id: Optional[str] = None


@dataclass(frozen=True)
class NormalizationResult:
    """Outcome of normalizing one raw record.

    Exhaustive: either ``product`` is populated and ``errors`` is empty, or
    ``product`` is ``None`` and ``errors`` explains every validation failure.
    ``missing`` lists accepted-but-absent optional fields so callers can
    distinguish a complete record from a sparse one.
    """

    product: Optional[NormalizedProduct]
    errors: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.product is not None and not self.errors

    @property
    def status(self) -> str:
        """``accepted`` | ``accepted_with_missing_optional`` | ``rejected``."""
        if not self.ok:
            return "rejected"
        return "accepted_with_missing_optional" if self.missing else "accepted"


def payload_hash(payload: object) -> str:
    """Deterministic SHA-256 of a structured payload.

    Canonical JSON (sorted keys, compact separators) makes the digest
    independent of key order and whitespace, so identical payloads hash
    identically and ``raw_source_records`` never duplicates them.
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_text(value: str) -> str:
    """NFC-normalize, drop control characters, collapse whitespace, strip.

    Unicode is preserved (multilingual titles survive); only invisible noise
    is removed, so normalization is deterministic and lossless for visible
    text.
    """
    text = unicodedata.normalize("NFC", value)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cc")
    return " ".join(text.split())


def _clean_required_str(
    value: object, *, max_len: int, field: str, errors: list[str]
) -> Optional[str]:
    if value is None:
        errors.append(f"{field} is required")
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return None
    text = _normalize_text(value)
    if not text:
        errors.append(f"{field} must be a non-empty string")
        return None
    if len(text) > max_len:
        errors.append(f"{field} exceeds {max_len} characters")
        return None
    return text


def _clean_optional_str(
    value: object, *, max_len: int, field: str, errors: list[str]
) -> Optional[str]:
    """Optional string: absent/blank -> ``None``; wrong type/length -> error."""
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append(f"{field} must be a string")
        return None
    text = _normalize_text(value)
    if not text:
        return None
    if len(text) > max_len:
        errors.append(f"{field} exceeds {max_len} characters")
        return None
    return text


def _clean_price(value: object, errors: list[str]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append("price must be a number")
        return None
    if not math.isfinite(value):
        errors.append("price must be a finite number")
        return None
    if value < 0:
        errors.append("price must be >= 0")
        return None
    return float(value)


def _clean_currency(value: object, errors: list[str]) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        errors.append("currency must be a 3-letter code")
        return None
    text = _normalize_text(value)
    if not text:
        return None
    if not _CURRENCY_RE.fullmatch(text):
        errors.append("currency must be a 3-letter code")
        return None
    return text.upper()


def _clean_availability(value: object, errors: list[str]) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        key = _normalize_text(value).lower()
        if key in _AVAILABILITY_TRUE:
            return True
        if key in _AVAILABILITY_FALSE:
            return False
    errors.append("availability must be a boolean")
    return None


def _clean_url(value: object, *, allow_relative: bool = False) -> Optional[str]:
    """An absolute ``http(s)`` URL, optional root-relative path, or ``None``."""
    if not isinstance(value, str):
        return None
    text = _normalize_text(value)
    if not text or len(text) > _URL_MAX:
        return None
    if allow_relative and text.startswith("/"):
        return text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    return text


def _gtin_check_digit_ok(code: str) -> bool:
    digits = [int(ch) for ch in code]
    check = digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - (total % 10)) % 10 == check


def _clean_gtin(value: object) -> Optional[str]:
    """A valid GTIN/EAN/UPC normalized to 14 digits, else ``None``.

    An invalid or bogus code is ignored (treated as absent), never corrected
    or fabricated.
    """
    if value is None:
        return None
    text = str(value).strip() if isinstance(value, (str, int)) else ""
    if not text.isdigit() or len(text) not in _GTIN_LENGTHS:
        return None
    if not _gtin_check_digit_ok(text):
        return None
    return text.zfill(14)


def _first(payload: dict, *keys: str):
    for key in keys:
        if payload.get(key) is not None:
            return payload[key]
    return None


def normalize_product(raw: RawSourceRecord) -> NormalizationResult:
    """Map one :class:`RawSourceRecord` to a :class:`NormalizedProduct`.

    Deterministic and total: it always returns a result and never raises for
    bad data — invalid input surfaces as ``errors`` with ``product=None``.
    """
    errors: list[str] = []
    payload = raw.payload
    if not isinstance(payload, dict):
        return NormalizationResult(
            product=None,
            errors=("payload must be a mapping",),
        )

    title = _clean_required_str(
        _first(payload, "title", "name"),
        max_len=_TITLE_MAX,
        field="title",
        errors=errors,
    )

    source_product_id = _clean_required_str(
        raw.source_record_id
        if raw.source_record_id is not None
        else _first(payload, "source_product_id", "product_id", "id", "sku"),
        max_len=_SOURCE_PRODUCT_ID_MAX,
        field="source_product_id",
        errors=errors,
    )

    brand = _clean_optional_str(
        payload.get("brand"), max_len=_BRAND_MAX, field="brand", errors=errors
    )
    category = _clean_optional_str(
        payload.get("category"), max_len=_CATEGORY_MAX, field="category", errors=errors
    )
    subcategory = _clean_optional_str(
        payload.get("subcategory"), max_len=_CATEGORY_MAX, field="subcategory", errors=errors
    )
    price = _clean_price(payload.get("price"), errors)
    currency = _clean_currency(payload.get("currency"), errors)
    availability = _clean_availability(payload.get("availability"), errors)

    product_url = None
    raw_product_url = _first(payload, "product_url", "url")
    if raw_product_url is not None:
        product_url = _clean_url(raw_product_url)
        if product_url is None:
            errors.append("product_url must be a valid http(s) URL")

    image_urls: list[str] = []
    raw_images = _first(payload, "image_urls", "images", "image_url")
    if raw_images is not None:
        entries = raw_images if isinstance(raw_images, (list, tuple)) else [raw_images]
        for entry in entries:
            url = _clean_url(entry, allow_relative=True)
            if url is None:
                errors.append("image_urls must contain valid http(s) URLs")
                break
            image_urls.append(url)

    attributes = payload.get("attributes")
    if attributes is None:
        attributes = {}
    elif not isinstance(attributes, dict):
        errors.append("attributes must be a mapping")
        attributes = {}

    gtin = _clean_gtin(_first(payload, *_GTIN_KEYS))
    manufacturer_id = _clean_optional_str(
        _first(payload, *_MANUFACTURER_KEYS),
        max_len=_MPN_MAX,
        field="manufacturer_id",
        errors=errors,
    )

    if errors:
        return NormalizationResult(product=None, errors=tuple(errors))

    missing = tuple(
        name
        for name, value in (
            ("brand", brand),
            ("category", category),
            ("subcategory", subcategory),
            ("attributes", attributes or None),
            ("price", price),
            ("currency", currency),
            ("availability", availability),
            ("product_url", product_url),
            ("image_urls", image_urls or None),
            ("gtin", gtin),
            ("manufacturer_id", manufacturer_id),
        )
        if value is None
    )

    product = NormalizedProduct(
        title=title,
        source=raw.source,
        source_product_id=source_product_id,
        brand=brand,
        category=category,
        subcategory=subcategory,
        attributes=attributes,
        price=price,
        currency=currency,
        availability=availability,
        product_url=product_url,
        image_urls=tuple(image_urls),
        observed_at=raw.source_timestamp,
        gtin=gtin,
        manufacturer_id=manufacturer_id,
    )
    return NormalizationResult(product=product, missing=missing)
