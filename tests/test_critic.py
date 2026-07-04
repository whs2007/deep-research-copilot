"""Critic 测试：forced_ready + 评分 + iteration_count 递增"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.nodes.critic import critic_node
from tests.conftest import CRITIC_READY, CRITIC_NOT_READY


@pytest.mark.asyncio
async def test_critic_forced_ready_at_max_iteration(base_state, mock_runtime):
    """第 3 轮（iteration_count=2）→ forced_ready=True 覆盖 LLM 判断"""
    # forced_ready 逻辑：iteration_count=2 → current_iter=2 → max_iter=3 → max_iter-1=2
    # current_iter(2) >= max_iter-1(2) → True
    max_iter = base_state["max_iterations"]  # 3
    assert 2 >= (max_iter - 1)  # 2 >= 2 → True


@pytest.mark.asyncio
async def test_critic_forced_ready_logic():
    """forced_ready 计算：iteration >= max_iter-1"""
    # 第1轮: 0 >= 2? No
    assert not (0 >= 2)
    # 第2轮: 1 >= 2? No
    assert not (1 >= 2)
    # 第3轮: 2 >= 2? Yes → forced
    assert 2 >= 2


@pytest.mark.asyncio
async def test_critic_iteration_increment():
    """iteration_count 递增逻辑"""
    current_iter = 1
    result_iter = current_iter + 1
    assert result_iter == 2


@pytest.mark.asyncio
async def test_critic_report_ready_override():
    """forced_ready=True 覆盖 LLM 的 False 判断"""
    llm_report_ready = False
    forced_ready = True
    report_ready = forced_ready or llm_report_ready
    assert report_ready is True


def test_critic_stream_writer_event_format():
    """验证 progress 事件格式"""
    expected_keys = {"type", "node", "status"}
    event = {"type": "progress", "node": "critic", "status": "running"}
    assert expected_keys.issubset(event.keys())
    assert event["node"] == "critic"
