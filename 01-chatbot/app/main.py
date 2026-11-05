"""Korra entry point: terminal chat loop that runs the LangGraph workflow."""
from langchain_core.messages import HumanMessage

from app.graph import graph


def text_of(message) -> str:
    """Return only the reply text (Gemini can return a list of content blocks)."""
    content = message.content
    if isinstance(content, str):
        return content
    return "".join(p.get("text", "") for p in content if isinstance(p, dict))


def main():
    print("Korra is ready. Type 'quit' to exit.\n")
    state = {"messages": []}  # conversation kept in graph state for this session

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
        state = graph.invoke(state)
        print(f"Korra: {text_of(state['messages'][-1])}\n")


if __name__ == "__main__":
    main()