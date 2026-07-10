import re
import uuid
from datetime import datetime, timezone

def extract_stage_id(text: str) -> str:
    match = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text, re.IGNORECASE)
    return match.group(0) if match else None

def extract_record_count(text: str) -> int:
    match = re.search(r'Records to update\s*:\s*(\d+)', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def extract_field_names(text: str) -> list:
    fields = ["hardAnchor", "B2BBackstop", "B2CBackstop", "plfThreshold"]
    found = []
    for f in fields:
        if f in text:
            found.append(f)
    return found

def generate_message_id() -> str:
    return str(uuid.uuid4())

def get_iso_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
