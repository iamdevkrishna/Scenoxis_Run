"""
agent/graph.py
Full LangGraph StateGraph for Scenoxis Run.

Graph shape:
  START → classify_intent
    → "app_launch"   → node_launch_app   → END
    → "calc"         → node_calculate    → END
    → "page_analyze" → node_page_analyze → END
    → "yt_download"  → node_yt_download  → END
    → "chat"         → node_retrieve_memory → node_groq_chat → node_maybe_write_memory → END

The groq_chat node loops back to itself if the model issues a tool call (web_search),
consuming results before producing the final answer.
"""
import logging
import os
import pathlib
from typing import Any, Literal

import yaml
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_groq import ChatGroq
from langgraph.graph import StateGraph, END, START

from agent.state import AgentState
from agent.classifier import classify
from agent.memory import get_store, should_store_as_memory
from agent.tools.launch_app import launch_app_direct
from agent.tools.calculator_tool import calculate
from agent.tools.web_search import web_search
from agent.tools.page_analyzer import analyze_current_page
from agent.tools.yt_downloader import download_youtube_video
from core.calculator import calculate as _calc_core
from core.app_index import get_index

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt loader with hot-reload
# ─────────────────────────────────────────────────────────────────────────────

_prompt_cache: dict[str, tuple[float, dict]] = {}   # path → (mtime, data)


def _load_prompt(filename: str) -> dict:
    path = pathlib.Path("prompts") / filename
    cache_key = str(path)
    try:
        mtime = path.stat().st_mtime
        if cache_key in _prompt_cache and _prompt_cache[cache_key][0] == mtime:
            return _prompt_cache[cache_key][1]
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        _prompt_cache[cache_key] = (mtime, data)
        return data
    except Exception as exc:
        log.warning("Could not load prompt %s: %s", filename, exc)
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# LLM client (shared, lazy)
# ─────────────────────────────────────────────────────────────────────────────

_llm: ChatGroq | None = None
_llm_with_tools: Any  = None

_CHAT_TOOLS = [web_search]


def _get_llm() -> ChatGroq:
    global _llm
    if _llm is None:
        prompt_cfg = _load_prompt("chat_system.yaml")
        _llm = ChatGroq(
            model=prompt_cfg.get("model", "llama-3.3-70b-versatile"),
            temperature=prompt_cfg.get("temperature", 0.4),
            max_tokens=prompt_cfg.get("max_tokens", 1024),
            api_key=os.environ.get("GROQ_API_KEY", ""),
            timeout=15.0,
            max_retries=0,
        )
    return _llm


def _get_llm_with_tools() -> Any:
    global _llm_with_tools
    if _llm_with_tools is None:
        _llm_with_tools = _get_llm().bind_tools(_CHAT_TOOLS)
    return _llm_with_tools


# ─────────────────────────────────────────────────────────────────────────────
# Graph nodes
# ─────────────────────────────────────────────────────────────────────────────

def node_classify_intent(state: AgentState) -> AgentState:
    query = state.get("query", "").strip()
    intent = classify(query, app_index=get_index())
    log.info("Intent: %s for query: %r", intent, query[:50])
    return {**state, "intent": intent, "is_thinking": False}


def node_launch_app(state: AgentState) -> AgentState:
    query = state.get("query", "")
    result_dict = launch_app_direct(query)
    if result_dict["launched"]:
        result = f"✓ Launched **{result_dict['name']}**"
    else:
        result = f"✗ Could not launch '{query}': {result_dict['error']}"
    return {**state, "result": result, "tool_output": result_dict}


def node_calculate(state: AgentState) -> AgentState:
    query = state.get("query", "")
    calc  = _calc_core(query)
    if calc["error"]:
        result = f"Could not evaluate: {query}"
    else:
        result = f"= **{calc['result']}**"
    return {**state, "result": result, "tool_output": calc}


