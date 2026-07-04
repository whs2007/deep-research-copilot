"""
FastAPI 服务 — 生产级：MySQL 持久化 + Redis 缓存 + RabbitMQ 任务队列 + SSE 流式
"""
import uuid
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.graph import graph
from app.agent.state import ResearchState
from app.db.connection import get_db, init_db
from app.db.models import ResearchReport, UserSession
from app.cache.redis_client import save_session_state, check_rate_limit
from app.queue.broker import publish_task
from app.core.logging import logger


class ResearchRequest(BaseModel):
    topic: str
    max_iterations: int = 3
    user_id: str = "anonymous"


class ReportResponse(BaseModel):
    session_id: str
    topic: str
    status: str
    fact_quality_score: float
    iteration_count: int
    evidence_count: int
    final_report: str | None
    created_at: str


app = FastAPI(title="Deep Research Copilot — Enterprise")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    init_db()
    logger.info("MySQL 表初始化完成")


@app.post("/api/research")
async def research(req: ResearchRequest, db: Session = Depends(get_db)):
    """提交调研任务 → 异步队列 → 立即返回 session_id"""
    if not check_rate_limit(req.user_id):
        raise HTTPException(429, "请求过于频繁，请稍后重试")

    session_id = str(uuid.uuid4())

    # 保存会话到 MySQL
    db_session = UserSession(
        session_id=session_id, user_id=req.user_id,
        topic=req.topic, max_iterations=req.max_iterations, status="queued"
    )
    db.add(db_session)
    db.commit()

    # 发布到 RabbitMQ
    publish_task(session_id, req.topic, req.max_iterations)

    return {"status": "queued", "session_id": session_id}


@app.get("/api/research/{session_id}/stream")
async def research_stream(session_id: str):
    """SSE 流式调研（同步模式，实时返回进度）"""
    state: ResearchState = {
        "research_topic": "", "research_plan": [], "search_queries": [],
        "evidence_pool": [], "verified_facts": [], "rejected_facts": [],
        "missing_angles": [], "fact_quality_score": 0.0, "final_report": "",
        "iteration_count": 0, "report_ready": False, "max_iterations": 3,
    }

    async def event_stream():
        try:
            async for chunk in graph.astream(state, stream_mode="custom"):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            final = await graph.ainvoke(state)
            yield f"data: {json.dumps({'type':'report','data':final.get('final_report','')}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/history")
async def list_reports(user_id: str = "anonymous", limit: int = 20, db: Session = Depends(get_db)):
    """查询历史调研报告"""
    reports = db.query(ResearchReport).filter(
        ResearchReport.session_id.in_(
            db.query(UserSession.session_id).filter(UserSession.user_id == user_id)
        )
    ).order_by(ResearchReport.created_at.desc()).limit(limit).all()
    return [{
        "session_id": r.session_id, "topic": r.topic, "status": r.status,
        "fact_quality_score": r.fact_quality_score, "iteration_count": r.iteration_count,
        "evidence_count": r.evidence_count, "created_at": str(r.created_at)
    } for r in reports]


@app.get("/api/report/{session_id}")
async def get_report(session_id: str, db: Session = Depends(get_db)):
    """获取单份调研报告详情"""
    report = db.query(ResearchReport).filter_by(session_id=session_id).first()
    if not report:
        raise HTTPException(404, "报告不存在")
    return {
        "session_id": report.session_id, "topic": report.topic,
        "final_report": report.final_report, "fact_quality_score": report.fact_quality_score,
        "iteration_count": report.iteration_count, "evidence_count": report.evidence_count,
        "status": report.status, "created_at": str(report.created_at)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=8000, reload=True)
