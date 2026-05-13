import logging
import logging.config
import os

import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.models import router as models_router
from routers.auth import router as auth_router
from routers.profile import router as profile_router
from routers.chat import router as chat_router
from routers.admin import router as admin_router
from middleware.logging import RequestLoggingMiddleware
from db.postgres import init_pool as init_postgres_pool, close_pool as close_postgres_pool, ping
from memory.session_memory import init_redis_pool, close_redis_pool
from auth.firebase_admin import initialize_firebase

# Structured JSON logging setup
logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"format": "%(message)s"},
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "request_console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "academong.requests": {"handlers": ["request_console"], "level": "INFO", "propagate": False},
        "uvicorn": {"handlers": ["console"], "level": "WARNING"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
})

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres_pool()
    init_redis_pool()
    initialize_firebase()
    yield
    await close_redis_pool()
    await close_postgres_pool()

app = FastAPI(title="AcadeMong API", version="0.1.0", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,    prefix="/api/auth",    tags=["Authentication"])
app.include_router(profile_router, prefix="/api/profile", tags=["Profile"])
app.include_router(chat_router,    prefix="/api/chat",    tags=["Chat"])
app.include_router(admin_router,   prefix="/api/admin",   tags=["Admin"])
app.include_router(models_router,  prefix="/api/models",  tags=["Models"])

async def _check_postgres() -> str:
    try:
        return "ok" if await ping() else "error: ping returned false"
    except Exception as e:
        return f"error: {e}"

async def _check_redis() -> str:
    try:
        import redis.asyncio as aioredis
        r = aioredis.Redis(
            host=os.getenv("REDIS_HOST"),
            port=int(os.getenv("REDIS_PORT")),
        )
        await r.ping()
        await r.aclose()
        return "ok"
    except Exception as e:
        return f"error: {e}"

async def _check_qdrant() -> str:
    try:
        url = f"http://{os.getenv('QDRANT_HOST')}:{os.getenv('QDRANT_PORT')}/healthz"
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url)
            return "ok" if r.status_code == 200 else f"error: status {r.status_code}"
    except Exception as e:
        return f"error: {e}"

async def _check_ollama() -> str:
    try:
        url = f"http://{os.getenv('OLLAMA_HOST')}:{os.getenv('OLLAMA_PORT')}/api/tags"
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url)
            return "ok" if r.status_code == 200 else f"error: status {r.status_code}"
    except Exception as e:
        return f"error: {e}"

@app.get("/health")
async def health():
    services = {
        "postgres": await _check_postgres(),
        "redis": await _check_redis(),
        "qdrant": await _check_qdrant(),
        "ollama": await _check_ollama(),
    }
    overall = all(v == "ok" for v in services.values())
    return {"status": "ok" if overall else "degraded", "services": services}
