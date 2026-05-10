from uuid import UUID

import asyncpg
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from auth.firebase_admin import verify_token
from db.postgres import fetchrow, execute
from memory.session_memory import set_user_session

router = APIRouter()


class RegisterRequest(BaseModel):
    idToken: str
    username: str = Field(
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$"
    )

class UserResponse(BaseModel):
    id: UUID


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Accepts a Firebase idToken and a desired username. Verifies the token, creates a new user in the database, and returns the new user's ID.",
)
async def register_user(req: RegisterRequest):
    """
    - Verifies the Firebase `idToken`.
    - Extracts `firebase_uid` and `email`.
    - Checks for existing user by `firebase_uid` or `email`.
    - Creates a new user in the `users` table.
    - Returns the new user's UUID.
    """
    decoded_token = await verify_token(req.idToken)

    firebase_uid = decoded_token.get("uid")
    email = decoded_token.get("email")

    if not firebase_uid or not email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Firebase token is missing 'uid' or 'email' claims.")

    existing_user = await fetchrow("SELECT id FROM users WHERE firebase_uid = $1 OR email = $2", firebase_uid, email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this Firebase account or email already exists.")

    try:
        new_user_record = await fetchrow(
            """
            INSERT INTO users (firebase_uid, email, username)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            firebase_uid,
            email,
            req.username,
        )
        if not new_user_record:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user and retrieve ID.")

        return UserResponse(id=new_user_record["id"])

    except asyncpg.exceptions.UniqueViolationError as e:
        # This handles race conditions where a user was created between our check and insert.
        constraint_name = e.constraint_name or ""
        if "username" in constraint_name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Username '{req.username}' is already taken.")
        if "email" in constraint_name or "firebase_uid" in constraint_name:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User with this Firebase account or email already exists.")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A database conflict occurred: {e.detail}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"A database error occurred: {e}")


class LoginRequest(BaseModel):
    idToken: str


class LoginResponse(BaseModel):
    message: str
    user_id: UUID
    username: str


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Log in a user and create a session",
    description="Accepts a Firebase idToken, verifies it, finds the user in the database, and caches their profile in Redis.",
)
async def login_user(req: LoginRequest):
    """
    - Verifies the Firebase `idToken`.
    - Looks up the user by `firebase_uid`.
    - Fetches the user's profile from PostgreSQL.
    - Caches the user and profile data into a Redis session.
    - Updates `last_login_at`.
    - Returns a success message with user details.
    """
    decoded_token = await verify_token(req.idToken)
    firebase_uid = decoded_token.get("uid")

    if not firebase_uid:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Firebase token is missing 'uid' claim.")

    # Find user in our database (include role for RBAC caching)
    user_record = await fetchrow(
        "SELECT id, username, role FROM users WHERE firebase_uid = $1",
        firebase_uid
    )

    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found. Please register first."
        )

    user_id = user_record["id"]

    # Update last login time
    await execute(
        "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = $1",
        user_id
    )

    # Fetch user profile to cache it (it's okay if it's not found)
    profile_record = await fetchrow(
        "SELECT id, user_id, first_name, last_name, date_of_birth, avatar_url, address, sub_district, district, province, postal_code, current_school, gpax FROM user_profiles WHERE user_id = $1",
        user_id
    )

    session_data = {"user": dict(user_record), "profile": dict(profile_record) if profile_record else None}

    await set_user_session(user_id=str(user_id), session_data=session_data)

    return LoginResponse(
        message="Login successful, session created.",
        user_id=user_id,
        username=user_record["username"]
    )
