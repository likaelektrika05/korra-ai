"""
Filename: guards.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 12 (System Prompts)

Checks that run in code, outside the model, so behavior does not depend only
on the model obeying the prompt:

    flag_injection(text)     marks requests that look like prompt injection
                             (recorded in guard_flags; the policy makes Korra refuse)
    redact(text)             removes secret values and key-shaped strings from
                             anything that is printed, logged or returned
    leaks_policy(text)       detects the hidden policy text or Policy ID in an
                             answer; the graph then replaces the answer with a refusal
"""

from __future__ import annotations

import os
import re

from korra_react.prompts import load_policy

INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|rules)",
    r"disregard (your|the) (rules|instructions|policy)",
    r"\byou are now\b", r"developer mode", r"\bjailbreak\b", r"\bDAN\b",
    r"(reveal|print|show|repeat|output).{0,30}(system prompt|hidden instructions|your instructions|policy)",
    r"^\s*system\s*:", r"\[/user_request\]",
]
_INJ = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE | re.MULTILINE)

KEY_SHAPES = re.compile(
    r"sk-[A-Za-z0-9_\-]{16,}|tvly-[A-Za-z0-9\-]{12,}|lsv2_[A-Za-z0-9_]{16,}"
    r"|postgres(ql)?://[^\s\"']+")
SECRET_ENV = ("OPENAI_API_KEY", "POSTGRES_PASSWORD", "LANGSMITH_API_KEY",
              "TAVILY_API_KEY", "DATABASE_URL")


def flag_injection(text: str) -> bool:
    return bool(_INJ.search(text or ""))


def secret_values() -> list[str]:
    vals = [os.getenv(k) for k in SECRET_ENV]
    return [v for v in vals if v and len(v) >= 6]


def redact(text: str) -> str:
    if not text:
        return text
    for v in secret_values():
        text = text.replace(v, "[REDACTED]")
    return KEY_SHAPES.sub("[REDACTED]", text)


def leaks_policy(text: str) -> bool:
    """True if the answer reproduces the policy ID or a distinctive policy sentence."""
    if not text:
        return False
    if "KP12-POLICY" in text:
        return True
    lowered = " ".join(text.lower().split())
    for line in load_policy().splitlines():
        line = " ".join(line.strip("-#* ").lower().split())
        if len(line) >= 60 and line in lowered:
            return True
    return False
