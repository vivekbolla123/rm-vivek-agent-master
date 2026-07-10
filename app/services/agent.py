import json
import asyncio
import os
from typing import Optional, AsyncGenerator
from anthropic import AsyncAnthropicBedrock
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession
import contextlib
from app.redis_client import load_history, save_history

class MCPManager:
    def __init__(self):
        self.anthropic_tools = None
        self.system_prompt = None
        self._lock = asyncio.Lock()

    async def get_cached_data(self):
        async with self._lock:
            if self.anthropic_tools is None or self.system_prompt is None:
                mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8003/sse")
                async with sse_client(url=mcp_url) as streams:
                    async with ClientSession(streams[0], streams[1]) as session:
                        await session.initialize()
                        mcp_tools = await session.list_tools()
                        
                        self.anthropic_tools = []
                        for t in mcp_tools.tools:
                            self.anthropic_tools.append({
                                "name": t.name,
                                "description": t.description or "",
                                "input_schema": t.inputSchema
                            })
                        
                        prompt_res = await session.get_prompt("aria_system_prompt")
                        self.system_prompt = prompt_res.messages[0].content.text
            return self.anthropic_tools, self.system_prompt
            
    async def clear_cache(self):
        async with self._lock:
            self.anthropic_tools = None
            self.system_prompt = None

mcp_manager = MCPManager()

