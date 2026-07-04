"""
Redis 缓存层 — 搜索结果 + LLM 响应缓存 + 速率限制
"""
import os
import json
import hashlib
from typing import Optional
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis = redis.from_url(REDIS_URL, decode_responses=True)

# TTL 配置
TAVILY_CACHE_TTL = 86400     # Tavily 搜索结果缓存 24 小时
LLM_CACHE_TTL = 3600          # LLM 响应缓存 1 小时
SESSION_TTL = 7200             # 会话状态 2 小时
RATE_LIMIT_WINDOW = 60        # 速率限制窗口 60 秒
RATE_LIMIT_MAX = 30            # 每窗口最多 30 次请求


def cache_tavily_result(query: str, results: list) -> None:
    """缓存 Tavily 搜索结果"""
    key = f"tavily:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
    _redis.setex(key, TAVILY_CACHE_TTL, json.dumps(results, ensure_ascii=False))


def get_cached_tavily_result(query: str) -> Optional[list]:
    """获取缓存的 Tavily 结果"""
    key = f"tavily:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
    data = _redis.get(key)
    return json.loads(data) if data else None


def cache_llm_response(prompt_hash: str, response: str) -> None:
    """缓存 LLM 响应"""
    _redis.setex(f"llm:{prompt_hash}", LLM_CACHE_TTL, response)


def get_cached_llm_response(prompt_hash: str) -> Optional[str]:
    """获取缓存的 LLM 响应"""
    return _redis.get(f"llm:{prompt_hash}")


def save_session_state(session_id: str, state: dict) -> None:
    """保存会话状态到 Redis"""
    _redis.setex(f"session:{session_id}", SESSION_TTL, json.dumps(
        {k: v for k, v in state.items() if k not in ("evidence_pool", "final_report")},
        ensure_ascii=False, default=str
    ))


def get_session_state(session_id: str) -> Optional[dict]:
    """获取会话状态"""
    data = _redis.get(f"session:{session_id}")
    return json.loads(data) if data else None


def check_rate_limit(user_id: str) -> bool:
    """速率限制：用户在窗口内是否超限"""
    key = f"ratelimit:{user_id}"
    current = _redis.incr(key)
    if current == 1:
        _redis.expire(key, RATE_LIMIT_WINDOW)
    return current <= RATE_LIMIT_MAX
