"""
Critic Agent — 信息质量评估
"""
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.agent.nodes.planner import _extract_json
from app.prompt.prompts import CRITIC_PROMPT


async def critic_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "critic", "status": "running",
            "evidence_count": len(state.get("evidence_pool", []))})

    prompt_text = CRITIC_PROMPT.format(
        research_topic=state["research_topic"],
        research_plan=state.get("research_plan", []),
        evidence_pool=state.get("evidence_pool", []),
        evidence_count=len(state.get("evidence_pool", [])),
        iteration_count=state.get("iteration_count", 0),
        max_iterations=state.get("max_iterations", 3),
    )
    resp = await model.ainvoke([HumanMessage(content=prompt_text)])
    result = _extract_json(resp.content)

    max_iter = state.get("max_iterations", 3)
    current_iter = state.get("iteration_count", 0)
    forced_ready = current_iter >= max_iter - 1
    report_ready = forced_ready or result.get("report_ready", False)

    writer({"type": "progress", "node": "critic", "status": "complete",
            "quality_score": result.get("fact_quality_score", 0.0),
            "report_ready": report_ready, "iteration": current_iter + 1})
    return {
        "verified_facts": result.get("verified_facts", []),
        "rejected_facts": result.get("rejected_facts", []),
        "missing_angles": result.get("missing_angles", []),
        "fact_quality_score": result.get("fact_quality_score", 0.0),
        "report_ready": report_ready,
        "iteration_count": current_iter + 1,
    }
