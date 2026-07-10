import os
import json
import redis.asyncio as redis

redis_host = os.getenv("REDIS_HOST", "")
redis_port = int(os.getenv("REDIS_PORT", "6379"))
redis_password = os.getenv("REDIS_PASSWORD", "")

if redis_host:
    redis_client = redis.Redis(
        host=redis_host, 
        port=redis_port, 
        password=redis_password if redis_password else None,
        decode_responses=True
    )
else:
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

async def init_redis():
    global redis_client
    await redis_client.ping()

async def close_redis():
    if redis_client:
        await redis_client.aclose()

async def load_history(session_id: str) -> list:
    """Load conversation history for the session from Redis."""
    key = f"chat_history:{session_id}"
    data = await redis_client.get(key)
    if data:
        try:
            return json.loads(data)
        except Exception:
            pass
    return []

async def save_history(session_id: str, messages: list):
    """Save conversation history to Redis with a 24-hour expiration."""
    key = f"chat_history:{session_id}"
    
    # Prune history to keep approximately the last 8 messages
    if len(messages) > 8:
        pruned = messages[-8:]
        # Ensure the conversation starts with a 'user' message
        while pruned and pruned[0].get("role") != "user":
            pruned.pop(0)
            
        # Ensure we don't have a 'user' message that starts with a tool_result
        # without its corresponding 'assistant' tool_use
        while pruned and pruned[0].get("role") == "user":
            content = pruned[0].get("content", [])
            has_tool_result = any(
                isinstance(c, dict) and c.get("type") == "tool_result" 
                for c in (content if isinstance(content, list) else [])
            )
            if has_tool_result:
                pruned.pop(0)
                # Now the next message would be 'assistant', so loop again
                while pruned and pruned[0].get("role") != "user":
                    pruned.pop(0)
            else:
                break
                
        messages = pruned

    await redis_client.set(key, json.dumps(messages), ex=86400)
