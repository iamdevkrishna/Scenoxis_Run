"""
agent/state.py
LangGraph AgentState TypedDict — the single shared state flowing through the graph.
"""
from typing import TypedDict, Optional, Any


class AgentState(TypedDict, total=False):
    # Raw user input
    query: str

    # Classified intent — set by classify_intent node
    # Possible values: "app_launch" | "calc" | "page_analyze" | "yt_download" | "chat"
    intent: str

    # Personal memory context retrieved from ChromaDB for this query
    memory_context: list[str]

    # Active browser tab URL (pushed by companion extension or clipboard detection)
    active_tab_url: Optional[str]

    # Pre-captured full screen image bytes (used by vision model)
    image_bytes: Optional[bytes]

    # Final human-readable result to display in the UI
    result: str

    # Structured output from a tool call (app entry, calc dict, etc.)
    tool_output: Optional[dict]

    # Running conversation history for the Groq chat loop
    # Each element is a LangChain BaseMessage (or dict with role/content)
    messages: list[Any]

    # Results from a Tavily web_search tool invocation
    search_results: list[dict]

    # Whether to show a "thinking" indicator in the UI
    is_thinking: bool

    # Error message if something went wrong
    error: Optional[str]
