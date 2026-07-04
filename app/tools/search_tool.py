"""
搜索工具 — Tavily API 封装
"""
import os
from langchain_core.tools import tool
from tavily import TavilyClient

_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", ""))


@tool
def web_search(query: str, max_results: int = 5) -> list[dict]:
    """
    互联网搜索工具。返回结构化搜索结果。

    :param query: 搜索关键词
    :param max_results: 返回结果数（3-10）
    :return: [{title, url, content, score}, ...]
    """
    response = _client.search(
        query=query,
        max_results=min(max_results, 10),
        include_raw_content=False,
    )
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""),
         "content": r.get("content", ""), "score": r.get("score", 0)}
        for r in response.get("results", [])
    ]
