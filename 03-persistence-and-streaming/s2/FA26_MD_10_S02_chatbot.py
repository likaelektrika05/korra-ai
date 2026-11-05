"""
Filename: FA26_MD_10_S02_chatbot.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026
Project: Project 10 - Korra: Persistence and Streaming (Section 2)

Description:
    The Project 06 Korra chatbot (one "chatbot" node, START -> chatbot -> END,
    messages kept in graph state) with three additions:

    1. Persistence  - the graph is compiled with a SqliteSaver checkpointer
                      backed by the FILE korra_checkpoints.db, so every turn
                      is written to disk and survives the program closing.
    2. Thread IDs   - at startup Korra asks for a thread ID. Reusing an ID
                      continues that saved conversation; a new ID starts clean.
    3. Streaming    - replies are printed token by token as the model
                      produces them (stream_mode="messages"), not after.

    Web search (Tavily) is kept from the Module 06 chatbot as a tool node.

    If the checkpoint database cannot be opened (missing folder, a folder in
    its place, or a file that is not a SQLite database), Korra prints a short
    message and exits with status 1 instead of showing a traceback.

Usage:
    conda activate korra
    python FA26_MD_10_S02_chatbot.py
    python FA26_MD_10_S02_chatbot.py --db some\\other\\path.db   (test a bad path)

    Keys come from .env (OPENAI_API_KEY, TAVILY_API_KEY), found by walking up
    from this folder.
"""

# ============================================================
# IMPORTS
# ============================================================

import argparse
import logging
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition


# ============================================================
# CONSTANTS
# ============================================================

MODEL_NAME = "gpt-4o-mini"
# Beside this script, so the same file is used whatever folder Korra is run from
DEFAULT_DB = Path(__file__).resolve().parent / "korra_checkpoints.db"
SYSTEM_PROMPT = ("You are Korra, a friendly AI assistant for a computer "
                 "architecture student. Use web search only for current "
                 "information. Keep answers short.")

logging.getLogger("httpx").setLevel(logging.WARNING)


# ============================================================
# STATE
# ============================================================

class State(TypedDict):
    # add_messages appends new messages instead of overwriting the list
    messages: Annotated[list, add_messages]


# ============================================================
# CHECKPOINTER
# ============================================================

def open_checkpointer(db_path: Path) -> SqliteSaver | None:
    """
    Open (or create) the checkpoint database and prepare its tables.

    Returns:
        SqliteSaver, or None after printing a one-line reason when the file
        cannot be used. No exception reaches the user.
    """
    try:
        # check_same_thread=False: LangGraph may write checkpoints from a
        # worker thread while the chat loop runs on the main thread
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()   # creates the checkpoint tables; fails on a non-database file
        return saver
    except (sqlite3.Error, OSError) as exc:
        print(f"Korra: Cannot open the checkpoint database '{db_path}'.")
        print(f"       Reason: {exc}")
        print("       Check that the folder exists and the file is a SQLite database.")
        return None


# ============================================================
# GRAPH
# ============================================================

def build_graph(checkpointer: SqliteSaver):
    search_tool = TavilySearch(max_results=2)
    llm = ChatOpenAI(model=MODEL_NAME, temperature=0.7).bind_tools([search_tool])

    def chatbot(state: State) -> dict:
        """Reads: messages. Writes: one AI message (an answer or a tool request)."""
        reply = llm.invoke([SystemMessage(content=SYSTEM_PROMPT)] + state["messages"])
        return {"messages": [reply]}

    builder = StateGraph(State)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", ToolNode([search_tool]))
    builder.add_edge(START, "chatbot")
    builder.add_conditional_edges("chatbot", tools_condition)   # -> tools or END
    builder.add_edge("tools", "chatbot")
    # The checkpointer saves the state after every step, keyed by thread_id
    return builder.compile(checkpointer=checkpointer)


# ============================================================
# CHAT LOOP
# ============================================================

def stream_reply(graph, user_text: str, config: dict) -> None:
    """Run one turn and print the model's tokens as they arrive."""
    print("Assistant: ", end="", flush=True)
    for chunk, metadata in graph.stream(
            {"messages": [HumanMessage(content=user_text)]},
            config, stream_mode="messages"):
        # Only the chatbot node's text tokens; tool results are not printed
        if (isinstance(chunk, AIMessageChunk)
                and metadata.get("langgraph_node") == "chatbot"):
            if chunk.content:
                print(chunk.content, end="", flush=True)
            elif chunk.tool_call_chunks and chunk.tool_call_chunks[0].get("name"):
                print("[searching the web...] ", end="", flush=True)
    print("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Korra chatbot with memory")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="checkpoint database file (default: korra_checkpoints.db)")
    args = parser.parse_args()

    load_dotenv()

    checkpointer = open_checkpointer(args.db)
    if checkpointer is None:
        return 1

    try:
        graph = build_graph(checkpointer)
    except Exception as exc:   # missing key, bad package: report, do not crash
        print(f"Korra: Could not start ({type(exc).__name__}: {exc})")
        return 1

    line = "=" * 60
    print(line)
    print("Welcome to Korra - AI Chatbot")
    print(f"Date: {date.today().strftime('%B %d, %Y')}")
    print(line)
    print("Reuse a thread ID to continue that saved conversation.")
    print("Type 'quit', 'exit', or 'q' to leave.\n")

    try:
        thread_id = input("Thread ID: ").strip()
        while not thread_id:
            thread_id = input("Thread ID (cannot be empty): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nKorra: Goodbye!")
        return 0

    config = {"configurable": {"thread_id": thread_id}}
    saved = graph.get_state(config).values.get("messages", [])
    if saved:
        print(f"(Continuing thread '{thread_id}': {len(saved)} saved messages)\n")
    else:
        print(f"(New thread '{thread_id}')\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nKorra: Goodbye!")
            break
        if user_input.lower() in {"quit", "exit", "q"}:
            print("Korra: Goodbye!")
            break
        if not user_input:
            continue
        try:
            stream_reply(graph, user_input, config)
        except Exception as exc:   # network or API failure: controlled reply
            print(f"\nKorra: Sorry, that request failed ({type(exc).__name__}). "
                  "Please try again.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
