import os
import jwt
import secrets
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from models import User, RefreshToken
from utils import generate_uuid7

SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 3))
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", 5))


def create_access_token(user: User, expires_minutes: int = None) -> str:
    now = datetime.now(timezone.utc)
    expiry = expires_minutes or ACCESS_TOKEN_EXPIRE_MINUTES
    payload = {
        "sub": str(user.id),
        "github_id": user.github_id,
        "username": user.username,
        "role": user.role,
        "iat": now,
        "exp": now + timedelta(minutes=expiry),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(user: User, db: Session) -> str:
    token_str = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)

    token = RefreshToken(
        id=generate_uuid7(),
        token=token_str,
        user_id=user.id,
        expires_at=expires_at,
    )
    db.add(token)
    db.commit()
    return token_str


def issue_token_pair(user: User, db: Session) -> dict:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user, db)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
    }


def rotate_refresh_token(old_token_str: str, db: Session):
    """Validate old refresh token, invalidate it, issue a new pair."""
    now = datetime.now(timezone.utc)

    token_record = (
        db.query(RefreshToken)
        .filter(RefreshToken.token == old_token_str)
        .first()
    )

    if not token_record:
        return None, "Invalid refresh token"

    if token_record.expires_at.replace(tzinfo=timezone.utc) < now:
        db.delete(token_record)
        db.commit()
        return None, "Refresh token expired"

    user = token_record.user
    if not user.is_active:
        return None, "Account is inactive"

    # Invalidate old token
    db.delete(token_record)
    db.commit()

    tokens = issue_token_pair(user, db)
    return tokens, None


def decode_access_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_or_create_user(github_user: dict, db: Session) -> User:
    """Create user if not exists, otherwise update login info."""
    github_id = str(github_user["id"])

    user = db.query(User).filter(User.github_id == github_id).first()

    if not user:
        user = User(
            id=generate_uuid7(),
            github_id=github_id,
            username=github_user.get("login", ""),
            email=github_user.get("email"),
            avatar_url=github_user.get("avatar_url"),
            role="analyst",
            is_active=True,
            last_login_at=datetime.now(timezone.utc),
        )
        db.add(user)
    else:
        user.username = github_user.get("login", user.username)
        user.email = github_user.get("email", user.email)
        user.avatar_url = github_user.get("avatar_url", user.avatar_url)
        user.last_login_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(user)
    return user