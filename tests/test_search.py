"""Search 测试：并发 + 去重"""
import pytest
from unittest.mock import AsyncMock, patch
from app.agent.nodes.search import search_node


@pytest.mark.asyncio
async def test_search_empty_queries_returns_existing(base_state, mock_runtime):
    """空 search_queries → 返回已有 evidence_pool"""
    existing = [{"fact": "已有", "source": "url", "relevance": "x", "confidence": "high"}]
    state = {**base_state, "evidence_pool": existing, "search_queries": []}
    result = await search_node(state, mock_runtime)
    assert result["evidence_pool"] == existing


@pytest.mark.asyncio
async def test_search_empty_queries_emits_progress(base_state, mock_runtime):
    """空查询时推送进度事件"""
    result = await search_node(base_state, mock_runtime)
    mock_runtime.stream_writer.assert_called()
    assert result["evidence_pool"] == []


@pytest.mark.asyncio
async def test_search_result_structure(base_state, mock_runtime):
    """验证返回结构包含 evidence_pool"""
    state = {**base_state, "search_queries": [{"query": "q", "priority": "high"}]}
    with patch('app.agent.nodes.search.asyncio.gather', AsyncMock(return_value=[])):
        result = await search_node(state, mock_runtime)
    assert "evidence_pool" in result
    assert isinstance(result["evidence_pool"], list)


@pytest.mark.asyncio
async def test_search_preserves_existing_evidence(base_state, mock_runtime):
    """已有证据不被覆盖"""
    existing = [{"fact": "已有", "source": "url", "relevance": "x", "confidence": "high"}]
    state = {**base_state, "evidence_pool": existing, "search_queries": [{"query": "q", "priority": "high"}]}
    with patch('app.agent.nodes.search.asyncio.gather', AsyncMock(return_value=[])):
        result = await search_node(state, mock_runtime)
    assert len(result["evidence_pool"]) == 1  # 新结果为空，保留已有
