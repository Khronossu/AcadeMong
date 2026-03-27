from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import httpx

app = FastAPI(title="AcadeMong API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def _check_postgres() -> str:
    try:
        import asyncpg                                                                                                                                                                              
        conn = await asyncpg.connect(
            host=os.getenv("POSTGRES_HOST"),                                                                                                                                                        
            port=int(os.getenv("POSTGRES_PORT")),                                                                                                                                                 
            database=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),                                                                                                                                                        
            password=os.getenv("POSTGRES_PASSWORD"),
        )                                                                                                                                                                                           
        await conn.close()                                                                                                                                                                        
        return "ok"
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
