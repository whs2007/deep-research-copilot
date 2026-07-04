"""
MySQL 数据模型 — SQLAlchemy ORM
四张表：users / research_reports / evidence_cache / user_sessions
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """用户表 — 账号与个人信息"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), unique=True, index=True, nullable=False)
    username = Column(String(100), unique=True, index=True)       # 登录用户名
    password_hash = Column(String(256))                           # bcrypt 哈希
    display_name = Column(String(100), default="未命名用户")
    is_guest = Column(Integer, default=1)                         # 1=游客 0=注册用户
    total_reports = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active_at = Column(DateTime, default=datetime.utcnow)

    reports = relationship("ResearchReport", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")


class ResearchReport(Base):
    """调研报告 — 每次调研任务完成后的完整记录"""
    __tablename__ = "research_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), index=True, nullable=False)
    user_id = Column(String(128), ForeignKey("users.user_id"), index=True, nullable=False)
    topic = Column(String(500), nullable=False)
    final_report = Column(Text)
    fact_quality_score = Column(Float, default=0.0)
    iteration_count = Column(Integer, default=0)
    evidence_count = Column(Integer, default=0)
    status = Column(String(20), default="completed")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    user = relationship("User", back_populates="reports")


class EvidenceCache(Base):
    """证据缓存 — 避免相同 query 重复调 Tavily"""
    __tablename__ = "evidence_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_hash = Column(String(64), unique=True, index=True)
    query_text = Column(String(500))
    evidence_json = Column(JSON)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


class UserSession(Base):
    """调研会话 — 每次调研任务的执行记录"""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(36), unique=True, index=True, nullable=False)
    user_id = Column(String(128), ForeignKey("users.user_id"), index=True, nullable=False)
    topic = Column(String(500))
    status = Column(String(20), default="pending")
    max_iterations = Column(Integer, default=3)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="sessions")