async def run_agent(message: str, session_id: str, user_id: Optional[str] = None, rm_token: Optional[str] = None) -> AsyncGenerator[str, None]:
    anthropic = AsyncAnthropicBedrock(
        aws_region=os.getenv("AWS_REGION", "ap-south-1")
    )
    
    # Request-scoped MCP session (only initialized if a tool is called)
    mcp_ctx = None
    mcp_session = None
    
    try:
        try:
            anthropic_tools, dynamic_system_prompt = await mcp_manager.get_cached_data()
        except Exception:
            await mcp_manager.clear_cache()
            anthropic_tools, dynamic_system_prompt = await mcp_manager.get_cached_data()
            
        messages = await load_history(session_id)
        
        if messages and messages[-1]["role"] == "user":
            if isinstance(messages[-1]["content"], list):
                messages[-1]["content"].append({"type": "text", "text": message})
            else:
                messages[-1]["content"] = [
                    {"type": "text", "text": messages[-1]["content"]},
                    {"type": "text", "text": message}
                ]
        else:
            messages.append({"role": "user", "content": message})
        
        while True:
            try:
                stream = await anthropic.messages.create(
                    model=os.getenv("BEDROCK_MODEL_ID", "apac.anthropic.claude-3-5-sonnet-20241022-v2:0"),
                    max_tokens=2048,
                    temperature=0.1,
                    system=dynamic_system_prompt,
                    tools=anthropic_tools,
                    messages=messages,
                    stream=True
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                yield f"event: error\ndata: {json.dumps({'detail': f'LLM Error: {str(e)}'})}\n\n"
                break
                
            current_tool_calls = []
            current_tool = None
            assistant_text = ""
            
            async for event in stream:
                if event.type == "content_block_delta" and event.delta.type == "text_delta":
                    text_chunk = event.delta.text
                    assistant_text += text_chunk
                    
                    if "<thinking>" in assistant_text and "</thinking>" not in assistant_text:
                        pass
                    elif text_chunk and not ("<thinking" in text_chunk or "</thinking" in text_chunk):
                        yield f"event: text\ndata: {json.dumps({'text': text_chunk})}\n\n"
                
                elif event.type == "content_block_start" and event.content_block.type == "tool_use":
                    current_tool = {"call": event.content_block, "args": ""}
                    current_tool_calls.append(current_tool)
                
                elif event.type == "content_block_delta" and event.delta.type == "input_json_delta":
                    if current_tool:
                        current_tool["args"] += event.delta.partial_json
                        
            if current_tool_calls:
                assistant_content = []
                if assistant_text:
                    assistant_content.append({"type": "text", "text": assistant_text})
                    
                    try:
                        from app.a2ui_orchestrator.parser import parse_agent_response
                        from app.a2ui_orchestrator.builder import build_a2ui_messages
                        parsed = parse_agent_response(assistant_text)
                        a2ui_msgs = build_a2ui_messages(parsed)
                        for msg in a2ui_msgs:
                            flat_msg = {**msg, **msg.get("metadata", {})}
                            yield f"event: metadata\ndata: {json.dumps({'messages': [flat_msg]})}\n\n"
                    except Exception as e:
                        pass

                for tc in current_tool_calls:
                    try:
                        parsed_args = json.loads(tc["args"])
                    except:
                        parsed_args = {}
                    assistant_content.append({
                        "type": "tool_use",
                        "id": tc["call"].id,
                        "name": tc["call"].name,
                        "input": parsed_args
                    })
                
                messages.append({
                    "role": "assistant",
                    "content": assistant_content
                })
                
                # Initialize MCP session lazily if not already open for this request
                if not mcp_session:
                    mcp_ctx = contextlib.AsyncExitStack()
                    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8003/sse")
                    streams = await mcp_ctx.enter_async_context(sse_client(url=mcp_url))
                    mcp_session = await mcp_ctx.enter_async_context(ClientSession(streams[0], streams[1]))
                    await mcp_session.initialize()
                
                async def execute_tool(tc):
                    tool_name = tc["call"].name
                    tool_id = tc["call"].id
                    try:
                        parsed_args = json.loads(tc["args"])
                    except:
                        parsed_args = {}
                        
                    tool_schema = next((t["input_schema"] for t in anthropic_tools if t["name"] == tool_name), {})
                    if "session_id" in tool_schema.get("properties", {}):
                        parsed_args["session_id"] = session_id
                    if "rm_token" in tool_schema.get("properties", {}) and rm_token:
                        parsed_args["rm_token"] = rm_token
                        
                    try:
                        result = await mcp_session.call_tool(tool_name, parsed_args)
                        tool_text = result.content[0].text if result.content else ""
                    except Exception as e:
                        return {
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "content": f"Error executing tool: {str(e)}",
                            "is_error": True
                        }

                    try:
                        parsed_result = json.loads(tool_text)
                        if "instruction" in parsed_result:
                            instr = parsed_result['instruction']
                            res = {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": tool_text
                            }
                            if instr.get("action") != "data_fetched":
                                res["_instruction_yield"] = instr
                            return res
                    except:
                        pass
                        
                    return {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": tool_text
                    }
                
                # Emit event: running instead of text
                yield f"event: running\ndata: {json.dumps({'status': True})}\n\n"
                
                tool_results = await asyncio.gather(*(execute_tool(tc) for tc in current_tool_calls))
                
                # Emit false after tools finish
                yield f"event: running\ndata: {json.dumps({'status': False})}\n\n"
                
                early_exit = False
                for res in tool_results:
                    if "_instruction_yield" in res:
                        instr_yield = res.pop("_instruction_yield")
                        yield f"event: metadata\ndata: {json.dumps({'messages': [instr_yield]})}\n\n"
                        early_exit = True
                
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
                
                if early_exit:
                    break
                    
                continue
                
            else:
                if assistant_text:
                    try:
                        from app.a2ui_orchestrator.parser import parse_agent_response
                        from app.a2ui_orchestrator.builder import build_a2ui_messages
                        
                        parsed = parse_agent_response(assistant_text)
                        a2ui_msgs = build_a2ui_messages(parsed)
                        for msg in a2ui_msgs:
                            flat_msg = {**msg, **msg.get("metadata", {})}
                            yield f"event: metadata\ndata: {json.dumps({'messages': [flat_msg]})}\n\n"
                    except Exception as e:
                        pass
                        
                    messages.append({"role": "assistant", "content": assistant_text})
                break
                
        await save_history(session_id, messages)
                    
    except asyncio.CancelledError:
        try:
            await save_history(session_id, messages)
        except:
            pass
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        err_msg = str(e)
        if hasattr(e, 'exceptions') and len(e.exceptions) > 0:
            err_msg = f"{type(e.exceptions[0]).__name__}: {str(e.exceptions[0])}"
        yield f"event: error\ndata: {json.dumps({'detail': f'Agent error: {err_msg}'})}\n\n"
    finally:
        if mcp_ctx:
            await mcp_ctx.aclose()
