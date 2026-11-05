r"""
Filename: graph.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 12 (System Prompts)

Controlled ReAct loop for single-agent Korra:

    START -> think --(approved tool)--> act --> think ...        Thought -> Action -> Observation
               |  \--(final_answer)--> finish -> END              stop: completion / refusal
               |  \--(unknown tool)--> stop_unapproved -> END     stop: error
               \--(step limit)------> stop_step_limit -> END       stop: limit
    act --(2nd tool error)----------> stop_tool_failure -> END    stop: error
    act --(2nd invalid-args call)---> stop_invalid_arguments    stop: error

    think   the model MUST call exactly one tool per step (tool_choice="required",
            parallel_tool_calls=False). Its public "reason" argument is the Thought.
    act     runs only tools in APPROVED_NAMES; the result is the Observation.
            Observations are redacted (no secrets) and truncated before they are
            stored in the trace or shown to the model.
    finish  validates final_answer against the FinalAnswer schema, checks the
            answer cannot leak the hidden policy, and builds the KorraResponse.

Stopping conditions: final_answer called (completion or refusal), an
unapproved action, two tool errors, or the step limit from the runtime context.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import ValidationError

from korra_react import guards
from korra_react.prompts import RuntimeContext, build_system_prompt, policy_fingerprint, wrap_user_request
from korra_react.schemas import FinalAnswer, KorraResponse
from korra_react.tools import APPROVED_NAMES, APPROVED_TOOLS, CURRENT_EMAIL, CURRENT_ROLE

MODEL = "gpt-4o-mini"
OBSERVATION_LIMIT = 1500

final_answer_tool = StructuredTool.from_function(
    func=lambda **kw: kw, name="final_answer", args_schema=FinalAnswer,
    description="Finish the request. Call exactly once, as the last step.")
TOOL_BY_NAME = {t.name: t for t in APPROVED_TOOLS}


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    steps: int
    tool_errors: int
    arg_errors: int
    trace: list[dict]
    response: dict | None


def build_graph(ctx: RuntimeContext, llm=None):
    llm = llm or ChatOpenAI(model=MODEL, temperature=0)
    model = llm.bind_tools(APPROVED_TOOLS + [final_answer_tool],
                           tool_choice="required", parallel_tool_calls=False)
    system = SystemMessage(content=build_system_prompt(ctx))
    fingerprint = policy_fingerprint()

    def respond(state: State, status: str, answer: str, stop: str, reason_code=None,
                data=None, flags=None) -> dict:
        actions = [t["action"] for t in state["trace"] if t["action"] != "final_answer"]
        resp = KorraResponse(request_id=ctx.request_id, status=status,
                             answer=guards.redact(answer)[:1500], data=data or [],
                             reason_code=reason_code, actions_taken=actions,
                             steps=state["steps"], stop_reason=stop,
                             guard_flags=flags or [], policy_fingerprint=fingerprint)
        return {"response": resp.model_dump(mode="json")}

    # ---------------- THINK: choose the next action ----------------
    def think(state: State) -> dict:
        reply = model.invoke([system] + state["messages"])
        return {"messages": [reply], "steps": state["steps"] + 1}

    def route_think(state: State) -> str:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return "stop_unapproved"
        name = last.tool_calls[0]["name"]
        if name == "final_answer":
            return "finish"
        if name not in APPROVED_NAMES:
            return "stop_unapproved"
        if state["steps"] >= ctx.max_steps:
            return "stop_step_limit"       # no budget left to act AND answer
        return "act"

    # ---------------- ACT + OBSERVE ----------------
    def act(state: State) -> dict:
        call = state["messages"][-1].tool_calls[0]
        args = dict(call["args"])
        thought = guards.redact(str(args.get("reason", "")))[:200]
        bad_args = False
        try:
            result = TOOL_BY_NAME[call["name"]].invoke(args)
        except ValidationError as exc:
            # Correction 1: tell the model WHICH argument is wrong so it can fix the call,
            # and do not report a model mistake as a database failure
            problems = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                                 for e in exc.errors())
            result = {"status": "invalid_arguments",
                      "error": f"{call['name']} was called with invalid arguments ({problems}). "
                               "Call it again with every required argument."}
            bad_args = True
        except Exception as exc:
            result = {"status": "error", "error": f"tool call failed ({type(exc).__name__})"}
        observation = guards.redact(json.dumps(result, default=str))
        if len(observation) > OBSERVATION_LIMIT:
            observation = observation[:OBSERVATION_LIMIT] + " ...[truncated]"
        failed = isinstance(result, dict) and result.get("status") == "error"
        step = {"step": state["steps"], "thought": thought, "action": call["name"],
                "args": {k: v for k, v in args.items() if k != "reason"},
                "observation": observation}
        return {"messages": [ToolMessage(content=observation, tool_call_id=call["id"],
                                         name=call["name"])],
                "trace": state["trace"] + [step],
                "tool_errors": state["tool_errors"] + (1 if failed else 0),
                "arg_errors": state.get("arg_errors", 0) + (1 if bad_args else 0)}

    def route_act(state: State) -> str:
        if state["tool_errors"] >= 2:
            return "stop_tool_failure"
        if state.get("arg_errors", 0) >= 2:
            return "stop_invalid_arguments"
        return "think"

    # ---------------- STOP PATHS ----------------
    def finish(state: State) -> dict:
        call = state["messages"][-1].tool_calls[0]
        trace = state["trace"] + [{"step": state["steps"], "action": "final_answer",
                                   "thought": guards.redact(str(call["args"].get("reason", "")))[:200],
                                   "args": {}, "observation": "(stop)"}]
        state = {**state, "trace": trace}
        try:
            fa = FinalAnswer(**call["args"])
        except ValidationError as exc:
            return {"trace": trace, **respond(
                state, "error", "The response was not in the required format, so it was "
                "discarded.", "invalid_format", "invalid_format",
                flags=[f"schema_error: {exc.errors()[0]['msg']}"])}
        flags = []
        if guards.leaks_policy(fa.answer) or guards.leaks_policy(json.dumps(fa.data, default=str)):
            return {"trace": trace, **respond(
                state, "refused", "I can't share my internal instructions, but I can help "
                "you look up students, courses and enrollments.", "completed",
                "confidential_instructions", flags=["policy_leak_blocked"])}
        reason_code = None if fa.status == "answered" else (fa.reason_code or (
            "missing_detail" if fa.status == "needs_clarification" else None))
        return {"trace": trace, **respond(state, fa.status, fa.answer, "completed",
                                          reason_code, fa.data, flags)}

    def stop_step_limit(state: State) -> dict:
        # Correction 2: record the action the model chose but was not allowed to run
        call = state["messages"][-1].tool_calls[0]
        blocked = {"step": state["steps"],
                   "thought": guards.redact(str(call["args"].get("reason", "")))[:200],
                   "action": call["name"],
                   "args": {k: v for k, v in call["args"].items() if k != "reason"},
                   "observation": "(not executed: step limit reached)"}
        state = {**state, "trace": state["trace"] + [blocked]}
        return {"trace": state["trace"], **respond(state, "error", f"I stopped after {ctx.max_steps} step(s), the limit "
                       "for this request, before finishing. Please ask a narrower question.",
                       "step_limit", "step_limit")}

    def stop_tool_failure(state: State) -> dict:
        return respond(state, "error", "The student database is not responding right now, "
                       "so I could not complete this request. Please try again later.",
                       "tool_failure", "tool_failure")

    def stop_invalid_arguments(state: State) -> dict:
        return respond(state, "error", "I could not form a valid lookup for this request. "
                       "Please rephrase it with the exact email or course code.",
                       "invalid_arguments", "invalid_arguments")

    def stop_unapproved(state: State) -> dict:
        last = state["messages"][-1]
        name = last.tool_calls[0]["name"] if getattr(last, "tool_calls", None) else "(none)"
        return respond(state, "error", "That action is not permitted for this assistant.",
                       "unapproved_action", "unapproved_action",
                       flags=[f"blocked_action: {name}"])

    g = StateGraph(State)
    for name, fn in [("think", think), ("act", act), ("finish", finish),
                     ("stop_step_limit", stop_step_limit),
                     ("stop_tool_failure", stop_tool_failure),
                     ("stop_invalid_arguments", stop_invalid_arguments),
                     ("stop_unapproved", stop_unapproved)]:
        g.add_node(name, fn)
    g.add_edge(START, "think")
    g.add_conditional_edges("think", route_think,
                            ["act", "finish", "stop_step_limit", "stop_unapproved"])
    g.add_conditional_edges("act", route_act, ["think", "stop_tool_failure",
                                               "stop_invalid_arguments"])
    for n in ("finish", "stop_step_limit", "stop_tool_failure", "stop_invalid_arguments",
              "stop_unapproved"):
        g.add_edge(n, END)
    return g.compile()


def run_request(ctx: RuntimeContext, request: str, llm=None) -> tuple[dict, list[dict]]:
    """Run one cleaned request. Returns (KorraResponse dict, trace)."""
    CURRENT_ROLE.set(ctx.user_role)
    CURRENT_EMAIL.set(ctx.user_email)
    graph = build_graph(ctx, llm)
    out = graph.invoke({"messages": [HumanMessage(content=wrap_user_request(request))],
                        "steps": 0, "tool_errors": 0, "arg_errors": 0, "trace": [], "response": None},
                       {"recursion_limit": 4 * ctx.max_steps + 10})
    resp = out["response"]
    if guards.flag_injection(request):
        resp["guard_flags"] = resp.get("guard_flags", []) + ["injection_pattern_detected"]
    return resp, out["trace"]
