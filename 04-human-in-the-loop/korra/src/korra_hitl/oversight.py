"""
Filename: oversight.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 11 (Human in the Loop)

Human-oversight bookkeeping, stored in PostgreSQL next to the LangGraph
checkpoints so a pending decision survives a restart.

    hitl_decisions   one row per protected action that was interrupted
    hitl_audit       append-only log of every oversight event

Decision lifecycle (see OVERSIGHT_POLICY.md):

    pending --approve--> approved --(save runs once)--> executed
            --revise---> revised  --(save runs once)--> executed
            --reject---> rejected
            --cancel---> cancelled
            --timeout--> timed_out

Exactly-once guarantees:
  * claim_decision() moves a row out of 'pending' with a single
    UPDATE ... WHERE status = 'pending'. Only one caller can win, so a
    second (duplicate or stale) decision is refused.
  * execute_approved_save() locks the row (SELECT ... FOR UPDATE), checks
    executed = false, inserts the student and sets executed = true in the
    SAME transaction, so the insert cannot happen twice.

Audit rows never contain environment values: details are built only from
decision fields, and scan_audit_for_secrets() verifies it.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from contextlib import closing
from datetime import datetime, timezone

import psycopg

from korra_hitl.student_db import connect, insert_student

DECISIONS = ("approve", "reject", "revise", "cancel")
FINAL_STATUS = {"approve": "approved", "reject": "rejected",
                "revise": "revised", "cancel": "cancelled", "timeout": "timed_out"}
REVISABLE_FIELDS = ("name", "email", "major", "gpa", "enrollment_date")
NAMESPACE = uuid.UUID("6f3c1a52-0b47-4a7e-9a59-2f1d5a0c4e11")   # fixed: stable IDs

SCHEMA = """
CREATE TABLE IF NOT EXISTS hitl_decisions (
    decision_id   TEXT PRIMARY KEY,
    thread_id     TEXT NOT NULL,
    tool_call_id  TEXT NOT NULL,
    action        TEXT NOT NULL,
    requested_by  TEXT NOT NULL,
    request_text  TEXT,
    proposed_args JSONB NOT NULL,
    final_args    JSONB,
    status        TEXT NOT NULL DEFAULT 'pending',
    reviewer      TEXT,
    reason        TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at    TIMESTAMPTZ,
    executed      BOOLEAN NOT NULL DEFAULT false,
    executed_at   TIMESTAMPTZ,
    result        JSONB
);
CREATE TABLE IF NOT EXISTS hitl_audit (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    decision_id TEXT,
    thread_id   TEXT,
    event       TEXT NOT NULL,
    actor       TEXT,
    detail      JSONB
);
"""


# ============================================================
# CONFIGURATION
# ============================================================

def authorized_reviewers() -> set[str]:
    raw = os.getenv("AUTHORIZED_REVIEWERS", "lia.surguladze,prof.nunez")
    return {r.strip().lower() for r in raw.split(",") if r.strip()}


def timeout_seconds() -> int:
    return int(os.getenv("HITL_TIMEOUT_SECONDS", "600"))


def ensure_schema() -> None:
    with closing(connect()) as conn:
        conn.execute(SCHEMA)
        conn.commit()


def make_decision_id(thread_id: str, tool_call_id: str) -> str:
    """Same thread + same tool call -> same ID, every time (stable across restarts)."""
    return "D-" + uuid.uuid5(NAMESPACE, f"{thread_id}:{tool_call_id}").hex[:12]


# ============================================================
# AUDIT
# ============================================================

def audit(cur, event: str, decision_id: str | None = None, thread_id: str | None = None,
          actor: str | None = None, **detail) -> None:
    cur.execute("INSERT INTO hitl_audit (decision_id, thread_id, event, actor, detail) "
                "VALUES (%s, %s, %s, %s, %s)",
                (decision_id, thread_id, event, actor, json.dumps(detail, default=str)))


def log_event(event: str, **kw) -> None:
    with closing(connect()) as conn:
        audit(conn.cursor(), event, **kw)
        conn.commit()


def read_audit(limit: int = 200) -> list[dict]:
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, at, decision_id, thread_id, event, actor, detail "
                    "FROM hitl_audit ORDER BY id DESC LIMIT %s", (limit,))
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in reversed(cur.fetchall())]


def scan_audit_for_secrets() -> tuple[int, list[str]]:
    """Look for any configured secret value or key-shaped string in the audit log."""
    secrets = [os.getenv(k) for k in ("OPENAI_API_KEY", "POSTGRES_PASSWORD",
                                       "LANGSMITH_API_KEY", "TAVILY_API_KEY")]
    secrets = [s for s in secrets if s and len(s) >= 6]
    patterns = re.compile(r"sk-[A-Za-z0-9_-]{16,}|tvly-[A-Za-z0-9]{16,}|lsv2_[A-Za-z0-9_]{16,}")
    rows = read_audit(limit=100000)
    hits = []
    for row in rows:
        text = json.dumps(row, default=str)
        if any(s in text for s in secrets) or patterns.search(text):
            hits.append(f"audit #{row['id']} ({row['event']})")
    return len(rows), hits


# ============================================================
# PENDING DECISIONS
# ============================================================

def record_pending(decision_id, thread_id, tool_call_id, requested_by, request_text,
                   proposed_args) -> bool:
    """Create the pending row once. Returns True only the first time (idempotent)."""
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO hitl_decisions (decision_id, thread_id, tool_call_id, action, "
            "requested_by, request_text, proposed_args) "
            "VALUES (%s, %s, %s, 'save_student_record', %s, %s, %s) "
            "ON CONFLICT (decision_id) DO NOTHING RETURNING decision_id",
            (decision_id, thread_id, tool_call_id, requested_by, request_text,
             json.dumps(proposed_args)))
        created = cur.fetchone() is not None
        if created:
            audit(cur, "interrupt_raised", decision_id, thread_id, requested_by,
                  action="save_student_record", proposed_args=proposed_args)
        conn.commit()
        return created


def get_decision(decision_id: str) -> dict | None:
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM hitl_decisions WHERE decision_id = %s", (decision_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(zip([c[0] for c in cur.description], row))


def list_decisions(status: str | None = "pending") -> list[dict]:
    with closing(connect()) as conn:
        cur = conn.cursor()
        if status:
            cur.execute("SELECT * FROM hitl_decisions WHERE status = %s "
                        "ORDER BY created_at", (status,))
        else:
            cur.execute("SELECT * FROM hitl_decisions ORDER BY created_at")
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def age_seconds(row: dict) -> float:
    return (datetime.now(timezone.utc) - row["created_at"]).total_seconds()


# ============================================================
# CLAIM (exactly one decision per pending row)
# ============================================================

def claim_decision(decision_id: str, decision: str, actor: str, reason: str | None,
                   final_args: dict | None) -> dict | None:
    """Atomically move pending -> final status. None means someone already decided."""
    status = FINAL_STATUS[decision]
    with closing(connect()) as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE hitl_decisions SET status = %s, reviewer = %s, reason = %s, "
            "final_args = %s, decided_at = now() "
            "WHERE decision_id = %s AND status = 'pending' RETURNING thread_id",
            (status, actor, reason, json.dumps(final_args) if final_args else None,
             decision_id))
        row = cur.fetchone()
        if row:
            audit(cur, f"decision_{status}", decision_id, row[0], actor,
                  reason=reason, final_args=final_args)
        conn.commit()
        return {"thread_id": row[0], "status": status} if row else None


# ============================================================
# EXACTLY-ONCE EXECUTION
# ============================================================

def execute_approved_save(decision_id: str, args: dict) -> dict:
    """Insert the student and mark the decision executed in one transaction."""
    try:
        with closing(connect()) as conn:
            cur = conn.cursor()
            cur.execute("SELECT status, executed, thread_id FROM hitl_decisions "
                        "WHERE decision_id = %s FOR UPDATE", (decision_id,))
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return {"status": "blocked", "reason": "no decision record"}
            status, executed, thread_id = row
            if status not in ("approved", "revised"):
                audit(cur, "execution_blocked", decision_id, thread_id, "system",
                      decision_status=status)
                conn.commit()
                return {"status": "blocked", "reason": f"decision is {status}, not approved"}
            if executed:
                audit(cur, "duplicate_execution_prevented", decision_id, thread_id, "system")
                conn.commit()
                return {"status": "duplicate_prevented",
                        "reason": "this approved action already ran once"}
            result = insert_student(cur, args)
            cur.execute("UPDATE hitl_decisions SET executed = true, executed_at = now(), "
                        "result = %s WHERE decision_id = %s",
                        (json.dumps(result, default=str), decision_id))
            audit(cur, "action_executed", decision_id, thread_id, "system",
                  outcome=result.get("status"), student_id=result.get("student_id"))
            conn.commit()
            return result
    except psycopg.Error as exc:
        return {"status": "error", "error": f"database unavailable: {type(exc).__name__}"}
