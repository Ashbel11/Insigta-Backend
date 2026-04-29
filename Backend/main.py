from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
import os

from middleware.version import APIVersionMiddleware
from middleware.rate_limit import RateLimitMiddleware
from middleware.logging import RequestLoggingMiddleware
from database import engine, Base
from routers.profiles import router as profiles_router
from routers.auth import router as auth_router  
from routers.web_auth import router as web_auth_router          
  

Base.metadata.create_all(bind=engine)

if os.path.exists("profiles_seed.json"):  
    from seed import seed                  
    seed("profiles_seed.json") 

app = FastAPI(
    title="Insighta Labs Intelligence Query Engine",
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(APIVersionMiddleware)    
app.add_middleware(RateLimitMiddleware)    
app.add_middleware(RequestLoggingMiddleware)  
app.mount("/web", StaticFiles(directory="web", html=True), name="web")

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "message": "Invalid parameter type"},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "Internal server error"},
    )

app.include_router(auth_router, prefix="/auth", tags=["auth"])  
app.include_router(web_auth_router, prefix="/web", tags=["web-auth"])
app.include_router(profiles_router, prefix="/api", tags=["profiles"])  

@app.get("/health")
def health():
    return {"status": "ok"}