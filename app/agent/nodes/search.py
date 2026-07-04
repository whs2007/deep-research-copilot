"""
Search Agent — 异步并发搜索（含 timeout + retry + 稳定去重 + Redis缓存）
"""
import asyncio
import hashlib
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.agent.nodes.planner import _extract_json
from app.tools.search_tool import web_search

TAVILY_TIMEOUT = 15   # Tavily 单次调用超时（秒）
LLM_TIMEOUT = 30      # LLM 整理调用超时（秒）
MAX_RETRIES = 2       # 单条查询最大重试次数


def _hash_fact(fact: str) -> str:
    """稳定哈希：hashlib.md5 替代 Python hash()，跨进程一致"""
    return hashlib.md5(fact.encode()).hexdigest()


async def search_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "search", "status": "running"})

    queries = state.get("search_queries", [])
    if not queries:
        writer({"type": "progress", "node": "search", "status": "complete", "count": 0})
        return {"evidence_pool": state.get("evidence_pool", [])}

    from app.cache.redis_client import get_cached_tavily_result, cache_tavily_result

    async def _async_search(q: dict) -> list[dict]:
        # Redis 缓存命中的话直接返回，不调 API
        cached = get_cached_tavily_result(q["query"])
        if cached:
            return cached

        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(
                        web_search.invoke, {"query": q["query"], "max_results": 5}
                    ),
                    timeout=TAVILY_TIMEOUT,
                )
                cache_tavily_result(q["query"], raw)
                prompt_text = f"""将以下搜索结果整理为结构化JSON证据列表。每条证据含fact/source/relevance/confidence字段。
搜索结果：{raw}
原始问题：{q['query']}
只输出JSON数组，不要其他文字。"""
                resp = await asyncio.wait_for(
                    model.ainvoke([HumanMessage(content=prompt_text)]),
                    timeout=LLM_TIMEOUT,
                )
                return _extract_json(resp.content)
            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1 * (attempt + 1))
            except Exception:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1 * (attempt + 1))
        return []  # 所有重试都失败

    tasks = [_async_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_evidence = []
    for r in results:
        if isinstance(r, list):
            new_evidence.extend(r)

    # 稳定去重：hashlib.md5 跨进程一致
    existing = state.get("evidence_pool", [])
    seen = {_hash_fact(e.get("fact", "")) for e in existing}
    for e in new_evidence:
        fh = _hash_fact(e.get("fact", ""))
        if fh not in seen and e.get("fact", "").strip():
            seen.add(fh)
            existing.append(e)

    writer({"type": "progress", "node": "search", "status": "complete",
            "new_count": len(new_evidence), "total_count": len(existing)})
    return {"evidence_pool": existing}
