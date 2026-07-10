from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.routers import chat
from app.redis_client import init_redis, close_redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    yield
    await close_redis()

app = FastAPI(title="RM Agent Bot", description="FastAPI wrapper for RM Agent", version="1.0.0", lifespan=lifespan)

app.include_router(chat.router, prefix="/v1/agent", tags=["agent"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
