import os
import httpx
from fastapi import APIRouter, Depends, Query, Request, Cookie
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from itsdangerous import URLSafeTimedSerializer, BadSignature
from database import get_db
from services.auth import get_or_create_user, issue_token_pair, rotate_refresh_token
from models import RefreshToken

router = APIRouter()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI_WEB = os.getenv("GITHUB_REDIRECT_URI_WEB", "http://localhost:8000/web/auth/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
SECRET_KEY = os.getenv("JWT_SECRET")
if not SECRET_KEY:
    raise ValueError("JWT_SECRET environment variable is not set!")

serializer = URLSafeTimedSerializer(SECRET_KEY)

COOKIE_SECURE = os.getenv("ENVIRONMENT", "development") == "production"


def set_auth_cookies(response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=3 * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=5 * 60,
    )


def generate_csrf_token(session_id: str) -> str:
    return serializer.dumps(session_id, salt="csrf-token")


def validate_csrf_token(token: str, session_id: str) -> bool:
    try:
        value = serializer.loads(token, salt="csrf-token", max_age=3600)
        return value == session_id
    except BadSignature:
        return False

@router.get("/github")
def web_github_login(
    state: str = Query(None),
    code_challenge: str = Query(None),
    code_challenge_method: str = Query("S256"),
):
    import secrets, hashlib, base64

    if not state:
        state = secrets.token_hex(16)
    if not code_challenge:
        verifier = secrets.token_urlsafe(32)
        digest = hashlib.sha256(verifier.encode()).digest()
        code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    github_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI_WEB}"
        f"&scope=read:user%20user:email"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method={code_challenge_method}"
    )
    return RedirectResponse(url=github_url, status_code=302) 


# ── GET /web/auth/login ───────────────────────────────────────────────────────
@router.get("/auth/login")
def web_login(state: str = Query(...), code_challenge: str = Query(...)):
    params = (
        f"client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI_WEB}"
        f"&scope=read:user,user:email"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    return RedirectResponse(url=f"https://github.com/login/oauth/authorize?{params}")


# ── GET /web/auth/callback ────────────────────────────────────────────────────
@router.get("/auth/callback")
async def web_callback(
    code: str = Query(...),
    state: str = Query(...),
    code_verifier: str = Query(None),
    db: Session = Depends(get_db),
):
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI_WEB,
                "code_verifier": code_verifier,
            },
        )

    token_data = token_response.json()
    github_access_token = token_data.get("access_token")

    if not github_access_token:
        return RedirectResponse(url="/web/login.html?error=auth_failed")

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
        return RedirectResponse(url="/web/login.html?error=user_fetch_failed")

    user = get_or_create_user(github_user, db)

    if not user.is_active:
        return RedirectResponse(url="/web/login.html?error=inactive")

    tokens = issue_token_pair(user, db)

    # Set HTTP-only cookies + redirect to dashboard
    response = RedirectResponse(url="/web/dashboard.html", status_code=302)
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])

    # Set CSRF token (not httponly — JS needs to read it)
    csrf_token = generate_csrf_token(str(user.id))
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=COOKIE_SECURE,
        samesite="lax",
        max_age=3600,
    )

    return response


# ── POST /web/auth/refresh ────────────────────────────────────────────────────
@router.post("/auth/refresh")
def web_refresh(
    request: Request,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    csrf_header = request.headers.get("X-CSRF-Token")
    if not csrf_header:
        return JSONResponse(status_code=403, content={"status": "error", "message": "CSRF token missing"})

    if not refresh_token:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not authenticated"})

    tokens, err = rotate_refresh_token(refresh_token, db)
    if err:
        return JSONResponse(status_code=401, content={"status": "error", "message": err})

    response = JSONResponse(content={"status": "success"})
    set_auth_cookies(response, tokens["access_token"], tokens["refresh_token"])
    return response


# ── POST /web/auth/logout ─────────────────────────────────────────────────────
@router.post("/auth/logout")
def web_logout(
    request: Request,
    refresh_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    if refresh_token:
        token_record = db.query(RefreshToken).filter(
            RefreshToken.token == refresh_token
        ).first()
        if token_record:
            db.delete(token_record)
            db.commit()

    response = JSONResponse(content={"status": "success", "message": "Logged out"})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    response.delete_cookie("csrf_token")
    return response


# ── GET /web/auth/me ──────────────────────────────────────────────────────────
@router.get("/auth/me")
def web_me(
    request: Request,
    access_token: str = Cookie(None),
    db: Session = Depends(get_db),
):
    from services.auth import decode_access_token
    from models import User

    if not access_token:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Not authenticated"})

    payload = decode_access_token(access_token)
    if not payload:
        return JSONResponse(status_code=401, content={"status": "error", "message": "Token expired"})

    user = db.query(User).filter(User.id == payload["sub"]).first()
    if not user:
        return JSONResponse(status_code=401, content={"status": "error", "message": "User not found"})

    return JSONResponse(content={
        "status": "success",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "role": user.role,
        }
    })

