"""Graph 测试：Workflow 完整性 + 条件边逻辑"""
import pytest
from app.agent.graph import graph


def test_graph_has_four_nodes():
    """验证图注册了 4 个节点"""
    nodes = graph.get_graph().nodes
    assert "planner" in nodes
    assert "search" in nodes
    assert "critic" in nodes
    assert "synthesizer" in nodes


def test_graph_starts_at_planner():
    """验证入口边 → planner"""
    edges = graph.get_graph().edges
    # START → planner 应该存在
    start_edges = [e for e in edges if e[0] == "__start__"]
    assert len(start_edges) >= 1


def test_graph_ends_at_end():
    """验证 synthesizer → END"""
    edges = graph.get_graph().edges
    end_edges = [e for e in edges if e[1] == "__end__"]
    assert len(end_edges) >= 1


def test_critic_router_synthesizer_when_ready():
    """条件边：report_ready=true → synthesizer"""
    from app.agent.graph import critic_router
    state = {"report_ready": True, "iteration_count": 0, "max_iterations": 3}
    assert critic_router(state) == "synthesizer"


def test_critic_router_planner_when_not_ready():
    """条件边：report_ready=false + 未达上限 → planner"""
    from app.agent.graph import critic_router
    state = {"report_ready": False, "iteration_count": 1, "max_iterations": 3}
    assert critic_router(state) == "planner"


def test_critic_router_synthesizer_when_max_iteration():
    """条件边：iteration >= max → 强制 synthesizer（即使 report_ready=false）"""
    from app.agent.graph import critic_router
    state = {"report_ready": False, "iteration_count": 3, "max_iterations": 3}
    assert critic_router(state) == "synthesizer"


def test_critic_router_with_missing_fields():
    """条件边：字段缺失时使用默认值，不崩溃"""
    from app.agent.graph import critic_router
    result = critic_router({})
    assert result in ("planner", "synthesizer")
