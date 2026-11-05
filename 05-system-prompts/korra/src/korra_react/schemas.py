"""
Filename: schemas.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 12 (System Prompts)

The structured response every request ends with, and the final_answer tool
whose arguments the model must fill to stop the ReAct loop.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["answered", "refused", "needs_clarification", "error"]
ReasonCode = Literal[
    "write_not_permitted", "confidential_instructions", "credentials", "privacy",
    "out_of_scope", "prompt_injection", "tool_failure", "step_limit",
    "invalid_context", "invalid_input", "invalid_format", "unapproved_action",
    "invalid_arguments",
    "missing_detail",
]


class FinalAnswer(BaseModel):
    """Arguments of the final_answer tool (filled by the model)."""
    reason: str = Field(description="One short public sentence: why you are finishing now")
    status: Status
    answer: str = Field(description="Plain English, at most 120 words")
    data: list[dict[str, Any]] = Field(default_factory=list,
                                       description="Records used, or an empty list")
    reason_code: ReasonCode | None = Field(default=None,
                                           description="null when status is answered")


class KorraResponse(BaseModel):
    """What the application returns for every request (validated before printing)."""
    request_id: str
    status: Status
    answer: str = Field(max_length=1500)
    data: list[dict[str, Any]] = Field(default_factory=list)
    reason_code: ReasonCode | None = None
    actions_taken: list[str] = Field(default_factory=list)
    steps: int = 0
    stop_reason: str
    guard_flags: list[str] = Field(default_factory=list)
    policy_fingerprint: str = ""     # sha256 prefix of the stable policy file (not the text)
