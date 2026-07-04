"""
请求上下文管理 — ContextVar 协程级隔离
参照 deepsearch-agents 的 ContextVar 设计模式
"""
from contextvars import ContextVar, Token
from typing import Optional

# 协程级上下文变量 — FastAPI 多并发请求不串台
_user_id_ctx: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_session_id_ctx: ContextVar[Optional[str]] = ContextVar("session_id", default=None)


def set_user_context(user_id: str) -> Token:
    """设置当前请求链路的用户 ID"""
    return _user_id_ctx.set(user_id)


def get_current_user() -> str:
    """获取当前请求的用户 ID，未设置返回 anonymous"""
    return _user_id_ctx.get() or "anonymous"


def set_session_context(session_id: str) -> Token:
    """设置当前请求的会话 ID"""
    return _session_id_ctx.set(session_id)


def get_current_session() -> Optional[str]:
    """获取当前请求的会话 ID"""
    return _session_id_ctx.get()


def reset_context(user_token: Token, session_token: Token = None) -> None:
    """恢复上下文，防止泄漏到下一个请求"""
    _user_id_ctx.reset(user_token)
    if session_token is not None:
        _session_id_ctx.reset(session_token)
