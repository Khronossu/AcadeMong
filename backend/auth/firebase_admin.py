import asyncio
import json
import os

import firebase_admin
from firebase_admin import auth, credentials
from fastapi import HTTPException, status


def initialize_firebase():
    """Initializes the Firebase Admin SDK app using environment variables."""
    if firebase_admin._apps:
        return

    creds_json_str = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if not creds_json_str:
        raise ValueError(
            "FIREBASE_CREDENTIALS_JSON environment variable not set. "
            "Please provide the full service account JSON content as a single-line string."
        )

    try:
        cred_info = json.loads(creds_json_str)
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize Firebase Admin SDK: {e}") from e


async def verify_token(token: str) -> dict:
    """Verifies a Firebase ID token and returns the decoded claims."""
    try:

        loop = asyncio.get_running_loop()

        def _verify():
            return auth.verify_id_token(token, clock_skew_seconds=10)

        decoded_token = await loop.run_in_executor(None, _verify)
        return decoded_token

    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid Firebase ID token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during token verification: {e}",
        )
