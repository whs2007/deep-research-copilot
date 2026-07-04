"""
测试 Fixtures — Mock LLM / Mock Tavily / 标准 State
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
def mock_llm_planner():
    """Mock Planner 的 LLM 返回"""
    mock = AsyncMock()
    mock.ainvoke.return_value = {
        "research_plan": ["子问题1", "子问题2", "子问题3"],
        "search_queries": [
            {"query": "test query 1", "source": "news", "priority": "high"},
            {"query": "test query 2", "source": "report", "priority": "medium"},
        ],
    }
    return mock


@pytest.fixture
def mock_llm_critic_ready():
    """Mock Critic 的 LLM 返回 — 证据充分"""
    mock = AsyncMock()
    mock.ainvoke.return_value = {
        "verified_facts": [
            {"fact": "事实1", "source": "url1", "relevance": "子问题1", "confidence": "high"}
        ],
        "rejected_facts": [],
        "missing_angles": [],
        "fact_quality_score": 0.85,
        "report_ready": True,
    }
    return mock


@pytest.fixture
def mock_llm_critic_not_ready():
    """Mock Critic 的 LLM 返回 — 证据不足"""
    mock = AsyncMock()
    mock.ainvoke.return_value = {
        "verified_facts": [],
        "rejected_facts": [
            {"fact": "低质量", "source": "url_x", "reason": "来源不可靠"}
        ],
        "missing_angles": ["缺失角度1", "缺失角度2"],
        "fact_quality_score": 0.3,
        "report_ready": False,
    }
    return mock


@pytest.fixture
def mock_llm_synthesizer():
    """Mock Synthesizer 的 LLM 返回"""
    mock = AsyncMock()
    mock.ainvoke.return_value = "# 测试报告\n\n内容"
    return mock


@pytest.fixture
def mock_tavily():
    """Mock Tavily 搜索返回"""
    return [
        {"title": "Test Result", "url": "https://example.com/1",
         "content": "test content", "score": 0.9}
    ]


@pytest.fixture
def mock_runtime():
    """Mock LangGraph Runtime（stream_writer）"""
    mock = MagicMock()
    mock.stream_writer = MagicMock()
    return mock
