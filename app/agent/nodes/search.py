"""
Search Agent — 异步并发搜索
"""
import asyncio
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.agent.nodes.planner import _extract_json
from app.tools.search_tool import web_search


async def search_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "search", "status": "running"})

    queries = state.get("search_queries", [])
    if not queries:
        writer({"type": "progress", "node": "search", "status": "complete", "count": 0})
        return {"evidence_pool": state.get("evidence_pool", [])}

    from app.cache.redis_client import get_cached_tavily_result, cache_tavily_result

    async def _async_search(q: dict) -> list[dict]:
        try:
            # Redis 缓存命中 → 直接返回，不调 Tavily
            cached = get_cached_tavily_result(q["query"])
            if cached:
                return cached

            raw = await asyncio.to_thread(
                web_search.invoke, {"query": q["query"], "max_results": 5}
            )
            # 缓存结果
            cache_tavily_result(q["query"], raw)
            prompt_text = f"""将以下搜索结果整理为结构化JSON证据列表。每条证据含fact/source/relevance/confidence字段。
搜索结果：{raw}
原始问题：{q['query']}
只输出JSON数组，不要其他文字。"""
            resp = await model.ainvoke([HumanMessage(content=prompt_text)])
            return _extract_json(resp.content)
        except Exception:
            return []

    tasks = [_async_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_evidence = []
    for r in results:
        if isinstance(r, list):
            new_evidence.extend(r)

    existing = state.get("evidence_pool", [])
    seen = {hash(e.get("fact", "")) for e in existing}
    for e in new_evidence:
        fh = hash(e.get("fact", ""))
        if fh not in seen:
            seen.add(fh)
            existing.append(e)

    writer({"type": "progress", "node": "search", "status": "complete",
            "new_count": len(new_evidence), "total_count": len(existing)})
    return {"evidence_pool": existing}
