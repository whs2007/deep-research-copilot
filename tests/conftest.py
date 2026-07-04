"""
测试 Fixtures — Mock LLM Chain / Mock Tavily / 标准 State
"""
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["TAVILY_API_KEY"] = "test-key"
os.environ["LLM_MODEL"] = "gpt-4o"


@pytest.fixture
def base_state():
    """标准初始 State"""
    return {
        "research_topic": "测试调研主题",
        "research_plan": [],
        "search_queries": [],
        "evidence_pool": [],
        "verified_facts": [],
        "rejected_facts": [],
        "missing_angles": [],
        "fact_quality_score": 0.0,
        "final_report": "",
        "iteration_count": 0,
        "report_ready": False,
        "max_iterations": 3,
    }


@pytest.fixture
def mock_runtime():
    """Mock LangGraph Runtime（stream_writer）"""
    mock = MagicMock()
    mock.stream_writer = MagicMock()
    return mock


# ── 预设的 chain.ainvoke 返回值 ──

PLANNER_RESULT = {
    "research_plan": ["子问题1", "子问题2", "子问题3"],
    "search_queries": [
        {"query": "test query 1", "source": "news", "priority": "high"},
        {"query": "test query 2", "source": "report", "priority": "medium"},
    ],
}

CRITIC_READY = {
    "verified_facts": [
        {"fact": "事实1", "source": "url1", "relevance": "子问题1", "confidence": "high"}
    ],
    "rejected_facts": [],
    "missing_angles": [],
    "fact_quality_score": 0.85,
    "report_ready": True,
}

CRITIC_NOT_READY = {
    "verified_facts": [],
    "rejected_facts": [
        {"fact": "低质量", "source": "url_x", "reason": "来源不可靠"}
    ],
    "missing_angles": ["缺失角度1", "缺失角度2"],
    "fact_quality_score": 0.3,
    "report_ready": False,
}

SYNTHESIZER_RESULT = "# 测试报告\n\n## 一、调研背景\n内容"

SEARCH_LLM_RESULT = [
    {"fact": "搜索事实", "source": "https://example.com", "relevance": "子问题1", "confidence": "high"}
]

TAVILY_RESULT = [
    {"title": "Test", "url": "https://example.com/1", "content": "test content", "score": 0.9}
]
