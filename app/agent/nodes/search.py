"""
Search Agent — 异步并发搜索
"""
import asyncio
from langgraph.runtime import Runtime
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.agent.llm import model
from app.agent.state import ResearchState
from app.tools.search_tool import web_search


async def _single_search(query_item: dict) -> list[dict]:
    """单次搜索 + LLM 结构化整理"""
    raw = web_search.invoke({"query": query_item["query"], "max_results": 5})
    # LLM 整理为 Evidence 格式
    prompt = PromptTemplate(
        template="""将以下搜索结果整理为结构化证据列表。每条证据含 fact/source/relevance/confidence。
搜索结果：{raw_results}
原始问题：{query}""",
        input_variables=["raw_results", "query"],
    )
    chain = prompt | model | JsonOutputParser()
    try:
        return await chain.ainvoke({"raw_results": str(raw), "query": query_item["query"]})
    except Exception:
        return []


async def search_node(state: ResearchState) -> dict:
    """并发执行所有搜索查询，汇总到 evidence_pool"""

    queries = state.get("search_queries", [])
    if not queries:
        return {"evidence_pool": state.get("evidence_pool", [])}

    # 异步并发：同一轮的所有搜索同时发出
    tasks = [_single_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_evidence = []
    for r in results:
        if isinstance(r, list):
            new_evidence.extend(r)

    # 合并已有证据（跨轮累积）
    existing = state.get("evidence_pool", [])
    return {"evidence_pool": existing + new_evidence}
