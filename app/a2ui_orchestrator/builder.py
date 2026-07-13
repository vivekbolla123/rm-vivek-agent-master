from .types import ParsedResponse, A2UIMessage, MessageType
from .utils import generate_message_id, get_iso_timestamp

def build_a2ui_messages(parsed_response: ParsedResponse) -> list[dict]:
    # Returns a list of dicts that can be easily JSON serialized
    messages = []
    
    base_msg = {
        "id": generate_message_id(),
        "type": parsed_response.type.value,
        "content": parsed_response.text,
        "timestamp": get_iso_timestamp(),
        "stage_id": parsed_response.stage_id,
        "metadata": {}
    }
    
    # Generate dynamic UI Schema (SDUI) for the frontend to render
    ui_schema = {
        "theme": "default",
        "components": [],
        "actions": []
    }
    
    # Store standard fields directly in metadata for backward compatibility
    # or for specific widget functionality (like table previews)
    if parsed_response.type == MessageType.STAGED:
        base_msg["metadata"] = {
            "total_records": parsed_response.total_records,
            "fields_changed": parsed_response.fields_changed,
            "sample_changes": parsed_response.sample_changes
        }
        ui_schema["theme"] = "success"
        ui_schema["components"] = [{"type": "markdown", "content": parsed_response.text}]
        ui_schema["actions"] = [
            {"label": "Show Preview", "style": "primary", "actionType": "show_preview", "payload": parsed_response.stage_id}
        ]
        
    elif parsed_response.type == MessageType.DATA_VIEW:
        base_msg["metadata"] = {
            "total_records": parsed_response.total_records,
            "sample_changes": parsed_response.sample_changes
        }
        ui_schema["theme"] = "info"
        ui_schema["components"] = [{"type": "markdown", "content": parsed_response.text}]
        ui_schema["actions"] = [
            {"label": "View Data Grid", "style": "primary", "actionType": "show_preview", "payload": parsed_response.stage_id}
        ]
        
    elif parsed_response.type == MessageType.CONFIRMATION:
        ui_schema["theme"] = "default"
        ui_schema["components"] = [{"type": "markdown", "content": parsed_response.text}]
        ui_schema["actions"] = [
            {"label": "Proceed", "style": "primary", "actionType": "send_text", "payload": "yes"},
            {"label": "Cancel", "style": "secondary", "actionType": "send_text", "payload": "cancel"}
        ]
        
    elif parsed_response.type == MessageType.VALIDATION_ERROR:
        base_msg["metadata"] = {
            "errors": parsed_response.errors
        }
        ui_schema["theme"] = "error"
        ui_schema["components"] = [{"type": "pre", "content": parsed_response.text}]
        
    elif parsed_response.type == MessageType.ERROR:
        ui_schema["theme"] = "error"
        ui_schema["components"] = [{"type": "pre", "content": parsed_response.text}]
        
    elif parsed_response.type == MessageType.SUCCESS:
        ui_schema["theme"] = "success"
        ui_schema["components"] = [
            {"type": "heading", "content": "✅ Success"},
            {"type": "markdown", "content": parsed_response.text}
        ]
        if parsed_response.stage_id:
            ui_schema["actions"] = [
                {"label": "View Records", "style": "primary", "actionType": "show_preview", "payload": parsed_response.stage_id}
            ]
        
    elif parsed_response.type == MessageType.CLARIFICATION:
        ui_schema["theme"] = "clarification"
        ui_schema["components"] = [{"type": "text", "content": parsed_response.text}]
        
    else:
        # Default TEXT handling
        ui_schema["theme"] = "default"
        ui_schema["components"] = [{"type": "text", "content": parsed_response.text}]

    base_msg["metadata"]["ui_schema"] = ui_schema
    messages.append(base_msg)
    
    return messages
