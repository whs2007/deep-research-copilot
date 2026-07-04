"""
Synthesizer Agent — 生成结构化调研报告
"""
from langgraph.runtime import Runtime
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.agent.llm import model
from app.agent.state import ResearchState
from app.prompt.prompts import SYNTHESIZER_PROMPT


async def synthesizer_node(state: ResearchState) -> dict:
    """
    基于审核通过的证据生成结构化报告。
    强制生成——即使 report_ready=false 也要产出包含"风险"章节的报告。
    """

    prompt = PromptTemplate(
        template=SYNTHESIZER_PROMPT,
        input_variables=[
            "research_topic", "verified_facts", "evidence_pool",
            "rejected_facts", "research_plan", "missing_angles",
            "fact_quality_score", "report_ready",
        ],
    )
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "synthesizer", "status": "running"})
    chain = prompt | model | StrOutputParser()

    report = await chain.ainvoke({
        "research_topic": state["research_topic"],
        "research_plan": state.get("research_plan", []),
        "verified_facts": state.get("verified_facts", []),
        "rejected_facts": state.get("rejected_facts", []),
        "missing_angles": state.get("missing_angles", []),
        "fact_quality_score": state.get("fact_quality_score", 0.0),
        "evidence_pool": state.get("evidence_pool", []),
        "report_ready": state.get("report_ready", False),
    })

    return {"final_report": report}
