"""Planner 测试：拆解质量 + 空转防护"""
import pytest
from unittest.mock import patch
from app.agent.nodes.planner import planner_node


@pytest.mark.asyncio
async def test_planner_first_round_generates_plan(base_state, mock_llm_planner, mock_runtime):
    """首轮应产出 3 个子问题 + 2 条搜索"""
    with patch.object(planner_node, '__wrapped__', None), \
         patch('app.agent.nodes.planner.model', mock_llm_planner):
        result = await planner_node(base_state, mock_runtime)
    assert len(result["research_plan"]) == 3
    assert len(result["search_queries"]) == 2


@pytest.mark.asyncio
async def test_planner_non_first_round_skip_when_no_missing(base_state, mock_runtime):
    """非首轮 + 无缺失角度 → 直接标记 report_ready"""
    state = {**base_state, "iteration_count": 1, "missing_angles": []}
    result = await planner_node(state, mock_runtime)
    assert result.get("report_ready") is True
    assert result.get("search_queries") is None  # 不应产出搜索


@pytest.mark.asyncio
async def test_planner_non_first_round_with_missing(base_state, mock_llm_planner, mock_runtime):
    """非首轮 + 有缺失角度 → 仍应生成补充搜索"""
    state = {**base_state, "iteration_count": 1, "missing_angles": ["缺失1"]}
    with patch.object(planner_node, '__wrapped__', None), \
         patch('app.agent.nodes.planner.model', mock_llm_planner):
        result = await planner_node(state, mock_runtime)
    assert len(result.get("search_queries", [])) > 0


@pytest.mark.asyncio
async def test_planner_stream_writer_called(base_state, mock_llm_planner, mock_runtime):
    """验证 stream_writer 被调用"""
    with patch.object(planner_node, '__wrapped__', None), \
         patch('app.agent.nodes.planner.model', mock_llm_planner):
        await planner_node(base_state, mock_runtime)
    assert mock_runtime.stream_writer.call_count >= 2  # progress start + complete
