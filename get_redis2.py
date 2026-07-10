import redis
import json
import sys

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
keys = r.keys('chat_history:*')
if not keys:
    sys.exit()

for key in keys:
    history = r.get(key)
    msgs = json.loads(history)
    print(f"--- Session: {key} (length: {len(msgs)}) ---")
    for m in msgs[-15:]:
        role = m.get('role')
        content = m.get('content')
        print(f"Role: {role}")
        if isinstance(content, list):
            for c in content:
                if c.get('type') == 'text':
                    print(f"  - text: {c.get('text', '')}")
                elif c.get('type') == 'tool_use':
                    print(f"  - tool_use: {c.get('name')} {c.get('input')}")
                elif c.get('type') == 'tool_result':
                    print(f"  - tool_result: {c.get('content')}")
        else:
            print(f"  - {str(content)}")
