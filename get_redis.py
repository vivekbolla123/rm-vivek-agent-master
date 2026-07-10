import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
keys = r.keys('chat_history:*')
if not keys:
    print("No history found")
else:
    for key in keys:
        history = r.get(key)
        msgs = json.loads(history)
        print(f"--- Session: {key} (length: {len(msgs)}) ---")
        for m in msgs[-5:]:
            print(f"Role: {m.get('role')}")
            content = m.get('content')
            if isinstance(content, list):
                for c in content:
                    print(f"  - type: {c.get('type')}, text: {c.get('text', '')[:100]}")
                    if c.get('type') == 'tool_use':
                        print(f"  - tool_use: {c.get('name')} {c.get('input')}")
            else:
                print(f"  - {str(content)[:100]}")
