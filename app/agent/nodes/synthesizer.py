"""
Synthesizer Agent — 生成结构化调研报告
"""
import asyncio
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.prompt.prompts import SYNTHESIZER_PROMPT

SYNTH_TIMEOUT = 90  # 报告生成超时（秒）


async def synthesizer_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "synthesizer", "status": "running"})

    # 裁剪 evidence 到前 10 条（避免 Prompt 过长导致 LLM 超时）
    verified = (state.get("verified_facts") or [])[:10]
    rejected = (state.get("rejected_facts") or [])[:5]
    evidence_pool = (state.get("evidence_pool") or [])[:10]

    prompt_text = SYNTHESIZER_PROMPT.format(
        research_topic=state["research_topic"],
        verified_facts=verified,
        rejected_facts=rejected,
        evidence_pool=evidence_pool,
        research_plan=state.get("research_plan", []),
        missing_angles=state.get("missing_angles", []),
        fact_quality_score=state.get("fact_quality_score", 0.0),
        report_ready=state.get("report_ready", False),
    )

    try:
        resp = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt_text)]),
            timeout=SYNTH_TIMEOUT,
        )
        writer({"type": "progress", "node": "synthesizer", "status": "complete"})
        return {"final_report": resp.content}
    except asyncio.TimeoutError:
        writer({"type": "progress", "node": "synthesizer", "status": "complete"})
        return {"final_report": f"## 报告生成超时\n\n调研主题「{state['research_topic']}」的证据已收集完成（共{len(state.get('evidence_pool',[]))}条），但报告生成超过{SYNTH_TIMEOUT}秒限制。\n\n建议：缩小调研范围或减少迭代轮次后重试。"}
