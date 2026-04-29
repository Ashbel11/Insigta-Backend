# Add to routers/users.py
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from models import User
from dependencies.auth import get_current_user

router = APIRouter()

@router.get("/users/me")
def get_me(current_user: User = Depends(get_current_user)):
    return JSONResponse(content={
        "status": "success",
        "data": {
            "id": str(current_user.id),
            "username": current_user.username,
            "email": current_user.email,
            "avatar_url": current_user.avatar_url,
            "role": current_user.role,
        }
    })