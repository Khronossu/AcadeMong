"""Structured metric emitter for AcadeMong.

Emits each metric as a single JSON log line to the 'academong.metrics' logger:
    {"metric": "llm.latency_ms", "value": 1240, "model": "typhoon2", "ts": "..."}

In production these lines are picked up by a CloudWatch Logs Metric Filter
(or Grafana Loki) and turned into numeric metrics.  Locally they appear in
stdout and are filterable with: docker logs fastapi | grep '"metric"'

Metric names
────────────
    llm.latency_ms              LLM generation latency (milliseconds)
    rag.retrieval_miss          RAG returned no results (value=1 per event)
    guardrail.injection_blocked Injection pattern detected (value=1)
    guardrail.topic_blocked     Hard off-topic block (value=1)
    guardrail.numeric_stripped  # of unsupported numeric claims stripped
    guardrail.safety_blocked    Llama Guard blocked a response (value=1)
    guardrail.citation_missing  RAG response had no inline citation (value=1)
    rate_limit.exceeded         User hit rate cap (value=1)
"""

from __future__ import annotations

import json
import logging
import time

_logger = logging.getLogger("academong.metrics")


def _emit(metric: str, value: float | int, **tags) -> None:
    record = {
        "metric": metric,
        "value": value,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **tags,
    }
    _logger.info(json.dumps(record, ensure_ascii=False))


# ── Public helpers ────────────────────────────────────────────────────────────

def llm_latency(latency_ms: int, model: str, mode: str) -> None:
    _emit("llm.latency_ms", latency_ms, model=model, mode=mode)


def rag_retrieval_miss(query_snippet: str = "") -> None:
    _emit("rag.retrieval_miss", 1, query=query_snippet[:60])


def guardrail_injection_blocked() -> None:
    _emit("guardrail.injection_blocked", 1)


def guardrail_topic_blocked() -> None:
    _emit("guardrail.topic_blocked", 1)


def guardrail_numeric_stripped(count: int, session_id: str = "") -> None:
    _emit("guardrail.numeric_stripped", count, session_id=session_id)


def guardrail_safety_blocked(categories: list[str]) -> None:
    _emit("guardrail.safety_blocked", 1, categories=",".join(categories))


def guardrail_citation_missing(session_id: str = "") -> None:
    _emit("guardrail.citation_missing", 1, session_id=session_id)


def rate_limit_exceeded(user_id: str, limit_type: str) -> None:
    _emit("rate_limit.exceeded", 1, user_id=user_id, limit_type=limit_type)
