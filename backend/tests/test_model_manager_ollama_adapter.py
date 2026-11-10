"""Comprehensive unit and integration tests for OllamaModelAdapter (Phase 2 Batch 2).

Verifies all 16 mandatory acceptance requirements with deterministic HTTP mocking:
1. Successful /api/ps response.
2. Multiple loaded models.
3. Qwen3-VL loaded detection.
4. Model not loaded.
5. Missing VRAM information.
6. Malformed API response.
7. Ollama connection failure.
8. HTTP error handling.
9. Successful unload request.
10. Unload verification through /api/ps.
11. Model remaining loaded after unload request.
12. Unload timeout.
13. Repeated unload requests.
14. Unknown model state.
15. Correct HOT/COLD/UNKNOWN mapping.
16. WARM state is never falsely assigned.

Additional coverage:
- Async and sync parity.
- Registry state synchronization.
- Lifecycle manager composition and delegation (tags check, warmup).
- Safe live read-only /api/ps probe against local daemon (zero mutations).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from typing import Any, List
from unittest.mock import MagicMock

import httpx
import pytest

from app.ai.lifecycle import ModelStatus, OllamaLifecycleManager
from app.ai.manager.adapters.ollama_adapter import (
    OllamaAdapterError,
    OllamaConnectionError,
    OllamaLoadedModel,
    OllamaModelAdapter,
    OllamaModelNotFoundError,
    OllamaModelResidency,
    OllamaResponseError,
    OllamaTimeoutError,
    OllamaUnloadError,
    OllamaUnloadResult,
    OllamaUnloadTimeoutError,
    matches_model_name,
)
from app.ai.manager.registry import ModelRegistry
from app.ai.manager.types import ModelState


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def make_ps_payload(models: List[dict[str, Any]]) -> dict[str, Any]:
    """Build mock Ollama /api/ps JSON response."""
    return {"models": models}


QWEN_PS_ITEM: dict[str, Any] = {
    "name": "qwen3-vl:4b-instruct",
    "model": "qwen3-vl:4b-instruct",
    "size": 3295636231,
    "digest": "ee4b975b58c17ce268cd19d40db35d5edc64603035d2ffc1fee1968eb0947f7b",
    "details": {
        "parent_model": "",
        "format": "gguf",
        "family": "qwen3vl",
        "families": ["qwen3vl"],
        "parameter_size": "4.4B",
        "quantization_level": "Q4_K_M",
    },
    "expires_at": "2026-11-10T22:30:00Z",
    "size_vram": 3527545978,
}

LLAMA_PS_ITEM: dict[str, Any] = {
    "name": "llama3.2-vision:latest",
    "model": "llama3.2-vision:latest",
    "size": 7900000000,
    "digest": "aa11bb22cc33",
    "details": {"family": "llama"},
    "expires_at": "2026-11-10T22:35:00Z",
    "size_vram": 5200000000,
}


# ---------------------------------------------------------------------------
# 1. Successful /api/ps Response
# ---------------------------------------------------------------------------


def test_successful_api_ps_response() -> None:
    """1. Verify successful /api/ps response parsing and normalized model container."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/ps"
        return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        loaded = adapter.list_loaded_models()

    assert len(loaded) == 1
    m = loaded[0]
    assert m.name == "qwen3-vl:4b-instruct"
    assert m.model == "qwen3-vl:4b-instruct"
    assert m.size_bytes == 3295636231
    assert m.size_vram_bytes == 3527545978
    assert m.size_mib == round(3295636231 / (1024 * 1024), 2)
    assert m.size_vram_mib == round(3527545978 / (1024 * 1024), 2)
    assert m.expires_at == "2026-11-10T22:30:00Z"
    assert m.digest == "ee4b975b58c17ce268cd19d40db35d5edc64603035d2ffc1fee1968eb0947f7b"
    assert m.details is not None
    assert m.details.get("family") == "qwen3vl"


# ---------------------------------------------------------------------------
# 2. Multiple Loaded Models
# ---------------------------------------------------------------------------


def test_multiple_loaded_models() -> None:
    """2. Verify handling of multiple loaded models simultaneously in /api/ps."""
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/ps"
        return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM, LLAMA_PS_ITEM]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        loaded = adapter.list_loaded_models()

    assert len(loaded) == 2
    names = {m.name for m in loaded}
    assert "qwen3-vl:4b-instruct" in names
    assert "llama3.2-vision:latest" in names


