# Deep Research Copilot — 深度剖析与面试备考文档

> 覆盖：源码级解释 / State 流转 / loop-back 机制 / 架构选型 / RAG对比 / 面试25题

---

## 一、Planner / Search / Critic / Synthesizer 源码级解释

### 1.1 Planner Agent

**源码位置**：`app/agent/nodes/planner.py`

**核心逻辑**：Planner 接收用户调研问题 + 已有证据状态，输出 JSON 结构化的研究计划和搜索查询。不是简单的"拆分问题"——它根据当前是第几轮迭代来调整策略。第一轮全角度覆盖，后续轮次只补充 Critic 标记的 `missing_angles`。

**关键参数**：temperature=0（调研场景需要事实稳定性，禁止模型"创造性发挥"），JsonOutputParser（强制结构化输出，不依赖 Markdown 代码块解析）。

**设计要点**：首轮时 `missing_angles` 为空，Planner 注入"（首轮调研，全角度覆盖）"提示词，引导模型生成 3-5 个子问题的全面计划。非首轮时，`missing_angles` 由 Critic 产出，Planner 只针对缺失角度生成补充搜索——避免全量重搜浪费 token。

### 1.2 Search Agent

**源码位置**：`app/agent/nodes/search.py`

**核心逻辑**：将 Planner 产出的 `search_queries` 列表分发为 `asyncio.gather` 并发执行。每条查询先调 Tavily API 获取原始结果，再经过 LLM 将搜索结果整理为结构化 Evidence（fact/source/relevance/confidence）。

**关键设计——Async 并发**：`asyncio.gather(*tasks, return_exceptions=True)` 是关键。一次 Planner 产出的 5-8 条搜索 5-8 次 Tavily API 调用，如果不并发就是串行 5-8 秒，并发后只等于最慢的那次（通常 1-2 秒）。`return_exceptions=True` 保证单次搜索失败不中断整体流程。

**LLM 后处理的价值**：Tavily 返回的 raw content 是网页摘要文本，格式不统一。LLM 后处理把噪声提炼为 fact/source/relevance/confidence 四个字段，为下游 Critic 的评估提供标准化输入。

### 1.3 Critic Agent

**源码位置**：`app/agent/nodes/critic.py`

**核心逻辑**：这是整个系统的"质量控制阀门"。Critic 从四个维度评估证据池——覆盖度（是否涵盖所有子问题）、可靠性（来源是否权威）、时效性（信息是否最新）、一致性（不同来源是否交叉验证）。输出包含 `report_ready` 布尔值，直接决定流程走向。

**强制终止机制**：即使 LLM 判断 `report_ready=false`，代码层有 `forced_ready = iteration_count >= max_iterations - 1` 的强制覆盖。这防止了模型陷入"永远不满意"的无限循环——模型负责判断质量，代码负责控制上限。

**参数级细节**：`fact_quality_score` 阈值 0.5 是经过保守设计的。即使证据质量不够高（0.4-0.5），系统也会在 Synthesizer 阶段在"风险"章节标注——宁可出一份"诚实标注不完整"的报告，也不在 Critic 阶段无限循环。

### 1.4 Synthesizer Agent

**源码位置**：`app/agent/nodes/synthesizer.py`

**核心逻辑**：即使 `report_ready=false` 也会被强制执行——这是关键设计。Synthesizer 用 `StrOutputParser` 而非 JSON 解析器，因为最终产出是 Markdown 文本而非结构化 JSON。报告结构严格遵循五段式（背景/发现/证据/风险/结论），这个结构是在 prompt 模板中硬编码的，不依赖模型自由发挥。

**证据不足时的行为**：当 `report_ready=false` 时，Synthesizer 仍会生成报告，但在"风险与不确定性"章节会明确指出哪些角度没有被充分验证。这是"partial report with honesty"策略——比返回"信息不足，无法生成报告"更有价值。

---

## 二、LangGraph State 流转过程

### 2.1 State 初始状态

```python
state = {
    "research_topic": "用户输入",
    "research_plan": [],
    "search_queries": [],
    "evidence_pool": [],
    "verified_facts": [],
    "rejected_facts": [],
    "missing_angles": [],
    "fact_quality_score": 0.0,
    "final_report": "",
    "iteration_count": 0,       # ← 流程控制核心
    "report_ready": False,      # ← 终止判断标志
    "max_iterations": 3,
}
```

### 2.2 流转序列

