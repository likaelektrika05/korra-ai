# Failures and Corrections (Project 12, Section 4)

Lia Surguladze · COMPE 475, Fall 2026

The behavior matrix was run in Docker with the real model (gpt-4o-mini). Evidence from the first run is kept unchanged in `evidence/run1_before_corrections/`; the final run is in `evidence/`.

## Run 1: 20/20 cases passed, but two real defects were found by reading the traces

A pass mark only checks the expected outcome, so every trace and demo log was also read by hand. That review found two defects that the pass marks hid.

### Defect 1: a model argument mistake was reported as a database failure

**Where:** `evidence/run1_before_corrections/02_react_normal.log` (request: *"Who is enrolled in COMPE475, and what is the course name?"*). The same mistake happened silently as the first step of case N3.

**What happened:**
```
Step 1  Action: course_roster({})            <- model left out the required course_code
        Observation: {"status": "error", "error": "tool call failed (ValidationError)"}
Step 2  Action: list_courses({})
Step 3  Action: course_roster({})            <- same mistake again: it was never told what was wrong
        -> stop_tool_failure: "The student database is not responding right now..."
```

**Why it was wrong:**
1. The observation hid the cause ("ValidationError"), so the model could not correct its call.
2. A model mistake (missing argument) was counted as a tool failure, so the user was told the **database** was down, which was false. The policy says Korra may only state facts from observations.

N3 passed only because the model happened to guess right on its second try.

**Correction (`graph.py`, act node, marked "Correction 1"):**
- Argument validation errors now return `{"status": "invalid_arguments", "error": "course_roster was called with invalid arguments (course_code: Field required). Call it again with every required argument."}`.
- They are counted separately (`arg_errors`) from real tool/database errors (`tool_errors`).
- A second invalid-argument call stops with a new, honest stop path: `stop_invalid_arguments` (`reason_code: invalid_arguments`, "I could not form a valid lookup for this request...").
- A regression case **N4** (the exact request that failed) was added to `tests/behavior_cases.json`. It requires `answered`, a `course_roster` call, the course name "Microprocessors", and forbids "not responding".

**Result after the correction** (`evidence/02_react_normal.log`):
```
Step 1  Action: course_roster({})
        Observation: {"status": "invalid_arguments", "error": "... (course_code: Field required). Call it again ..."}
Step 2  Action: course_roster({"course_code": "COMPE475"})      <- model fixed its own call
        Observation: {"status": "success", "course_name": "Microprocessors", "count": 3, ...}
Step 3  final_answer -> answered: "The course COMPE475 is titled 'Microprocessors'. The students enrolled are Alice Johnson, Bob Smith, and Carol Davis."
```

### Defect 2: the step-limit trace said "(no model call)"

**Where:** `evidence/run1_before_corrections/04_react_stops.log`, request with `--max-steps 1`.

**What happened:** the model *did* run (step 1 chose `course_roster`), but the graph stopped before executing it and recorded nothing, so the trace header printed "(no model call)". That is misleading evidence.

**Correction (`graph.py`, `stop_step_limit`, marked "Correction 2"; `cli.py`):** the blocked action is now recorded in the trace with the observation `(not executed: step limit reached)`. The empty-trace message now reads "(rejected before any model call)" and appears only for the validation failures (M1-M6), where it is true.

**Result after the correction** (`evidence/04_react_stops.log`):
```
Step 1  Thought: To find out which students are enrolled in COMPE475.
        Action: course_roster({})
        Observation: (not executed: step limit reached)
-> error / step_limit
```

## Observation kept as a known limitation (not changed)

**B2 ("Which students have a GPA of at least 3.9?"):** in both runs the model called `list_students` without the `min_gpa` filter and filtered the five returned rows itself. The answer is correct and comes only from observation data (Carol Davis, 3.9), so it passes, but it uses an extra step. Forcing the filter would mean weakening the "use as few steps as possible" design or hard-coding query rules into the prompt, so it is documented rather than patched.

## Final run: 21/21 passed

| | Run 1 (before corrections) | Final run |
|---|---|---|
| Cases | 20 | 21 (added regression N4) |
| Passed | 20 | 21 |
| Demo request "roster + course name" | wrong answer: "database is not responding" | correct: Microprocessors, Alice / Bob / Carol |
| Step-limit trace | "(no model call)" (misleading) | blocked action recorded |
| Secret scan | passed | passed |

Note from the final traces: gpt-4o-mini **consistently** leaves out `course_code` on its first `course_roster` call (N3, N4 and the demo all show it). Correction 1 is therefore not a rare edge case: every course-roster request now depends on the clear `invalid_arguments` observation to recover in one extra step. Files: `evidence/05_validation.log`, `evidence/validation_report.md`, `evidence/06_secrets.log`.
