"""
FastAPI 服务 — /research API + 流式 SSE 输出
"""
import uuid
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.graph import graph
from app.agent.state import ResearchState


class ResearchRequest(BaseModel):
    topic: str
    max_iterations: int = 3


app = FastAPI(title="Deep Research Copilot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.post("/api/research")
async def research(req: ResearchRequest):
    """启动调研任务，SSE 流式返回各节点进度和最终报告"""

    state: ResearchState = {
        "research_topic": req.topic,
        "research_plan": [],
        "search_queries": [],
        "evidence_pool": [],
        "verified_facts": [],
        "rejected_facts": [],
        "missing_angles": [],
        "fact_quality_score": 0.0,
        "final_report": "",
        "iteration_count": 0,
        "report_ready": False,
        "max_iterations": max(req.max_iterations, 3),
    }

    async def event_stream():
        try:
            async for chunk in graph.astream(state, stream_mode="custom"):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

            # 拉取最终 state 中的报告
            final = await graph.ainvoke(state)
            yield f"data: {json.dumps({'type': 'report', 'data': final.get('final_report', '')}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=8000, reload=True)
