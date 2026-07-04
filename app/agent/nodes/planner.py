"""
Planner Agent — 调研问题拆解与搜索规划
"""
import json
from langgraph.runtime import Runtime
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.agent.llm import model
from app.agent.state import ResearchState
from app.prompt.prompts import PLANNER_PROMPT


async def planner_node(state: ResearchState, runtime: Runtime) -> dict:
    """拆解调研问题，输出研究计划和搜索查询"""

    writer = runtime.stream_writer
    writer({"type": "progress", "node": "planner", "status": "running"})

    # 非首轮且无缺失角度 → 直接标记就绪，跳过空转
    missing = state.get("missing_angles", [])
    if state.get("iteration_count", 0) > 0:
        if not missing:
            writer({"type": "progress", "node": "planner", "status": "complete"})
            return {
                "report_ready": True,
                "iteration_count": state["iteration_count"],
            }
        # 有缺失角度 → 限制 query 数量到 5 条
        max_q = 5

    prompt = PromptTemplate(
        template=PLANNER_PROMPT,
        input_variables=["research_topic", "evidence_count", "missing_angles",
                        "iteration_count", "max_iterations"],
    )
    chain = prompt | model | JsonOutputParser()

    result = await chain.ainvoke({
        "research_topic": state["research_topic"],
        "evidence_count": len(state.get("evidence_pool", [])),
        "missing_angles": missing if missing else ["（首轮调研，全角度覆盖）"],
        "iteration_count": state.get("iteration_count", 0),
        "max_iterations": state.get("max_iterations", 3),
    })

    queries = result.get("search_queries", [])
    writer({"type": "progress", "node": "planner", "status": "complete",
            "plan_count": len(result.get("research_plan", [])),
            "query_count": len(queries)})

    return {
        "research_plan": result.get("research_plan", []),
        "search_queries": queries,
    }
