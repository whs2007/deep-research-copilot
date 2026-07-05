# 深度研报 — AI 企业调研助手

基于 LangGraph 构建的 4 Agent 协作调研系统。Planner → Search → Critic → Synthesizer 多阶段流水线，支持 loop-back 迭代补充调研，SSE 流式输出结构化报告。

生产级架构：**MySQL 持久化 + Redis 缓存 + RabbitMQ 任务队列 + 独立 Worker 进程**，配套用户系统（注册/登录/游客）与暗色主题前端。

## 截图

### 测试

![pytest](docs/images/test-pytest.png)

### 界面截图获取指南

界面截图需启动项目后手动截取。以下是操作步骤和每张截图应捕捉的内容：

**前置准备**（任选一种方式启动）：

- **Docker Compose**：`docker-compose up -d` → 访问 `http://localhost:8000/ui`
- **本地开发**：`python -m app.api.server` → 访问 `http://localhost:8001/ui`

> 本地开发模式需自行启动 MySQL / Redis / RabbitMQ 才能使用完整功能（不启动会降级，但 SSE 流式调研可正常使用）。

启动后，按下表操作并截图，保存到 `docs/images/`：

| 截图文件名 | 操作方式 | 应捕捉的画面 |
|-----------|---------|-------------|
| `homepage-empty.png` | 打开 `/ui`，不输入任何内容 | 空首页：暗色主题，顶部栏「深度研报」，左侧「历史对话」空列表，中央输入框 + 5 个示例按钮（新能源汽车/AI芯片/光伏产业/半导体/氢能） |
| `homepage-examples.png` | 点击某个示例按钮（如「新能源汽车」） | 输入框自动填入示例话题文本，按钮仍可点击 |
| `homepage-input.png` | 手动在输入框中输入一个调研主题 | 输入框显示已输入的文字，光标闪烁 |
| `progress-searching.png` | 点击「开始调研」，等 Search 节点执行 | 状态栏圆点变为黄色脉动，进度面板出现 `🔍 信息检索 ⏳ 并发搜索中…` |
| `progress-critic.png` | 等待 Critic 节点执行 | 进度面板出现 `🔬 质量审核` 行，状态栏显示轮次/证据数/质量分 |
| `progress-synthesizer.png` | 等待 Synthesizer 节点执行 | 进度面板出现 `📝 报告生成 ⏳ 撰写报告中…` |
| `report-full.png` | 调研完成，报告完整渲染 | 报告面板：Markdown 渲染的标题/段落/列表/链接，蓝白配色 |
| `report-result.png` | 滚动到报告底部或截取摘要区域 | 报告结尾部分或左侧历史栏出现新记录（含质量分/证据数/轮次） |

**截图技巧**：
- 浏览器全屏后用系统截图工具（Win+Shift+S / macOS Cmd+Shift+4）
- 进度类截图需手快——节点执行可能只有几秒，可多次调研抓拍
- 建议用「光伏产业技术路线TOPCon vs HJT」等话题测试，搜索结果较稳定

## 系统架构

### Agent 流水线

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

### 生产部署架构

```
┌──────────────┐      ┌─────────────┐      ┌──────────────┐
│  前端 (SPA)   │─────▶│  FastAPI     │─────▶│   RabbitMQ    │
│  /ui 暗色主题 │ SSE  │  API 服务    │ 入队  │  research_tasks│
└──────────────┘      └──────┬──────┘      └──────┬───────┘
                             │                     │
              ┌──────────────┼─────────────┐       │ 消费
              ▼              ▼             ▼       ▼
         ┌────────┐    ┌──────────┐  ┌──────────────────┐
         │ MySQL  │    │  Redis   │  │   Worker 进程     │
         │ 4 张表  │    │ 缓存+限流 │  │ 执行 Graph 流程   │
         └────────┘    └──────────┘  │ 结果写回 MySQL    │
                                     └──────────────────┘
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
| **MySQL 持久化** | 用户/报告/证据缓存/会话 4 张表，报告永久留存 |
| **Redis 缓存** | Tavily 结果(24h) + LLM 响应(1h) + 会话状态(2h) + 速率限制(60s/30次) |
| **RabbitMQ 队列** | 异步任务分发，消息持久化 + 公平分发，API 与 Worker 解耦 |
| **用户系统** | 注册/登录/游客，X-User-ID 认证，ContextVar 协程级隔离 |
| **Docker 部署** | docker-compose 一键拉起 5 服务（app/worker/mysql/redis/rabbitmq） |

## 快速开始

### 方式一：Docker Compose（推荐，一键启动全套）

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 和 TAVILY_API_KEY

# 2. 一键启动（app + worker + mysql + redis + rabbitmq）
docker-compose up -d

# 3. 访问
#   前端:  http://localhost:8000/ui
#   API:   http://localhost:8000
#   健康检查: http://localhost:8000/health
#   RabbitMQ 管理台: http://localhost:15672  (guest/guest)
```

