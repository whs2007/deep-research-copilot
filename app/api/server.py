"""
FastAPI 服务 — 生产级：MySQL 持久化 + Redis 缓存 + RabbitMQ 任务队列 + SSE 流式
用户系统：ContextVar 协程级会话隔离 + X-User-ID 请求头认证
"""
import uuid
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional
from pathlib import Path

from app.agent.graph import graph
from app.agent.state import ResearchState
from app.db.connection import get_db, init_db
from app.db.models import User, ResearchReport, UserSession
from app.core.logging import logger
from app.core.context import (
    set_user_context, reset_context, get_current_user, set_session_context
)


class ResearchRequest(BaseModel):
    topic: str = ""  # 必填
    max_iterations: int = 3


class ReportResponse(BaseModel):
    session_id: str
    topic: str
    status: str
    fact_quality_score: float
    iteration_count: int
    evidence_count: int
    final_report: str | None
    created_at: str


app = FastAPI(title="深度研报 — AI企业调研助手", version="1.0.0")


def _ensure_user(user_id: str) -> None:
    """确保用户存在于数据库中（自动注册）"""
    try:
        from app.db.connection import SessionLocal
        db = SessionLocal()
        existing = db.query(User).filter_by(user_id=user_id).first()
        if not existing:
            db.add(User(user_id=user_id, display_name=f"用户_{user_id[:8]}"))
            db.commit()
        else:
            existing.last_active_at = datetime.utcnow()
            db.commit()
        db.close()
    except Exception:
        pass  # MySQL 不可用时跳过


@app.get("/health")
async def health():
    """健康检查端点（Docker HEALTHCHECK / K8s liveness probe）"""
    return {"status": "healthy", "version": "1.0.0"}

@app.get("/api/user")
async def get_user(x_user_id: Optional[str] = Header(None, alias="X-User-ID")):
    """获取当前用户信息（自动注册）"""
    user_id = x_user_id or "anonymous"
    _ensure_user(user_id)
    try:
        from app.db.connection import SessionLocal
        db = SessionLocal()
        u = db.query(User).filter_by(user_id=user_id).first()
        result = {"user_id": user_id, "display_name": u.display_name if u else user_id,
                  "total_reports": u.total_reports if u else 0,
                  "created_at": str(u.created_at) if u else None}
        db.close()
        return result
    except Exception:
        return {"user_id": user_id, "display_name": user_id}
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# 前端静态文件（通过 /ui 访问，避免与 API 路由冲突）
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/ui", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
    logger.info(f"前端静态文件已挂载: http://localhost:8001/ui")
else:
    logger.warning(f"前端目录不存在: {frontend_path}")


from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        logger.info("MySQL 表初始化完成")
    except Exception as e:
        logger.warning(f"MySQL 不可用（开发模式跳过）: {e}")
    yield

app.router.lifespan_context = lifespan


@app.post("/api/research")
async def research(
    req: ResearchRequest,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    """提交调研任务 → 异步队列 → 立即返回 session_id"""
    # ═══ ContextVar 用户上下文 ═══
    user_id = x_user_id or "anonymous"
    user_token = set_user_context(user_id)
    session_id = str(uuid.uuid4())
    session_token = set_session_context(session_id)

    try:
        # 速率限制
        try:
            from app.cache.redis_client import check_rate_limit
            if not check_rate_limit(user_id):
                raise HTTPException(429, "请求过于频繁，请稍后重试")
        except Exception:
            pass

        # 保存会话到 MySQL
        try:
            db_session = UserSession(
                session_id=session_id, user_id=user_id,
                topic=req.topic, max_iterations=req.max_iterations, status="queued"
            )
            db.add(db_session)
            db.commit()
        except Exception as e:
            logger.warning(f"MySQL 不可用，会话跳过: {e}")

        # 发布到 RabbitMQ
        try:
            from app.queue.broker import publish_task
            publish_task(session_id, req.topic, req.max_iterations)
        except Exception as e:
            logger.warning(f"RabbitMQ 不可用，队列跳过: {e}")

        return {"status": "queued", "session_id": session_id}
    finally:
        reset_context(user_token, session_token)


@app.get("/api/research/stream")
async def research_stream_simple(
    topic: str = "",
    max_iterations: int = 3,
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    """SSE 流式调研（ContextVar 自动注入用户上下文）"""
    user_id = x_user_id or "anonymous"
    _ensure_user(user_id)
    set_user_context(user_id)
    state: ResearchState = {
        "research_topic": topic, "research_plan": [], "search_queries": [],
        "evidence_pool": [], "verified_facts": [], "rejected_facts": [],
        "missing_angles": [], "fact_quality_score": 0.0, "final_report": "",
        "iteration_count": 0, "report_ready": False, "max_iterations": max_iterations,
    }

    async def event_stream():
        try:
            async for chunk in graph.astream(state, stream_mode="custom"):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            final = await graph.ainvoke(state)
            report_text = final.get('final_report', '')
            yield f"data: {json.dumps({'type':'report','data':report_text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

            # 自动保存报告到 MySQL（用户历史记录）
            sid = str(uuid.uuid4())
            try:
                from app.db.connection import SessionLocal
                db = SessionLocal()
                db.add(ResearchReport(
                    session_id=sid, user_id=user_id, topic=topic, final_report=report_text,
                    fact_quality_score=final.get('fact_quality_score',0.0),
                    iteration_count=final.get('iteration_count',0),
                    evidence_count=len(final.get('evidence_pool',[])),
                    status='completed', completed_at=datetime.utcnow()))
                db.add(UserSession(session_id=sid, user_id=user_id, topic=topic,
                                   max_iterations=max_iterations, status='completed'))
                # 更新用户报告计数
                u = db.query(User).filter_by(user_id=user_id).first()
                if u:
                    u.total_reports = (u.total_reports or 0) + 1
                    u.last_active_at = datetime.utcnow()
                db.commit(); db.close()
            except Exception as e:
                logger.warning(f"MySQL 保存失败: {e}")
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/research/{session_id}/stream")
async def research_stream(session_id: str, topic: str = ""):
    """SSE 流式调研（带 session_id 版本）"""
    return await research_stream_simple(topic=topic or session_id)


@app.get("/api/history")
async def list_reports(
    limit: int = 20,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(None, alias="X-User-ID"),
):
    """查询当前用户的历史调研报告（ContextVar 自动获取用户身份）"""
    user_id = x_user_id or get_current_user()
    reports = db.query(ResearchReport).filter(
        ResearchReport.user_id == user_id
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
    uvicorn.run("app.api.server:app", host="0.0.0.0", port=8001, reload=True)
