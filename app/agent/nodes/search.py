"""
Search Agent — 双模型并行搜索 + 分轮Token预算 + 超时降级
"""
import asyncio, hashlib, logging, os, time
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from langchain.chat_models import init_chat_model
from app.agent.state import ResearchState
from app.tools.search_tool import web_search

logger = logging.getLogger("deepresearch.search")
TAVILY_TIMEOUT = 12
MAX_RESULTS = 4
MAX_RETRIES = 2

# Qwen 模型（懒加载）
_qwen_model = None

def _get_qwen():
    global _qwen_model
    if _qwen_model is None and os.getenv("QWEN_API_KEY"):
        _qwen_model = init_chat_model(
            model=os.getenv("QWEN_MODEL", "qwen-max"),
            model_provider="openai",
            base_url=os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            api_key=os.getenv("QWEN_API_KEY"),
            temperature=0, request_timeout=30,
        )
    return _qwen_model

def _hash_fact(fact: str) -> str:
    return hashlib.md5(fact.encode()).hexdigest()

def _tavily_to_evidence(raw_results: list, query: str) -> list[dict]:
    evidence = []
    for r in raw_results:
        title = (r.get("title") or "").strip()
        url = (r.get("url") or "").strip()
        content = (r.get("content") or "").strip()
        if not title or not url: continue
        evidence.append({"fact": f"{title}: {content}" if content else title,
                         "source": url, "relevance": query, "confidence": "medium"})
    return evidence


async def search_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "search", "status": "running"})

    queries = state.get("search_queries", [])
    if not queries:
        writer({"type": "progress", "node": "search", "status": "complete", "count": 0})
        return {"evidence_pool": state.get("evidence_pool", [])}

    # ═══ 分轮 Token 预算 ═══
    iteration = state.get("iteration_count", 0)
    if iteration == 0:       # 第1轮：全面搜索
        max_queries = 8; max_results_per = 4
    elif iteration == 1:     # 第2轮：补充搜索
        max_queries = 4; max_results_per = 3
    else:                    # 第3轮+：精准补充
        max_queries = 2; max_results_per = 2
    queries = queries[:max_queries]

    # ═══ 双模型分工 ═══
    qwen = _get_qwen()
    mid = len(queries) // 2 if qwen else len(queries)
    ds_queries = queries[:mid] if qwen else queries
    qw_queries = queries[mid:] if qwen else []

    try:
        from app.cache.redis_client import get_cached_tavily_result, cache_tavily_result
    except Exception:
        get_cached_tavily_result = lambda _: None
        cache_tavily_result = lambda _a, _b: None

    async def _search_one(q: dict, llm_model) -> list[dict]:
        """单条查询：Tavily → 直接转 Evidence"""
        query_text = q.get("query", "")
        if not query_text: return []

        # 实时推送：正在搜索什么
        writer({"type": "progress", "node": "search", "status": "query",
                "query": query_text[:60]})

        try:
            cached = get_cached_tavily_result(query_text)
            if cached:
                ev = _tavily_to_evidence(cached, query_text)
                writer({"type": "progress", "node": "search", "status": "found",
                        "query": query_text[:40], "count": len(ev), "cached": True})
                return ev
        except Exception: pass

        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = await asyncio.wait_for(
                    asyncio.to_thread(web_search.invoke, {"query": query_text, "max_results": max_results_per}),
                    timeout=TAVILY_TIMEOUT,
                )
                if not raw: continue
                try: cache_tavily_result(query_text, raw)
                except Exception: pass
                ev = _tavily_to_evidence(raw, query_text)
                writer({"type": "progress", "node": "search", "status": "found",
                        "query": query_text[:40], "count": len(ev)})
                return ev
            except asyncio.TimeoutError:
                if attempt < MAX_RETRIES: await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                logger.warning(f"Search failed [{query_text[:40]}]: {e}")
                if attempt < MAX_RETRIES: await asyncio.sleep(0.5 * (attempt + 1))
        return []

    # ═══ 并行搜索 + 超时协调 ═══
    t0 = time.time()
    SEARCH_TIMEOUT = 20  # 单模型总超时

    async def _search_batch(batch_queries, llm_model, label):
        if not batch_queries: return []
        try:
            tasks = [_search_one(q, llm_model) for q in batch_queries]
            results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=SEARCH_TIMEOUT)
            evidence = []
            for r in results:
                if isinstance(r, list): evidence.extend(r)
            logger.info(f"[{label}] {len(batch_queries)} queries → {len(evidence)} evidence ({time.time()-t0:.1f}s)")
            return evidence
        except asyncio.TimeoutError:
            logger.warning(f"[{label}] timeout after {SEARCH_TIMEOUT}s, partial results used")
            return []

    # 两个模型同时跑
    ds_task = _search_batch(ds_queries, None, "DeepSeek")
    qw_task = _search_batch(qw_queries, qwen, "Qwen") if qw_queries else asyncio.sleep(0)

    if qw_queries:
        ds_evidence, _ = await asyncio.gather(ds_task, qw_task, return_exceptions=True)
        qw_evidence = _ if isinstance(_, list) else []
    else:
        ds_evidence = await ds_task
        qw_evidence = []

    all_new = (ds_evidence if isinstance(ds_evidence, list) else []) + qw_evidence
    logger.info(f"Total: DS={len(ds_evidence) if isinstance(ds_evidence,list) else 0} + QW={len(qw_evidence)} = {len(all_new)} evidence")

    # ═══ 去重 ═══
    existing = state.get("evidence_pool", [])
    seen = {_hash_fact(e.get("fact", "")) for e in existing}
    for e in all_new:
        fh = _hash_fact(e.get("fact", ""))
        if fh not in seen and (e.get("fact") or "").strip():
            seen.add(fh); existing.append(e)

    writer({"type": "progress", "node": "search", "status": "complete",
            "new_count": len(all_new), "total_count": len(existing)})
    return {"evidence_pool": existing}