```
轮次1:
  START → planner → {research_plan: [...], search_queries: [...]}
        → search  → {evidence_pool: [e1...e8]}
        → critic  → {verified_facts: [...], report_ready: False, missing_angles: ["竞品定价策略"], iteration_count: 1}

轮次2 (loop-back):
  [critic.router → "planner"]
        → planner → {search_queries: [针对性补充查询]}
        → search  → {evidence_pool: [e1...e8, e9...e12]}  # 跨轮累积
        → critic  → {verified_facts: [...], report_ready: True, iteration_count: 2}

轮次2 (终止):
  [critic.router → "synthesizer"]
        → synthesizer → {final_report: "..."}
        → END
```

关键设计：`evidence_pool` 跨轮累积——第二轮 search 结果追加到第一轮后面，不覆盖。这样 Synthesizer 能看到全部 12 条证据，而不是只有最后一轮的 4 条。

---

## 三、Loop-Back 机制如何防止死循环

### 3.1 三重保险

```
保险1: max_iterations=3 硬上限
  代码层: forced_ready = iteration_count >= max_iterations - 1
  → 第3轮 Critic 必须输出 report_ready=true（强制覆盖 LLM 判断）

保险2: critic_router 双重条件
  if ready OR iteration >= max_iter → synthesizer
  → 任何一个条件满足都终止

保险3: search 节点空查询保护
  if not queries: return existing_pool
  → Planner 返回空查询时不调用搜索，不消耗 token
```

### 3.2 为什么是 3 次而不是更多？

调研任务的信息增益符合边际递减规律。第一轮搜索覆盖 70-80% 的信息，第二轮补充到 90-95%，第三轮以上的信息增益微乎其微但 token 消耗线性增长。3 次是在信息完整度和成本之间的平衡点。

---

## 四、为什么不用单 Agent 或 AutoGen

### vs 单 Agent（ReAct）

单 Agent 把规划、搜索、评估、撰写全部交给一个 LLM 在循环中完成。问题：LLM 在单一上下文中同时扮演四个角色会导致角色混淆——"搜索专家"和"质量审核者"的思维模式互相干扰。多 Agent 方案每个 Agent 有独立的 system prompt 和上下文，角色清晰。

### vs AutoGen

AutoGen 的 agent 之间可以自由对话，调用关系不受约束。这在调研场景中是问题：我们需要确保"先搜索→再审核→再决定是否补充搜索"这个固定流程。LangGraph 的图结构天然表达了这种约束性，而 AutoGen 需要额外的编排逻辑。

---

## 五、RAG vs 多 Agent 系统对比

| 维度 | RAG | Deep Research Copilot |
|------|-----|----------------------|
| 检索方式 | 单次向量检索 + 生成 | 多轮搜索 + 评估 + 补充 |
| 质量控制 | 无（检索到什么用什么） | Critic Agent 质量评估 + 过滤 |
| 信息完整性 | 取决于一次检索的召回率 | 多轮迭代直到满足质量阈值 |
| 输出结构 | LLM 自由生成 | 强制五段式结构化报告 |
| 适用场景 | 事实型问答（What/When） | 分析型调研（Why/How/What if） |

本质区别：RAG 是"找资料→回答"，Copilot 是"找资料→评估→不够再找→评估→够了才写"。

---

## 六、面试高频问答（25 题）

### Q1：这个系统的整体架构是怎样的？
A：四 Agent LangGraph 流水线。Planner 拆解调研问题为搜索计划，Search 并发执行搜索并整理为结构化证据，Critic 从覆盖度/可靠性/时效性/一致性四个维度评估证据质量，决定是否需要补充搜索。Synthesizer 强制生成五段式结构化报告。整个流程通过 State 中的 iteration_count 和 report_ready 标志控制 loop-back。

### Q2：为什么选 LangGraph 而不是直接用 LangChain Agent？
A：LangChain Agent（ReAct）是模型自主决策调用哪个工具，流程不确定。调研任务需要确保"先搜索→再审核→再决定"这个固定顺序——LangGraph 的图结构天然保证了这一点。另外 StateGraph 的 State 让数据流转可追踪，条件边让 loop-back 逻辑清晰可调试。

### Q3：loop-back 最多 3 次是怎么确定的？
A：调研信息增益遵循边际递减——第一轮搜到 70-80%，第二轮到 90-95%，第三轮以上增益极小但成本线性。3 次是信息完整度和 token 成本的平衡点。代码层面有硬上限：Critic 节点中 `forced_ready = iteration_count >= max_iterations - 1` 强制覆盖 LLM 判断。

