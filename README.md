# Deep Research Copilot — 企业信息调研助手

基于 LangGraph 构建的多 Agent 协作调研系统。Planner（规划）→ Search（检索）→ Critic（审核）→ Synthesizer（报告生成）四阶段流水线，支持 loop-back 迭代补充调研。

## 架构

```
用户问题 → Planner → Search (async并发) → Critic
                ↑                              │
                └── report_ready=false ────────┘  (最多3次)
                                                   │
                                        report_ready=true
                                                   │
                                                   ▼
                                            Synthesizer → 结构化报告
```

## 快速开始

```bash
pip install -r requirements.txt
cp .env.example .env  # 填入 API Key
python test_run.py
```

## API

```bash
uvicorn app.api.server:app --reload

# 启动调研
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "2026年中国AI行业发展趋势", "max_iterations": 3}'
```

## 项目结构

```
├── app/agent/
│   ├── state.py      # ResearchState 定义
│   ├── graph.py      # LangGraph 工作流
│   ├── llm.py        # LLM 初始化
│   └── nodes/        # 4 个 Agent 节点
├── app/api/server.py # FastAPI /research
├── app/tools/        # Tavily 搜索工具
├── app/prompt/       # Prompt 模板
├── test_run.py       # 本地测试
└── .env.example
```
