r"""
Filename: graph.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026 - Project 11 (Human in the Loop)

Korra from Project 10 with a supervised write path:

    START -> korra --route--> read_database_node -> korra          (unprotected)
                       \----> approval_gate --approve/revise--> save_database_node -> korra
                       |             \--reject/timeout--> korra (model explains)
                       |             \--cancel--------> END
                       \----> END

approval_gate is the interrupt point. It runs BEFORE the protected action:
  1. computes a stable decision ID from (thread_id, tool_call_id)
  2. records the pending decision (idempotent) and the audit event
  3. calls interrupt(context) - the graph stops here and the checkpointer
     saves the full state (messages + the proposed tool call) in PostgreSQL
  4. on resume, applies the human decision and picks the continuation

The save never runs from a ToolNode; save_database_node calls
oversight.execute_approved_save(), which refuses unless the decision row
says approved/revised and not yet executed.

Note: LangGraph re-runs approval_gate from its first line when it resumes,
which is why step 2 must be idempotent (ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

import json
from typing import Annotated, Literal

from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from korra_hitl import oversight
from korra_hitl.student_db import decision_context, read_student_records, save_student_record

MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are Korra, an assistant for the COMPE 475 student records database. "
    "Use read_student_records to list or look up students. When the user asks "
    "to add a student and gives all five fields (name, email, major, GPA, "
    "enrollment date YYYY-MM-DD), call save_student_record right away with "
    "exactly those values; do not ask the user to confirm, because a human "
    "reviewer approves every save. If a field is missing, ask for it. Tool "
    "results carry a status: explain saved, refused, rejected, timed_out and "
    "error results in plain words, including the reviewer's reason. Never "
    "invent records."
)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    requested_by: str
    approved_decision_id: str | None


def build_graph(checkpointer):
    llm = ChatOpenAI(model=MODEL, temperature=0).bind_tools(
        [read_student_records, save_student_record], parallel_tool_calls=False)
    read_node = ToolNode([read_student_records])

    def korra(state: State) -> dict:
        reply = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
        return {"messages": [reply]}

    def route(state: State) -> str:
        last = state["messages"][-1]
        if not isinstance(last, AIMessage) or not last.tool_calls:
            return END
        name = last.tool_calls[0]["name"]
        if name == read_student_records.name:
            return "read_database_node"
        if name == save_student_record.name:
            return "approval_gate"          # protected: never straight to execution
        return END

    def approval_gate(state: State, config: RunnableConfig) -> Command[
            Literal["save_database_node", "korra", "__end__"]]:
        thread_id = config["configurable"]["thread_id"]
        ai = state["messages"][-1]
        call = ai.tool_calls[0]
        decision_id = oversight.make_decision_id(thread_id, call["id"])
        request = next((m.content for m in reversed(state["messages"])
                        if isinstance(m, HumanMessage)), "")
        requested_by = state.get("requested_by") or "student"

        # Idempotent: on resume this line runs again and does nothing
        oversight.record_pending(decision_id, thread_id, call["id"], requested_by,
                                 request, call["args"])

        # ---- the graph pauses here; state is checkpointed ----
        decision = interrupt({
            "decision_id": decision_id,
            "action": call["name"],
            "requested_by": requested_by,
            "request": request,
            "proposed_args": call["args"],
            "context": decision_context(call["args"]),
            "allowed_decisions": list(oversight.DECISIONS),
            "timeout_seconds": oversight.timeout_seconds(),
        })
        # ---- resumed: `decision` is the validated payload from cli.decide ----

        kind = decision["decision"]
        if kind in ("approve", "revise"):
            update = {"approved_decision_id": decision_id}
            if kind == "revise":
                new_args = {**call["args"], **decision["revisions"]}
                # Replace the AI message (same id) so the save uses the revised values
                update["messages"] = [ai.model_copy(update={"tool_calls": [
                    {**call, "args": new_args}]})]
            return Command(goto="save_database_node", update=update)

        result = {"status": oversight.FINAL_STATUS[kind],
                  "decision_id": decision_id,
                  "reviewer": decision.get("actor"),
                  "reason": decision.get("reason"),
                  "message": "Nothing was saved."}
        tool_msg = ToolMessage(content=json.dumps(result), tool_call_id=call["id"],
                               name=call["name"])
        if kind == "cancel":
            done = AIMessage(content=f"The save request {decision_id} was cancelled "
                                     f"by {decision.get('actor')}. Nothing was saved.")
            return Command(goto=END, update={"messages": [tool_msg, done]})
        return Command(goto="korra", update={"messages": [tool_msg]})   # reject / timeout

    def save_database_node(state: State) -> dict:
        ai = state["messages"][-1]
        call = ai.tool_calls[0]
        decision_id = state.get("approved_decision_id")
        result = (oversight.execute_approved_save(decision_id, call["args"])
                  if decision_id else {"status": "blocked", "reason": "no approval"})
        result["decision_id"] = decision_id
        return {"messages": [ToolMessage(content=json.dumps(result, default=str),
                                         tool_call_id=call["id"], name=call["name"])],
                "approved_decision_id": None}

    builder = StateGraph(State)
    builder.add_node("korra", korra)
    builder.add_node("read_database_node", read_node)
    builder.add_node("approval_gate", approval_gate)
    builder.add_node("save_database_node", save_database_node)
    builder.add_edge(START, "korra")
    builder.add_conditional_edges("korra", route,
                                  ["read_database_node", "approval_gate", END])
    builder.add_edge("read_database_node", "korra")
    builder.add_edge("save_database_node", "korra")
    return builder.compile(checkpointer=checkpointer)