# ---------------------------------------------------------------------------
# 3. Qwen3-VL Loaded Detection
# ---------------------------------------------------------------------------


def test_qwen3_vl_loaded_detection() -> None:
    """3. Verify explicit detection of configured Qwen3-VL model residency."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        assert adapter.is_model_loaded() is True
        residency = adapter.get_model_residency()

    assert residency.is_hot is True
    assert residency.state == ModelState.HOT
    assert residency.model_name == "qwen3-vl:4b-instruct"
    assert residency.size_vram_bytes == 3527545978


# ---------------------------------------------------------------------------
# 4. Model Not Loaded (COLD)
# ---------------------------------------------------------------------------


def test_model_not_loaded() -> None:
    """4. Verify model not in /api/ps reports COLD when Ollama responds normally."""
    def handler(request: httpx.Request) -> httpx.Response:
        # Llama is loaded, but Qwen is not
        return httpx.Response(200, json=make_ps_payload([LLAMA_PS_ITEM]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        assert adapter.is_model_loaded("qwen3-vl:4b-instruct") is False
        residency = adapter.get_model_residency("qwen3-vl:4b-instruct")

    assert residency.is_cold is True
    assert residency.state == ModelState.COLD
    assert residency.is_loaded is False
    assert residency.size_vram_bytes is None


# ---------------------------------------------------------------------------
# 5. Missing VRAM Information
# ---------------------------------------------------------------------------


def test_missing_vram_information() -> None:
    """5. Verify honest representation when Ollama omits size_vram (produces UNKNOWN, F-01)."""
    item_without_vram = {
        "name": "qwen3-vl:4b-instruct",
        "model": "qwen3-vl:4b-instruct",
        "size": 3295636231,
        # size_vram is deliberately absent
        "digest": "abc123",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([item_without_vram]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        residency = adapter.get_model_residency()
        is_loaded = adapter.is_model_loaded()

    assert residency.is_hot is False
    assert residency.is_unknown is True
    assert residency.state == ModelState.UNKNOWN
    assert residency.is_loaded is True
    assert residency.size_vram_bytes is None  # Not fabricated
    assert residency.loaded_model is not None
    assert residency.loaded_model.size_vram_mib is None
    assert residency.error is not None
    assert "Missing or unparseable size_vram" in residency.error
    assert is_loaded is False


def test_zero_vram_produces_unknown_residency() -> None:
    """F-01: Verify size_vram == 0 produces UNKNOWN residency and does not claim CPU."""
    item_zero_vram = {
        "name": "qwen3-vl:4b-instruct",
        "model": "qwen3-vl:4b-instruct",
        "size": 3295636231,
        "size_vram": 0,
        "digest": "abc123",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([item_zero_vram]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        residency = adapter.get_model_residency()
        is_loaded = adapter.is_model_loaded()

    assert residency.is_hot is False
    assert residency.is_unknown is True
    assert residency.state == ModelState.UNKNOWN
    assert residency.is_loaded is True
    assert residency.size_vram_bytes == 0
    assert residency.error is not None
    # Invariant: do not claim CPU residency
    assert "CPU" not in residency.error
    assert "size_vram=0" in residency.error
    assert is_loaded is False


def test_negative_vram_produces_unknown_residency() -> None:
    """F-01: Verify invalid negative size_vram produces UNKNOWN residency."""
    item_neg_vram = {
        "name": "qwen3-vl:4b-instruct",
        "model": "qwen3-vl:4b-instruct",
        "size": 3295636231,
        "size_vram": -1024,
        "digest": "abc123",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([item_neg_vram]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        residency = adapter.get_model_residency()
        is_loaded = adapter.is_model_loaded()

    assert residency.is_hot is False
    assert residency.is_unknown is True
    assert residency.state == ModelState.UNKNOWN
    assert residency.is_loaded is True
    assert residency.error is not None
    assert "negative" in residency.error.lower()
    assert is_loaded is False


def test_invalid_unparseable_vram_produces_unknown_residency() -> None:
    """F-01: Verify non-integer or boolean size_vram produces UNKNOWN residency."""
    item_invalid_vram = {
        "name": "qwen3-vl:4b-instruct",
        "model": "qwen3-vl:4b-instruct",
        "size": 3295636231,
        "size_vram": "unparseable_vram_string",
        "digest": "abc123",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([item_invalid_vram]))

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            host="http://test-ollama:11434",
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
        )
        residency = adapter.get_model_residency()
        is_loaded = adapter.is_model_loaded()

    assert residency.is_hot is False
    assert residency.is_unknown is True
    assert residency.state == ModelState.UNKNOWN
    assert residency.size_vram_bytes is None
    assert residency.error is not None
    assert is_loaded is False


# ---------------------------------------------------------------------------
# 6. Malformed API Response
# ---------------------------------------------------------------------------


def test_malformed_api_response() -> None:
    """6. Verify robust error handling on non-JSON, invalid structures, or missing keys."""
    # Case A: Non-JSON body
    def handler_non_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>502 Bad Gateway</html>")

    transport = httpx.MockTransport(handler_non_json)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        with pytest.raises(OllamaResponseError):
            adapter.list_loaded_models()
        res = adapter.get_model_residency(raise_on_error=False)
        assert res.state == ModelState.UNKNOWN

    # Case B: JSON is not a dictionary (e.g. a list)
    def handler_list_json(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler_list_json)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        with pytest.raises(OllamaResponseError) as exc_info:
            adapter.list_loaded_models()
        assert "Expected JSON object" in str(exc_info.value)

    # Case C: Missing 'models' key
    def handler_missing_models(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(handler_missing_models)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        with pytest.raises(OllamaResponseError) as exc_info:
            adapter.list_loaded_models()
        assert "Missing 'models' key" in str(exc_info.value)

    # Case D: Model entry missing both name and model
    def handler_bad_entry(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"size": 123}]})

    transport = httpx.MockTransport(handler_bad_entry)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        with pytest.raises(OllamaResponseError) as exc_info:
            adapter.list_loaded_models()
        assert "missing both 'name' and 'model'" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 7. Ollama Connection Failure
# ---------------------------------------------------------------------------


def test_ollama_connection_failure() -> None:
    """7. Verify connection failure translates to typed OllamaConnectionError."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused by peer")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(host="http://localhost:11434", sync_client=client)
        with pytest.raises(OllamaConnectionError) as exc_info:
            adapter.list_loaded_models()
        assert "Connection refused" in str(exc_info.value)

        # In get_model_residency with raise_on_error=False, returns UNKNOWN
        res = adapter.get_model_residency(raise_on_error=False)
        assert res.state == ModelState.UNKNOWN
        assert res.is_loaded is False
        assert "Connection refused" in str(res.error)