def node_page_analyze(state: AgentState) -> AgentState:
    query    = state.get("query", "")
    # Strip trigger phrases to extract any specific instruction
    instruction = query.lower()
    for phrase in ("analyse the page", "analyze the page", "describe the screen",
                   "what is on screen", "analyse this", "analyze this"):
        instruction = instruction.replace(phrase, "").strip()

    image_bytes = state.get("image_bytes")
    
    if image_bytes:
        from agent.tools.page_analyzer import _call_groq_vision
        answer = _call_groq_vision(image_bytes, instruction)
    else:
        answer = analyze_current_page.invoke({"instruction": instruction})
        
    messages = list(state.get("messages", []))
    messages.append(HumanMessage(content=query))
    messages.append(AIMessage(content=answer))
        
    return {**state, "result": answer, "messages": messages, "is_thinking": False}


def node_yt_download(state: AgentState) -> AgentState:
    query = state.get("query", "")
    url   = state.get("active_tab_url") or query
    answer = download_youtube_video.invoke({"url": url})
    return {**state, "result": answer, "tool_output": {"url": url}}


def node_retrieve_memory(state: AgentState) -> AgentState:
    query   = state.get("query", "")
    store   = get_store()
    context = store.retrieve_personal_context(query, n_results=5)
    session = store.retrieve_session_context(query, n_results=3)
    return {**state, "memory_context": context + session, "is_thinking": True}


def node_groq_chat(state: AgentState) -> AgentState:
    """
    Send messages to Groq. If the model issues a tool call (web_search),
    execute it and loop back by returning 'continue_tools' routing signal
    embedded in the state. We handle this as an inline tool-call loop here
    (LangGraph handles the routing via the conditional edge below).
    """
    query          = state.get("query", "")
    memory_context = state.get("memory_context", [])
    messages       = list(state.get("messages", []))

    # Always append the user's current query to the message history
    messages.append(HumanMessage(content=query))

    # Build system prompt with injected memory context
    prompt_cfg = _load_prompt("chat_system.yaml")
    sys_template = prompt_cfg.get(
        "system_prompt",
        "You are Scenoxis, a personal AI assistant.\n\nPersonal context:\n{memory_context}"
    )
    ctx_str = "\n".join(f"- {m}" for m in memory_context) if memory_context else "None available."
    system_content = sys_template.format(memory_context=ctx_str)
    
    import datetime
    current_time_str = datetime.datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
    system_content += f"\n\nCurrent system time: {current_time_str}"

    full_messages = [SystemMessage(content=system_content)] + messages

    llm = _get_llm_with_tools()
    try:
        response = llm.invoke(full_messages)
    except Exception as exc:
        log.error("Groq chat failed: %s", exc)
        err_str = str(exc)
        if "tool call validation failed" in err_str or "400" in err_str or "Failed to call a function" in err_str:
            friendly_err = "I'm sorry, I got a little confused trying to answer that. Could you please rephrase your follow-up?"
        else:
            friendly_err = f"LLM error: {exc}"
        
        messages.append(AIMessage(content=friendly_err))
        return {**state, "result": friendly_err, "messages": messages, "is_thinking": False}

    # Append the model's response to the running history
    messages = messages + [response]

    # Check if the model wants to call a tool
    if hasattr(response, "tool_calls") and response.tool_calls:
        tool_call = response.tool_calls[0]
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]

        log.info("Tool call: %s(%s)", tool_name, tool_args)

        tool_result = ""
        search_results = []

        if tool_name == "web_search":
            tool_result = web_search.invoke(tool_args)
            search_results = [{"query": tool_args.get("query", ""), "result": tool_result}]

        # Append tool result message
        messages = messages + [
            ToolMessage(content=str(tool_result), tool_call_id=tool_call["id"])
        ]

        # Make a second Groq call with the tool result
        full_messages2 = [SystemMessage(content=system_content)] + messages
        try:
            final_response = _get_llm().invoke(full_messages2)
            messages = messages + [final_response]
            result_text = final_response.content or ""
        except Exception as exc:
            log.error("Groq post-tool call failed: %s", exc)
            err_str = str(exc)
            if "tool call validation failed" in err_str or "400" in err_str or "Failed to call a function" in err_str:
                result_text = "I'm sorry, I got a little confused trying to answer that. Could you please rephrase your follow-up?"
            else:
                result_text = f"LLM error: {exc}"
            messages.append(AIMessage(content=result_text))

        return {
            **state,
            "result":         result_text,
            "messages":       messages,
            "search_results": search_results,
            "is_thinking":    False,
        }

    # No tool call — direct answer
    result_text = response.content or ""
    return {
        **state,
        "result":      result_text,
        "messages":    messages,
        "is_thinking": False,
    }


