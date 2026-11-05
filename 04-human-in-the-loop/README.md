# Korra: Human in the Loop (Project 11)

Lia Surguladze · COMPE 475, Fall 2026

Korra from Project 10 (LangGraph + PostgreSQL student database) with human oversight. Before the protected action `save_student_record` writes anything, Korra **interrupts**, checkpoints her state in PostgreSQL, and issues a stable **decision ID**. An authorized reviewer then **approves, rejects, revises or cancels**; an unanswered request **times out**. The workflow resumes exactly once from the checkpoint, the write happens at most once, and every step goes to an audit log that contains no secrets. Model: OpenAI `gpt-4o-mini`.

No project manual was provided, so the design decisions are documented in **`OVERSIGHT_POLICY.md`** (Section 1).

## Contents

```
Surguladze_Lia_Project11/
├── README.md
├── OVERSIGHT_POLICY.md        S1: approval points, decisions, context, priority, authorization, audit, failures
├── decision_schema.json       S1: decision payload + decision record schema
├── diagrams/                  S1: workflow_graph.png, decision_states.png (+ .mmd sources)
├── Project11_Evidence.pdf     every scenario's output, labeled by section
├── evidence/                  raw logs 00-09 written by run_demo.ps1
├── docker-compose.yml         db (postgres:17, named volume) + korra (CLI image)
├── schema.sql                 student tables + seed rows (run once on an empty volume)
├── run_demo.ps1               runs the full oversight lifecycle and saves the logs
├── .env.example               key names only
└── korra/
    ├── Dockerfile, .dockerignore, pyproject.toml, requirements.txt
    └── src/korra_hitl/
        ├── graph.py           S2: korra -> approval_gate (interrupt) -> save_database_node
        ├── oversight.py       S2/S3: decision IDs, pending records, atomic claim, exactly-once save, audit
        ├── cli.py             S3: ask / pending / show / decide / sweep / audit / history / students
        └── student_db.py      Project 10 tools on PostgreSQL; validation shared with revisions
```

## Setup

`.env` beside `docker-compose.yml` (never submitted):
```
OPENAI_API_KEY=sk-...
POSTGRES_PASSWORD=choose_a_password
# optional
AUTHORIZED_REVIEWERS=lia.surguladze,prof.nunez
HITL_TIMEOUT_SECONDS=600
```

## Run the full demonstration (Section 4)

```
cd C:\k11
powershell -ExecutionPolicy Bypass -File run_demo.ps1
```
It builds the images, waits for the database to be healthy, runs every scenario below, and writes `evidence\00_build.log` to `evidence\09_audit_no_secrets.log`. To start over from an empty database: `docker compose down -v`.

## Run commands by hand

Each command runs in a fresh container; all state is in PostgreSQL.
```
docker compose up -d --wait db
docker compose run --rm korra ask --thread t1 --user student "Please add a student: Ana Lopez, ana@sdsu.edu, Computer Engineering, 3.6, 2026-10-26"
docker compose run --rm korra pending
docker compose run --rm korra show D-xxxxxxxxxxxx
docker compose run --rm korra decide D-xxxxxxxxxxxx approve --by lia.surguladze --reason "verified"
docker compose run --rm korra decide D-xxxxxxxxxxxx revise  --by lia.surguladze --set gpa=3.7
docker compose run --rm korra decide D-xxxxxxxxxxxx reject  --by prof.nunez --reason "..."
docker compose run --rm korra decide D-xxxxxxxxxxxx cancel  --by student
docker compose run --rm korra sweep
docker compose run --rm korra audit --check-secrets
docker compose run --rm korra history --thread t1
docker compose run --rm korra students
docker compose down          # keeps the volume (pending decisions survive)
```

## How it works

**Section 2: interruption and checkpoint state** (`graph.py`, `oversight.record_pending`)
- The router sends any `save_student_record` proposal to `approval_gate`, never to a tool node; reads go straight to `read_database_node`.
- `approval_gate` computes `decision_id = D-` + uuid5(thread_id:tool_call_id), records the pending row idempotently, and calls `interrupt()` with the decision context. The `PostgresSaver` checkpointer stores the full graph state.
- While pending: nothing is written, `korra students` is unchanged, `history` shows the next node is `approval_gate`, and a new message on that thread is refused.

**Section 3: decision handling and safe resume** (`cli.cmd_decide`, `oversight.claim_decision`, `oversight.execute_approved_save`)
- Validation order: decision value, known ID, authorization, still pending, not expired, checkpoint really paused on this ID, valid revisions; then an atomic `UPDATE ... WHERE status='pending'` claim.
- Resume with `Command(resume=decision)`: approve/revise → `save_database_node`; reject/timeout → back to `korra`, which explains; cancel → `END`.
- Exactly once: only one decision can claim a pending row, and the insert plus `executed=true` happen in one locked transaction (`duplicate_prevented` on any second run).

## Evidence (`Project11_Evidence.pdf`, `evidence/`)

| Log | Section | Shows |
|---|---|---|
| 00_build | S4 | images built; db healthy before Korra runs |
| 01_interrupt_paused_state | S2 | pause before the save; decision card with context; pending list; no row written; checkpoint next = approval_gate; paused thread refuses input |
| 02_invalid_decisions | S3 | unauthorized reviewer, invalid decision value, unknown ID refused; still pending |
| 03_approve_resume_once | S3 | approve → resume from checkpoint → saved once; second approval refused |
| 04_reject | S3 | reject → nothing saved, Korra explains the reviewer's reason |
| 05_revise | S3 | invalid revisions refused; valid revision saved with corrected values |
| 06_cancel | S3 | requester cancels → workflow ends, nothing saved |
| 07_restart_pending_preserved | S4 | all containers destroyed and recreated; the decision is still pending and is approved after the restart |
| 08_timeout | S4 | request expires → treated as reject; late approval refused |
| 09_audit_no_secrets | S4 | full audit trail; secret scan passes; image environment holds no key |
