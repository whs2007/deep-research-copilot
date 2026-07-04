"""
Synthesizer Agent — 生成结构化调研报告
"""
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.prompt.prompts import SYNTHESIZER_PROMPT


async def synthesizer_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "synthesizer", "status": "running"})

    prompt_text = SYNTHESIZER_PROMPT.format(
        research_topic=state["research_topic"],
        verified_facts=state.get("verified_facts", []),
        rejected_facts=state.get("rejected_facts", []),
        evidence_pool=state.get("evidence_pool", []),
        research_plan=state.get("research_plan", []),
        missing_angles=state.get("missing_angles", []),
        fact_quality_score=state.get("fact_quality_score", 0.0),
        report_ready=state.get("report_ready", False),
    )
    resp = await model.ainvoke([HumanMessage(content=prompt_text)])

    writer({"type": "progress", "node": "synthesizer", "status": "complete"})
    return {"final_report": resp.content}
