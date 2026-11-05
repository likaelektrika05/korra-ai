# Korra Oversight Policy and Interrupt Design (Project 11, Section 1)

Lia Surguladze · COMPE 475, Fall 2026

No project manual was provided for Project 11, so this document is the specification. Each choice below is justified and mapped to the code that implements it (`korra/src/korra_hitl/`).

## 1. Approval points: what is protected and why

| Operation | Tool | Protected? | Reason |
|---|---|---|---|
| List / look up students | `read_student_records` | No | Read-only; no state changes, so nothing to undo. Runs as soon as the model asks. |
| Add a student | `save_student_record` | **Yes** | Writes a permanent record to the database. A model can misread a request, invent a value, or be asked to add someone who should not be added. A wrong insert affects real records, so a human approves first. |

There is exactly **one approval point**: the `approval_gate` node, which sits between Korra's proposal and `save_database_node`. The model is allowed to *propose* a save (the tool is bound so it can fill in the arguments), but no path in the graph sends a save to execution without going through `approval_gate`.

## 2. Interrupt condition and placement

```
START -> korra --route--> read_database_node -> korra                 (unprotected)
                   \----> approval_gate --approve/revise--> save_database_node -> korra
                   |            \--reject/timeout--> korra (model explains)
                   |            \--cancel--------> END
                   \----> END (plain answer)
```

- **Condition:** the model's reply contains a tool call named `save_student_record`. The router (`graph.route`) sends that turn to `approval_gate` and never to a tool node.
- **Placement:** *before* the protected action. `approval_gate` calls LangGraph `interrupt()`; the graph stops and the PostgreSQL checkpointer saves the whole state (messages, the proposed tool call with its arguments, the requester). `save_database_node` has not run, and nothing has been written.
- **One call per reply:** the model is bound with `parallel_tool_calls=False`, so a reply carries at most one tool call and one decision.

See `diagrams/workflow_graph.png` and `diagrams/decision_states.png`.

## 3. Decisions and their behavior

| Decision | Who may make it | Effect on the record | Workflow continuation | Final status |
|---|---|---|---|---|
| **approve** | authorized reviewer | proposed values saved, **once** | `save_database_node`, then `korra` reports the result | `approved` → `executed` |
| **revise** | authorized reviewer | reviewer's corrected values saved, **once** | the AI message's tool call is replaced with the revised arguments, then `save_database_node` → `korra` | `revised` → `executed` |
| **reject** | authorized reviewer | nothing saved | a `rejected` tool result (with reviewer and reason) goes back to `korra`, which explains it | `rejected` |
| **cancel** | authorized reviewer **or the original requester** | nothing saved | the workflow terminates (`END`) with a cancellation message | `cancelled` |
| **timeout** | the system, automatically | nothing saved | treated exactly like reject; `korra` explains | `timed_out` |

**Timeout.** A pending decision expires after `HITL_TIMEOUT_SECONDS` (default 600 s). Expiry is enforced every time a reviewer command runs (`pending`, `decide`, `sweep`): overdue decisions are claimed as `timed_out` and resumed as a rejection. A decision that arrives after expiry is refused. *Justification:* a stale approval should not silently write data minutes or hours after the request; failing closed (no write) is the safe default.

**Revision rules.** Only the five student fields can be changed (`--set field=value`). The revised record is validated with the same rules as any insert (valid email, GPA 0.0 to 4.0, date `YYYY-MM-DD`, non-empty name and major). An invalid revision is refused and the decision **stays pending**.

## 4. Decision context shown to the reviewer

`korra pending` lists every waiting decision; `korra show <ID>` and the `ask` output print the full card:

| Field | Why the reviewer needs it |
|---|---|
| `decision_id` | stable handle for the decision |
| protected action | what will happen if approved (`save_student_record`) |
| requested by, original request text | who asked and in what words, to catch a misread request |
| proposed values (all five fields) | exactly what would be written |
| relevant state: students on record, whether the email is already used (and by whom), validation problems | lets the reviewer spot duplicates and bad values before deciding |
| allowed decisions, timeout | what can be done and how long is left |
| status: `PENDING - nothing has been written` | confirms no side effect has happened yet |

## 5. Stable decision identifier

`decision_id = "D-" + uuid5(fixed namespace, thread_id + ":" + tool_call_id)[:12]`

The same thread and the same proposed tool call always produce the same ID, on every machine and after any restart. Because LangGraph re-runs `approval_gate` from its first line on resume, the pending row is written with `INSERT ... ON CONFLICT DO NOTHING`. Re-running never creates a second decision.

## 6. Authorization

- Reviewers are listed in `AUTHORIZED_REVIEWERS` (default `lia.surguladze,prof.nunez`), supplied at run time.
- `approve`, `reject` and `revise` require an authorized reviewer.
- `cancel` is allowed for an authorized reviewer or for the user who made the request (a requester may withdraw their own request, but may not approve it).
- Every refused attempt is written to the audit log with the actor and reason.
- Limitation: identity is the `--by` name given on the command line. This models the policy; a production system would authenticate the reviewer (login or signed token) instead of trusting the name.