# ---------------------------------------------------------------------------
# 8. HTTP Error Handling
# ---------------------------------------------------------------------------


def test_http_error_handling() -> None:
    """8. Verify HTTP non-200 responses raise OllamaResponseError with status code."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error in GPU worker")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        with pytest.raises(OllamaResponseError) as exc_info:
            adapter.list_loaded_models()
        assert exc_info.value.status_code == 500
        assert "HTTP 500" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 9. Successful Unload Request
# ---------------------------------------------------------------------------


def test_successful_unload_request() -> None:
    """9. Verify successful model unloading via /api/generate with keep_alive: 0."""
    ps_call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ps_call_count
        if request.url.path == "/api/generate":
            payload = json.loads(request.content)
            assert payload["model"] == "qwen3-vl:4b-instruct"
            assert payload["keep_alive"] == 0
            assert payload.get("stream") is False
            return httpx.Response(
                200,
                json={"model": "qwen3-vl:4b-instruct", "done": True, "done_reason": "unload"},
            )
        elif request.url.path == "/api/ps":
            ps_call_count += 1
            # On first check after unload request, model is gone
            return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=client,
            poll_interval_s=0.01,
            unload_timeout_s=1.0,
        )
        result = adapter.unload_model()

    assert result.success is True
    assert result.verified_unloaded is True
    assert result.final_state == ModelState.COLD
    assert result.model_name == "qwen3-vl:4b-instruct"
    assert result.attempts >= 2  # initial request + /api/ps poll


# ---------------------------------------------------------------------------
# 10. Unload Verification Through /api/ps
# ---------------------------------------------------------------------------


def test_unload_verification_through_api_ps() -> None:
    """10. Verify adapter polls /api/ps and does not claim success on HTTP 200 alone."""
    ps_call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal ps_call_count
        if request.url.path == "/api/generate":
            return httpx.Response(
                200, json={"model": "qwen3-vl:4b-instruct", "done": True, "done_reason": "unload"}
            )
        elif request.url.path == "/api/ps":
            ps_call_count += 1
            if ps_call_count == 1:
                # Still resident on first poll (delayed unloading)
                return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
            else:
                # Successfully unmapped on second poll
                return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=client,
            poll_interval_s=0.02,
            unload_timeout_s=1.0,
        )
        result = adapter.unload_model()

    assert ps_call_count >= 2
    assert result.success is True
    assert result.verified_unloaded is True
    assert result.final_state == ModelState.COLD


# ---------------------------------------------------------------------------
# 11. Model Remaining Loaded After Unload Request
# ---------------------------------------------------------------------------


def test_model_remaining_loaded_after_unload_request() -> None:
    """11. Verify failure when model remains in /api/ps after unload request."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(
                200, json={"model": "qwen3-vl:4b-instruct", "done": True, "done_reason": "unload"}
            )
        elif request.url.path == "/api/ps":
            # Model stubbornly remains loaded in VRAM
            return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=client,
            poll_interval_s=0.02,
            unload_timeout_s=0.08,
        )
        # Should raise OllamaUnloadTimeoutError when raise_on_error=True
        with pytest.raises(OllamaUnloadTimeoutError) as exc_info:
            adapter.unload_model(raise_on_error=True)
        assert "remained loaded" in str(exc_info.value)

        # Should return structured failure when raise_on_error=False
        res = adapter.unload_model(raise_on_error=False)
        assert res.success is False
        assert res.verified_unloaded is False
        assert res.final_state == ModelState.HOT  # Still HOT!


