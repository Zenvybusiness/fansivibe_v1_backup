"""Fashion reasoning API router — Phase 3AJ.

Exposes the frozen reasoning pipeline over the versioned API boundary:
  `POST /v1/reasoning`
  `POST /v1/reasoning/query`

Preserves all domain boundaries, validates input/output contracts,
enforces 3T admission and 3P reference selection, and maps errors
deterministically to the project's frozen 12-category error contract.
Raw model JSON never escapes this boundary.
"""

from __future__ import annotations

import logging

import time

from fastapi import APIRouter, Depends, Header, Request

from app.ai.ollama_reasoner import ReasoningExecutionError
from app.api.deps import get_fashion_reasoner
from app.api.errors import ApiError, validation, _request_id
from app.api.rate_limit import (
    get_reasoning_concurrency_limiter,
    reasoning_rate_limit,
)
from app.api.schemas.reasoning import (
    FashionReasoningRequest,
    FashionReasoningResponse,
    ReasoningConclusionSchema,
    ReasoningVersionsSchema,
)
from app.application.reasoning import ReasonFashionQuery
from app.config.settings import get_settings
from app.data.ffo import corpus
from app.domain.ports.reasoning import FashionReasoner
from app.domain.services.ffo_reasoning import (
    FashionReasoningOutput,
    ReasoningContractError,
)

logger = logging.getLogger("fansivibe.api.reasoning")

router = APIRouter(prefix="/v1/reasoning", tags=["reasoning"])


def _output_to_response(output: FashionReasoningOutput) -> FashionReasoningResponse:
    if output.versions is None:
        raise ApiError(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Reasoning output missing required version pins",
        )
    return FashionReasoningResponse(
        answer=output.answer,
        conclusions=[
            ReasoningConclusionSchema(
                statement=c.statement,
                evidence_ids=list(c.evidence_ids),
                ffo_refs=list(c.ffo_refs),
                reasoning_note=c.reasoning_note,
                standing=c.standing,
            )
            for c in output.conclusions
        ],
        uncertainties=list(output.uncertainties),
        missing_evidence=list(output.missing_evidence),
        contradictions=list(output.contradictions),
        confidence=output.confidence,
        unsupported=output.unsupported,
        versions=ReasoningVersionsSchema(
            ffo_version=output.versions.ffo_version,
            corpus_digest=output.versions.corpus_digest,
            evidence_schema=output.versions.evidence_schema,
            reasoning_contract_version=output.versions.reasoning_contract_version,
        ),
    )


