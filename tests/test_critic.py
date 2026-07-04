"""Critic 测试：forced_ready + 评分 + iteration_count 递增"""
import pytest
from unittest.mock import patch
from app.agent.nodes.critic import critic_node


@pytest.mark.asyncio
async def test_critic_forced_ready_at_max_iteration(base_state, mock_llm_critic_not_ready, mock_runtime):
    """第 3 轮（iteration_count=2）→ forced_ready=True 覆盖 LLM 判断"""
    state = {**base_state, "iteration_count": 2}  # 第3轮(0-indexed: 0,1,2)
    with patch('app.agent.nodes.critic.model', mock_llm_critic_not_ready):
        result = await critic_node(state, mock_runtime)
    assert result["report_ready"] is True  # forced override
    assert result["iteration_count"] == 3  # 2 + 1


@pytest.mark.asyncio
async def test_critic_respects_llm_when_ready(base_state, mock_llm_critic_ready, mock_runtime):
    """LLM 判断 ready → 直接采纳"""
    with patch('app.agent.nodes.critic.model', mock_llm_critic_ready):
        result = await critic_node(state=base_state, runtime=mock_runtime)
    assert result["report_ready"] is True
    assert result["fact_quality_score"] == 0.85
    assert result["iteration_count"] == 1


@pytest.mark.asyncio
async def test_critic_iteration_count_increments(base_state, mock_llm_critic_not_ready, mock_runtime):
    """iteration_count 正确递增"""
    state = {**base_state, "iteration_count": 1}
    with patch('app.agent.nodes.critic.model', mock_llm_critic_not_ready):
        result = await critic_node(state, mock_runtime)
    assert result["iteration_count"] == 2


@pytest.mark.asyncio
async def test_critic_returns_missing_angles(base_state, mock_llm_critic_not_ready, mock_runtime):
    """LLM 返回 missing_angles → 进入 State"""
    with patch('app.agent.nodes.critic.model', mock_llm_critic_not_ready):
        result = await critic_node(base_state, mock_runtime)
    assert len(result["missing_angles"]) == 2
    assert "缺失角度1" in result["missing_angles"]


@pytest.mark.asyncio
async def test_critic_stream_writer_has_quality_score(base_state, mock_llm_critic_ready, mock_runtime):
    """stream_writer 推送 quality_score"""
    with patch('app.agent.nodes.critic.model', mock_llm_critic_ready):
        await critic_node(base_state, mock_runtime)
    # 最后一条 complete 事件应含 quality_score
    last_call = mock_runtime.stream_writer.call_args_list[-1]
    args = last_call[0][0]
    assert args["status"] == "complete"
    assert "quality_score" in args