### Q4：证据池为什么跨轮累积而不是每轮覆盖？
A：跨轮累积让 Synthesizer 能看到所有轮次收集的证据。如果覆盖，第三轮只看到最后一轮的结果，丢失了前两轮的发现。但也会累积噪声——所以 Critic 里有 rejected_facts 字段标记不可靠证据，Synthesizer 会参考这个标记。

### Q5：Critic 怎么判断证据质量？四个维度各有什么权重？
A：覆盖度（是否涵盖所有子问题）、可靠性（来源是否权威——官方 > 媒体 > 个人）、时效性（是否最新）、一致性（不同来源是否交叉验证，至少 3 个独立来源才算可靠）。不设固定权重——Critic 根据调研主题的特性（如技术趋势重时效、行业格局重覆盖度）动态调整。

### Q6：为什么 Search 用 asyncio.gather 并发而不是串行？
A：一次 Planner 产出 5-8 条搜索查询。串行执行 = 5-8 秒的总时间，并发 = 最慢的那次（1-2 秒）。return_exceptions=True 保证单次搜索失败不中断其他。这是系统延迟从 8 秒降到 2 秒的关键优化。

### Q7：为什么 Search 之后还要做 LLM 后处理？直接用 Tavily 返回不行吗？
A：Tavily 返回的 content 是网页摘要文本，格式不统一——有的是一段话，有的是标题列表，有的含 Markdown。LLM 后处理把噪声提炼为统一的 fact/source/relevance/confidence 结构，让 Critic 能标准化评估。标准化输入 = 更准确的评估。

### Q8：Planner 在首轮和后续轮次有什么区别？
A：首轮：全角度覆盖，生成 3-5 个子问题和对应的搜索查询。后续轮次：只针对 Critic 标记的 missing_angles 生成补充搜索。差异化避免全量重搜浪费 token——第二轮只需要搜"竞品定价"而不是重新搜"市场份额"。

### Q9：Synthesizer 为什么即使 report_ready=false 也要生成报告？
A："Partial report with honesty"策略——在"风险"章节诚实标注哪些角度未被充分验证，比返回"信息不足"更有价值。因为企业调研场景中，80% 完成度的报告加上诚实的信息缺口标注，比 0% 的"我们还在查"有用得多。

### Q10：为什么不用向量数据库做 RAG 而要自己建多 Agent？
A：RAG 的检索是一次性的——检索到什么用什么，没有"评估→不够→再搜"的机制。调研场景需要多轮迭代：第一轮搜完发现少了竞品数据，第二轮针对性补充。这是检索策略的不同，不是技术堆叠的问题。

### Q11：temperature 为什么要设 0？
A：调研需要事实准确性，不需要创意。temperature=0 意味着每次同样的输入产生同样的输出（确定性），这对引用来源、提取事实、评估可靠性至关重要。temperature>0 可能导致同一段搜索结果被评估为不同的可靠性等级——这在调研场景中不可接受。

### Q12：如果 Tavily API 挂了，系统怎么处理？
A：search_node 中 `asyncio.gather(return_exceptions=True)` 保证单次搜索异常不中断整体。如果所有搜索都失败（evidence_pool 仍为空），Critic 会发现 fact_quality_score=0.0 并标记 report_ready=false。但 iteration_count 仍会递增——硬上限机制保证系统最终进入 Synthesizer，此时报告会明确声明"因搜索服务不可用，本报告无证据支撑"。

### Q13：为什么 State 里要有 evidence_pool 和 verified_facts 两个字段？
A：evidence_pool 是原始+LLM 整理后的证据（可能有噪声），verified_facts 是经过 Critic 审核通过的证据（高质量）。两者的分离让 Synthesizer 能看到"有什么证据可用"和"哪些证据被拒绝了"——被拒绝的证据在报告的"风险"章节也有参考价值。

### Q14：max_iterations 为什么是 State 字段而不是常量？
A：允许调用方（API / test_run）按任务复杂度灵活调整。简单事实型查询（"XX公司去年营收多少"）1 轮就够了，复杂分析型（"行业竞争格局"）需要 3 轮。放在 State 中让系统对不同的任务类型有自适应性。

### Q15：怎么保证 Prompt 不被用户注入攻击？
A：用户输入（research_topic）只在一个位置被注入——PromptTemplate 的 input_variables 中，和其他结构化变量一起传入。这避免了直接字符串拼接。另外 Critic 和 Synthesizer 的 prompt 完全不包含用户原始输入——它们只消费上游 Agent 的标准化的 State 数据。