## 7. Validation order for a decision (`cli.cmd_decide`)

1. decision value is one of `approve / reject / revise / cancel`, otherwise refused
2. decision ID exists, otherwise refused
3. actor is authorized for that decision, otherwise refused
4. decision is still `pending`, otherwise refused as duplicate/stale (`already approved by ...`)
5. not past the timeout, otherwise expired, resumed as timeout, and the decision refused
6. the thread's checkpoint is actually paused on this decision ID, otherwise refused as stale
7. revisions name real fields and produce a valid record, otherwise refused (stays pending)
8. **atomic claim**: `UPDATE hitl_decisions SET status=... WHERE decision_id=... AND status='pending'`. Only one caller can win, even if two reviewers decide at the same moment.
9. resume the graph with `Command(resume=decision)` from the checkpoint

## 8. Exactly-once execution

Two independent guards:

1. **Exactly one decision**: the atomic claim (step 8). A second approve, or an approve after reject or timeout, is refused before the graph is touched.
2. **Exactly one write**: `save_database_node` calls `oversight.execute_approved_save()`, which in **one transaction** locks the decision row (`SELECT ... FOR UPDATE`), checks `status in (approved, revised)` and `executed = false`, inserts the student, and sets `executed = true`. A second call returns `duplicate_prevented`; a call for a rejected decision returns `blocked`. Both are written to the audit log.

## 9. Priority

1. **Safety over progress.** Any failure (unknown decision, invalid input, database unavailable, timeout) leaves the record unwritten. The system fails closed.
2. **Cancellation over approval.** Whichever decision is claimed first wins (step 8). A requester's cancel that lands first prevents a later approval; an approval that lands first cannot be cancelled afterwards (the write has happened).
3. **Explicit decision over timeout.** A decision is accepted only while the request is within its timeout; past the limit the timeout is applied first.
4. **Order of review.** `korra pending` lists decisions oldest first (FIFO), so the request closest to its timeout is reviewed first.
5. **Blocked thread.** While a thread is paused, new messages on that thread are refused (`Thread 'X' is paused on D-...`). The conversation cannot move past an undecided action.

## 10. Audit requirements

Every oversight event is appended to `hitl_audit` (time, decision ID, thread, event, actor, detail):

`interrupt_raised`, `decision_approved`, `decision_revised`, `decision_rejected`, `decision_cancelled`, `decision_timed_out`, `decision_refused` (unauthorized, invalid, duplicate, stale, expired), `action_executed`, `duplicate_execution_prevented`, `execution_blocked`.

**No secrets.** Audit details are built only from decision fields (proposed values, reviewer, reason, outcome). Environment values are never written. `korra audit --check-secrets` scans every audit row for the configured OpenAI key, database password and LangSmith/Tavily keys, and for key-shaped strings, and reports any match.

## 11. Failure behavior

| Failure | Behavior |
|---|---|
| Database unavailable | the command prints `ERROR: database unavailable` and exits 1; nothing is decided or written |
| Unknown decision ID / invalid decision value / unauthorized actor | `REFUSED: ...`, exit 2, audited, decision stays pending |
| Duplicate or stale decision | `REFUSED: decision ... is already <status>`, audited |
| Invalid revision | refused, decision stays pending |
| Timeout | resumed as reject; later decisions refused |
| Process or container restart while pending | nothing lost: the checkpoint and decision row live in PostgreSQL; the decision can be made after the restart |
| Insert refused by the database rules (for example duplicate email) | the decision is marked executed with a `refused` result, so it is not retried; Korra explains |

## 12. Decision schema

Machine-readable in `decision_schema.json`. The payload passed to `Command(resume=...)`:

```json
{
  "decision": "approve | reject | revise | cancel | timeout",
  "actor": "lia.surguladze",
  "reason": "details verified",
  "revisions": { "gpa": 3.7 }
}
```

## 13. Workflow interrupt vs. CPU interrupt (Module 11.6 / 11.7)

| CPU interrupt | Korra approval interrupt |
|---|---|
| an event stops the normal instruction sequence | a `save_student_record` proposal stops the normal graph flow |
| processor state (PC, registers) is saved | graph state (messages, pending tool call, next node) is checkpointed to PostgreSQL |
| the handler services the event | a human reviewer makes a decision |
| return-from-interrupt restores state and continues | `Command(resume=...)` restores the checkpoint and continues on the chosen path |
| priority and masking | FIFO review, cancel-first-wins, and a paused thread refusing new input |

**Where the analogy stops:** there is no processor privilege level, no interrupt vector table, no hardware register save, and no hardware arbitration between devices. The pause can last minutes and survive a power cycle, which a CPU interrupt never does. It is an application-level control transfer that borrows the save, handle, restore shape.