### 方式二：本地开发（仅核心流水线，可选依赖）

不启动 MySQL/Redis/RabbitMQ 也能运行——代码对各中间件做了容错，不可用时自动降级跳过。

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 和 TAVILY_API_KEY

# 3. 本地测试（直接跑 Graph，不需要数据库/队列）
python test_run.py

# 4. 启动 API 服务（端口 8001）
python -m app.api.server
# 或: uvicorn app.api.server:app --reload --port 8001

# 5. 启动 Worker（如需异步队列模式，需先启动 MySQL + RabbitMQ）
python worker.py
```

## 环境变量

在 `.env` 中配置（参考 `.env.example`）：

| 变量 | 必填 | 说明 | 默认值 |
|------|------|------|--------|
| `OPENAI_BASE_URL` | 是 | LLM API 地址（OpenAI 兼容协议） | — |
| `OPENAI_API_KEY` | 是 | LLM API Key | — |
| `LLM_MODEL` | 是 | 模型名（gpt-4o / deepseek / qwen 等） | `gpt-4o` |
| `TAVILY_API_KEY` | 是 | Tavily 搜索 API Key | — |
| `MYSQL_URL` | 否 | MySQL 连接串 | `mysql+pymysql://root:root@localhost:3306/research_copilot` |
| `REDIS_URL` | 否 | Redis 连接串 | `redis://localhost:6379/0` |
| `RABBITMQ_URL` | 否 | RabbitMQ 连接串 | `amqp://guest:guest@localhost:5672/` |
| `MYSQL_ROOT_PASSWORD` | 否 | Docker MySQL root 密码 | `root` |

## API 接口

### 用户系统

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/register` | 注册（username + password）→ 返回 user_id / token |
| `POST` | `/api/login` | 登录 → 返回 user_id / token / display_name |
| `POST` | `/api/guest` | 游客登录 → 生成临时 guest_xxxx ID |
| `GET`  | `/api/user` | 获取当前用户信息（`X-User-ID` 头，自动注册游客） |

> 除注册/登录外，所有接口通过请求头 `X-User-ID` 标识用户身份。

### 调研任务

#### POST `/api/research` — 异步队列模式

提交调研任务到 RabbitMQ，立即返回 `session_id`，由 Worker 异步执行。

```bash
curl -X POST http://localhost:8001/api/research \
  -H "Content-Type: application/json" \
  -H "X-User-ID: u_12345678" \
  -d '{"topic": "2026年中国新能源汽车市场竞争格局", "max_iterations": 3}'
```

请求体：
```json
{
  "topic": "string (必填)",
  "max_iterations": "int (可选, 默认 3, 上限 5)"
}
```

响应：
```json
{ "status": "queued", "session_id": "uuid" }
```

#### GET `/api/research/stream` — SSE 流式模式

实时流式返回调研进度与最终报告（不走队列，同步执行 Graph）。

```bash
curl -N "http://localhost:8001/api/research/stream?topic=新能源汽车&max_iterations=3" \
  -H "X-User-ID: u_12345678"
```

SSE 事件流（`data: <json>\n\n` 格式）：

| 事件 `type` | 含义 |
|------------|------|
| `progress` | 节点执行进度（含 node / message / 附加数据） |
| `report` | 最终结构化报告（Markdown） |
| `error` | 全局异常 |
| `[DONE]` | 流结束标记 |

#### GET `/api/research/{session_id}/stream`

带 `session_id` 的 SSE 流式版本，`topic` 可通过 query 传入。

### 历史与报告

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/history` | 当前用户的历史调研报告列表（按时间倒序，默认 20 条） |
| `GET` | `/api/report/{session_id}` | 获取单份调研报告详情 |
| `GET` | `/health` | 健康检查（Docker HEALTHCHECK / K8s probe） |
| `GET` | `/ui` | 前端静态页面 |

