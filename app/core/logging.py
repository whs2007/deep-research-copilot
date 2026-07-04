"""结构化日志 — loguru + thread_id 注入"""
import sys
from loguru import logger

LOG_FORMAT = (
    "<green>{time:HH:mm:ss.SSS}</green> | "
    "<level>{level: <8}</level> | "
    "<level>{message}</level>"
)

logger.remove()
logger.add(sys.stderr, level="INFO", format=LOG_FORMAT, colorize=True)
