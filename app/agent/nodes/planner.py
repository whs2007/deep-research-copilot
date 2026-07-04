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


async def planner_node(state: ResearchState) -> dict:
    """拆解调研问题，输出研究计划和搜索查询"""

    # 已在第 1 轮之外，只补充缺失角度
    missing = state.get("missing_angles", [])
    if state.get("iteration_count", 0) > 0 and not missing:
        return {"search_queries": [], "iteration_count": state["iteration_count"]}

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

    return {
        "research_plan": result.get("research_plan", []),
        "search_queries": result.get("search_queries", []),
    }
