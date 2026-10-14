"""Amazon India Fashion Catalog source adapter (DISCOVERY-10B-4).

Conforms to ``SourceAdapter`` and provides structured catalog ingestion
for authentic Indian fashion e-commerce inventory.

Supports two authorized integration channels:
1. Direct Amazon Product Advertising API 5.0 (PA-API 5.0) with AWS SigV4 signing.
2. Rainforest API commercial Amazon.in catalog & search proxy (bootstrap fallback).

Offline / Safety Guarantee:
- If credentials are not configured in environment or passed directly,
  ``fetch_batch`` fails closed with ``SourceAuthError``.
- Never makes unauthorized network calls and never fabricates mock responses.
- Images are strictly direct CDN hotlinks (m.media-amazon.com); zero local binary hosting.
- Ingestion records are marked with ``fixture: False``; never touches synthetic demo data.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

from app.config.settings import get_settings
from app.domain.ports.source_adapter import (
    RawSourceRecord,
    SourceAdapter,
    SourceAuthError,
    SourceError,
    SourcePayloadError,
    SourceRateLimitError,
    SourceTransientError,
    SourceBatch,
)

logger = logging.getLogger(__name__)

SOURCE_AMAZON_IN = "amazon_in"
DEFAULT_AMAZON_MARKETPLACE = "www.amazon.in"
DEFAULT_PAAPI_ENDPOINT = "webservices.amazon.in"
DEFAULT_PAAPI_REGION = "eu-west-1"
DEFAULT_RAINFOREST_ENDPOINT = "https://api.rainforestapi.com/request"
DEFAULT_PACE_INTERVAL_S = 1.0  # Amazon 1 req/sec policy
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE_S = 0.5


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_signature_key(key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
    k_date = _sign(("AWS4" + key).encode("utf-8"), date_stamp)
    k_region = _sign(k_date, region_name)
    k_service = _sign(k_region, service_name)
    k_signing = _sign(k_service, "aws4_request")
    return k_signing


def _generate_sigv4_headers(
    *,
    access_key: str,
    secret_key: str,
    region: str,
    host: str,
    target: str,
    payload_str: str,
    amz_date: datetime,
) -> dict[str, str]:
    """Generate AWS Signature Version 4 authentication headers for PA-API 5.0."""
    service = "ProductAdvertisingAPI"
    date_stamp = amz_date.strftime("%Y%m%d")
    amz_date_str = amz_date.strftime("%Y%m%dT%H%M%SZ")

    canonical_uri = "/paapi5/searchitems"
    canonical_querystring = ""
    payload_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    canonical_headers = (
        f"content-encoding:amz-1.0\n"
        f"content-type:application/json; charset=utf-8\n"
        f"host:{host}\n"
        f"x-amz-date:{amz_date_str}\n"
        f"x-amz-target:{target}\n"
    )
    signed_headers = "content-encoding;content-type;host;x-amz-date;x-amz-target"

    canonical_request = (
        f"POST\n"
        f"{canonical_uri}\n"
        f"{canonical_querystring}\n"
        f"{canonical_headers}\n"
        f"{signed_headers}\n"
        f"{payload_hash}"
    )

    algorithm = "AWS4-HMAC-SHA256"
    credential_scope = f"{date_stamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n"
        f"{amz_date_str}\n"
        f"{credential_scope}\n"
        f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
    )

    signing_key = _get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization_header = (
        f"{algorithm} Credential={access_key}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )

    return {
        "content-encoding": "amz-1.0",
        "content-type": "application/json; charset=utf-8",
        "host": host,
        "x-amz-date": amz_date_str,
        "x-amz-target": target,
        "Authorization": authorization_header,
    }


def _append_affiliate_tag(url: str, tag: Optional[str]) -> str:
    """Safely append Amazon Associate Tag to product destination URL."""
    if not tag or not url:
        return url
    try:
        parsed = urlparse(url)
        params = dict(parse_qsl(parsed.query))
        if "tag" not in params:
            params["tag"] = tag
            new_query = urlencode(params)
            return urlunparse((
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            ))
        return url
    except Exception:
        return url


class AmazonProductAdapter:
    """Source adapter for Amazon India fashion inventory conforming to ``SourceAdapter``."""

    source_id = SOURCE_AMAZON_IN

    def __init__(
        self,
        *,
        http_client: Optional[httpx.Client] = None,
        associate_tag: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region: Optional[str] = None,
        rainforest_api_key: Optional[str] = None,
        search_query: str = "fashion",
        category: str = "apparel",
        pace_interval_s: float = DEFAULT_PACE_INTERVAL_S,
        request_timeout_s: float = DEFAULT_TIMEOUT_S,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
        records: Optional[Sequence[RawSourceRecord]] = None,
    ) -> None:
        settings = get_settings()
        self._associate_tag = associate_tag or settings.amazon_associate_tag
        self._access_key = access_key or settings.amazon_paapi_access_key
        self._secret_key = secret_key or settings.amazon_paapi_secret_key
        self._region = region or settings.amazon_paapi_region or DEFAULT_PAAPI_REGION
        self._rainforest_api_key = rainforest_api_key or settings.rainforest_api_key

        self._search_query = search_query
        self._category = category
        self._pace_interval_s = max(0.0, pace_interval_s)
        self._request_timeout_s = max(0.1, request_timeout_s)
        self._max_retries = max(0, max_retries)
        self._backoff_base_s = max(0.01, backoff_base_s)

        self._client = http_client or httpx.Client(timeout=self._request_timeout_s)
        self._owns_client = http_client is None
        self._records = tuple(records) if records is not None else None
        self._last_request_monotonic: float = 0.0

    @property
    def has_credentials(self) -> bool:
        """True if either direct PA-API or Rainforest API credentials are configured."""
        if self._records is not None:
            return True
        paapi_ready = bool(self._access_key and self._secret_key and self._associate_tag)
        rainforest_ready = bool(self._rainforest_api_key)
        return paapi_ready or rainforest_ready

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AmazonProductAdapter:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_batch(
        self,
        *,
        continuation: Optional[str] = None,
        limit: int = 50,
    ) -> SourceBatch:
        """Fetch a batch of raw Amazon.in records conforming to SourceAdapter."""
        # Offline replay mode with seeded records
        if self._records is not None:
            start = int(continuation) if continuation is not None else 0
            chunk = self._records[start : start + limit]
            next_start = start + len(chunk)
            nxt = str(next_start) if next_start < len(self._records) else None
            return SourceBatch(source=self.source_id, records=chunk, continuation=nxt)

        # Safety boundary: fail closed when live credentials are not configured
        if not self.has_credentials:
            raise SourceAuthError(
                "Amazon product ingestion credentials are not configured in environment. "
                "Provide AMAZON_PAAPI_ACCESS_KEY / AMAZON_PAAPI_SECRET_KEY / AMAZON_ASSOCIATE_TAG "
                "or RAINFOREST_API_KEY."
            )

        page = int(continuation) if continuation is not None else 1

        # Prefer direct PA-API 5.0 if configured; otherwise use Rainforest API
        if self._access_key and self._secret_key and self._associate_tag:
            return self._fetch_paapi_batch(page=page, limit=limit)
        elif self._rainforest_api_key:
            return self._fetch_rainforest_batch(page=page, limit=limit)

        raise SourceAuthError("No valid provider authentication method found")

    def _apply_pacing(self) -> None:
        """Enforce rate-limiting interval between successive requests."""
        if self._pace_interval_s > 0.0 and self._last_request_monotonic > 0.0:
            elapsed = time.monotonic() - self._last_request_monotonic
            remaining = self._pace_interval_s - elapsed
            if remaining > 0.0:
                time.sleep(remaining)
        self._last_request_monotonic = time.monotonic()

    def _fetch_paapi_batch(self, *, page: int, limit: int) -> SourceBatch:
        """Query Amazon PA-API 5.0 SearchItems endpoint."""
        host = DEFAULT_PAAPI_ENDPOINT
        target = "com.amazon.paapi5.v1.ProductAdvertisingAPIv1.SearchItems"
        endpoint = f"https://{host}/paapi5/searchitems"

        # PA-API ItemCount is max 10 per request; ItemPage is 1..10
        item_count = min(10, max(1, limit))
        payload_dict = {
            "Keywords": self._search_query,
            "SearchIndex": "Apparel",
            "ItemCount": item_count,
            "ItemPage": page,
            "PartnerTag": self._associate_tag,
            "PartnerType": "Associates",
            "Marketplace": DEFAULT_AMAZON_MARKETPLACE,
            "Resources": [
                "Images.Primary.Large",
                "ItemInfo.Title",
                "ItemInfo.ByLineInfo",
                "ItemInfo.Classifications",
                "ItemInfo.Features",
                "ItemInfo.ManufactureInfo",
                "Offers.Listings.Price",
                "Offers.Listings.SavingBasis",
                "Offers.Listings.Availability.Message",
                "Offers.Listings.Availability.Type",
            ],
        }
        payload_str = json.dumps(payload_dict)

        headers = _generate_sigv4_headers(
            access_key=self._access_key or "",
            secret_key=self._secret_key or "",
            region=self._region,
            host=host,
            target=target,
            payload_str=payload_str,
            amz_date=datetime.now(timezone.utc),
        )

        response = self._execute_request(
            method="POST",
            url=endpoint,
            headers=headers,
            content=payload_str.encode("utf-8"),
        )

        try:
            data = response.json()
        except Exception as exc:
            raise SourcePayloadError(f"PA-API returned non-JSON payload: {exc}") from exc

        if not isinstance(data, dict):
            raise SourcePayloadError("PA-API response must be a JSON object")

        # Handle API errors
        errors = data.get("Errors")
        if errors and isinstance(errors, list):
            err_code = (errors[0].get("Code") or "").lower()
            err_msg = errors[0].get("Message") or "PA-API error"
            if "noteligible" in err_code or "unauthorized" in err_code:
                raise SourceAuthError(f"PA-API authorization failed: {err_msg}")
            if "toomanyrequests" in err_code or "throttl" in err_code:
                raise SourceRateLimitError(f"PA-API rate limit reached: {err_msg}")

        search_result = data.get("SearchResult", {})
        raw_items = search_result.get("Items", [])
        if not isinstance(raw_items, list):
            raw_items = []

        total_result_count = search_result.get("TotalResultCount", 0)
        max_pages = min(10, (total_result_count + item_count - 1) // item_count) if total_result_count else 10
        next_continuation = str(page + 1) if page < max_pages and len(raw_items) > 0 else None

        records: list[RawSourceRecord] = []
        for item in raw_items:
            rec = self._parse_paapi_item(item)
            if rec is not None:
                records.append(rec)

        return SourceBatch(
            source=self.source_id,
            records=tuple(records),
            continuation=next_continuation,
        )

    def _fetch_rainforest_batch(self, *, page: int, limit: int) -> SourceBatch:
        """Query Rainforest API Amazon.in Search proxy."""
        params = {
            "api_key": self._rainforest_api_key,
            "amazon_domain": "amazon.in",
            "type": "search",
            "search_term": self._search_query,
            "page": str(page),
        }

        response = self._execute_request(
            method="GET",
            url=DEFAULT_RAINFOREST_ENDPOINT,
            params=params,
        )

        try:
            data = response.json()
        except Exception as exc:
            raise SourcePayloadError(f"Rainforest returned non-JSON payload: {exc}") from exc

        if not isinstance(data, dict):
            raise SourcePayloadError("Rainforest response must be a JSON object")

        pagination = data.get("pagination", {})
        total_pages = pagination.get("total_pages", 1)
        next_continuation = str(page + 1) if page < total_pages else None

        raw_items = data.get("search_results", [])
        if not isinstance(raw_items, list):
            raw_items = []

        records: list[RawSourceRecord] = []
        for item in raw_items:
            rec = self._parse_rainforest_item(item)
            if rec is not None:
                records.append(rec)

        return SourceBatch(
            source=self.source_id,
            records=tuple(records),
            continuation=next_continuation,
        )

    def _execute_request(
        self,
        *,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        params: Optional[dict[str, str]] = None,
        content: Optional[bytes] = None,
    ) -> httpx.Response:
        """Execute HTTP request with rate-limiting pacing, error translation, and retry backoff."""
        attempt = 0
        while True:
            self._apply_pacing()
            try:
                response = self._client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    content=content,
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt < self._max_retries:
                    attempt += 1
                    time.sleep(self._backoff_base_s * (2 ** (attempt - 1)))
                    continue
                raise SourceTransientError(f"Network error accessing Amazon source: {exc}") from exc

            # Auth failures
            if response.status_code in (401, 403):
                raise SourceAuthError(
                    f"Authentication rejected by provider with HTTP {response.status_code}"
                )

            # Throttling
            if response.status_code == 429:
                retry_after: Optional[float] = None
                raw_retry = response.headers.get("Retry-After")
                if raw_retry:
                    try:
                        retry_after = float(raw_retry)
                    except ValueError:
                        pass
                raise SourceRateLimitError(
                    "Provider throttled request (HTTP 429)",
                    retry_after_s=retry_after,
                )

            # Server errors safe to retry
            if response.status_code in (500, 502, 503, 504):
                if attempt < self._max_retries:
                    attempt += 1
                    time.sleep(self._backoff_base_s * (2 ** (attempt - 1)))
                    continue
                raise SourceTransientError(
                    f"Provider returned transient server error HTTP {response.status_code}"
                )

            if not response.is_success:
                raise SourcePayloadError(
                    f"Unexpected HTTP {response.status_code} from provider"
                )

            return response

    def _parse_paapi_item(self, item: dict[str, Any]) -> Optional[RawSourceRecord]:
        """Convert a raw PA-API Item dictionary into a normalized RawSourceRecord."""
        if not isinstance(item, dict):
            return None

        asin = item.get("ASIN")
        if not asin or not isinstance(asin, str):
            return None

        item_info = item.get("ItemInfo", {})
        title = item_info.get("Title", {}).get("DisplayValue")
        if not title:
            return None

        brand = item_info.get("ByLineInfo", {}).get("Brand", {}).get("DisplayValue")
        features = item_info.get("Features", {}).get("DisplayValues", [])
        mpn = item_info.get("ManufactureInfo", {}).get("ItemPartNumber", {}).get("DisplayValue")

        # Category resolution
        classifications = item_info.get("Classifications", {})
        binding = classifications.get("Binding", {}).get("DisplayValue", "").lower()
        product_group = classifications.get("ProductGroup", {}).get("DisplayValue", "").lower()

        category = "tops"
        subcategory = "shirts"
        text_context = f"{title} {binding} {product_group}".lower()
        if any(w in text_context for w in ("jacket", "coat", "hoodie", "cardigan", "blazer", "outerwear")):
            category = "outerwear"
            subcategory = "jackets"
        elif any(w in text_context for w in ("shoe", "sneaker", "boot", "loafer", "footwear", "sandal")):
            category = "footwear"
            subcategory = "shoes"
        elif any(w in text_context for w in ("trouser", "pant", "jean", "short", "chino", "bottom")):
            category = "bottoms"
            subcategory = "pants"
        elif any(w in text_context for w in ("bag", "belt", "watch", "sunglass", "hat", "accessory", "wallet")):
            category = "accessories"
            subcategory = "accessories"

        # Pricing & availability
        offers = item.get("Offers", {}).get("Listings", [])
        listing = offers[0] if offers and isinstance(offers, list) else {}
        price_val: Optional[float] = None
        price_dict = listing.get("Price", {})
        if isinstance(price_dict, dict) and "Amount" in price_dict:
            try:
                price_val = float(price_dict["Amount"])
            except (ValueError, TypeError):
                pass

        orig_price_val: Optional[float] = None
        orig_dict = listing.get("SavingBasis", {})
        if isinstance(orig_dict, dict) and "Amount" in orig_dict:
            try:
                orig_price_val = float(orig_dict["Amount"])
            except (ValueError, TypeError):
                pass

        currency_val = price_dict.get("Currency", "INR") if isinstance(price_dict, dict) else "INR"

        avail_dict = listing.get("Availability", {})
        avail_msg = avail_dict.get("Message", "").lower()
        avail_type = avail_dict.get("Type", "")
        availability = True
        if avail_type == "NOW" or "in stock" in avail_msg:
            availability = True
        elif "out of stock" in avail_msg or "unavailable" in avail_msg:
            availability = False

        # Destination URL with affiliate tag
        raw_url = item.get("DetailPageURL") or f"https://www.amazon.in/dp/{asin}"
        affiliate_url = _append_affiliate_tag(raw_url, self._associate_tag)

        # Image URLs (strictly hotlinked from Amazon CDN)
        images_dict = item.get("Images", {}).get("Primary", {}).get("Large", {})
        img_url = images_dict.get("URL")
        image_urls = [img_url] if img_url else []

        payload = {
            "source_product_id": asin,
            "title": title,
            "brand": brand,
            "category": category,
            "subcategory": subcategory,
            "price": price_val,
            "original_price": orig_price_val,
            "currency": currency_val,
            "availability": availability,
            "product_url": affiliate_url,
            "image_urls": image_urls,
            "attributes": {
                "asin": asin,
                "features": features,
                "fixture": False,
                "synthetic": False,
            },
            "manufacturer_id": mpn,
        }

        return RawSourceRecord(
            source=self.source_id,
            source_record_id=asin,
            payload=payload,
            source_timestamp=datetime.now(timezone.utc),
        )

    def _parse_rainforest_item(self, item: dict[str, Any]) -> Optional[RawSourceRecord]:
        """Convert a raw Rainforest API search result into a normalized RawSourceRecord."""
        if not isinstance(item, dict):
            return None

        asin = item.get("asin")
        title = item.get("title")
        if not asin or not title:
            return None

        brand = item.get("brand")
        raw_link = item.get("link") or f"https://www.amazon.in/dp/{asin}"
        affiliate_url = _append_affiliate_tag(raw_link, self._associate_tag)

        # Image
        img_url = item.get("image")
        image_urls = [img_url] if img_url else []

        # Price
        price_val: Optional[float] = None
        price_obj = item.get("price")
        if isinstance(price_obj, dict):
            price_val = price_obj.get("value")
            currency_val = price_obj.get("currency", "INR")
        elif isinstance(price_obj, (int, float)):
            price_val = float(price_obj)
            currency_val = "INR"
        else:
            currency_val = "INR"

        orig_price_val: Optional[float] = None
        orig_obj = item.get("rrp") or item.get("original_price")
        if isinstance(orig_obj, dict):
            orig_price_val = orig_obj.get("value")
        elif isinstance(orig_obj, (int, float)):
            orig_price_val = float(orig_obj)

        avail_raw = (item.get("availability") or {}).get("raw", "").lower()
        availability = "out of stock" not in avail_raw and "unavailable" not in avail_raw

        category = "tops"
        subcategory = "shirts"
        text_context = title.lower()
        if any(w in text_context for w in ("jacket", "coat", "hoodie", "cardigan", "blazer", "outerwear")):
            category = "outerwear"
            subcategory = "jackets"
        elif any(w in text_context for w in ("shoe", "sneaker", "boot", "loafer", "footwear", "sandal")):
            category = "footwear"
            subcategory = "shoes"
        elif any(w in text_context for w in ("trouser", "pant", "jean", "short", "chino", "bottom")):
            category = "bottoms"
            subcategory = "pants"
        elif any(w in text_context for w in ("bag", "belt", "watch", "sunglass", "hat", "accessory", "wallet")):
            category = "accessories"
            subcategory = "accessories"

        variants = item.get("variants", [])
        variant_size = None
        variant_color = None
        if variants and isinstance(variants, list) and isinstance(variants[0], dict):
            variant_size = variants[0].get("size")
            variant_color = variants[0].get("color")

        payload = {
            "source_product_id": asin,
            "title": title,
            "brand": brand,
            "category": category,
            "subcategory": subcategory,
            "price": price_val,
            "original_price": orig_price_val,
            "currency": currency_val,
            "availability": availability,
            "product_url": affiliate_url,
            "image_urls": image_urls,
            "attributes": {
                "asin": asin,
                "fixture": False,
                "synthetic": False,
            },
        }
        if variant_size:
            payload["attributes"]["size"] = variant_size
        if variant_color:
            payload["attributes"]["color"] = variant_color

        return RawSourceRecord(
            source=self.source_id,
            source_record_id=asin,
            payload=payload,
            source_timestamp=datetime.now(timezone.utc),
        )
