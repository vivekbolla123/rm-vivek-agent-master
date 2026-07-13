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
        self.session = None
        self.exit_stack = None
        self._lock = asyncio.Lock()

    async def get_cached_data(self):
        async with self._lock:
            if self.session is None:
                mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:8003/sse")
                max_retries = 3
                retry_delay = 1
                for attempt in range(max_retries):
                    try:
                        self.exit_stack = contextlib.AsyncExitStack()
                        streams = await self.exit_stack.enter_async_context(sse_client(url=mcp_url))
                        self.session = await self.exit_stack.enter_async_context(ClientSession(streams[0], streams[1]))
                        await self.session.initialize()
                        break
                    except Exception as e:
                        if self.exit_stack:
                            await self.exit_stack.aclose()
                        if attempt == max_retries - 1:
                            raise Exception(f"Failed to connect to MCP server after {max_retries} attempts: {str(e)}")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                
            if self.anthropic_tools is None or self.system_prompt is None:
                mcp_tools = await self.session.list_tools()
                
                self.anthropic_tools = []
                for t in mcp_tools.tools:
                    self.anthropic_tools.append({
                        "name": t.name,
                        "description": t.description or "",
                        "input_schema": t.inputSchema
                    })
                
                prompt_res = await self.session.get_prompt("rm_assistant_system_prompt")
                self.system_prompt = prompt_res.messages[0].content.text
            return self.anthropic_tools, self.system_prompt, self.session
            
    async def clear_cache(self):
        async with self._lock:
            self.anthropic_tools = None
            self.system_prompt = None
            if self.exit_stack:
                await self.exit_stack.aclose()
            self.session = None
            self.exit_stack = None

mcp_manager = MCPManager()

async def run_agent(message: str, session_id: str, user_id: Optional[str] = None, rm_token: Optional[str] = None, anthropic: AsyncAnthropicBedrock = None) -> AsyncGenerator[str, None]:
    if anthropic is None:
        raise ValueError("Anthropic Bedrock client must be provided")
    
    # Request-scoped MCP session (only initialized if a tool is called)
    mcp_ctx = None
    mcp_session = None
    
    try:
        try:
            anthropic_tools, dynamic_system_prompt, mcp_session = await mcp_manager.get_cached_data()
        except Exception:
            await mcp_manager.clear_cache()
            anthropic_tools, dynamic_system_prompt, mcp_session = await mcp_manager.get_cached_data()
            
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
                yield {"event": "error", "data": {"detail": f"LLM Error: {str(e)}"}}
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
                        yield {"event": "text", "data": {"text": text_chunk}}
                
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
                            yield {"event": "metadata", "data": {"messages": [flat_msg]}}
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
                
                # We now use the persistent mcp_session from mcp_manager, no need to initialize it here.

                
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
                        try:
                            # Attempt reconnection and retry
                            await mcp_manager.clear_cache()
                            _, _, new_mcp_session = await mcp_manager.get_cached_data()
                            result = await new_mcp_session.call_tool(tool_name, parsed_args)
                            tool_text = result.content[0].text if result.content else ""
                        except Exception as retry_e:
                            return {
                                "type": "tool_result",
                                "tool_use_id": tool_id,
                                "content": f"Error executing tool (and retry failed): {str(retry_e)}",
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
                yield {"event": "running", "data": {"status": True}}
                
                tool_results = await asyncio.gather(*(execute_tool(tc) for tc in current_tool_calls))
                
                
                early_exit = False
                for res in tool_results:
                    if "_instruction_yield" in res:
                        instr_yield = res.pop("_instruction_yield")
                        yield {"event": "metadata", "data": {"messages": [instr_yield]}}
                        if instr_yield.get("action") != "data_fetched":
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
                            yield {"event": "metadata", "data": {"messages": [flat_msg]}}
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
        yield {"event": "error", "data": {"detail": f"Agent error: {err_msg}"}}
