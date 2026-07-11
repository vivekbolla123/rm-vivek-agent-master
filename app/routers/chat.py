from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json
from app.services.agent import run_agent

router = APIRouter()

class ChatRequest(BaseModel):
    message: str
    session_id: str
    user_id: Optional[str] = None
    rm_token: Optional[str] = None

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    async def sse_generator():
        try:
            async for data_dict in run_agent(
                message=request.message,
                session_id=request.session_id,
                user_id=request.user_id,
                rm_token=request.rm_token
            ):
                event = data_dict.get("event", "message")
                data = json.dumps(data_dict.get("data", {}))
                yield f"event: {event}\ndata: {data}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(sse_generator(), media_type="text/event-stream")

@router.websocket("/ws/chat")
async def websocket_chat_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message")
            session_id = data.get("session_id")
            user_id = data.get("user_id")
            rm_token = data.get("rm_token")
            
            if not message or not session_id:
                await websocket.send_json({"event": "error", "data": {"detail": "Missing message or session_id"}})
                continue
                
            async for data_dict in run_agent(
                message=message,
                session_id=session_id,
                user_id=user_id,
                rm_token=rm_token
            ):
                await websocket.send_json(data_dict)
                
    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({"event": "error", "data": {"detail": str(e)}})

