# Korra: System Prompts (Project 12)

Lia Surguladze · COMPE 475, Fall 2026

Single-agent Korra (Project 10 student database, PostgreSQL) with an explicit **behavioral control layer**: a stable system policy, a validated runtime template, structured JSON responses, and a controlled ReAct loop (Thought → Action → Observation) limited to approved read-only tools, with defined stopping conditions. A 21-case behavior matrix validates it in Docker. Model: OpenAI `gpt-4o-mini`.

No project manual was provided; the specification and rationale are in **`BEHAVIOR_SPEC.md`** and the failures found during validation, with their fixes, in **`CORRECTIONS.md`**.

## Contents

```
Surguladze_Lia_Project12/
├── README.md
├── BEHAVIOR_SPEC.md            S1: role, scope, priorities, refusals, uncertainty, response rules, rationale
├── CORRECTIONS.md              S4: defects found in run 1 and how they were fixed
├── Project12_Evidence.pdf      all evidence, labeled by section
├── prompts/
│   ├── system_policy.md        S1: the STABLE system prompt (mounted read-only)
│   └── runtime_context.tmpl    S2: template; only validated $variables
├── tests/behavior_cases.json   S4: 21 cases in 8 categories with expected outcomes
├── diagrams/react_workflow.png S3: controlled ReAct workflow
├── evidence/                   final run logs + validation_report.md/.json; run1_before_corrections/
├── docker-compose.yml, schema.sql, run_demo.ps1, .env.example
└── korra/
    ├── Dockerfile, .dockerignore, pyproject.toml, requirements.txt
    └── src/korra_react/
        ├── prompts.py          S2: RuntimeContext validation, input cleaning, prompt assembly
        ├── schemas.py          S2: FinalAnswer + KorraResponse schemas
        ├── tools.py            S3: four approved read-only tools, role-based privacy filter
        ├── graph.py            S3: think / act / finish + stop paths (limit, tool failure, bad args, unapproved)
        ├── guards.py           S3: injection flag, secret redaction, policy-leak guard
        └── cli.py              ask / validate / show-prompt / check-secrets
```

## Setup and run

`.env` beside `docker-compose.yml` (never submitted):
```
OPENAI_API_KEY=sk-...
POSTGRES_PASSWORD=choose_a_password
```

Full demonstration (build, sample requests, 21-case matrix, secret scan); logs go to `evidence\`:
```
cd C:\k12
powershell -ExecutionPolicy Bypass -File run_demo.ps1
```

By hand:
```
docker compose up -d --wait db
docker compose run --rm korra show-prompt --role student --name "Lia Surguladze" --email lia@sdsu.edu
docker compose run --rm korra ask --role instructor --name "Prof Nunez" "Who is enrolled in COMPE475?"
docker compose run --rm korra ask --role student --name "Alice Johnson" --email alice@sdsu.edu "What is my GPA?"
docker compose run --rm korra validate
docker compose run --rm korra check-secrets --paths evidence
docker compose down
```

## How the control layer works

**S1, system prompt** (`prompts/system_policy.md`): role, priority order (policy > runtime context > user), user text as data, the five permitted actions, refusal rules with reason codes (`write_not_permitted`, `confidential_instructions`, `credentials`, `privacy`, `out_of_scope`, `prompt_injection`), uncertainty handling (`needs_clarification`, no guessing), and response rules.

**S2, templates and structure:** `RuntimeContext` validates every template variable (role must be student or instructor, a valid email required for students, ISO date, name pattern with no newlines, step limit 1-8). `string.Template.substitute` fails on a missing variable. The user's message never enters the system message: it is cleaned and sent separately inside `<user_request>` tags. Invalid values produce a structured `error` (`invalid_context` / `invalid_input`) **without calling the model**. Every response is a validated `KorraResponse`.

**S3, controlled ReAct:** each step must call exactly one tool. The public `reason` argument is the Thought, the tool call is the Action, and the redacted, truncated result is the Observation. Only the four read-only tools and `final_answer` are allowed. Stops: `final_answer` (completion or refusal), unapproved tool, two tool errors, two invalid-argument calls, or the step limit. The privacy rule is enforced in the tools as well as the prompt; a leak guard replaces any answer that reproduces policy text.

**S4, validation:** `korra validate` runs `tests/behavior_cases.json` and checks status, reason code, required and forbidden tools, forbidden text, schema validity, and that no secret or policy text appears anywhere in the trace.

## Results (final run)

**21/21 passed** (`evidence/validation_report.md`):

| Category | Cases | What is proven |
|---|---|---|
| normal | N1-N4 | correct answers from tool data; N4 is the run-1 regression |
| boundary | B1-B3 | no-match lookup, GPA range edge, ambiguous request → needs_clarification |
| conflicting | C1-C2 | student asking for another student's GPA → privacy (also redacted in the tool); write → refused |
| refusal | R1 | out-of-scope homework request |
| adversarial | A1-A3 | prompt injection, request for keys, injection hidden after a valid request |
| malformed | M1-M6 | bad role, bad date, missing email, newline in a template value, empty request, step limit out of range |
| tool failure | T1 | database unavailable → error / tool_failure, no connection details shown |
| limit | S1 | step limit 1 → stop with the blocked action recorded |

Secret scan passed; the image environment contains no key or password.