# ---------------------------------------------------------------------------
# 12. Unload Timeout
# ---------------------------------------------------------------------------


def test_unload_timeout() -> None:
    """12. Verify unload operation respects explicit verification timeout bounds."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True, "done_reason": "unload"})
        elif request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=client,
            poll_interval_s=0.01,
            unload_timeout_s=0.05,
        )
        with pytest.raises(OllamaUnloadTimeoutError) as exc_info:
            adapter.unload_model(verification_timeout_s=0.05)
        assert exc_info.value.timeout_s == 0.05


# ---------------------------------------------------------------------------
# 13. Repeated Unload Requests
# ---------------------------------------------------------------------------


def test_repeated_unload_requests() -> None:
    """13. Verify calling unload on an already unloaded (COLD) model succeeds safely."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True, "done_reason": "unload"})
        elif request.url.path == "/api/ps":
            # Model is already not loaded
            return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=client,
            poll_interval_s=0.01,
            unload_timeout_s=0.5,
        )
        # First unload
        res1 = adapter.unload_model()
        assert res1.success is True
        assert res1.final_state == ModelState.COLD

        # Repeated unload
        res2 = adapter.unload_model()
        assert res2.success is True
        assert res2.final_state == ModelState.COLD


# ---------------------------------------------------------------------------
# 14. Unknown Model State
# ---------------------------------------------------------------------------


