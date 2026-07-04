"""
Search Agent — 异步并发搜索（极速版：零LLM整理 + 降级兜底 + 去重）
"""
import asyncio
import hashlib
import logging
from langgraph.runtime import Runtime
from app.agent.state import ResearchState
from app.tools.search_tool import web_search

logger = logging.getLogger("deepresearch.search")

TAVILY_TIMEOUT = 12   # 缩短超时（P95~10s, 留2s余量）
MAX_RESULTS = 4        # 减少结果数（4条足够覆盖, 加速Tavily响应）
MAX_RETRIES = 2


def _hash_fact(fact: str) -> str:
    return hashlib.md5(fact.encode()).hexdigest()


def _tavily_to_evidence(raw_results: list, query: str) -> list[dict]:
    """Tavily 原始结果直接转 Evidence——零 LLM 调用, 最快的路径"""
    evidence = []
    for r in raw_results:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip()
        if not title or not url:
            continue
        evidence.append({
            "fact": f"{title}: {content}" if content else title,
            "source": url,
            "relevance": query,
            "confidence": "medium",
        })
    return evidence


async def search_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "search", "status": "running"})

    queries = state.get("search_queries", [])
    if not queries:
        writer({"type": "progress", "node": "search", "status": "complete", "count": 0})
        return {"evidence_pool": state.get("evidence_pool", [])}

    # 截断：最多5条查询（Planner可能生成10条）
    queries = queries[:5]

    try:
        from app.cache.redis_client import get_cached_tavily_result, cache_tavily_result
    except Exception:
        get_cached_tavily_result = lambda _: None
        cache_tavily_result = lambda _a, _b: None

    async def _async_search(q: dict) -> list[dict]:
        query_text = q.get("query", "")
        if not query_text:
            return []

        # Redis 缓存
        try:
            cached = get_cached_tavily_result(query_text)
            if cached:
                return _tavily_to_evidence(cached, query_text)
        except Exception:
            pass

        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(web_search.invoke,
                        {"query": query_text, "max_results": MAX_RESULTS}),
                    timeout=TAVILY_TIMEOUT,
                )
                if not raw:
                    continue

                try:
                    cache_tavily_result(query_text, raw)
                except Exception:
                    pass

                # 直接转 Evidence——不再走 LLM 整理（省 10 次 LLM 调用）
                return _tavily_to_evidence(raw, query_text)

            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.warning(f"Search失败 [{query_text[:40]}]: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(0.5 * (attempt + 1))
        return []

    tasks = [_async_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_evidence = []
    for r in results:
        if isinstance(r, list):
            new_evidence.extend(r)

    existing = state.get("evidence_pool", [])
    seen = {_hash_fact(e.get("fact", "")) for e in existing}
    for e in new_evidence:
        fh = _hash_fact(e.get("fact", ""))
        if fh not in seen and (e.get("fact") or "").strip():
            seen.add(fh)
            existing.append(e)

    writer({"type": "progress", "node": "search", "status": "complete",
            "new_count": len(new_evidence), "total_count": len(existing)})
    return {"evidence_pool": existing}
