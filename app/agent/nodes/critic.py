"""
Critic Agent — 信息质量评估。决定是否 loop-back 或进入 Synthesizer
"""
from langgraph.runtime import Runtime
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.agent.llm import model
from app.agent.state import ResearchState
from app.prompt.prompts import CRITIC_PROMPT


async def critic_node(state: ResearchState, runtime: Runtime) -> dict:
    """评估证据质量，输出验证结果 + 缺失角度 + 终止判断"""

    writer = runtime.stream_writer
    writer({"type": "progress", "node": "critic", "status": "running",
            "evidence_count": len(state.get("evidence_pool", []))})

    prompt = PromptTemplate(template=CRITIC_PROMPT, input_variables=[])
    chain = prompt | model | JsonOutputParser()

    result = await chain.ainvoke({
        "research_topic": state["research_topic"],
        "research_plan": state.get("research_plan", []),
        "evidence_pool": state.get("evidence_pool", []),
        "iteration_count": state.get("iteration_count", 0),
        "max_iterations": state.get("max_iterations", 3),
    })

    max_iter = state.get("max_iterations", 3)
    current_iter = state.get("iteration_count", 0)
    forced_ready = current_iter >= max_iter - 1
    report_ready = forced_ready or result.get("report_ready", False)

    writer({"type": "progress", "node": "critic", "status": "complete",
            "quality_score": result.get("fact_quality_score", 0.0),
            "report_ready": report_ready,
            "iteration": current_iter + 1})

    return {
        "verified_facts": result.get("verified_facts", []),
        "rejected_facts": result.get("rejected_facts", []),
        "missing_angles": result.get("missing_angles", []),
        "fact_quality_score": result.get("fact_quality_score", 0.0),
        "report_ready": report_ready,
        "iteration_count": current_iter + 1,
    }
