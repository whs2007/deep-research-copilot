"""
LangGraph Workflow — Planner → Search → Critic → [loop|continue] → Synthesizer

loop-back 机制：
- Critic 评估后，report_ready=false 且未达 max_iterations → 回到 Planner 补充搜索
- report_ready=true 或达到 max_iterations → 进入 Synthesizer 强制生成报告
- max_iterations=3 硬上限，从 Crtic 节点强制终止
"""
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from app.agent.state import ResearchState
from app.agent.nodes import (
    planner_node,
    search_node,
    critic_node,
    synthesizer_node,
)

builder = StateGraph(state_schema=ResearchState)

# 注册节点
builder.add_node("planner", planner_node)
builder.add_node("search", search_node)
builder.add_node("critic", critic_node)
builder.add_node("synthesizer", synthesizer_node)

# 边定义：Planner → Search → Critic
builder.add_edge(START, "planner")
builder.add_edge("planner", "search")
builder.add_edge("search", "critic")

# 条件分支：Critic 决定下一步
def critic_router(state: ResearchState) -> str:
    """
    Critic 路由逻辑：
    - report_ready=true → synthesizer（生成报告）
    - report_ready=false 且 iteration_count < max_iterations → planner（loop-back）
    - report_ready=false 且 iteration_count >= max_iterations → synthesizer（强制生成）
    """
    ready = state.get("report_ready", False)
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", 3)

    if ready or iteration >= max_iter:
        return "synthesizer"
    return "planner"

builder.add_conditional_edges("critic", critic_router, {
    "synthesizer": "synthesizer",
    "planner": "planner",
})

builder.add_edge("synthesizer", END)

graph = builder.compile()
