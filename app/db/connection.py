"""
MySQL 连接管理
"""
import os
from dotenv import find_dotenv, load_dotenv
load_dotenv(find_dotenv())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.db.models import Base

DATABASE_URL = os.getenv(
    "MYSQL_URL",
    "mysql+pymysql://root:root@localhost:3309/research_copilot"
)

engine = create_engine(DATABASE_URL, pool_size=10, pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """创建所有表（启动时调用）"""
    Base.metadata.create_all(engine)


def get_db() -> Session:
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
