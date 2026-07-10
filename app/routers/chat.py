from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from app.services.agent import run_agent

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = None
    rm_token: Optional[str] = None

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    try:
        # returns an AsyncGenerator
        stream = run_agent(
            message=request.message,
            session_id=request.session_id,
            user_id=request.user_id,
            rm_token=request.rm_token
        )
        return StreamingResponse(stream, media_type="text/event-stream")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

