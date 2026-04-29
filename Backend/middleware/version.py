from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class APIVersionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            auth_header = request.headers.get("Authorization")
            # Only enforce version if auth header is present
            # If no auth header, let auth dependency return 401
            if auth_header:
                version = request.headers.get("X-API-Version")
                if version != "3":
                    return JSONResponse(
                        status_code=400,
                        content={
                            "status": "error",
                            "message": "Missing or invalid API version. Set header X-API-Version: 3",
                        },
                    )
        return await call_next(request)