## 测试

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

## 数据模型

MySQL 共 4 张表（SQLAlchemy ORM，启动时自动建表）：

| 表 | 说明 |
|----|------|
| `users` | 用户：user_id / username / password_hash / is_guest / total_reports |
| `research_reports` | 调研报告：session_id / topic / final_report / 评分 / 迭代次数 / 证据数 / 状态 |
| `evidence_cache` | 证据缓存：query_hash → evidence_json，避免重复调 Tavily |
| `user_sessions` | 调研会话：session_id / status（queued/running/completed/failed）/ max_iterations |

## State 总览

LangGraph 核心 State（`ResearchState`），围绕"报告生成"设计，非消息堆积：

| 字段 | 类型 | 写入节点 | 作用 |
|------|------|---------|------|
| `research_topic` | `str` | 用户输入 | 调研主题 |
| `research_plan` | `list[str]` | Planner | 拆解后的子问题 |
| `search_queries` | `list[SearchQuery]` | Planner | 驱动 Search 并发（query/source/priority） |
| `evidence_pool` | `list[Evidence]` | Search（追加） | 跨轮证据池（fact/source/relevance/confidence） |
| `verified_facts` | `list[Evidence]` | Critic | 通过审核的证据 |
| `rejected_facts` | `list[Evidence]` | Critic | 被拒绝的证据 |
| `missing_angles` | `list[str]` | Critic | 缺失角度 → loop-back |
| `fact_quality_score` | `float` | Critic | 证据质量 0.0-1.0 |
| `final_report` | `str` | Synthesizer | Markdown 报告 |
| `iteration_count` | `int` | Critic(+1) | 防死循环计数器 |
| `report_ready` | `bool` | Critic, Planner | 条件边判断 |
| `max_iterations` | `int` | 用户 | 硬上限（默认 3） |

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
│   │   └── server.py             # FastAPI + SSE + 用户系统 + 队列发布
│   ├── db/
│   │   ├── connection.py         # MySQL 连接池（SQLAlchemy）
│   │   └── models.py             # 4 张表 ORM（User/Report/Cache/Session）
│   ├── cache/
│   │   └── redis_client.py       # Redis 缓存 + 会话状态 + 速率限制
│   ├── queue/
│   │   └── broker.py             # RabbitMQ Producer/Consumer
│   ├── core/
│   │   ├── context.py            # ContextVar 协程级用户/会话隔离
│   │   └── logging.py            # loguru 结构化日志
│   ├── tools/
│   │   └── search_tool.py        # Tavily API 封装
│   └── prompt/
│       └── prompts.py            # 4 个 Agent 的 System Prompt
├── frontend/
│   └── index.html                # 暗色主题单页前端（挂载于 /ui）
├── tests/                        # 测试套件
│   ├── conftest.py               # Fixtures + Mock 配置
│   ├── test_planner.py           # Planner 拆解 + 空转防护
│   ├── test_search.py            # 并发 + 去重
│   ├── test_critic.py            # forced_ready + 评分
│   ├── test_synthesizer.py       # 证据注入验证
│   ├── test_graph.py             # Workflow + 条件边
│   └── test_api.py               # /research 接口
├── worker.py                     # RabbitMQ Worker（消费队列执行 Graph）
├── test_run.py                   # 本地调试入口
├── requirements.txt
├── Dockerfile                    # 多阶段构建 + HEALTHCHECK + 优雅关闭
├── docker-compose.yaml           # 5 服务编排
├── .env.example
└── README.md
```

## 技术栈

| 层级 | 技术 |
|------|------|
| Agent 编排 | LangGraph StateGraph |
| LLM | OpenAI 兼容协议（GPT-4o / DeepSeek / qwen） |
| 搜索 | Tavily API |
| 后端 | FastAPI + SSE StreamingResponse |
| 数据库 | MySQL 8.0 + SQLAlchemy ORM |
| 缓存 | Redis 7（搜索/LLM/会话缓存 + 速率限制） |
| 队列 | RabbitMQ 3（pika，消息持久化 + 公平分发） |
| 日志 | loguru 结构化日志 |
| 上下文隔离 | ContextVar（协程级用户/会话隔离） |
| 部署 | Docker + docker-compose + Uvicorn |
| 测试 | pytest + pytest-asyncio + pytest-cov |
| Python | ≥3.12 |

## License

MIT
