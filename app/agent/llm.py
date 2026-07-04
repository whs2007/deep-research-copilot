"""
LLM 初始化模块 — OpenAI 兼容协议接入
"""
import os
from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model

load_dotenv(find_dotenv())

# 调研场景需要稳定性和事实准确性，temperature=0
model = init_chat_model(
    model=os.getenv("LLM_MODEL", "gpt-4o"),
    model_provider="openai",
    base_url=os.getenv("OPENAI_BASE_URL"),
    api_key=os.getenv("OPENAI_API_KEY"),
    temperature=0,
    request_timeout=60,  # LLM 调用超时 60 秒（防 Worker 卡死）
)
