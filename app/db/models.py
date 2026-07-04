"""
MySQL 数据模型 — SQLAlchemy ORM
三张表：research_reports / evidence_cache / sessions
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class ResearchReport(Base):
    """调研报告 — 每次调研任务完成后的完整记录"""
    __tablename__ = "research_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), index=True, nullable=False)
    topic = Column(String(500), nullable=False)
    final_report = Column(Text)                       # Markdown 完整报告
    fact_quality_score = Column(Float, default=0.0)   # Critic 评分
    iteration_count = Column(Integer, default=0)       # 实际迭代次数
    evidence_count = Column(Integer, default=0)        # 证据总数
    status = Column(String(20), default="completed")   # running / completed / failed
    error_message = Column(Text)                       # 失败时的错误信息
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class EvidenceCache(Base):
    """证据缓存 — 避免相同 query 重复调 Tavily"""
    __tablename__ = "evidence_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_hash = Column(String(64), unique=True, index=True)  # SHA256(query)
    query_text = Column(String(500))
    evidence_json = Column(JSON)                    # 缓存的证据列表
    hit_count = Column(Integer, default=0)           # 命中次数
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)                     # TTL 过期时间


class UserSession(Base):
    """用户会话 — 多用户隔离"""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), unique=True, index=True, nullable=False)
    user_id = Column(String(128), index=True, default="anonymous")
    topic = Column(String(500))
    status = Column(String(20), default="pending")    # pending / queued / running / completed / failed
    max_iterations = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
