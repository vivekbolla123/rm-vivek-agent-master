from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.routers import chat
from app.redis_client import init_redis, close_redis
from app.bedrock_client import init_bedrock, close_bedrock

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    init_bedrock()
    yield
    await close_redis()
    await close_bedrock()

app = FastAPI(
    title="RM Agent Bot", 
    description="FastAPI wrapper for RM Agent", 
    version="1.0.0", 
    lifespan=lifespan,
    root_path="/api/rm-fastapi-agent"
)

app.include_router(chat.router, prefix="/v1/agent", tags=["agent"])

@app.get("/health")
async def health_check():
    return {"status": "ok"}
