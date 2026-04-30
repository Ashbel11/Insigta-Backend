from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from database import get_db
from models import User
from services.auth import decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise _auth_error(401, "Not authenticated")

    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload:
        raise _auth_error(401, "Invalid or expired token")

    user = db.query(User).filter(User.id == payload["sub"]).first()

    if not user:
        raise _auth_error(401, "User not found")

    if not user.is_active:
        raise _auth_error(403, "Account is inactive")

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise _auth_error(403, "Admin access required")
    return current_user


def require_analyst(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in ("admin", "analyst"):
        raise _auth_error(403, "Access denied")
    return current_user


from fastapi import HTTPException
from fastapi.responses import JSONResponse

def _auth_error(status_code: int, message: str):
    from fastapi import HTTPException
    raise HTTPException(
        status_code=status_code,
        detail={"status": "error", "message": message}
    )