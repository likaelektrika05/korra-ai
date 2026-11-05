r"""
Filename: graph.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026
Project: Project 10 - Korra: Persistence and Streaming (Sections 3 and 4)

Description:
    Korra with two database tools, each on its own node, routed by the name
    on the tool call (the Project 09 router pattern):

        START -> korra --route_tool_call--> read_database_node -> korra
                                       \--> save_database_node -> korra
                                       \--> END (no tool call)

    korra               gpt-4o-mini with both tools bound,
                        parallel_tool_calls=False (one tool call per reply)
    read_database_node  read_student_records  (list all / look up by email)
    save_database_node  save_student_record   (insert one student)

    The records live in the student database, not in the conversation, so
    a saved student is still there after the server restarts. Which node
    ran is visible in Studio, so the graph shows which tool answered.

Usage:
    pip install -e .     (from the korra folder)
    langgraph dev
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from dotenv import load_dotenv
from typing_extensions import TypedDict

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from korra_m10.tools.student_db_tools import read_student_records, save_student_record

load_dotenv()

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = (
    "You are Korra, an assistant for the COMPE 475 student records database. "
    "Use read_student_records to list students or look one up by email, and "
    "save_student_record to add a student. To add a student you need full "
    "name, email, major, GPA (0.0-4.0) and enrollment date (YYYY-MM-DD); ask "
    "for anything missing instead of guessing. Tool results have a status: "
    "explain 'refused', 'not_found' and 'error' results to the user in plain "
    "words. Never invent records."
)

NODE_KORRA = "korra"
NODE_READ = "read_database_node"
NODE_SAVE = "save_database_node"
TOOL_OWNER = {read_student_records.name: NODE_READ,
              save_student_record.name: NODE_SAVE}


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


llm = ChatOpenAI(model=MODEL, temperature=0).bind_tools(
    [read_student_records, save_student_record], parallel_tool_calls=False)

read_node = ToolNode([read_student_records])
save_node = ToolNode([save_student_record])


def korra(state: State) -> dict:
    """Answer, or request exactly one database tool."""
    reply = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
    return {"messages": [reply]}


def route_tool_call(state: State) -> str:
    """Send the turn to the node that owns the requested tool, or END."""
    last = state["messages"][-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return END
    name = last.tool_calls[0]["name"]
    node = TOOL_OWNER.get(name, END)
    logger.info("Router: %s -> %s", name, node)
    return node


builder = StateGraph(State)
builder.add_node(NODE_KORRA, korra)
builder.add_node(NODE_READ, read_node)
builder.add_node(NODE_SAVE, save_node)
builder.add_edge(START, NODE_KORRA)
builder.add_conditional_edges(NODE_KORRA, route_tool_call,
                              {NODE_READ: NODE_READ, NODE_SAVE: NODE_SAVE, END: END})
builder.add_edge(NODE_READ, NODE_KORRA)
builder.add_edge(NODE_SAVE, NODE_KORRA)

graph = builder.compile()

backend = "PostgreSQL" if os.getenv("DATABASE_URL") else "SQLite"
logger.info("Korra M10 graph ready: korra -> %s | %s (%s)", NODE_READ, NODE_SAVE, backend)
