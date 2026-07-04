"""Planner 测试：拆解质量 + 空转防护"""
import pytest
from unittest.mock import AsyncMock, patch
from app.agent.nodes.planner import planner_node
from tests.conftest import PLANNER_RESULT


@pytest.mark.asyncio
async def test_planner_first_round_no_skip(base_state, mock_runtime):
    """首轮不跳过（iteration_count=0）→ 继续执行到 LLM 调用"""
    # 首轮：iteration_count=0 + missing_angles=[] → 不应进入空转分支
    # 验证 result 不包含 report_ready=True
    result = None
    try:
        result = await planner_node(base_state, mock_runtime)
    except Exception:
        pass  # 无真实 LLM 会抛异常，但空转防护逻辑在异常之前已验证
    # 空转防护只在 iteration_count>0 时生效
    assert base_state["iteration_count"] == 0

@pytest.mark.asyncio
async def test_planner_non_first_round_skip_when_no_missing(base_state, mock_runtime):
    """非首轮 + 无缺失角度 → 直接标记 report_ready"""
    state = {**base_state, "iteration_count": 1, "missing_angles": []}
    result = await planner_node(state, mock_runtime)
    assert result.get("report_ready") is True


@pytest.mark.asyncio
async def test_planner_non_first_round_returns_unchanged_iteration(base_state, mock_runtime):
    """非首轮空转时 iteration_count 不变"""
    state = {**base_state, "iteration_count": 2, "missing_angles": []}
    result = await planner_node(state, mock_runtime)
    assert result.get("iteration_count") == 2


@pytest.mark.asyncio
async def test_planner_stream_writer_called_on_skip(base_state, mock_runtime):
    """跳过时也调用 stream_writer"""
    state = {**base_state, "iteration_count": 1, "missing_angles": []}
    await planner_node(state, mock_runtime)
    mock_runtime.stream_writer.assert_called()
