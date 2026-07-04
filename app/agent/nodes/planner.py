"""
Planner Agent — 调研问题拆解与搜索规划
"""
import json
from langgraph.runtime import Runtime
from langchain_core.messages import HumanMessage
from app.agent.llm import model
from app.agent.state import ResearchState
from app.prompt.prompts import PLANNER_PROMPT


async def planner_node(state: ResearchState, runtime: Runtime) -> dict:
    writer = runtime.stream_writer
    writer({"type": "progress", "node": "planner", "status": "running"})

    missing = state.get("missing_angles", [])
    if state.get("iteration_count", 0) > 0:
        if not missing:
            writer({"type": "progress", "node": "planner", "status": "complete"})
            return {"report_ready": True, "iteration_count": state["iteration_count"]}

    # 使用 Python 原生 .format() 替代 LangChain PromptTemplate
    prompt_text = PLANNER_PROMPT.format(
        research_topic=state["research_topic"],
        evidence_count=len(state.get("evidence_pool", [])),
        missing_angles=missing if missing else ["（首轮调研，全角度覆盖）"],
        iteration_count=state.get("iteration_count", 0),
        max_iterations=state.get("max_iterations", 3),
    )
    resp = await model.ainvoke([HumanMessage(content=prompt_text)])
    # 从 LLM 响应中提取 JSON
    result = _extract_json(resp.content)
    queries = result.get("search_queries", [])
    writer({"type": "progress", "node": "planner", "status": "complete",
            "plan_count": len(result.get("research_plan", [])), "query_count": len(queries)})
    return {"research_plan": result.get("research_plan", []), "search_queries": queries}


def _extract_json(text: str) -> dict:
    """从 LLM 响应中提取 JSON，兼容 ```json``` 包裹格式"""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    text = text.strip()
    return json.loads(text)