@router.post(
    "",
    response_model=FashionReasoningResponse,
    responses={
        422: {"model": dict, "description": "Validation error or invalid intent"},
        429: {"model": dict, "description": "Rate limited or concurrency exceeded"},
        502: {"model": dict, "description": "Model output / contract failure"},
        503: {"model": dict, "description": "Reasoning service unavailable or disabled"},
        504: {"model": dict, "description": "Reasoning service timeout"},
    },
)
@router.post(
    "/query",
    response_model=FashionReasoningResponse,
    responses={
        422: {"model": dict, "description": "Validation error or invalid intent"},
        429: {"model": dict, "description": "Rate limited or concurrency exceeded"},
        502: {"model": dict, "description": "Model output / contract failure"},
        503: {"model": dict, "description": "Reasoning service unavailable or disabled"},
        504: {"model": dict, "description": "Reasoning service timeout"},
    },
)
def reason_fashion_query(
    request: FashionReasoningRequest,
    raw_request: Request,
    authorization: str | None = Header(default=None),
    reasoner: FashionReasoner = Depends(get_fashion_reasoner),
    _rate_limit: None = Depends(reasoning_rate_limit),
) -> FashionReasoningResponse:
    """Execute a structured fashion reasoning query over the FFO corpus.

    Flow:
      request -> normalization -> retrieval -> evidence pack -> FashionReasoningInput
      -> FashionReasoner port -> Ollama adapter (validation, admission, selector)
      -> validated FashionReasoningOutput -> API response.

    Authentication is optional (session-first); callers without tokens
    are supported for knowledge exploration and public styling reasoning.
    Protected by in-process concurrency guard and sliding-window rate limit.
    """
    settings = get_settings()
    req_id = _request_id(raw_request)
    t0 = time.monotonic()

    # Typed kill-switch check
    if settings.disable_reasoning:
        raise ApiError(
            status_code=503,
            code="AI_FAILURE",
            message="The fashion reasoning service is currently disabled in configuration.",
            details={"category": "disabled"},
        )

    # Concurrency limiter to protect single-process resources / GPU VRAM
    limiter = get_reasoning_concurrency_limiter()
    from app.telemetry.metrics import get_metrics_collector
    collector = get_metrics_collector()

    if not limiter.acquire(timeout=1.0):
        collector.record_reasoning_query(status="concurrency_saturated", duration_s=time.monotonic() - t0)
        logger.warning(
            "Reasoning concurrency limit reached (%d active) [req_id=%s]",
            limiter.limit,
            req_id,
        )
        raise ApiError(
            status_code=429,
            code="RATE_LIMITED",
            message="The reasoning service is currently at maximum capacity. Please retry shortly.",
            details={"retry_after": 5},
        )

    collector.set_active_concurrency(limiter.active_count)
    try:
        # Section 6: Input handling — reject unpermitted control characters; no silent semantic rewrite
        if any(ord(c) < 32 and c not in "\n\r\t" for c in request.query):
            collector.record_reasoning_query(status="validation_error", duration_s=time.monotonic() - t0)
            raise validation([{"field": "query", "error": "Query contains unpermitted control characters."}])
        query_text = request.query
        context_dict = request.context.model_dump(exclude_none=True) if request.context else None

        use_case = ReasonFashionQuery(reasoner=reasoner)
        try:
            output = use_case(
                query=query_text,
                intent=request.intent,
                context=context_dict,
                max_conclusions=request.max_conclusions or 3,
                evidence_only=request.evidence_only if request.evidence_only is not None else True,
            )
        except ReasoningContractError as exc:
            collector.record_reasoning_query(status="contract_error", duration_s=time.monotonic() - t0)
            raise validation([{"field": "query", "error": str(exc)}])
        except corpus.CorpusError as exc:
            collector.record_reasoning_query(status="corpus_error", duration_s=time.monotonic() - t0)
            logger.error("Corpus error during reasoning query [req_id=%s]: %s", req_id, exc)
            raise ApiError(
                status_code=500,
                code="INTERNAL_ERROR",
                message=f"Corpus error: {exc}",
            )
        except ReasoningExecutionError as exc:
            duration_s = time.monotonic() - t0
            collector.record_reasoning_query(status=exc.category, duration_s=duration_s)
            elapsed_ms = round(duration_s * 1000, 2)
            logger.warning(
                "Reasoning execution failure category=%s message=%s [req_id=%s, latency_ms=%s]",
                exc.category,
                exc,
                req_id,
                elapsed_ms,
            )
            if exc.category == "unavailable":
                raise ApiError(
                    status_code=503,
                    code="AI_FAILURE",
                    message="The reasoning service is temporarily unavailable. Please try again shortly.",
                    details={"category": exc.category},
                )
            if exc.category == "timeout":
                raise ApiError(
                    status_code=504,
                    code="TIMEOUT",
                    message="The reasoning service timed out while processing the query.",
                    details={"category": exc.category},
                )
            if exc.category in ("malformed_json", "invalid_output", "http_error"):
                raise ApiError(
                    status_code=502,
                    code="AI_FAILURE",
                    message=f"The reasoning model failed to generate a valid response: {exc}",
                    details={"category": exc.category},
                )
            raise ApiError(
                status_code=502,
                code="AI_FAILURE",
                message=f"Reasoning failure: {exc}",
                details={"category": exc.category},
            )

        duration_s = time.monotonic() - t0
        collector.record_reasoning_query(status="success", duration_s=duration_s)
        elapsed_ms = round(duration_s * 1000, 2)
        logger.info(
            "Reasoning query completed [req_id=%s] query_len=%d intent=%s conclusions=%d confidence=%s latency_ms=%s",
            req_id,
            len(query_text),
            request.intent or "inferred",
            len(output.conclusions),
            output.confidence,
            elapsed_ms,
        )
        return _output_to_response(output)
    finally:
        limiter.release()
        collector.set_active_concurrency(limiter.active_count)