### Q16：如果 LLM 返回的 JSON 格式不对（解析失败），怎么办？
A：LangChain 的 JsonOutputParser 内部有 retry 机制——解析失败时会抛 OutputParserException，LCEL 管道会自动重试（把解析错误反馈给 LLM，让它修正格式）。如果多次重试仍失败，search_node 和 critic_node 中的 except 捕获异常后返回空值（[]/0.0/false），不中断流程。

### Q17：这个系统和 Perplexity 有什么不同？
A：Perplexity 是"搜索→直接给答案"（单轮 RAG），Copilot 是"搜索→评估→不够→再搜→评估→够了→写报告"（多轮 Agent）。Perplexity 适合事实型问答（"iPhone 15 什么时候发布"），Copilot 适合分析型调研（"智能手机市场竞争格局及未来趋势"）。

### Q18：你怎么评估这个系统的输出质量？
A：三个维度。一是证据引用率——报告中多少百分比的关键声明有来源标注。二是信息覆盖度——调研计划的子问题有多少在报告中得到了回答。三是人工评分——由领域专家对报告的可信度、全面性、可操作性打分。这类似于 RAGAS 的 Faithfulness + Answer Relevance 但针对调研报告场景定制。

### Q19：如果要扩展到 100 并发用户，瓶颈在哪？
A：一是 LLM API 速率限制——4 个 Agent 节点每轮都调 LLM，1 个任务就是 4 次调用（首轮）+ 可能的 3 次（loop-back），100 用户瞬时并发 = 400-700 次 API 调用。需要 API 层的速率控制和队列。二是 Tavily API 速率限制（免费版每月 1000 次）。三是 State 大小——evidence_pool 跨轮累积可能导致 State 膨胀，需要在 Critic 阶段做证据去重和裁剪。

### Q20：如果让你重新设计，你会做什么不同的决策？
A：一是在 Search 和 Critic 之间加一个 Dedup 节点——当前跨轮 evidence_pool 可能有重复证据。二是给 Critic 增加"工具调用"能力——当前 Critic 只做文本评估，如果能调用搜索工具对可疑来源做二次验证（fact-check），质量会更高。三是将 Prompt 模板外置为独立的 .prompt 文件而非 Python 字符串，方便非开发人员调优。

### Q21：Planner 怎么知道该拆成几个子问题？
A：Prompt 模板里约束了"3-5 个子问题"。太少（1-2 个）= 角度不全，太多（6+ 个）= 搜索成本高且 Critic 难以全面评估。3-5 个是在广度和成本之间的平衡。LLM 根据调研主题的复杂度自主决定具体数量。

### Q22：为什么 Search Agent 使用 Tavily 而不是直接调 Google API 或自建爬虫？
A：Tavily 是专为 AI Agent 设计的搜索 API——返回结果已经做过网页抓取和内容提取，格式统一，支持 topic 分类。直接调 Google API 需要处理 HTML 清洗、反爬、结果解析等工程问题，偏离了项目核心（多 Agent 协作调研）。

### Q23：这个系统能处理实时数据吗（比如股票价格）？
A：取决于 Tavily API 返回的结果时效性。Tavily 索引的网页有 1-24 小时的延迟，不是实时数据。如果调研需要实时金融数据，应该替换 Search Agent 的底层工具——比如换成 Yahoo Finance API 或 Bloomberg API——其他 Agent（Planner/Critic/Synthesizer）的架构不需要改动。这就是 Search Agent 作为"可替换模块"的意义。

### Q24：Critic 的 fact_quality_score 阈值 0.5 是拍脑袋定的还是有依据的？
A：来自设计原则而非统计数据。0.5 表示"一半以上的证据通过了审查"——这是一个保守的阈值。如果设太高（0.8），大部分调研会因为证据不够而无限循环。设太低（0.3），低质量证据会直接进入报告。0.5 是"先保证产出，在报告中坦诚标注不足"策略的体现。

### Q25：你从这个项目中学到了什么可以在后续项目中复用的？
A：三条核心经验。一是 State 驱动流程图控制——用 iteration_count 和 report_ready 做条件分支比在 prompt 里写"最多 3 次"可靠得多。二是 Agent 的输出标准化——Search 给 Critic 的输入必须经过 LLM 整理为统一格式，标准化是质量评估的前提。三是"部分诚实"比"完美主义"更有工程价值——强制生成+标注不足 > 循环到永远。
