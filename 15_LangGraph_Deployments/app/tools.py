"""Toolbelt assembly for agents.

Collects third-party tools and local tools (like RAG) into a single list that
graphs can bind to their language models.
"""
from __future__ import annotations

import asyncio
from typing import List

from langchain_tavily import TavilySearch
from langchain_community.tools.arxiv.tool import ArxivQueryRun
from langchain_mcp_adapters.client import MultiServerMCPClient
from app.rag import retrieve_information


async def _get_mcp_tools_async() -> List:
    client = MultiServerMCPClient(
        {
            "systeminfo": {
                "transport": "http",
                "url": "http://localhost:8000/mcp"
            },
        }
    )
    return await client.get_tools()

def get_mcp_tools() -> List:
    """Return LangChain tools from the MCP server (sync wrapper)."""
    return asyncio.run(_get_mcp_tools_async())

def get_tool_belt() -> List:
    """Return the list of tools available to agents (Tavily, Arxiv, RAG)."""
    tavily_tool = TavilySearch(max_results=5)
    system_info_tools = get_mcp_tools()
    return [tavily_tool, ArxivQueryRun(), retrieve_information, *system_info_tools]


