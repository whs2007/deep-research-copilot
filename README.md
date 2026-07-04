# 深度研报 — AI 企业调研助手

基于 LangGraph 构建的 4 Agent 协作调研系统。Planner → Search → Critic → Synthesizer 多阶段流水线，支持 loop-back 迭代补充调研，SSE 流式输出结构化报告。

## 界面截图

| 首页 | 调研结果 |
|------|---------|
| ![首页](docs/images/屏幕截图%202026-07-04%20154427.png) | ![结果](docs/images/屏幕截图%202026-07-04%20154818.png) |

## 系统架构

```
                    START
                      │
                 ┌────▼────┐
                 │ Planner │  拆解问题 → 3-5 个搜索查询
                 └────┬────┘
                      │
                 ┌────▼────┐
                 │ Search  │  asyncio.gather 并发搜索 + 去重
                 └────┬────┘
                      │
                 ┌────▼────┐
                 │ Critic  │  4 维评估（覆盖度/可靠性/时效性/一致性）
                 └──┬──┬──┘
                    │  │
       证据不足/    │  │  证据充分/
       次数未达上限 │  │  次数达上限
                    │  │
              ┌─────┘  └─────┐
              ▼               ▼
         (回到Planner)   ┌────────────┐
         最多 3 次       │Synthesizer │  五段式结构化报告
                         └─────┬──────┘
                               │
                              END
```

## 核心特性

| 特性 | 实现 |
|------|------|
| **多 Agent 协作** | 4 个独立 Agent，通过统一 State 解耦通信 |
| **loop-back 迭代** | Critic 评估不足 → 自动回 Planner 补充搜索（最多 3 次） |
| **async 并发搜索** | `asyncio.to_thread` + `asyncio.gather` 真正并行 |
| **证据质量控制** | 覆盖度/可靠性/时效性/一致性 4 维评估 + 去重 |
| **SSE 流式输出** | 每个节点实时推送进度，前端打字机效果 |
| **防死循环** | `iteration_count` 硬上限 + `forced_ready` 代码层覆盖 |
| **Docker 部署** | 多阶段构建，`.env` 环境变量注入 |

## 快速开始

```bash
# 1. 安装
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 和 TAVILY_API_KEY

# 3. 本地测试
python test_run.py

# 4. 启动 API 服务
uvicorn app.api.server:app --reload --port 8000
```

## API

### POST /api/research

启动一次调研任务，SSE 流式返回进度和最终报告。

```bash
curl -X POST http://localhost:8000/api/research \
  -H "Content-Type: application/json" \
  -d '{"topic": "2026年中国新能源汽车市场竞争格局", "max_iterations": 3}'
```

请求体：
```json
{
  "topic": "string (required)",
  "max_iterations": "int (optional, default=3, max=5)"
}
```

SSE 事件类型：
| 事件 | 含义 |
|------|------|
| `progress` | 节点执行进度（node/status/附加数据） |
| `report` | 最终结构化报告（Markdown） |
| `[DONE]` | 流结束 |
| `error` | 全局异常 |

### 测试

| 模块 | 用例数 | 覆盖范围 |
|------|--------|---------|
| `test_graph.py` | 7 | 节点存在 / 边正确 / 条件边 3 场景 / 字段缺失容错 |
| `test_critic.py` | 5 | forced_ready 逻辑 / 递增 / LLM 覆盖 / 事件格式 |
| `test_planner.py` | 4 | 首轮不跳过 / 空转防护 / iteration 不变 / stream_writer |
| `test_search.py` | 4 | 空查询 / 结构 / 已有证据保留 / 进度推送 |
| `test_synthesizer.py` | 5 | Prompt 8 占位符 / 五段式结构 / 禁止编造 / 返回格式 / 事件 |
| `test_api.py` | 4 | SSE 响应 / 默认参数 / 422 校验 / content-type |

```bash
# 运行所有测试
pytest tests/ -v

# 29 passed in ~7s
```

```
============================= 29 passed in 7.52s =============================
```

## 项目结构

```
├── app/
│   ├── agent/
│   │   ├── state.py              # ResearchState（13 字段）
│   │   ├── graph.py              # LangGraph 工作流 + 条件边
│   │   ├── llm.py                # OpenAI 兼容 LLM（temperature=0）
│   │   └── nodes/
│   │       ├── planner.py        # Planner Agent
│   │       ├── search.py         # Search Agent（async 并发 + 去重）
│   │       ├── critic.py         # Critic Agent（4 维评估 + 强制终止）
│   │       └── synthesizer.py    # Synthesizer Agent（证据注入报告）
│   ├── api/
│   │   └── server.py             # FastAPI + SSE StreamingResponse
│   ├── tools/
│   │   └── search_tool.py        # Tavily API 封装
│   └── prompt/
│       └── prompts.py            # 4 个 Agent 的 System Prompt
├── tests/                        # 测试套件
│   ├── conftest.py               # Fixtures + Mock 配置
│   ├── test_planner.py           # Planner 拆解 + 空转防护
│   ├── test_search.py            # 并发 + 去重
│   ├── test_critic.py            # forced_ready + 评分
│   ├── test_synthesizer.py       # 证据注入验证
│   ├── test_graph.py             # Workflow + 条件边
│   └── test_api.py               # /research 接口
├── test_run.py                   # 本地调试入口
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 编排 | LangGraph StateGraph |
| LLM | OpenAI 兼容协议（GPT-4o / qwen / DeepSeek） |
| 搜索 | Tavily API |
| 后端 | FastAPI + SSE |
| 部署 | Docker + Uvicorn |
| 测试 | pytest + pytest-asyncio + pytest-cov |
| Python | ≥3.12 |

## State 总览

| 字段 | 类型 | 写入节点 | 作用 |
|------|------|---------|------|
| `research_topic` | `str` | 用户输入 | 调研主题 |
| `research_plan` | `list[str]` | Planner | 拆解后的子问题 |
| `search_queries` | `list[dict]` | Planner | 驱动 Search 并发 |
| `evidence_pool` | `list[dict]` | Search（追加） | 跨轮证据池 |
| `verified_facts` | `list[dict]` | Critic | 通过审核的证据 |
| `rejected_facts` | `list[dict]` | Critic | 被拒绝的证据 |
| `missing_angles` | `list[str]` | Critic | 缺失角度 → loop-back |
| `fact_quality_score` | `float` | Critic | 证据质量 0.0-1.0 |
| `final_report` | `str` | Synthesizer | Markdown 报告 |
| `iteration_count` | `int` | Critic(+1) | 防死循环计数器 |
| `report_ready` | `bool` | Critic, Planner | 条件边判断 |
| `max_iterations` | `int` | 用户 | 硬上限（默认 3） |

## License

MIT
