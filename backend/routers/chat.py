"""Chat router — eligibility query endpoint (current scope).

This is the current-scope version of the chat router. It covers Flow B (TCAS
eligibility) without RAG context — just deterministic SQL matching. Flow A
(Career Dreamer) and RAG-augmented responses are deferred pending Phase 6/7.

Endpoints:
    POST /api/chat/eligibility          — run eligibility check for current user
    POST /api/chat/eligibility/{major_id} — scoped to a single major
    GET  /api/chat/sessions             — list chat sessions for current user
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth.firebase_admin import get_current_user
from db.postgres import execute, fetch, fetchrow
from engines.eligibility_engine import check_eligibility, check_eligibility_for_major

router = APIRouter()
