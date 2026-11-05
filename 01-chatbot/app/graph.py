"""Korra LangGraph workflow (Project 06).

State : messages - the running conversation (list of chat messages).
Node  : chatbot  - sends the conversation to the LLM and appends its reply.
Edges : START -> chatbot -> END  (one model call per user turn, then stop)
"""
import os
from typing import Annotated
from typing_extensions import TypedDict

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

load_dotenv()  # reads GOOGLE_API_KEY and MODEL_NAME from .env (or Docker env vars)


class State(TypedDict):
    # add_messages appends new messages instead of overwriting the list
    messages: Annotated[list, add_messages]


llm = ChatGoogleGenerativeAI(
    model=os.getenv("MODEL_NAME", "gemini-3.8-flash"),
    google_api_key=os.getenv("GOOGLE_API_KEY"),
)


def chatbot(state: State) -> dict:
    """Reads: messages. Writes: one new AI message."""
    reply = llm.invoke(state["messages"])
    return {"messages": [reply]}


def build_graph():
    builder = StateGraph(State)
    builder.add_node("chatbot", chatbot)
    builder.add_edge(START, "chatbot")   # entry point
    builder.add_edge("chatbot", END)     # termination
    return builder.compile()


graph = build_graph()