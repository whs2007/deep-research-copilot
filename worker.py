"""
RabbitMQ Worker — 消费调研任务，执行 Graph 流程，结果写入 MySQL
启动: python worker.py
"""
import asyncio
from datetime import datetime
from sqlalchemy.orm import Session
from app.agent.graph import graph
from app.agent.state import ResearchState
from app.db.connection import SessionLocal
from app.db.models import ResearchReport, UserSession
from app.queue.broker import start_consumer
from app.core.logging import logger


def process_task(task: dict):
    """被 RabbitMQ Consumer 回调：执行一次完整调研"""
    session_id = task["session_id"]
    topic = task["topic"]
    max_iter = task.get("max_iterations", 3)
    db: Session = SessionLocal()

    try:
        # 更新状态 → running
        session = db.query(UserSession).filter_by(session_id=session_id).first()
        if session:
            session.status = "running"
            session.updated_at = datetime.utcnow()
            db.commit()

        # 执行 Graph
        state: ResearchState = {
            "research_topic": topic, "research_plan": [], "search_queries": [],
            "evidence_pool": [], "verified_facts": [], "rejected_facts": [],
            "missing_angles": [], "fact_quality_score": 0.0, "final_report": "",
            "iteration_count": 0, "report_ready": False, "max_iterations": max_iter,
        }
        final = asyncio.run(graph.ainvoke(state))

        # 保存报告到 MySQL
        report = ResearchReport(
            session_id=session_id, topic=topic,
            final_report=final.get("final_report", ""),
            fact_quality_score=final.get("fact_quality_score", 0.0),
            iteration_count=final.get("iteration_count", 0),
            evidence_count=len(final.get("evidence_pool", [])),
            status="completed", completed_at=datetime.utcnow(),
        )
        db.add(report)

        if session:
            session.status = "completed"
            session.updated_at = datetime.utcnow()
        db.commit()
        logger.info(f"调研完成: {session_id}")

    except Exception as e:
        logger.error(f"调研失败 {session_id}: {e}")
        report = ResearchReport(
            session_id=session_id, topic=topic,
            status="failed", error_message=str(e),
            completed_at=datetime.utcnow(),
        )
        db.add(report)
        if session := db.query(UserSession).filter_by(session_id=session_id).first():
            session.status = "failed"
            session.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("Worker 启动，等待 RabbitMQ 任务...")
    start_consumer(process_task)
