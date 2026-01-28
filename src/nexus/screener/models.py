from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field

class ScreeningDecision(str, Enum):
    """Decision for paper screening."""
    INCLUDE = "include"
    EXCLUDE = "exclude"
    MAYBE = "maybe"

class ScreeningResult(BaseModel):
    """Result of an LLM screening task."""
    doi: Optional[str] = None
    title: str
    decision: ScreeningDecision
    confidence: int = Field(..., ge=0, le=100, description="Confidence score 0-100")
    reasoning: str = Field(..., description="Brief explanation for the decision")
    tags: list[str] = Field(default_factory=list, description="Relevant keywords found")
