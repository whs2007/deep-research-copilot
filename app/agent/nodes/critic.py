"""
Critic Agent — 信息质量评估（含超时降级 + 证据裁剪）
"""
import asyncio
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.agent.nodes.planner import _extract_json
from app.prompt.prompts import CRITIC_PROMPT

CRITIC_TIMEOUT = 25      # 评估超时（秒）
MAX_EVIDENCE_FOR_CRITIC = 15  # 最多评估15条（防Prompt过长卡死）


async def critic_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    total_evidence = len(state.get("evidence_pool", []))
    writer({"type": "progress", "node": "critic", "status": "running",
            "evidence_count": total_evidence})

    # ═══ 裁剪证据：跨轮累积可能上百条，只取前15条给LLM评估 ═══
    pool = (state.get("evidence_pool") or [])[:MAX_EVIDENCE_FOR_CRITIC]
    plan = (state.get("research_plan") or [])[:5]

    prompt_text = CRITIC_PROMPT.format(
        research_topic=state["research_topic"],
        research_plan=plan,
        evidence_pool=pool,
        evidence_count=total_evidence,  # 告诉Critic实际总量(但只给15条评估)
        iteration_count=state.get("iteration_count", 0),
        max_iterations=state.get("max_iterations", 3),
    )

    max_iter = state.get("max_iterations", 3)
    current_iter = state.get("iteration_count", 0)
    forced_ready = current_iter >= max_iter - 1

    try:
        resp = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt_text)]),
            timeout=CRITIC_TIMEOUT,
        )
        result = _extract_json(resp.content)
        report_ready = forced_ready or result.get("report_ready", False)
        quality = result.get("fact_quality_score", 0.0)
        verified = result.get("verified_facts", [])
        rejected = result.get("rejected_facts", [])
        missing = result.get("missing_angles", [])
    except (asyncio.TimeoutError, Exception):
        # LLM超时/异常 → 强制终止（证据已收集，直接进入报告生成）
        report_ready = True
        quality = 0.5
        verified = pool[:5]
        rejected = []
        missing = []

    writer({"type": "progress", "node": "critic", "status": "complete",
            "quality_score": quality, "report_ready": report_ready,
            "iteration": current_iter + 1})
    return {
        "verified_facts": verified,
        "rejected_facts": rejected,
        "missing_angles": missing,
        "fact_quality_score": quality,
        "report_ready": report_ready,
        "iteration_count": current_iter + 1,
    }
