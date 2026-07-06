"""
Synthesizer Agent — 生成结构化报告（极简版,适配慢速LLM）
"""
import asyncio
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState

SYNTH_TIMEOUT = 25  # 报告生成超时


async def synthesizer_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "synthesizer", "status": "running"})

    topic = state["research_topic"]
    pool = state.get("evidence_pool") or []
    verified = state.get("verified_facts") or pool[:3]
    score = state.get("fact_quality_score", 0)

    # 极简Prompt——每证据一行,不含复杂格式指令
    lines = [f"调研主题: {topic}", "", "证据列表:"]
    for i, e in enumerate(verified[:3]):
        f = (e.get("fact") or "")[:60]
        s = (e.get("source") or "")[:40]
        lines.append(f"{i+1}. {f} [{s}]")
    lines.append(f"\n证据评分: {score}/1.0")
    lines.append("\n根据以上证据写一份简短调研报告（300-500字），包含: 核心发现、证据来源、风险提示。禁止编造。")

    prompt = "\n".join(lines)

    try:
        resp = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt)]),
            timeout=SYNTH_TIMEOUT,
        )
        writer({"type": "progress", "node": "synthesizer", "status": "complete"})
        return {"final_report": resp.content}
    except asyncio.TimeoutError:
        # 超时→直接用证据生成摘要
        summary = f"## {topic} — 调研摘要\n\n> 报告生成超时（{SYNTH_TIMEOUT}秒），以下基于已收集的{len(pool)}条证据的自动摘要。\n\n"
        for i, e in enumerate(pool[:5]):
            f = (e.get("fact") or "")[:80]
            s = (e.get("source") or "")
            summary += f"**{i+1}.** {f}\n> 来源: {s}\n\n"
        summary += f"\n*证据评分: {score}/1.0 · 共{len(pool)}条证据*"
        writer({"type": "progress", "node": "synthesizer", "status": "complete"})
        return {"final_report": summary}
