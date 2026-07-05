"""
Synthesizer Agent — 生成结构化调研报告（精简版Prompt, DeepSeek优化）
"""
import asyncio
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState

SYNTH_TIMEOUT = 60


def _format_evidence(items: list, max_items: int = 5) -> str:
    """将证据列表压缩为紧凑文本，每个最多80字符"""
    if not items:
        return "（无）"
    lines = []
    for e in items[:max_items]:
        fact = (e.get("fact") or "")[:100]
        src = (e.get("source") or "")[:60]
        lines.append(f"- {fact} | 来源: {src}")
    return "\n".join(lines)


async def synthesizer_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "synthesizer", "status": "running"})

    # 精简 Prompt：只给关键信息，每个条目截断到 100 字符
    topic = state["research_topic"]
    plan = "\n".join(f"- {p}" for p in (state.get("research_plan") or [])[:4])
    verified_text = _format_evidence(state.get("verified_facts") or [], 5)
    evidence_text = _format_evidence(state.get("evidence_pool") or [], 5)
    missing = ", ".join((state.get("missing_angles") or [])[:5]) or "无"
    score = state.get("fact_quality_score", 0)

    prompt = f"""基于以下调研结果，生成结构化Markdown报告。

调研主题: {topic}

研究计划:
{plan}

关键证据:
{evidence_text}

审核通过:
{verified_text}

缺失角度: {missing}
证据质量: {score}/1.0

报告结构（严格遵守）:
# {topic} — 深度调研报告
## 一、调研背景
## 二、核心发现（每条标注来源）
## 三、证据支撑（引用URL）
## 四、风险与不确定性
## 五、结论与建议

规则: 只使用上述证据、禁止编造、每条发现标注来源URL。如果证据评分<0.5，在风险章节说明。"""

    try:
        resp = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content=prompt)]),
            timeout=SYNTH_TIMEOUT,
        )
        writer({"type": "progress", "node": "synthesizer", "status": "complete"})
        return {"final_report": resp.content}
    except asyncio.TimeoutError:
        writer({"type": "progress", "node": "synthesizer", "status": "complete"})
        return {"final_report": f"## 调研摘要: {topic}\n\n证据已收集（{len(state.get('evidence_pool',[]))}条），但报告生成超时。\n\n### 关键发现\n{evidence_text}\n\n建议缩小范围或减少轮次重试。"}
