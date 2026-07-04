"""Synthesizer 测试：证据注入验证"""
import pytest
from unittest.mock import patch
from app.agent.nodes.synthesizer import synthesizer_node
from app.prompt.prompts import SYNTHESIZER_PROMPT


@pytest.mark.asyncio
async def test_synthesizer_uses_evidence_data(base_state, mock_llm_synthesizer, mock_runtime):
    """验证 evidence_pool 和 verified_facts 被传入 LLM 调用"""
    state = {
        **base_state,
        "verified_facts": [
            {"fact": "测试事实", "source": "https://test.com", "relevance": "子问题1", "confidence": "high"}
        ],
        "evidence_pool": [{"fact": "测试事实", "source": "https://test.com", "relevance": "子问题1", "confidence": "high"}],
    }
    with patch('app.agent.nodes.synthesizer.model', mock_llm_synthesizer):
        result = await synthesizer_node(state, mock_runtime)
    assert "final_report" in result
    # 验证 LLM 被调用时传入了 evidence 数据
    mock_llm_synthesizer.ainvoke.assert_called_once()
    call_args = mock_llm_synthesizer.ainvoke.call_args[0][0]
    assert "测试事实" in str(call_args)


@pytest.mark.asyncio
async def test_synthesizer_generates_report_even_with_empty_evidence(base_state, mock_llm_synthesizer, mock_runtime):
    """即使证据为空，Synthesizer 也应强制生成报告（在风险章节标注）"""
    with patch('app.agent.nodes.synthesizer.model', mock_llm_synthesizer):
        result = await synthesizer_node(base_state, mock_runtime)
    assert result["final_report"] == "# 测试报告\n\n内容"


def test_synthesizer_prompt_has_evidence_placeholders():
    """审计修复验证：Prompt 模板必须包含证据占位符"""
    required_placeholders = [
        "{verified_facts}", "{evidence_pool}", "{rejected_facts}",
        "{research_plan}", "{missing_angles}", "{fact_quality_score}",
        "{report_ready}", "{research_topic}",
    ]
    for ph in required_placeholders:
        assert ph in SYNTHESIZER_PROMPT, f"缺失占位符: {ph}"
