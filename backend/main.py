from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx
from routers.models import router as models_router
from contextlib import asynccontextmanager
from db.postgres import init_pool, close_pool, ping

@asynccontextmanager
async def lifespan(app):
    await init_pool()
    yield
    await close_pool()

app = FastAPI(title="AcadeMong API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models_router, prefix="/api/models")

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

