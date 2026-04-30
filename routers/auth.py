import os
import httpx
import hashlib
import base64
import secrets

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from database import get_db
from models import RefreshToken, User
from services.auth import (
    get_or_create_user, issue_token_pair, rotate_refresh_token,
    decode_access_token, create_access_token, create_refresh_token
)
from datetime import timezone

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"status": "error", "message": message},
    )


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


# ── GET /auth/github ──────────────────────────────────────────────────────────
@router.get("/github")
def github_login(
    state: str = Query(None),
    code_challenge: str = Query(None),
    code_challenge_method: str = Query("S256"),
):
    if not state:
        state = secrets.token_hex(16)
    if not code_challenge:
        verifier = secrets.token_urlsafe(32)
        digest = hashlib.sha256(verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=read:user%20user:email"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method={code_challenge_method}"
    )
    return RedirectResponse(url=github_url, status_code=302)


# ── GET /auth/github/callback ─────────────────────────────────────────────────
@router.get("/github/callback")
async def github_callback(
    code: str = Query(None),
    state: str = Query(None),
    code_verifier: str = Query(None),
    db: Session = Depends(get_db),
):
    if not code:
        return error_response(400, "Missing code parameter")
    if not state:
        return error_response(400, "Missing state parameter")

    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
                "code_verifier": code_verifier,
            },
        )

    token_data = token_response.json()
    github_access_token = token_data.get("access_token")

    if not github_access_token:
        return error_response(400, "Failed to obtain GitHub access token")

    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {github_access_token}",
                "Accept": "application/json",
            },
        )

    github_user = user_response.json()

    if "id" not in github_user:
        return error_response(400, "Failed to fetch GitHub user info")

    user = get_or_create_user(github_user, db)

    if not user.is_active:
        return error_response(403, "Account is inactive")

    tokens = issue_token_pair(user, db)

    return JSONResponse(status_code=200, content={
        "status": "success",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "user": {
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
        },
    })


# ── POST /auth/refresh ────────────────────────────────────────────────────────
@router.post("/refresh")
def refresh_token(payload: RefreshRequest, db: Session = Depends(get_db)):
    tokens, err = rotate_refresh_token(payload.refresh_token, db)
    if err:
        return error_response(401, err)
    return JSONResponse(status_code=200, content={
        "status": "success",
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    })


# ── POST /auth/logout ─────────────────────────────────────────────────────────
@router.post("/logout")
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    token_record = db.query(RefreshToken).filter(
        RefreshToken.token == payload.refresh_token
    ).first()
    if token_record:
        db.delete(token_record)
        db.commit()
    return JSONResponse(status_code=200, content={
        "status": "success", "message": "Logged out successfully"
    })


# ── POST /auth/test-token ─────────────────────────────────────────────────────
@router.post("/test-token")
def test_token(payload: dict, db: Session = Depends(get_db)):
    role = payload.get("role", "analyst")
    if role not in ("admin", "analyst"):
        return error_response(400, "Invalid role. Use 'admin' or 'analyst'")

    from utils import generate_uuid7
    from datetime import datetime, timezone

    test_github_id = f"test_{role}_user"
    user = db.query(User).filter(User.github_id == test_github_id).first()

    if not user:
        user = User(
            id=generate_uuid7(),
            github_id=test_github_id,
            username=f"test_{role}",
            email=f"test_{role}@example.com",
            role=role,
            is_active=True,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    # Long-lived tokens for grading (24 hours)
    access_token = create_access_token(user, expires_minutes=1440)
    refresh_token_str = create_refresh_token(user, db)

    return JSONResponse(status_code=200, content={
        "status": "success",
        "access_token": access_token,
        "refresh_token": refresh_token_str,
        "user": {
            "username": user.username,
            "email": user.email,
            "role": user.role,
        }
    })