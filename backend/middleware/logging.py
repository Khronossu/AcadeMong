"""Structured request logging middleware with PII redaction.

Logs every request as a single JSON line:
    {timestamp, method, path, status_code, latency_ms, user_id}

PII redacted before logging:
    - Thai national ID (13-digit)
    - Phone numbers (Thai format)
    - Email addresses
    - Raw prompt/response bodies are never logged
"""

from __future__ import annotations

import json
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from guardrails.pii_redactor import redact as _redact

logger = logging.getLogger("academong.requests")


def _extract_user_id(request: Request) -> str:
    """Best-effort user_id from request state (set by auth dependency)."""
    return getattr(request.state, "user_id", "anonymous")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        latency_ms = round((time.monotonic() - start) * 1000)

        path = _redact(request.url.path)
        query = _redact(str(request.url.query)) if request.url.query else ""

        record = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": request.method,
            "path": path,
            "query": query or None,
            "status_code": response.status_code,
            "latency_ms": latency_ms,
            "user_id": _extract_user_id(request),
        }

        # Remove None values for cleaner logs
        record = {k: v for k, v in record.items() if v is not None}

        if response.status_code >= 500:
            logger.error(json.dumps(record, ensure_ascii=False))
        elif response.status_code >= 400:
            logger.warning(json.dumps(record, ensure_ascii=False))
        else:
            logger.info(json.dumps(record, ensure_ascii=False))

        return response