def test_unknown_model_state() -> None:
    """14. Verify state maps to UNKNOWN when connectivity or inspection fails."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Ollama read timed out")

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        res = adapter.get_model_residency("qwen3-vl:4b-instruct", raise_on_error=False)

    assert res.state == ModelState.UNKNOWN
    assert res.is_unknown is True
    assert res.is_hot is False
    assert res.is_cold is False
    assert "timed out" in str(res.error)


# ---------------------------------------------------------------------------
# 15. Correct HOT/COLD/UNKNOWN Mapping
# ---------------------------------------------------------------------------


def test_correct_hot_cold_unknown_mapping() -> None:
    """15. Exhaustive check of state mapping transitions."""
    # HOT: Model present in /api/ps
    def handler_hot(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))

    adapter_hot = OllamaModelAdapter(
        sync_client=httpx.Client(transport=httpx.MockTransport(handler_hot))
    )
    res_hot = adapter_hot.get_model_residency("qwen3-vl:4b-instruct")
    assert res_hot.state == ModelState.HOT

    # COLD: /api/ps returns 200 with empty list
    def handler_cold(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=make_ps_payload([]))

    adapter_cold = OllamaModelAdapter(
        sync_client=httpx.Client(transport=httpx.MockTransport(handler_cold))
    )
    res_cold = adapter_cold.get_model_residency("qwen3-vl:4b-instruct")
    assert res_cold.state == ModelState.COLD

    # UNKNOWN: 500 error
    def handler_err(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal error")

    adapter_err = OllamaModelAdapter(
        sync_client=httpx.Client(transport=httpx.MockTransport(handler_err))
    )
    res_err = adapter_err.get_model_residency("qwen3-vl:4b-instruct", raise_on_error=False)
    assert res_err.state == ModelState.UNKNOWN


# ---------------------------------------------------------------------------
# 16. WARM State is NEVER Falsely Assigned
# ---------------------------------------------------------------------------


def test_warm_state_is_never_falsely_assigned() -> None:
    """16. Verify ModelState.WARM is strictly rejected for Ollama models."""
    with pytest.raises(ValueError) as exc_info:
        OllamaModelResidency(
            model_name="qwen3-vl:4b-instruct",
            state=ModelState.WARM,
            is_loaded=True,
        )
    assert "ModelState.WARM is not supported for Ollama models" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 17. Async Parity Tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_async_operations_parity() -> None:
    """17. Verify asynchronous API methods operate identically to synchronous methods."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True, "done_reason": "unload"})
        elif request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as async_client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            client=async_client,
            poll_interval_s=0.01,
            unload_timeout_s=0.05,
        )

        # list_loaded_models_async
        loaded = await adapter.list_loaded_models_async()
        assert len(loaded) == 1
        assert loaded[0].name == "qwen3-vl:4b-instruct"

        # get_model_residency_async
        res = await adapter.get_model_residency_async()
        assert res.state == ModelState.HOT
        assert res.is_hot is True

        # is_model_loaded_async
        is_loaded = await adapter.is_model_loaded_async()
        assert is_loaded is True

        # unload_model_async failure with model still loaded
        with pytest.raises(OllamaUnloadTimeoutError):
            await adapter.unload_model_async(raise_on_error=True)


# ---------------------------------------------------------------------------
# 18. Model Registry State Synchronization
# ---------------------------------------------------------------------------


def test_registry_state_synchronization() -> None:
    """18. Verify ModelRegistry state is updated when registry is attached."""
    registry = ModelRegistry(pre_register_defaults=True)
    # Default state is COLD
    assert registry.get("qwen3-vl:4b-instruct").current_state == ModelState.COLD

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=client,
            registry=registry,
        )
        res = adapter.get_model_residency()

    assert res.state == ModelState.HOT
    # Verify registry was updated to HOT
    assert registry.get("qwen3-vl:4b-instruct").current_state == ModelState.HOT


# ---------------------------------------------------------------------------
# 19. Lifecycle Manager Delegation (Tags & Warmup)
# ---------------------------------------------------------------------------


def test_lifecycle_manager_delegation() -> None:
    """19. Verify check_installed and warmup delegate to OllamaLifecycleManager."""
    mock_lifecycle = MagicMock(spec=OllamaLifecycleManager)
    mock_lifecycle.model = "qwen3-vl:4b-instruct"
    mock_lifecycle.check_availability.return_value = ModelStatus(
        available=True,
        model_present=True,
        model_name="qwen3-vl:4b-instruct",
        host="http://localhost:11434",
        latency_ms=12.5,
    )
    mock_lifecycle.warmup.return_value = True

    adapter = OllamaModelAdapter(
        default_model="qwen3-vl:4b-instruct",
        lifecycle_manager=mock_lifecycle,
    )

    status = adapter.check_installed()
    assert status.model_present is True
    mock_lifecycle.check_availability.assert_called_once_with(timeout_s=3.0)

    warmed = adapter.warmup()
    assert warmed is True
    mock_lifecycle.warmup.assert_called_once_with(timeout_s=30.0)


# ---------------------------------------------------------------------------
# 20. Non-Existent Model Unload Returns 404
# ---------------------------------------------------------------------------


