"""Chat router — conversational AI endpoints + eligibility utilities.

Endpoints:
    POST /api/chat/session              — create a new chat session (dreamer or tcas_rag)
    POST /api/chat/{session_id}/message — send a message, receive an AI response
    GET  /api/chat/{session_id}/messages — fetch full message history for a session
    POST /api/chat/eligibility          — raw SQL eligibility check (no LLM)
    POST /api/chat/eligibility/{major_id} — scoped raw eligibility check
    GET  /api/chat/sessions             — list user's chat sessions
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from auth.firebase_admin import get_current_user
from db.postgres import execute, fetch, fetchrow
from engines.eligibility_engine import check_eligibility, check_eligibility_for_major
from engines.mode_selector import validate_mode
from engines.orchestrator import handle_message
from guardrails.input_gate import detect_injection, validate_topic
from memory.long_term_memory import (
    create_chat_session,
    get_messages,
    get_session,
    save_message,
)
from memory.session_memory import clear_chat_window, clear_user_session
from engines.summarizer import summarize_session
import asyncio

router = APIRouter()


# ── Request / response models ─────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    ai_mode: str


class CreateSessionResponse(BaseModel):
    session_id: str
    ai_mode: str


class SendMessageRequest(BaseModel):
    content: str


class RenameSessionRequest(BaseModel):
    name: str


class UpdateModeRequest(BaseModel):
    ai_mode: str


class MessageResponse(BaseModel):
    role: str
    content: str


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[dict]


# ── Eligibility response models ───────────────────────────────────────────────

class SubjectResult(BaseModel):
    subject: str
    min_score: Optional[float]
    student_score: Optional[float]
    weight_percent: Optional[float]
    ok: bool


class EligibilityResult(BaseModel):
    admission_project_id: str
    major_id: Optional[str] = None
    project_name: str
    major: str
    field: Optional[str] = None
    faculty: str
    university: str
    round_number: int
    year: int
    seats: Optional[int]
    gpax_min: Optional[float]
    gpax_ok: bool
    subject_results: list[SubjectResult]
    eligible: bool
    source_url: Optional[str]


class EligibilityResponse(BaseModel):
    year: int
    total_projects: int
    eligible_count: int
    results: list[EligibilityResult]


# ── Chat endpoints ────────────────────────────────────────────────────────────

@router.post(
    "/session",
    response_model=CreateSessionResponse,
    summary="Create a new chat session",
    description="ai_mode must be 'dreamer' (Flow A) or 'tcas_rag' (Flow B).",
)
async def create_session(
    body: CreateSessionRequest,
    user: dict = Depends(get_current_user),
):
    try:
        mode = validate_mode(body.ai_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    session_id = await create_chat_session(user["id"], mode)
    return CreateSessionResponse(session_id=str(session_id), ai_mode=mode)


@router.post(
    "/{session_id}/message",
    response_model=MessageResponse,
    summary="Send a message and receive an AI response",
)
async def send_message(
    session_id: UUID,
    body: SendMessageRequest,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if detect_injection(body.content):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message contains disallowed patterns.")
    validate_topic(body.content)  # advisory — logs warning, never blocks

    response_text = await handle_message(
        session_id=session_id,
        user_id=user["id"],
        ai_mode=session["ai_mode"],
        content=body.content,
    )
    return MessageResponse(role="assistant", content=response_text)


@router.get(
    "/{session_id}/messages",
    response_model=HistoryResponse,
    summary="Fetch full message history for a session",
)
async def get_message_history(
    session_id: UUID,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    messages = await get_messages(session_id)
    return HistoryResponse(session_id=str(session_id), messages=messages)


@router.delete(
    "/{session_id}",
    summary="Delete a chat session and all its messages",
)
async def delete_session(
    session_id: UUID,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    await execute("DELETE FROM chat_sessions WHERE id = $1", session_id)
    await clear_chat_window(str(user["id"]), str(session_id))
    return {"ok": True}


@router.post(
    "/{session_id}/end",
    summary="End a session, trigger summarization and clear cache",
)
async def end_session(
    session_id: UUID,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    
    # Trigger summarization in the background so we don't block the client
    asyncio.create_task(summarize_session(user["id"], session_id))
    
    # Clear the session cache
    await clear_chat_window(str(user["id"]), str(session_id))
    await clear_user_session(str(user["id"]))
    
    return {"status": "ok", "message": "Session ended and summarization started"}


# ── Eligibility endpoints ──────────────────────────────────────────────────────

@router.post(
    "/eligibility",
    response_model=EligibilityResponse,
    summary="Check eligibility across all Round 3 admission projects",
    description=(
        "Uses the student's saved GPAX and test scores to evaluate every "
        "Round 3 admission project for the given year. Purely SQL — no LLM."
    ),
)
async def eligibility_all(
    year: Optional[int] = Query(None, description="TCAS cycle year (defaults to latest in DB)"),
    user: dict = Depends(get_current_user),
):
    user_id: UUID = user["id"]
    results = await check_eligibility(user_id=user_id, year=year)

    used_year = results[0]["year"] if results else year or 0
    eligible_count = sum(1 for r in results if r["eligible"])

    return EligibilityResponse(
        year=used_year,
        total_projects=len(results),
        eligible_count=eligible_count,
        results=[EligibilityResult(**r) for r in results],
    )


class BatchCutoffRequest(BaseModel):
    ids: list[str]   # admission_project_ids, max 20


@router.post(
    "/cutoffs/batch",
    summary="Historical cutoffs for multiple admission projects at once",
)
async def get_cutoffs_batch(
    body: BatchCutoffRequest,
    user: dict = Depends(get_current_user),
):
    ids = body.ids[:20]  # cap at 20
    if not ids:
        return {"cutoffs": {}}
    rows = await fetch(
        """SELECT admission_project_id::text, year,
                  min_admitted_score, max_admitted_score,
                  applicants_count, accepted_count
           FROM historical_cutoffs
           WHERE admission_project_id = ANY($1::uuid[])
             AND effective_to IS NULL
           ORDER BY admission_project_id, year ASC""",
        ids,
    )
    result: dict[str, list] = {}
    for row in rows:
        key = row["admission_project_id"]
        result.setdefault(key, []).append(dict(row))
    return {"cutoffs": result}


@router.get(
    "/cutoffs/{admission_project_id}",
    summary="Historical cutoff scores for an admission project",
)
async def get_cutoffs(
    admission_project_id: UUID,
    user: dict = Depends(get_current_user),
):
    rows = await fetch(
        """SELECT year, min_admitted_score, max_admitted_score, median_score,
                  applicants_count, accepted_count
           FROM historical_cutoffs
           WHERE admission_project_id = $1
             AND effective_to IS NULL
           ORDER BY year ASC""",
        admission_project_id,
    )
    return {"cutoffs": [dict(r) for r in rows]}


@router.get(
    "/sessions",
    summary="List chat sessions for current user",
)
async def list_sessions(user: dict = Depends(get_current_user)):
    user_id: UUID = user["id"]
    sessions = await fetch(
        """SELECT id, ai_mode, name, created_at
           FROM chat_sessions
           WHERE user_id = $1
           ORDER BY created_at DESC
           LIMIT 20""",
        user_id,
    )
    return {"sessions": [dict(s) for s in sessions]}


@router.patch(
    "/{session_id}/name",
    summary="Rename a chat session",
)
async def rename_session(
    session_id: UUID,
    body: RenameSessionRequest,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    name = body.name.strip()[:200] or None
    await execute(
        "UPDATE chat_sessions SET name = $1 WHERE id = $2",
        name, session_id,
    )
    return {"ok": True}


@router.patch(
    "/{session_id}/mode",
    summary="Switch AI mode for a session",
)
async def update_mode(
    session_id: UUID,
    body: UpdateModeRequest,
    user: dict = Depends(get_current_user),
):
    session = await get_session(session_id)
    if not session or session["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    try:
        mode = validate_mode(body.ai_mode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await execute(
        "UPDATE chat_sessions SET ai_mode = $1 WHERE id = $2",
        mode, session_id,
    )
    return {"ok": True, "ai_mode": mode}


@router.post(
    "/eligibility/{major_id}",
    response_model=EligibilityResponse,
    summary="Check eligibility for a specific major",
)
async def eligibility_for_major(
    major_id: UUID,
    year: Optional[int] = Query(None),
    user: dict = Depends(get_current_user),
):
    user_id: UUID = user["id"]
    results = await check_eligibility_for_major(
        user_id=user_id, major_id=major_id, year=year
    )

    used_year = results[0]["year"] if results else year or 0
    eligible_count = sum(1 for r in results if r["eligible"])

    return EligibilityResponse(
        year=used_year,
        total_projects=len(results),
        eligible_count=eligible_count,
        results=[EligibilityResult(**r) for r in results],
    )
