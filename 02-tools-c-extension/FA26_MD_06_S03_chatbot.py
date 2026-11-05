"""
Filename: FA26_MD_06_S03_chatbot.py
Author: Lia Surguladze
Course: COMPE 475, Fall 2026, Project 08 - Korra: Tools

Korra chatbot with two tools bound to the model through LangGraph:
  - tavily_search            : web search (Tavily)
  - analyze_file_statistics  : the compiled C tool from Project 07, run through
                               the supplied Python wrapper (tools/file_stats_tool.py)

Graph:  START -> chatbot --(tool calls?)--> tools -> chatbot ... --(no tool calls)--> END
Every tool call and tool result is printed so the evidence shows what the
model asked for and exactly what the C program returned.

Run from this folder:  python FA26_MD_06_S03_chatbot.py
"""
import os
from typing import Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_tavily import TavilySearch
from langgraph.graph import StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from tools.file_stats_tool import analyze_file_statistics

load_dotenv()  # GOOGLE_API_KEY, MODEL_NAME, TAVILY_API_KEY


# ---------------- State ----------------
class State(TypedDict):
    messages: Annotated[list, add_messages]


# ---------------- Tools and model ----------------
search_tool = TavilySearch(max_results=2)
tools = [search_tool, analyze_file_statistics]

llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_NAME", "gemini-3.8-flash"),
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)
# Retry temporary API errors (such as 503 high demand) before giving up
llm_with_tools = llm.bind_tools(tools).with_retry(
    stop_after_attempt=4, wait_exponential_jitter=True
)

# ---------------- Nodes ----------------
def chatbot(state: State) -> dict:
    """Reads the conversation; returns an answer or a request to call tools."""
    return {"messages": [llm_with_tools.invoke(state["messages"])]}


# ---------------- Graph ----------------
builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.add_node("tools", ToolNode(tools))   # executes whichever tool the model chose
builder.add_edge(START, "chatbot")
builder.add_conditional_edges("chatbot", tools_condition)  # -> "tools" or END
builder.add_edge("tools", "chatbot")         # tool results go back to the model
graph = builder.compile()


# ---------------- Display helpers ----------------
def text_of(message) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict))


def show(message) -> None:
    if isinstance(message, AIMessage) and message.tool_calls:
        for call in message.tool_calls:
            print(f"  [TOOL CALL]   {call['name']}({call['args']})")
    elif isinstance(message, ToolMessage):
        result = str(message.content)
        if len(result) > 600:  # web search results are long; C results are short
            result = result[:600] + " ...[truncated]"
        print(f"  [TOOL RESULT] {message.name}: {result}")
    elif isinstance(message, AIMessage):
        print(f"Korra: {text_of(message)}\n")


# ---------------- Chat loop ----------------
def main():
    print("Korra (with tools) is ready. Type 'quit' to exit.\n")
    state = {"messages": []}

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

        state["messages"].append(HumanMessage(content=user_input))
        seen = len(state["messages"])

        before = list(state["messages"])
        try:
            # Stream each step so tool calls and results appear as they happen
            for snapshot in graph.stream(state, stream_mode="values"):
                for message in snapshot["messages"][seen:]:
                    show(message)
                seen = len(snapshot["messages"])
                state = snapshot
        except Exception as exc:
            # A model or network failure becomes a controlled reply, not a crash
            print(f"Korra: Sorry, I couldn't complete that ({type(exc).__name__}). "
                  "Please try again.\n")
            state = {"messages": before[:-1]}  # drop the failed turn

if __name__ == "__main__":
    main()