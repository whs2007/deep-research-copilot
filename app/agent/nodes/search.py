"""
Search Agent — 异步并发搜索（含 timeout + retry + 稳定去重 + Redis缓存 + 降级兜底）
"""
import asyncio
import hashlib
import logging
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.tools.search_tool import web_search

logger = logging.getLogger("deepresearch.search")

TAVILY_TIMEOUT = 15
LLM_TIMEOUT = 30
MAX_RETRIES = 2


def _hash_fact(fact: str) -> str:
    return hashlib.md5(fact.encode()).hexdigest()


def _safe_extract_json(text: str) -> list:
    """从 LLM 响应中提取 JSON 数组。解析失败返回空列表，不抛异常"""
    if not text or not text.strip():
        return []
    try:
        import json as _json
        # 去除 markdown 代码块包裹
        t = text.strip()
        if "```json" in t:
            t = t.split("```json")[1].split("```")[0]
        elif "```" in t:
            parts = t.split("```")
            if len(parts) >= 2:
                t = parts[1]
        t = t.strip()
        result = _json.loads(t)
        # 兼容：LLM 返回的是单个对象而非数组
        if isinstance(result, dict):
            return [result]
        if isinstance(result, list):
            return result
        return []
    except Exception as e:
        logger.warning(f"JSON 解析失败: {e} | text[:200]={text[:200]}")
        return []


def _tavily_to_evidence(raw_results: list, query: str) -> list[dict]:
    """Tavily 原始结果直接转 Evidence（不依赖 LLM，最低保障）"""
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
        cached = get_cached_tavily_result(query_text)
        if cached:
            return _tavily_to_evidence(cached, query_text)

        for attempt in range(MAX_RETRIES + 1):
            try:
                # ═══ Tavily 搜索 ═══
                raw = await asyncio.wait_for(
                    asyncio.to_thread(web_search.invoke, {"query": query_text, "max_results": 5}),
                    timeout=TAVILY_TIMEOUT,
                )
                if not raw:
                    continue

                cache_tavily_result(query_text, raw)

                # ═══ LLM 整理（可选——失败则降级到原始结果） ═══
                try:
                    prompt_text = f"""将以下搜索结果整理为结构化JSON证据列表。
每条证据含 fact/source/relevance/confidence 字段。
搜索结果：{raw}
原始问题：{query_text}
只输出JSON数组，不要其他文字。"""
                    resp = await asyncio.wait_for(
                        model.ainvoke([HumanMessage(content=prompt_text)]),
                        timeout=LLM_TIMEOUT,
                    )
                    llm_evidence = _safe_extract_json(resp.content)
                    if llm_evidence:
                        return llm_evidence
                except Exception:
                    pass  # LLM 整理失败 → 降级到原始结果

                # ═══ 降级：Tavily 原始结果直接用作 Evidence ═══
                return _tavily_to_evidence(raw, query_text)

            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1 * (attempt + 1))
            except Exception as e:
                logger.warning(f"Search 失败 [{query_text[:40]}]: {e}")
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(1 * (attempt + 1))
        return []

    tasks = [_async_search(q) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    new_evidence = []
    for r in results:
        if isinstance(r, list):
            new_evidence.extend(r)

    # 去重
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
