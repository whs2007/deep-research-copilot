"""Search 测试：并发 + 去重"""
import pytest
from unittest.mock import patch, AsyncMock
from app.agent.nodes.search import search_node


@pytest.mark.asyncio
async def test_search_empty_queries_returns_existing(base_state, mock_runtime):
    """空 search_queries → 返回已有 evidence_pool"""
    existing = [{"fact": "已有", "source": "url", "relevance": "x", "confidence": "high"}]
    state = {**base_state, "evidence_pool": existing, "search_queries": []}
    result = await search_node(state, mock_runtime)
    assert result["evidence_pool"] == existing


@pytest.mark.asyncio
async def test_search_concurrent_execution(base_state, mock_runtime, mock_tavily):
    """并发搜索：asyncio.gather 创建并行任务"""
    queries = [{"query": f"q{i}", "priority": "high"} for i in range(3)]
    state = {**base_state, "search_queries": queries}

    async def fake_search(q):
        return [{"fact": f"fact_{q['query']}", "source": "url", "relevance": "x", "confidence": "high"}]

    # Mock LLM 返回结构化证据
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = [{"fact": "fact", "source": "url", "relevance": "x", "confidence": "high"}]

    with patch('app.agent.nodes.search.model', mock_llm), \
         patch('app.agent.nodes.search.web_search.invoke', return_value=mock_tavily):
        result = await search_node(state, mock_runtime)
    assert len(result["evidence_pool"]) >= 3


@pytest.mark.asyncio
async def test_search_dedup_across_rounds(base_state, mock_runtime, mock_tavily):
    """跨轮去重：相同 fact 不重复添加"""
    dup_fact = {"fact": "重复事实", "source": "url", "relevance": "x", "confidence": "high"}
    state = {
        **base_state,
        "evidence_pool": [dup_fact],
        "search_queries": [{"query": "q", "priority": "high"}],
    }
    mock_llm = AsyncMock()
    mock_llm.ainvoke.return_value = [dup_fact]  # LLM 返回相同证据

    with patch('app.agent.nodes.search.model', mock_llm), \
         patch('app.agent.nodes.search.web_search.invoke', return_value=mock_tavily):
        result = await search_node(state, mock_runtime)
    assert len(result["evidence_pool"]) == 1  # 去重后仍为 1


@pytest.mark.asyncio
async def test_search_failure_graceful(base_state, mock_runtime):
    """单次搜索失败不中断整体"""
    state = {**base_state, "search_queries": [
        {"query": "fail", "priority": "high"},
        {"query": "ok", "priority": "high"},
    ]}
    mock_llm = AsyncMock()
    mock_llm.ainvoke.side_effect = [Exception("fail"), [{"fact": "ok", "source": "url", "relevance": "x", "confidence": "high"}]]

    with patch('app.agent.nodes.search.model', mock_llm), \
         patch('app.agent.nodes.search.web_search.invoke', return_value=[]):
        result = await search_node(state, mock_runtime)
    assert len(result["evidence_pool"]) == 1  # 只有成功的
