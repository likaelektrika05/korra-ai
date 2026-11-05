"""
Filename: prompts.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 12 (System Prompts)

Builds the model's instruction layer from three separate pieces:

    prompts/system_policy.md      STABLE policy text (never formatted, never edited at run time)
    prompts/runtime_context.tmpl  TEMPLATE with $variables, filled only with VALIDATED values
    the user's message            DATA, wrapped in <user_request> tags in a separate human message

Because the user's text never goes through the template and never enters the
system message, it cannot silently replace control instructions. Runtime
values are validated (RuntimeContext) before substitution, and the template
uses string.Template.substitute, which fails on any missing variable instead
of leaving a hole.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import unicodedata
from datetime import date
from pathlib import Path
from string import Template
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

PROMPTS_DIR = Path(os.getenv("PROMPTS_DIR", Path(__file__).resolve().parents[3] / "prompts"))
MAX_REQUEST_CHARS = 2000
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z .'\-]{0,39}$")
EMAIL_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


class PromptError(ValueError):
    """Raised for missing or malformed runtime values or user input."""

    def __init__(self, code: str, problems: list[str]):
        super().__init__("; ".join(problems))
        self.code, self.problems = code, problems


# ============================================================
# VALIDATED TEMPLATE VARIABLES
# ============================================================

class RuntimeContext(BaseModel):
    """Every value that may be inserted into the template, with its rules."""
    model_config = {"extra": "forbid"}

    user_name: str = Field(default="Guest")
    user_role: Literal["student", "instructor"]
    user_email: str | None = None
    current_date: date = Field(default_factory=date.today)
    max_steps: int = Field(default=6, ge=1, le=8)
    request_id: str = Field(default_factory=lambda: "R-" + secrets.token_hex(4))

    @field_validator("user_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not NAME_RE.match(v):
            raise ValueError("user_name must be 1-40 letters, spaces, . ' or -")
        return v

    @field_validator("user_email")
    @classmethod
    def _email(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return None
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("user_email is not a valid email address")
        return v

    @model_validator(mode="after")
    def _student_needs_email(self):
        if self.user_role == "student" and not self.user_email:
            raise ValueError("user_email is required when user_role is student")
        return self


def build_context(**raw) -> RuntimeContext:
    """Validate raw runtime values; raise PromptError('invalid_context') on any problem."""
    raw = {k: v for k, v in raw.items() if v is not None}
    try:
        return RuntimeContext(**raw)
    except ValidationError as exc:
        problems = [f"{'.'.join(str(p) for p in e['loc']) or 'context'}: {e['msg']}"
                    for e in exc.errors()]
        raise PromptError("invalid_context", problems) from None


# ============================================================
# USER INPUT (DATA, NOT INSTRUCTIONS)
# ============================================================

def clean_user_request(text: str | None) -> str:
    """Normalize the request; raise PromptError('invalid_input') if unusable."""
    if text is None:
        raise PromptError("invalid_input", ["request is missing"])
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    text = text.strip()
    if not text:
        raise PromptError("invalid_input", ["request is empty"])
    if len(text) > MAX_REQUEST_CHARS:
        raise PromptError("invalid_input",
                          [f"request is {len(text)} characters (limit {MAX_REQUEST_CHARS})"])
    # The user cannot close our data tags and start "instructions"
    return text.replace("<user_request>", "[user_request]").replace(
        "</user_request>", "[/user_request]")


def wrap_user_request(text: str) -> str:
    return f"<user_request>\n{text}\n</user_request>"


# ============================================================
# PROMPT ASSEMBLY
# ============================================================

def load_policy() -> str:
    return (PROMPTS_DIR / "system_policy.md").read_text(encoding="utf-8")


def policy_fingerprint() -> str:
    return hashlib.sha256(load_policy().encode("utf-8")).hexdigest()[:16]


def render_runtime_context(ctx: RuntimeContext) -> str:
    template = Template((PROMPTS_DIR / "runtime_context.tmpl").read_text(encoding="utf-8"))
    try:
        return template.substitute(
            request_id=ctx.request_id, user_name=ctx.user_name, user_role=ctx.user_role,
            user_email=ctx.user_email or "(not provided)",
            current_date=ctx.current_date.isoformat(), max_steps=ctx.max_steps)
    except (KeyError, ValueError) as exc:
        raise PromptError("invalid_template", [f"template variable problem: {exc}"]) from None


def build_system_prompt(ctx: RuntimeContext) -> str:
    """Stable policy first, then the validated runtime block. User text is never here."""
    return load_policy().rstrip() + "\n\n" + render_runtime_context(ctx)