def test_unload_model_not_found() -> None:
    """20. Verify HTTP 404 from Ollama unload raises OllamaModelNotFoundError."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model 'nonexistent-model' not found"})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        adapter = OllamaModelAdapter(sync_client=client)
        with pytest.raises(OllamaModelNotFoundError) as exc_info:
            adapter.unload_model("nonexistent-model")
        assert "nonexistent-model" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 21. Model Name Matching Helper
# ---------------------------------------------------------------------------


def test_matches_model_name_helper() -> None:
    """21. Verify matches_model_name handles case, tags, and avoids prefix errors."""
    assert matches_model_name("qwen3-vl:4b-instruct", "qwen3-vl:4b-instruct") is True
    assert matches_model_name("QWEN3-VL:4B-INSTRUCT", "qwen3-vl:4b-instruct") is True
    assert matches_model_name("qwen3-vl:4b-instruct:latest", "qwen3-vl:4b-instruct") is True
    assert matches_model_name("qwen3-vl:4b-instruct", "qwen3-vl:4b-instruct:latest") is True

    # Negative matches
    assert matches_model_name("qwen3-vl:8b-instruct", "qwen3-vl:4b-instruct") is False
    assert matches_model_name("qwen3-vl", "qwen3-vl:4b-instruct") is False
    assert matches_model_name("qwen3-vl:4b-instruct-extra", "qwen3-vl:4b-instruct") is False


# ---------------------------------------------------------------------------
# 22. Safe Live Read-Only /api/ps Probe (Conditional)
# ---------------------------------------------------------------------------


def test_live_read_only_api_ps_probe_if_available() -> None:
    """22. Read-only live test against host Ollama daemon if running (zero mutations)."""
    try:
        # Check if local Ollama daemon is reachable
        resp = httpx.get("http://localhost:11434/api/tags", timeout=1.0)
        if resp.status_code != 200:
            pytest.skip("Local Ollama daemon not returning HTTP 200")
    except Exception:
        pytest.skip("Local Ollama daemon is not running on localhost:11434")

    adapter = OllamaModelAdapter(host="http://localhost:11434")
    # Read-only query: list_loaded_models
    loaded = adapter.list_loaded_models()
    assert isinstance(loaded, list)

    # Read-only residency query
    residency = adapter.get_model_residency()
    assert residency.state in (ModelState.HOT, ModelState.COLD)
    assert residency.state != ModelState.WARM


# ---------------------------------------------------------------------------
# 23. Bounded Unload Verification Polling with Stalled Request (F-03)
# ---------------------------------------------------------------------------


def test_unload_verification_bounded_by_deadline_with_stalled_request() -> None:
    """F-03: Verify unload verification polling requests are bounded by remaining deadline."""
    call_durations: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True, "done_reason": "unload"})
        if request.url.path == "/api/ps":
            t_call = time.monotonic()
            # Simulate a slow server that delays longer than remaining deadline
            time.sleep(0.25)
            call_durations.append(time.monotonic() - t_call)
            # Still report model present to force continued polling
            return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as sync_client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            sync_client=sync_client,
            request_timeout_s=10.0,  # General timeout is 10s!
            poll_interval_s=0.05,
        )
        # Total verification timeout configured to 0.4s:
        # Must not block for 10s! Total time should be approx ~0.4s to ~0.7s
        t0 = time.monotonic()
        with pytest.raises(OllamaUnloadTimeoutError):
            adapter.unload_model(
                "qwen3-vl:4b-instruct",
                verification_timeout_s=0.4,
                raise_on_error=True,
            )
        elapsed = time.monotonic() - t0
        # Must be bounded by verification_timeout_s within reasonable scheduling tolerance
        assert elapsed < 1.2, f"Unload took too long ({elapsed:.2f}s), should be bounded near 0.4s"

        # Model must not be claimed unloaded
        res = adapter.unload_model(
            "qwen3-vl:4b-instruct",
            verification_timeout_s=0.2,
            raise_on_error=False,
        )
        assert res.success is False
        assert res.verified_unloaded is False


# ---------------------------------------------------------------------------
# 24. Concurrency & Unload Mutual Exclusion (F-05)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_concurrent_unloads_same_model_serialized_async() -> None:
    """F-05: Concurrent unload requests for the same model must not overlap."""
    active_concurrency = 0
    max_concurrency = 0
    lock = asyncio.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_concurrency, max_concurrency
        if request.url.path == "/api/generate":
            async with lock:
                active_concurrency += 1
                if active_concurrency > max_concurrency:
                    max_concurrency = active_concurrency
            await asyncio.sleep(0.08)
            async with lock:
                active_concurrency -= 1
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            client=client,
            unload_timeout_s=2.0,
            poll_interval_s=0.02,
        )

        task1 = asyncio.create_task(adapter.unload_model_async("qwen3-vl:4b-instruct"))
        task2 = asyncio.create_task(adapter.unload_model_async("qwen3-vl:4b-instruct"))
        r1, r2 = await asyncio.gather(task1, task2)

        assert r1.success is True
        assert r2.success is True
        # Serialized per-model: max concurrent unloads on same model is exactly 1
        assert max_concurrency == 1


@pytest.mark.anyio
async def test_concurrent_unloads_different_models_parallel_async() -> None:
    """F-05: Concurrent unloads of different models proceed concurrently."""
    active_concurrency = 0
    max_concurrency = 0
    lock = asyncio.Lock()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_concurrency, max_concurrency
        if request.url.path == "/api/generate":
            async with lock:
                active_concurrency += 1
                if active_concurrency > max_concurrency:
                    max_concurrency = active_concurrency
            await asyncio.sleep(0.12)
            async with lock:
                active_concurrency -= 1
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = OllamaModelAdapter(
            client=client,
            unload_timeout_s=2.0,
            poll_interval_s=0.02,
        )

        task1 = asyncio.create_task(adapter.unload_model_async("qwen3-vl:4b-instruct"))
        task2 = asyncio.create_task(adapter.unload_model_async("llama3.1:8b"))
        r1, r2 = await asyncio.gather(task1, task2)

        assert r1.success is True
        assert r2.success is True
        # Different models are not blocked by each other
        assert max_concurrency == 2


@pytest.mark.anyio
async def test_concurrent_unload_mixed_sync_and_async() -> None:
    """F-05: Sync threads and async coroutines mutually exclude each other on same model."""
    active_concurrency = 0
    max_concurrency = 0
    th_lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_concurrency, max_concurrency
        if request.url.path == "/api/generate":
            with th_lock:
                active_concurrency += 1
                if active_concurrency > max_concurrency:
                    max_concurrency = active_concurrency
            time.sleep(0.08)
            with th_lock:
                active_concurrency -= 1
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as s_client:
        async with httpx.AsyncClient(transport=transport) as a_client:
            adapter = OllamaModelAdapter(
                default_model="qwen3-vl:4b-instruct",
                sync_client=s_client,
                client=a_client,
                unload_timeout_s=2.0,
                poll_interval_s=0.02,
            )

            sync_results = []
            def sync_worker():
                res = adapter.unload_model("qwen3-vl:4b-instruct")
                sync_results.append(res)

            thread = threading.Thread(target=sync_worker)
            thread.start()

            r_async = await adapter.unload_model_async("qwen3-vl:4b-instruct")
            thread.join()

            assert r_async.success is True
            assert len(sync_results) == 1
            assert sync_results[0].success is True
            # Cross-paradigm exclusion: sync and async never overlapped
            assert max_concurrency == 1


@pytest.mark.anyio
async def test_async_unload_cancellation_releases_lock() -> None:
    """F-05: Unload exclusion is reliably released after asyncio cancellation."""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            await asyncio.sleep(1.0)
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            client=client,
            unload_timeout_s=5.0,
        )

        task = asyncio.create_task(adapter.unload_model_async("qwen3-vl:4b-instruct"))
        await asyncio.sleep(0.04)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Verify exclusion was released and can be acquired immediately
        assert adapter._acquire_unload_sync("qwen3-vl:4b-instruct", timeout_s=0.1) is True
        adapter._release_unload_sync("qwen3-vl:4b-instruct")


@pytest.mark.anyio
async def test_readonly_inspection_not_blocked_during_unload() -> None:
    """F-05: Read-only inspection is never blocked by an in-progress unload."""
    unload_started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/generate":
            unload_started.set()
            await asyncio.sleep(0.15)
            return httpx.Response(200, json={"done": True})
        if request.url.path == "/api/ps":
            return httpx.Response(200, json=make_ps_payload([QWEN_PS_ITEM]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = OllamaModelAdapter(
            default_model="qwen3-vl:4b-instruct",
            client=client,
            unload_timeout_s=2.0,
        )

        unload_task = asyncio.create_task(
            adapter.unload_model_async("qwen3-vl:4b-instruct", raise_on_error=False)
        )
        await unload_started.wait()

        # Perform read-only queries while unload is in-flight
        t0 = time.monotonic()
        loaded = await adapter.list_loaded_models_async()
        residency = await adapter.get_model_residency_async()
        t_inspect = time.monotonic() - t0

        # Inspection completed immediately without waiting for unload to finish
        assert t_inspect < 0.1
        assert len(loaded) == 1
        assert residency.is_hot is True

        await unload_task

