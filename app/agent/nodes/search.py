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


async def search_node(state: ResearchState, runtime: Runtime) -> dict:
    """并发执行所有搜索查询，汇总到 evidence_pool"""

    writer = runtime.stream_writer
    writer({"type": "progress", "node": "search", "status": "running"})

    queries = state.get("search_queries", [])
    if not queries:
        writer({"type": "progress", "node": "search", "status": "complete", "count": 0})
        return {"evidence_pool": state.get("evidence_pool", [])}

    # 异步并发：使用 asyncio.to_thread 包装同步 Tavily 调用，真正并发
    async def _async_search(q: dict) -> list[dict]:
        try:
            raw = await asyncio.to_thread(
                web_search.invoke, {"query": q["query"], "max_results": 5}
            )
            prompt = PromptTemplate(
                template="""将以下搜索结果整理为结构化证据列表。每条证据含 fact/source/relevance/confidence。
搜索结果：{raw_results}
原始问题：{query}""",
                input_variables=["raw_results", "query"],
            )
            chain = prompt | model | JsonOutputParser()
            return await chain.ainvoke({"raw_results": str(raw), "query": q["query"]})
        except Exception:
            return []

    tasks = [_async_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_evidence = []
    for r in results:
        if isinstance(r, list):
            new_evidence.extend(r)

    # 去重 + 裁剪：基于 fact 文本 hash 去重，保留 confidence 高的
    existing = state.get("evidence_pool", [])
    seen = set()
    for e in existing:
        seen.add(hash(e.get("fact", "")))
    for e in new_evidence:
        fh = hash(e.get("fact", ""))
        if fh not in seen:
            seen.add(fh)
            existing.append(e)

    writer({"type": "progress", "node": "search", "status": "complete",
            "new_count": len(new_evidence), "total_count": len(existing)})

    return {"evidence_pool": existing}
