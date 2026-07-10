from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Any, List

class MessageType(str, Enum):
    TEXT = 'TEXT'                           # Plain bot text
    CLARIFICATION = 'CLARIFICATION'         # Bot asks for more info
    CONFIRMATION = 'CONFIRMATION'           # Structured confirmation block before tools run
    THINKING = 'THINKING'                   # Processing indicator
    STAGED = 'STAGED'                       # Changes staged, show preview button
    DATA_VIEW = 'DATA_VIEW'                 # View only, show preview button but different UI
    VALIDATION_ERROR = 'VALIDATION_ERROR'   # Validation failed, show error table
    PREVIEW = 'PREVIEW'                     # Diff table data
    SUCCESS = 'SUCCESS'                     # Submit completed
    ERROR = 'ERROR'                         # System error

@dataclass
class ParsedResponse:
    type: MessageType
    text: str
    stage_id: Optional[str] = None
    report_type: Optional[str] = None
    total_records: Optional[int] = None
    fields_changed: List[str] = field(default_factory=list)
    errors: List[dict] = field(default_factory=list)
    sample_changes: List[dict] = field(default_factory=list)

@dataclass
class A2UIMessage:
    id: str                                 # UUID
    type: MessageType
    content: str                            # Display text
    timestamp: str                          # ISO format
    stage_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)  # type-specific data
