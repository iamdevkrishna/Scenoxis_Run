"""
agent/tools/web_search.py
LangChain @tool wrapper for Tavily web search.
"""
import os
import ssl
import logging
from langchain_core.tools import tool

log = logging.getLogger(__name__)


@tool
def web_search(query: str) -> str:
    """
    Search the web via Tavily for current or external information not available
    in personal memory or the model's training data.
    Use this for news, current events, facts that change over time, or anything
    that needs verification from live sources.
    Returns a formatted summary of the top search results.
    """
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return "Tavily API key not configured. Set TAVILY_API_KEY in .env."

    # Try normal SSL first, then retry with verification disabled
    # (handles corporate proxies / VPNs that inject self-signed certs)
    for attempt in range(2):
        try:
            from tavily import TavilyClient

            if attempt == 1:
                log.debug("Retrying Tavily with SSL verification disabled")
                os.environ["CURL_CA_BUNDLE"] = ""
                os.environ["REQUESTS_CA_BUNDLE"] = ""
                try:
                    ssl._create_default_https_context = ssl._create_unverified_context
                except AttributeError:
                    pass

            client = TavilyClient(api_key=api_key)
            response = client.search(
                query=query,
                search_depth="basic",
                max_results=5,
                include_answer=True,
            )

            parts: list[str] = []

            if response.get("answer"):
                parts.append(f"**Summary:** {response['answer']}\n")

            results = response.get("results", [])
            for i, r in enumerate(results, 1):
                title   = r.get("title", "No title")
                url     = r.get("url", "")
                content = r.get("content", "").strip()
                if len(content) > 300:
                    content = content[:300] + "…"
                parts.append(f"{i}. **{title}**\n   {url}\n   {content}")

            if not parts:
                return "No results found."

            return "\n\n".join(parts)

        except Exception as exc:
            if attempt == 0 and "SSL" in str(exc):
                continue
            log.error("Tavily search failed: %s", exc)
            return f"Web search failed: {exc}"
