from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class LessonDecision(str, Enum):
    KEEP = "KEEP"
    PARTIAL = "PARTIAL"
    REVERT = "REVERT"

class LessonEntry(BaseModel):
    """
    Schema for lessons.jsonl items
    """
    lesson_id: str
    date: str
    solution_id: str
    fingerprint: str
    change: str
    measured: Dict[str, Any] = Field(description="snapshot_before, snapshot_after, result")
    decision: LessonDecision
    reason: str
    revisit_if: Optional[str] = None
