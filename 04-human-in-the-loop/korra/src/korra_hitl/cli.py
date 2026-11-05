"""
Filename: cli.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 11 (Human in the Loop)

Command-line front end for supervised Korra. Every command is a separate
process (in Docker, a fresh container), so state lives only in PostgreSQL:
the LangGraph checkpoints plus the hitl_decisions / hitl_audit tables.

    ask      --thread T [--user U] "message"   talk to Korra; stops at an approval point
    pending  [--latest-id]                      list decisions waiting for a reviewer
    show     ID                                 full decision context for one request
    decide   ID approve|reject|revise|cancel --by NAME [--reason R] [--set field=value ...]
    sweep                                       time out pending decisions past the limit
    audit    [--check-secrets]                  print the audit log
    history  --thread T                         show a thread's saved conversation
    students                                    list the students table

Exit status: 0 success, 2 refused/invalid decision, 1 error.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from korra_hitl import oversight
from korra_hitl.graph import build_graph
from korra_hitl.student_db import STUDENT_FIELDS, connect, validate_student

logging.basicConfig(level=logging.WARNING)
for noisy in ("httpx", "openai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

LINE = "-" * 68


# ============================================================
# SETUP
# ============================================================

@contextmanager
def korra_graph():
    conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True,
                           prepare_threshold=0, row_factory=dict_row)
    try:
        saver = PostgresSaver(conn)
        saver.setup()
        yield build_graph(saver)
    finally:
        conn.close()


def cfg(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def pending_interrupt(graph, thread_id: str) -> dict | None:
    """The interrupt payload waiting on this thread, or None."""
    state = graph.get_state(cfg(thread_id))
    for task in state.tasks:
        for intr in task.interrupts:
            return intr.value
    return None


def short(value, limit=220) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


# ============================================================
# OUTPUT
# ============================================================

def print_updates(graph, payload, thread_id: str) -> None:
    """Run the graph and print each node that executes (the path through the graph)."""
    for update in graph.stream(payload, cfg(thread_id), stream_mode="updates"):
        for node, change in update.items():
            if node == "__interrupt__":
                continue
            msgs = (change or {}).get("messages", []) if isinstance(change, dict) else []
            for m in msgs if isinstance(msgs, list) else [msgs]:
                if isinstance(m, AIMessage) and m.tool_calls:
                    c = m.tool_calls[0]
                    print(f"[{node}] proposes {c['name']}({json.dumps(c['args'])})")
                elif isinstance(m, ToolMessage):
                    print(f"[{node}] result: {short(m.content)}")
                elif isinstance(m, AIMessage):
                    print(f"[{node}] Korra: {m.content}")
            if not msgs:
                print(f"[{node}]")


def print_card(payload: dict) -> None:
    print(LINE)
    print(f"APPROVAL REQUIRED   decision_id: {payload['decision_id']}")
    print(LINE)
    print(f"Protected action : {payload['action']}")
    print(f"Requested by     : {payload['requested_by']}")
    print(f"Original request : {payload['request']}")
    print("Proposed values  :")
    for k in STUDENT_FIELDS:
        print(f"    {k:<16}= {payload['proposed_args'].get(k)}")
    ctx = payload["context"]
    print("Relevant state   :")
    for k, v in ctx.items():
        print(f"    {k:<22}= {v}")
    print(f"Allowed decisions: {', '.join(payload['allowed_decisions'])}")
    print(f"Times out after  : {payload['timeout_seconds']} s (treated as reject)")
    print("Status           : PENDING - nothing has been written to the database")
    print(LINE)
    print(f"DECISION_ID={payload['decision_id']}")


# ============================================================
# COMMANDS
# ============================================================

def cmd_ask(args) -> int:
    with korra_graph() as graph:
        waiting = pending_interrupt(graph, args.thread)
        if waiting:
            print(f"Thread '{args.thread}' is paused on {waiting['decision_id']}. "
                  "A reviewer must decide before the conversation continues.")
            print_card(waiting)
            return 2
        print(f"[{args.user}@{args.thread}] {args.message}")
        print_updates(graph, {"messages": [HumanMessage(content=args.message)],
                              "requested_by": args.user}, args.thread)
        waiting = pending_interrupt(graph, args.thread)
        if waiting:
            print_card(waiting)
    return 0


def expire_overdue(graph, only_id: str | None = None) -> int:
    """Time out pending decisions older than the limit and resume them as 'timeout'."""
    limit = oversight.timeout_seconds()
    count = 0
    for row in oversight.list_decisions("pending"):
        if only_id and row["decision_id"] != only_id:
            continue
        age = oversight.age_seconds(row)
        if age <= limit:
            continue
        reason = f"no decision within {limit} s (waited {int(age)} s)"
        if oversight.claim_decision(row["decision_id"], "timeout", "system", reason, None):
            print(f"TIMEOUT {row['decision_id']}: {reason} -> treated as reject")
            print_updates(graph, Command(resume={"decision": "timeout", "actor": "system",
                                                 "reason": reason}), row["thread_id"])
            count += 1
    return count


def cmd_pending(args) -> int:
    with korra_graph() as graph:
        expire_overdue(graph)
    rows = oversight.list_decisions("pending")
    if args.latest_id:
        if rows:
            print(rows[-1]["decision_id"])
        return 0 if rows else 1
    print(f"Pending decisions: {len(rows)}   (timeout {oversight.timeout_seconds()} s)")
    for r in rows:
        a = r["proposed_args"]
        print(f"  {r['decision_id']}  thread={r['thread_id']}  by={r['requested_by']}  "
              f"age={int(oversight.age_seconds(r))}s  save {a.get('name')} <{a.get('email')}>")
    return 0


def cmd_show(args) -> int:
    row = oversight.get_decision(args.decision_id)
    if not row:
        print(f"Unknown decision id {args.decision_id}")
        return 2
    with korra_graph() as graph:
        payload = pending_interrupt(graph, row["thread_id"])
    if row["status"] == "pending" and payload and payload["decision_id"] == args.decision_id:
        print_card(payload)
    else:
        print(json.dumps(row, indent=2, default=str))
    return 0


def refuse(message: str, decision_id: str | None, actor: str, **detail) -> int:
    print(f"REFUSED: {message}")
    oversight.log_event("decision_refused", decision_id=decision_id, actor=actor,
                        reason=message, **detail)
    return 2


def cmd_decide(args) -> int:
    actor = (args.by or "").strip().lower()
    did = args.decision_id

    # 1. Valid decision value
    if args.decision not in oversight.DECISIONS:
        return refuse(f"'{args.decision}' is not a valid decision "
                      f"(use {', '.join(oversight.DECISIONS)})", did, actor)
    # 2. Known decision
    row = oversight.get_decision(did)
    if not row:
        return refuse(f"unknown decision id {did}", did, actor)
    # 3. Authorization: reviewers decide; the requester may only cancel
    reviewers = oversight.authorized_reviewers()
    is_requester = actor == row["requested_by"].lower()
    if actor not in reviewers and not (args.decision == "cancel" and is_requester):
        return refuse(f"'{actor}' is not authorized to {args.decision} "
                      f"(authorized reviewers: {', '.join(sorted(reviewers))})", did, actor,
                      attempted=args.decision)
    # 4. Duplicate / stale decision
    if row["status"] != "pending":
        return refuse(f"decision {did} is already {row['status']}"
                      f"{' by ' + row['reviewer'] if row['reviewer'] else ''}; "
                      "it cannot be decided again", did, actor, attempted=args.decision)

    with korra_graph() as graph:
        # 5. Timeout is checked before any decision is accepted
        if expire_overdue(graph, only_id=did):
            return refuse(f"decision {did} expired before this decision arrived", did,
                          actor, attempted=args.decision)
        # 6. The checkpoint must really be waiting on THIS decision
        waiting = pending_interrupt(graph, row["thread_id"])
        if not waiting or waiting["decision_id"] != did:
            return refuse(f"thread {row['thread_id']} is not paused on {did} (stale)",
                          did, actor)
        # 7. Revisions must name real fields and produce a valid record
        revisions = {}
        if args.decision == "revise":
            for item in args.set or []:
                field, _, value = item.partition("=")
                field = field.strip()
                if field not in oversight.REVISABLE_FIELDS or not _:
                    return refuse(f"invalid revision '{item}' (fields: "
                                  f"{', '.join(oversight.REVISABLE_FIELDS)})", did, actor)
                revisions[field] = float(value) if field == "gpa" and _is_num(value) else value
            if not revisions:
                return refuse("revise needs at least one --set field=value", did, actor)
            _, problems = validate_student({**row["proposed_args"], **revisions})
            if problems:
                return refuse(f"revised record is invalid: {'; '.join(problems)}", did, actor)
        final_args = ({**row["proposed_args"], **revisions}
                      if args.decision in ("approve", "revise") else None)
        # 8. Atomic claim: only one decision can ever leave 'pending'
        if not oversight.claim_decision(did, args.decision, actor, args.reason, final_args):
            return refuse(f"decision {did} was decided by someone else first", did, actor)

        print(f"ACCEPTED: {args.decision} on {did} by {actor}"
              + (f" (revisions: {revisions})" if revisions else "")
              + (f" reason: {args.reason}" if args.reason else ""))
        print(f"Resuming thread '{row['thread_id']}' from its checkpoint ...")
        print_updates(graph, Command(resume={"decision": args.decision, "actor": actor,
                                             "reason": args.reason,
                                             "revisions": revisions}), row["thread_id"])
    return 0


def _is_num(text: str) -> bool:
    try:
        float(text)
        return True
    except ValueError:
        return False


def cmd_sweep(args) -> int:
    with korra_graph() as graph:
        n = expire_overdue(graph)
    print(f"Timed out {n} decision(s) (limit {oversight.timeout_seconds()} s).")
    return 0


def cmd_audit(args) -> int:
    rows = oversight.read_audit(limit=args.limit)
    print(f"{'#':>4}  {'time (UTC)':<19}  {'decision':<14}  {'event':<30}  {'actor':<15}  detail")
    for r in rows:
        print(f"{r['id']:>4}  {r['at'].strftime('%Y-%m-%d %H:%M:%S'):<19}  "
              f"{(r['decision_id'] or '-'):<14}  {r['event']:<30}  {(r['actor'] or '-'):<15}  "
              f"{short(r['detail'], 110)}")
    if args.check_secrets:
        total, hits = oversight.scan_audit_for_secrets()
        print(LINE)
        if hits:
            print(f"SECRET CHECK FAILED: {', '.join(hits)}")
            return 1
        print(f"SECRET CHECK PASSED: scanned {total} audit records for the configured "
              "API keys, the database password and key-shaped strings - none found.")
    return 0


def cmd_history(args) -> int:
    with korra_graph() as graph:
        state = graph.get_state(cfg(args.thread))
        for m in state.values.get("messages", []):
            if isinstance(m, HumanMessage):
                print(f"  user : {m.content}")
            elif isinstance(m, AIMessage) and m.tool_calls:
                print(f"  korra: proposes {m.tool_calls[0]['name']}({json.dumps(m.tool_calls[0]['args'])})")
            elif isinstance(m, ToolMessage):
                print(f"  tool : {short(m.content, 160)}")
            elif isinstance(m, AIMessage):
                print(f"  korra: {m.content}")
        print(f"  next : {state.next or '(finished)'}")
    return 0


def cmd_students(args) -> int:
    with connect() as conn:
        for r in conn.execute("SELECT id, name, email, major, gpa, enrollment_date "
                              "FROM students ORDER BY id"):
            print(f"  #{r[0]:<3} {r[1]:<22} {r[2]:<24} {r[3]:<24} {r[4]:<4} {r[5]}")
    return 0


# ============================================================
# MAIN
# ============================================================

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="korra-hitl", description="Supervised Korra")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask"); a.add_argument("--thread", required=True)
    a.add_argument("--user", default="student"); a.add_argument("message")
    a.set_defaults(fn=cmd_ask)
    pe = sub.add_parser("pending"); pe.add_argument("--latest-id", action="store_true")
    pe.set_defaults(fn=cmd_pending)
    s = sub.add_parser("show"); s.add_argument("decision_id"); s.set_defaults(fn=cmd_show)
    d = sub.add_parser("decide"); d.add_argument("decision_id"); d.add_argument("decision")
    d.add_argument("--by", required=True); d.add_argument("--reason")
    d.add_argument("--set", action="append", help="revision, e.g. --set gpa=3.7")
    d.set_defaults(fn=cmd_decide)
    sub.add_parser("sweep").set_defaults(fn=cmd_sweep)
    au = sub.add_parser("audit"); au.add_argument("--check-secrets", action="store_true")
    au.add_argument("--limit", type=int, default=200); au.set_defaults(fn=cmd_audit)
    h = sub.add_parser("history"); h.add_argument("--thread", required=True)
    h.set_defaults(fn=cmd_history)
    sub.add_parser("students").set_defaults(fn=cmd_students)
    args = p.parse_args(argv)

    try:
        oversight.ensure_schema()
        return args.fn(args)
    except psycopg.OperationalError as exc:
        print(f"ERROR: database unavailable ({type(exc).__name__}). "
              "Is the db container running and healthy?")
        return 1
    except KeyError as exc:
        print(f"ERROR: missing configuration {exc} (check .env)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
