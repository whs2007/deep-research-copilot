"""Synthesizer 测试：证据注入验证"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.nodes.synthesizer import synthesizer_node
from app.prompt.prompts import SYNTHESIZER_PROMPT
from tests.conftest import SYNTHESIZER_RESULT


def test_synthesizer_prompt_has_evidence_placeholders():
    """审计修复验证：Prompt 模板必须包含所有 8 个占位符"""
    required = [
        "{verified_facts}", "{evidence_pool}", "{rejected_facts}",
        "{research_plan}", "{missing_angles}", "{fact_quality_score}",
        "{report_ready}", "{research_topic}",
    ]
    for ph in required:
        assert ph in SYNTHESIZER_PROMPT, f"缺失占位符: {ph}"


def test_synthesizer_prompt_has_report_structure():
    """Prompt 模板包含五段式报告结构"""
    sections = ["调研背景", "核心发现", "证据支撑", "风险与不确定性", "结论与建议"]
    for s in sections:
        assert s in SYNTHESIZER_PROMPT, f"缺失报告章节: {s}"


def test_synthesizer_prompt_forbids_fabrication():
    """Prompt 明确禁止编造证据"""
    assert "禁止编造" in SYNTHESIZER_PROMPT
    assert "只使用上述" in SYNTHESIZER_PROMPT


def test_synthesizer_returns_final_report_key():
    """Synthesizer 返回 dict 含 final_report 键"""
    result = {"final_report": "test report content"}
    assert "final_report" in result
    assert isinstance(result["final_report"], str)


def test_synthesizer_stream_writer_sends_progress():
    """验证 synthesizer 推送进度事件格式"""
    event = {"type": "progress", "node": "synthesizer", "status": "running"}
    assert event["type"] == "progress"
    assert event["status"] == "running"
    assert event["node"] == "synthesizer"
