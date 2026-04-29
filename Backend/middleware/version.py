from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class APIVersionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce on /api/* routes
        if request.url.path.startswith("/api/"):
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