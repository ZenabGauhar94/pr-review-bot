"""
Structured output schema for the LLM review step.

We force the model to return JSON matching this schema instead of free text.
This is the difference between "an LLM wrapper" and something you can build
a real pipeline on top of: structured output means we can validate it,
filter by severity/confidence, post comments programmatically, and run
evals against a labeled dataset.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    NIT = "nit"           # style / nitpick, non-blocking
    SUGGESTION = "suggestion"
    BUG = "bug"            # likely functional bug
    SECURITY = "security"  # security-relevant issue


class Category(str, Enum):
    CORRECTNESS = "correctness"
    STYLE = "style"
    PERFORMANCE = "performance"
    SECURITY = "security"
    MAINTAINABILITY = "maintainability"
    TESTING = "testing"


class ReviewIssue(BaseModel):
    file: str
    line: int = Field(..., description="Real line number in the NEW file version")
    severity: Severity
    category: Category
    comment: str = Field(..., max_length=500)
    confidence: float = Field(..., ge=0.0, le=1.0)

    @field_validator("comment")
    @classmethod
    def comment_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("comment must not be empty")
        return v.strip()


class ReviewResult(BaseModel):
    summary: str = Field(..., max_length=1000)
    issues: list[ReviewIssue] = Field(default_factory=list)
    overall_risk: Severity = Severity.NIT
