"""
Filename: cli.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 12 (System Prompts)

    ask       --role R [--name N] [--email E] [--date D] [--max-steps K] "request"
    validate  [--cases tests/behavior_cases.json] [--out evidence] [--only ID ...]
    show-prompt [--role R --email E]   policy fingerprint + rendered runtime block
    check-secrets [--paths ...]        scan prompts, rendered prompt and evidence for secrets

Exit status: 0 ok, 1 error, 2 validation failures.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from korra_react import guards
from korra_react.prompts import (PROMPTS_DIR, PromptError, build_context, build_system_prompt,
                                 clean_user_request, load_policy, policy_fingerprint,
                                 render_runtime_context)
from korra_react.schemas import KorraResponse

logging.basicConfig(level=logging.WARNING)
for noisy in ("httpx", "openai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
LINE = "-" * 72


def error_response(request_id: str, code: str, problems: list[str]) -> dict:
    return KorraResponse(request_id=request_id, status="error",
                         answer="The request could not be processed: " + "; ".join(problems),
                         reason_code=code, stop_reason=code,
                         policy_fingerprint=policy_fingerprint()).model_dump(mode="json")


def handle(raw_ctx: dict, request: str | None, llm=None) -> tuple[dict, list[dict], dict]:
    """Validate context and input, then run the ReAct graph. Never raises."""
    from korra_react.graph import run_request
    try:
        ctx = build_context(**raw_ctx)
    except PromptError as exc:
        return error_response("R-invalid", exc.code, exc.problems), [], {}
    try:
        text = clean_user_request(request)
    except PromptError as exc:
        return error_response(ctx.request_id, exc.code, exc.problems), [], ctx.model_dump(mode="json")
    try:
        resp, trace = run_request(ctx, text, llm)
    except Exception as exc:          # model/API failure: structured error, no traceback
        resp, trace = error_response(ctx.request_id, "tool_failure",
                                     [f"model call failed ({type(exc).__name__})"]), []
    return resp, trace, ctx.model_dump(mode="json")


def print_trace(trace: list[dict]) -> None:
    for t in trace:
        print(f"  Step {t['step']}")
        print(f"    Thought     : {t['thought']}")
        print(f"    Action      : {t['action']}({json.dumps(t['args'])})")
        print(f"    Observation : {t['observation'][:400]}"
              + (" ..." if len(t['observation']) > 400 else ""))


def cmd_ask(a) -> int:
    raw = {"user_name": a.name, "user_role": a.role, "user_email": a.email,
           "current_date": a.date, "max_steps": a.max_steps}
    print(f"REQUEST ({a.role}{', ' + a.email if a.email else ''}): {a.request!r}")
    resp, trace, _ = handle(raw, a.request)
    print("REACT TRACE" + ("" if trace else "  (rejected before any model call)"))
    print_trace(trace)
    print("STRUCTURED RESPONSE")
    print(json.dumps(resp, indent=2, default=str))
    return 0


# ============================================================
# BEHAVIOR VALIDATION
# ============================================================

def check_case(case: dict, resp: dict, trace: list[dict]) -> list[str]:
    exp, fails = case["expect"], []
    try:
        KorraResponse(**resp)
    except Exception as exc:
        fails.append(f"response does not match schema: {exc}")
    if resp["status"] not in exp["status"]:
        fails.append(f"status {resp['status']} not in {exp['status']}")
    if "reason_code" in exp and resp.get("reason_code") not in exp["reason_code"]:
        fails.append(f"reason_code {resp.get('reason_code')} not in {exp['reason_code']}")
    called = {t["action"] for t in trace} - {"final_answer"}
    for t in exp.get("must_call", []):
        if t not in called:
            fails.append(f"expected tool {t} was not called")
    for t in exp.get("must_not_call", []):
        if t == "*" and called:
            fails.append(f"no tool should run, but ran {sorted(called)}")
        elif t in called:
            fails.append(f"tool {t} must not be called")
    blob = (resp.get("answer", "") + json.dumps(resp.get("data", []), default=str)).lower()
    for s in exp.get("answer_excludes", []):
        if s.lower() in blob:
            fails.append(f"answer contains forbidden text {s!r}")
    for s in exp.get("answer_includes_any", []) and [exp["answer_includes_any"]]:
        if not any(x.lower() in blob for x in s):
            fails.append(f"answer contains none of {s}")
    if "max_steps_used" in exp and resp["steps"] > exp["max_steps_used"]:
        fails.append(f"used {resp['steps']} steps (> {exp['max_steps_used']})")
    leak = guards.leaks_policy(resp.get("answer", "")) or any(
        guards.leaks_policy(t["observation"]) or guards.leaks_policy(t["thought"]) for t in trace)
    if leak:
        fails.append("hidden policy text appeared in the answer or trace")
    secrets = guards.secret_values()
    text = json.dumps([resp, trace], default=str)
    if any(s in text for s in secrets) or guards.KEY_SHAPES.search(text):
        fails.append("a secret or key-shaped string appeared in the answer or trace")
    return fails


def cmd_validate(a) -> int:
    cases = json.loads(Path(a.cases).read_text(encoding="utf-8"))
    if a.only:
        cases = [c for c in cases if c["id"] in a.only]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    results, original_env = [], dict(os.environ)
    print(f"Running {len(cases)} behavior cases (policy fingerprint {policy_fingerprint()})")
    for c in cases:
        os.environ.clear(); os.environ.update(original_env)
        for k, v in c.get("env", {}).items():
            if k == "DATABASE_URL" and v == "@bad_database":
                v = original_env["DATABASE_URL"].rsplit("/", 1)[0] + "/no_such_database"
            os.environ[k] = v
        t0 = time.time()
        resp, trace, ctx = handle(c["context"], c.get("request"))
        os.environ.clear(); os.environ.update(original_env)
        fails = check_case(c, resp, trace)
        results.append({"id": c["id"], "category": c["category"], "title": c["title"],
                        "context": c["context"], "request": c.get("request"),
                        "expect": c["expect"], "response": resp, "trace": trace,
                        "passed": not fails, "failures": fails,
                        "seconds": round(time.time() - t0, 1)})
        mark = "PASS" if not fails else "FAIL"
        print(f"  [{mark}] {c['id']:<4} {c['category']:<12} {resp['status']:<20} "
              f"{str(resp.get('reason_code')):<26} steps={resp['steps']}  {c['title']}")
        for f in fails:
            print(f"         -> {f}")
    passed = sum(r["passed"] for r in results)
    print(LINE)
    print(f"RESULT: {passed}/{len(results)} passed")
    (out / "validation_results.json").write_text(json.dumps(results, indent=2, default=str),
                                                 encoding="utf-8")
    write_report(results, out / "validation_report.md")
    print(f"Wrote {out / 'validation_report.md'} and validation_results.json")
    return 0 if passed == len(results) else 2


def write_report(results: list[dict], path: Path) -> None:
    lines = ["# Korra behavior validation report", "",
             f"Policy fingerprint: `{policy_fingerprint()}` · cases: {len(results)} · "
             f"passed: {sum(r['passed'] for r in results)}", "",
             "| ID | Category | Case | Expected | Got | Steps | Tools | Result |",
             "|---|---|---|---|---|---|---|---|"]
    for r in results:
        e, g = r["expect"], r["response"]
        exp = "/".join(e["status"]) + (f" ({'/'.join(e['reason_code'])})" if "reason_code" in e else "")
        got = g["status"] + (f" ({g['reason_code']})" if g.get("reason_code") else "")
        tools = ", ".join(g["actions_taken"]) or "none"
        lines.append(f"| {r['id']} | {r['category']} | {r['title']} | {exp} | {got} | "
                     f"{g['steps']} | {tools} | {'PASS' if r['passed'] else 'FAIL: ' + '; '.join(r['failures'])} |")
    lines += ["", "## Case details", ""]
    for r in results:
        lines += [f"### {r['id']} · {r['title']}", "",
                  f"- context: `{json.dumps(r['context'])}`",
                  f"- request: `{r['request']!r}`", "", "ReAct trace:", "", "```"]
        for t in r["trace"]:
            lines.append(f"Step {t['step']}: Thought: {t['thought']}")
            lines.append(f"        Action: {t['action']}({json.dumps(t['args'])})")
            lines.append(f"        Observation: {t['observation'][:300]}")
        if not r["trace"]:
            lines.append("(rejected before any model call)")
        lines += ["```", "", "Response:", "", "```json",
                  json.dumps(r["response"], indent=2, default=str), "```", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================
# PROMPT INSPECTION AND SECRET CHECK
# ============================================================

def cmd_show_prompt(a) -> int:
    ctx = build_context(user_name=a.name, user_role=a.role, user_email=a.email)
    policy = load_policy()
    print(f"Stable policy file : {PROMPTS_DIR / 'system_policy.md'}")
    print(f"Policy fingerprint : sha256 {policy_fingerprint()} ({len(policy)} chars, "
          f"{len(policy.splitlines())} lines; text not printed: it is confidential to the model)")
    print(f"Template file      : {PROMPTS_DIR / 'runtime_context.tmpl'}")
    print("Rendered runtime block (validated values only):")
    print(render_runtime_context(ctx))
    sys_prompt = build_system_prompt(ctx)
    print(f"Assembled system prompt = policy ({len(policy)} chars) + runtime block "
          f"({len(sys_prompt) - len(policy)} chars). The user's request is NOT part of it;")
    print("it is sent separately inside <user_request> tags as data.")
    return 0


def cmd_check_secrets(a) -> int:
    secrets = guards.secret_values()
    targets = [PROMPTS_DIR / "system_policy.md", PROMPTS_DIR / "runtime_context.tmpl"]
    for p in a.paths:
        pp = Path(p)
        targets += [f for f in pp.rglob("*") if f.is_file()] if pp.is_dir() else [pp]
    ctx = build_context(user_name="Check", user_role="instructor")
    blobs = [("rendered system prompt", build_system_prompt(ctx))]
    blobs += [(str(f), f.read_text(encoding="utf-8", errors="ignore")) for f in targets if f.exists()]
    hits = []
    for name, text in blobs:
        if any(s in text for s in secrets):
            hits.append(f"{name}: contains a configured secret value")
        m = guards.KEY_SHAPES.search(text)
        if m:
            hits.append(f"{name}: key-shaped string {m.group(0)[:12]}...")
    print(f"Scanned {len(blobs)} items for {len(secrets)} configured secret values "
          "(OPENAI_API_KEY, POSTGRES_PASSWORD, DATABASE_URL ...) and key-shaped strings.")
    if hits:
        print("SECRET CHECK FAILED:\n  " + "\n  ".join(hits))
        return 1
    print("SECRET CHECK PASSED: no secrets in the prompts, the rendered system prompt, "
          "or the evidence files.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="korra-react")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("ask")
    a.add_argument("--role", required=True); a.add_argument("--name", default="Guest")
    a.add_argument("--email"); a.add_argument("--date"); a.add_argument("--max-steps", type=int)
    a.add_argument("request"); a.set_defaults(fn=cmd_ask)
    v = sub.add_parser("validate")
    v.add_argument("--cases", default="tests/behavior_cases.json")
    v.add_argument("--out", default="evidence"); v.add_argument("--only", nargs="*")
    v.set_defaults(fn=cmd_validate)
    s = sub.add_parser("show-prompt")
    s.add_argument("--role", default="student"); s.add_argument("--name", default="Lia Surguladze")
    s.add_argument("--email", default="lia@sdsu.edu"); s.set_defaults(fn=cmd_show_prompt)
    c = sub.add_parser("check-secrets"); c.add_argument("--paths", nargs="*", default=[])
    c.set_defaults(fn=cmd_check_secrets)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
