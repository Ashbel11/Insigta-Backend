import time
from collections import defaultdict
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Per-route limits: (max_requests, window_seconds)
RATE_LIMITS = {
    "/auth/github":          (20, 60),
    "/auth/github/callback": (20, 60),
    "/auth/refresh":         (10, 60),
    "/api/profiles":         (60, 60),
    "/api/profiles/search":  (30, 60),
}

DEFAULT_LIMIT = (100, 60)

# In-memory store: {route: {ip: [timestamps]}}
_request_log: dict = defaultdict(lambda: defaultdict(list))


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        ip = request.client.host
        now = time.time()

        # Find matching route limit
        limit, window = DEFAULT_LIMIT
        for route, (r_limit, r_window) in RATE_LIMITS.items():
            if path.startswith(route):
                limit, window = r_limit, r_window
                break

        # Clean old timestamps outside the window
        timestamps = _request_log[path][ip]
        _request_log[path][ip] = [t for t in timestamps if now - t < window]

        if len(_request_log[path][ip]) >= limit:
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "message": "Too many requests. Please slow down.",
                },
            )

        _request_log[path][ip].append(now)
        return await call_next(request)