def node_maybe_write_memory(state: AgentState) -> AgentState:
    messages = state.get("messages", [])
    if len(messages) < 2:
        return state

    # Find last human + last AI message
    last_human = ""
    last_ai    = ""
    for m in reversed(messages):
        if isinstance(m, AIMessage) and not last_ai:
            last_ai = m.content or ""
        elif isinstance(m, HumanMessage) and not last_human:
            last_human = m.content or ""
        if last_human and last_ai:
            break

    if not last_human:
        return state

    if should_store_as_memory(last_human, last_ai):
        # Store user message as the canonical fact text
        store = get_store()
        store.add_personal_fact(f"User said: {last_human}")
        log.info("Stored new personal fact from conversation")

    return state


# ─────────────────────────────────────────────────────────────────────────────
# Routing
# ─────────────────────────────────────────────────────────────────────────────

def _route_intent(state: AgentState) -> Literal[
    "app_launch", "calc", "page_analyze", "yt_download", "chat", "__end__"
]:
    intent = state.get("intent", "chat")
    if intent in ("app_launch", "calc", "page_analyze", "yt_download", "chat"):
        return intent
    return "__end__"


# ─────────────────────────────────────────────────────────────────────────────
# Graph assembly
# ─────────────────────────────────────────────────────────────────────────────

def build_graph():
    g = StateGraph(AgentState)

    # Nodes
    g.add_node("classify_intent",    node_classify_intent)
    g.add_node("app_launch",         node_launch_app)
    g.add_node("calc",               node_calculate)
    g.add_node("page_analyze",       node_page_analyze)
    g.add_node("yt_download",        node_yt_download)
    g.add_node("retrieve_memory",    node_retrieve_memory)
    g.add_node("groq_chat",          node_groq_chat)
    g.add_node("maybe_write_memory", node_maybe_write_memory)

    # Entry
    g.add_edge(START, "classify_intent")

    # Routing from classifier
    g.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "app_launch":   "app_launch",
            "calc":         "calc",
            "page_analyze": "page_analyze",
            "yt_download":  "yt_download",
            "chat":         "retrieve_memory",
            "__end__":      END,
        },
    )

    # Fast-path terminals
    g.add_edge("app_launch",   END)
    g.add_edge("calc",         END)
    g.add_edge("page_analyze", END)
    g.add_edge("yt_download",  END)

    # Chat pipeline
    g.add_edge("retrieve_memory",    "groq_chat")
    g.add_edge("groq_chat",          "maybe_write_memory")
    g.add_edge("maybe_write_memory", END)

    return g.compile()


# Module-level compiled graph singleton
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


def run_query(query: str, active_tab_url: str | None = None, messages: list | None = None, image_bytes: bytes | None = None) -> AgentState:
    """
    Top-level entry point used by the UI worker thread.
    Returns the final AgentState dict.
    """
    initial: AgentState = {
        "query":          query,
        "intent":         "",
        "memory_context": [],
        "active_tab_url": active_tab_url,
        "image_bytes":    image_bytes,
        "result":         "",
        "tool_output":    None,
        "messages":       messages or [],
        "search_results": [],
        "is_thinking":    True,
        "error":          None,
    }
    graph = get_graph()
    final = graph.invoke(initial)
    return final
