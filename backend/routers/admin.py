"""Admin router — RBAC-gated endpoints for system operators.

All endpoints require role='admin'. Promotion is done manually via SQL:
    UPDATE users SET role = 'admin' WHERE email = '...';

Endpoints:
    GET  /api/admin/users                    — list all users
    PUT  /api/admin/users/{id}/role          — promote/demote user
    GET  /api/admin/flagged                  — list flagged outputs for review
    POST /api/admin/flag/{message_id}        — flag a message for review
    PATCH /api/admin/flagged/{id}/reviewed   — mark as reviewed
    GET  /api/admin/usage/{user_id}          — get rate limit usage for a user
"""

from __future__ import annotations

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from auth.firebase_admin import get_current_user
from db.postgres import execute, fetch, fetchrow
from guardrails.input_gate import check_role
from guardrails.rate_limiter import get_usage

router = APIRouter()


def _require_admin(user: dict = Depends(get_current_user)) -> dict:
    check_role(user, "admin")
    return user


# ── User management ───────────────────────────────────────────────────────────

@router.get("/users", summary="List all users (admin only)")
async def list_users(_: dict = Depends(_require_admin)):
    rows = await fetch(
        """SELECT id, email, username, role, created_at, last_login_at
           FROM users ORDER BY created_at DESC LIMIT 200""",
    )
    return {"users": [dict(r) for r in rows]}


class UpdateRoleRequest(BaseModel):
    role: str  # 'student' | 'admin'


@router.put("/users/{user_id}/role", summary="Promote or demote a user (admin only)")
async def update_role(
    user_id: UUID,
    body: UpdateRoleRequest,
    admin: dict = Depends(_require_admin),
):
    if body.role not in ("student", "admin"):
        raise HTTPException(status_code=422, detail="role must be 'student' or 'admin'")
    if str(user_id) == str(admin["id"]) and body.role == "student":
        raise HTTPException(status_code=400, detail="Cannot demote yourself")
    target = await fetchrow("SELECT id FROM users WHERE id = $1", user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await execute("UPDATE users SET role = $1 WHERE id = $2", body.role, user_id)
    return {"ok": True, "user_id": str(user_id), "role": body.role}


# ── Human review queue ────────────────────────────────────────────────────────

class FlagRequest(BaseModel):
    reason: str   # 'guardrail_trip' | 'user_report' | 'admin_review'
    notes: Optional[str] = None


@router.post("/flag/{message_id}", summary="Flag a message for human review")
async def flag_message(
    message_id: UUID,
    body: FlagRequest,
    user: dict = Depends(get_current_user),  # any authenticated user can flag
):
    msg = await fetchrow("SELECT id FROM chat_messages WHERE id = $1", message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    await execute(
        """INSERT INTO flagged_outputs (message_id, flagged_by, reason, notes)
           VALUES ($1, $2, $3, $4)
           ON CONFLICT DO NOTHING""",
        message_id, user["id"], body.reason[:100], body.notes,
    )
    return {"ok": True}


@router.get("/flagged", summary="List unreviewed flagged outputs (admin only)")
async def list_flagged(
    reviewed: bool = False,
    _: dict = Depends(_require_admin),
):
    rows = await fetch(
        """SELECT f.id, f.reason, f.notes, f.reviewed, f.created_at,
                  f.message_id, cm.content AS message_content,
                  u.email AS flagged_by_email
           FROM flagged_outputs f
           LEFT JOIN chat_messages cm ON cm.id = f.message_id
           LEFT JOIN users u ON u.id = f.flagged_by
           WHERE f.reviewed = $1
           ORDER BY f.created_at DESC
           LIMIT 100""",
        reviewed,
    )
    return {"flagged": [dict(r) for r in rows]}


@router.patch("/flagged/{flag_id}/reviewed", summary="Mark a flagged output as reviewed")
async def mark_reviewed(flag_id: UUID, _: dict = Depends(_require_admin)):
    row = await fetchrow("SELECT id FROM flagged_outputs WHERE id = $1", flag_id)
    if not row:
        raise HTTPException(status_code=404, detail="Flag not found")
    await execute("UPDATE flagged_outputs SET reviewed = TRUE WHERE id = $1", flag_id)
    return {"ok": True}


# ── Usage / rate limits ───────────────────────────────────────────────────────

@router.get("/usage/{user_id}", summary="Get rate limit usage for a user (admin only)")
async def user_usage(user_id: UUID, _: dict = Depends(_require_admin)):
    usage = await get_usage(user_id)
    return {"user_id": str(user_id), **usage}
